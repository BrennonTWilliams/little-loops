---
type: project
tags:
  - project/little-loops
  - project/hermes-agent
  - genai/agents
  - status/planning
created: 2026-05-18
status: draft
---

# PRD: little-loops × Hermes Agent Integration

*A first-class integration between little-loops (FSM-driven automation engine) and Hermes Agent (multi-platform AI agent framework) — making loops a primitive Hermes can trigger, schedule, fan-out, monitor, and report on from anywhere.*

---

## Problem

little-loops runs **FSM-driven automation loops** — long-horizon, eval-gated workflows like `harness-optimize`, `docs-sync`, `deep-research`, `autodev`, and `rn-plan`. Each loop is a state machine with deterministic action+evaluate→route semantics. There are ~50 built-in loops spanning issue management, code quality, harness optimization, RL training, prompt optimization, planning, and research across 11 categories (`apo`, `code-quality`, `data`, `evaluation`, `harness`, `issue-management`, `meta`, `optimization`, `planning`, `research`, `rl`).

But loops only run where little-loops runs: inside Claude Code, in a terminal, in one repo at a time. There's no way to kick off `harness-optimize` from Telegram, schedule a nightly `docs-sync` across five repos via cron, or ask "what loop should I run on this repo next?" from a phone.

Meanwhile, Hermes Agent has broad surface area — Telegram, Discord, Slack, cron, webhooks, subagents — but no deep coding workflow intelligence. It can run shell commands, but it doesn't understand FSM execution, harness-driven verification, or persistent loop state.

**The gap:** Loops are the unit of work in little-loops, but they have no cross-surface trigger, scheduler, or monitor. "Run harness-optimize on blender-agents tonight, ping me in the morning" is a one-sentence request that has no executable path today.

## Vision

Make little-loops a first-class Hermes toolset so that **FSM loops become a primitive Hermes can trigger, schedule, fan out, monitor, and report on across all its surfaces** — messaging platforms, scheduled jobs, subagents, and webhooks. Any Hermes user with `pip install little-loops` gets autonomous software development capabilities across all those surfaces.

The integration must handle the fundamental mismatch: little-loops is project-scoped (one repo), while Hermes is session-scoped (one conversation that may span many repos).

## Users

**Primary:** Existing Hermes users who also write code. They have Hermes running on Telegram or Discord. They have repos. They want loop execution (codebase scans, harness optimization, doc syncs, dead-code cleanup, issue automation) without being at a terminal.

**Secondary:** little-loops users who discover Hermes through this integration. The pitch: "little-loops, but from anywhere."

## Goals

1. A Hermes user can trigger, monitor, resume, and inspect FSM loops across multiple registered repos from any Hermes surface.
2. Cron jobs can run nightly loops (`docs-sync`, `harness-optimize`, `dead-code-cleanup`) across repos and deliver morning briefings.
3. The model autonomously composes loop execution with other Hermes tools (messaging for status, delegation for long-running loops, cron for scheduling).
4. Subagents can be scoped to a single repo with little-loops tool access only — including long-running loop execution.
5. Zero changes to the `ll-*` CLI interface — Hermes wraps via subprocess; slash-command-only features are bridged through `ll-action invoke`.

## Non-Goals

- little-loops does not become part of the Hermes codebase
- No new `ll-*` commands created specifically for Hermes
- No shared state format between Hermes sessions and little-loops loops
- **Hermes does not become a loop authoring environment.** Loop YAMLs are created via `/ll:create-loop` inside Claude Code; Hermes triggers and observes them.
- Level 3 shared abstractions (unified issue model, loop engine as Hermes primitive) are out of scope for v1
- **Hermes handlers wrap `ll-*` binaries only; never the underlying host CLI** (`claude`, `codex`, `opencode`). If host CLI invocation is ever needed on the little-loops side, it routes through `resolve_host()` in `scripts/little_loops/host_runner.py` — that is not Hermes's concern.

---

## Architecture

### Repo Registration (Option B)

A config-level mapping between human-friendly names and filesystem paths:

```yaml
# ~/.hermes/config.yaml  (skills.config section — see note below)
little-loops:
  repos:
    my-app: /home/user/projects/my-app
    work-api: /home/user/work/api-service
    blender-agents: /home/user/dev/blender-agents
```

Users set this up once. Auto-discovery is possible by scanning for `.ll/` directories, but explicit registration is the primary path.

**CLI:**
```bash
hermes config set little-loops.repos.my-app /path/to/my-app
```

**Config namespace note:** `hermes config set little-loops.repos.my-app /path` writes to `skills.config.little-loops.repos.my-app` inside `~/.hermes/config.yaml`. The `load_registered_repos()` function must read from `config["skills"]["config"]["little-loops"]["repos"]`, not from a top-level `little-loops` key.

### Session-Scoped Project Binding (Option C)

A conversation-level "current project" that persists across turns. The model can switch projects mid-conversation, but defaults to the bound one.

**Mechanism:**
- Natural language: "I'm working on my-app today" → model detects intent, binds session
- Slash command: `/project my-app` (explicit)
- Implicit: if only one repo registered, auto-bind
- Override: any tool call with explicit `repo` parameter overrides the session binding

**Storage:** Hermes's public API does **not** expose `session.metadata` — session data lives in SQLite at `~/.hermes/state.db` and is not accessible to tool handlers. Handlers receive context only via `task_id` in `**kwargs`. Session binding is stored in a **module-level in-memory dict** keyed by `task_id`:

```python
# tools/little_loops_tool.py — module level
_session_bindings: dict[str, str] = {}  # task_id → repo name or path
```

The `/project <name>` command writes `_session_bindings[task_id] = name`; every tool handler reads from it via `task_id`. This is ephemeral per process and gives the correct per-session semantics without touching SQLite.

**Phase 1 note:** Session binding and the `/project` command are Phase 2 deliverables. In Phase 1 (skill pack), users must pass `repo=` explicitly on every tool call, or have exactly one repo registered to use the single-repo fallback. The Phase 1 skill documentation must state this constraint explicitly.

### Repo Resolution Logic

Every little-loops tool handler resolves the working directory through a priority chain:

```
1. Explicit `repo` parameter on the tool call (name or absolute path)
2. Session binding (_session_bindings[task_id])
3. Single-repo fallback (exactly one repo registered → use it automatically)
4. Error: structured payload {"error": "ambiguous_repo",
                              "registered": ["my-app", "work-api"],
                              "hint": "pass repo= or bind with /project <name>"}
```

After resolution, the path is validated against disk (R10). Unit tests must cover each priority level independently and the path-not-found case (see Phase 2 acceptance tests).

### Tool Registration

Each high-value little-loops capability becomes a registered Hermes tool. Two routing paths exist:

- **Direct CLI:** Real `ll-*` executables (`ll-loop`, `ll-parallel`, `ll-auto`) are invoked via subprocess. This is the primary integration surface.
- **`ll-action invoke` bridge:** Slash commands (`/ll:scan-codebase`, `/ll:manage-issue`, `/ll:commit`, ...) have no direct CLI counterpart, but `ll-action invoke <skill> --output json` exposes any `/ll:*` skill as a one-shot call with structured output. Hermes shells out uniformly. Always pass `--output json` for batched/single-shot calls; `--output stream-json` (the default) emits NDJSON events unsuitable for a single return value.

**Tools (organized by tier):**

| Tier | Tool Name | CLI Command / Bridge | What It Does |
|------|-----------|----------------------|--------------|
| **Loops (primary surface)** | `ll_loop_run` | `ll-loop run <name>` | Execute an FSM loop (supports `--background`, `--worktree`, `--max-iterations`, `--dry-run`, `--context KEY=VALUE`, `--queue`, `--quiet`, `--builtin`). **`--background` and `--worktree` are mutually exclusive.** |
|  | `ll_loop_list` | `ll-loop list [--builtin] [--running] [--status <status>] [--category <cat>] [--label <label>]` | Discover available loops: project-local `.loops/<name>.yaml` AND built-ins shipped in the package; `--running` filters to active instances; `--status <status>` narrows to a specific lifecycle state (e.g. `interrupted`, `awaiting_continuation`, `running`); `--category` filters to a single category; `--label` (repeatable) filters by label tag. **Note:** the `--json` output format includes `{name, path, category, labels}` for project loops and adds `built_in: true` for built-ins (the key is absent — not `false` — for project-local loops; treat missing `built_in` as `false`); no `description` field; use `ll-action list --output json` for human-readable loop descriptions. |
|  | `ll_loop_status` | `ll-loop status <loop_name>` | Show state, iteration, and verdict for all instances of a named loop (loop_name required). Returns an array — one entry per instance with `instance_id`, `current_state`, `iteration`, `pid`, and full LoopState fields. |
|  | `ll_loop_stop` | `ll-loop stop <loop_name>` | Halt all running instances of a named loop (stops by name, not instance ID) |
|  | `ll_loop_resume` | `ll-loop resume <loop_name>` | Resume an interrupted loop from its persisted state |
|  | `ll_loop_history` | `ll-loop history <loop_name> [run_id]` | Past runs and verdicts for a named loop (loop_name required); optional run_id for event-level drill-down into a specific run |
|  | `ll_loop_show` | `ll-loop show <name>` | Inspect a loop's FSM (states, transitions, schema) |
|  | `ll_loop_simulate` | `ll-loop simulate <name> [--scenario <scenario>] [--max-iterations <n>]` | Interactive dry-run; `scenario` bypasses interactive prompts — choices: `all-pass`, `all-fail`, `all-error`, `first-fail`, `alternating`. Required for non-interactive Hermes contexts (cron, subagent). `--max-iterations` overrides the loop's default, capped at 20 by the simulator. |
|  | `ll_loop_validate` | `ll-loop validate <name>` | Validate loop YAML |
|  | `ll_loop_test` | `ll-loop test <name> [--exit-code N]` | Single-iteration dry-run with injected exit code; lets Hermes users verify a loop is wired correctly before a real run. |
|  | `ll_loop_next` | `ll-loop next-loop` | Suggest a loop based on repo history |
| **Orchestration** | `ll_parallel` | `ll-parallel` | Fan out N workers in isolated worktrees (often used to parallelize loops over issues) |
|  | `ll_auto` | `ll-auto` | Sequential issue pipeline with auto-continuation |
| **Issue/sprint scaffolding (loop inputs)** | `ll_scan_codebase` | `ll-action invoke scan-codebase --output json` | Scan for issues that loops can consume |
|  | `ll_manage_issue` | `ll-action invoke manage-issue --output json` | Plan→implement→verify cycle |
|  | `ll_prioritize_issues` | `ll-action invoke prioritize-issues --output json` | Auto-assign P0–P5 priorities |
|  | `ll_verify_issues` | `ll-action invoke verify-issues --output json` | Test issue claims against code |
|  | `ll_sprint_create` | `ll-action invoke create-sprint --output json` | Create a sprint from curated issues |
|  | `ll_commit` | `ll-action invoke commit --output json` | Structured commit with issue linkage |
|  | `ll_open_pr` | `ll-action invoke open-pr --output json` | Open a PR with generated description |
|  | `ll_handoff` | `ll-action invoke handoff --output json` | Generate session continuation prompt |
|  | `ll_run_tests` | `ll-action invoke run-tests --output json` | Run project test suite |

**Tool registration pattern:**

Tools self-register via `registry.register()` at module import time and are discovered by Hermes's `discover_builtin_tools()` (which AST-scans `tools/*.py`). Do **not** edit `TOOLSETS` dict directly — that is a legacy pattern. Use `tool_error(message)` and `tool_result(...)` helpers for return values; handlers must return strings, never raw dicts.

```python
# tools/little_loops_tool.py
from tools.registry import registry, tool_error, tool_result

# Register each tool individually; all share the same check_fn and toolset label.
registry.register(
    name="ll_loop_run",
    toolset="little-loops",
    schema=LL_LOOP_RUN_SCHEMA,
    handler=lambda args, **kw: run_ll_loop("run", args, **kw),
    check_fn=check_little_loops,   # zero-arg callable; see below
    is_async=False,
)
# ... one registry.register() call per tool (22 total)
```

**Availability gate (`check_fn`):** `check_little_loops` is a **zero-argument callable** returning `bool`. Hermes TTL-caches the result for **30 seconds** (hardcoded; `_CHECK_FN_TTL_SECONDS = 30.0`). Cache is invalidated only by `hermes tools enable/disable`. Implication: if `ll-loop` or `ll-action` is installed mid-session, the toolset won't become available until the TTL expires. **Setup instructions must advise: restart Hermes after installing or updating little-loops.**

Three checks run sequentially; all must pass and the skill catalog must be non-empty:

1. `shutil.which("ll-loop")` — confirms `ll-loop` is on `PATH`; returns `None` if absent → return `False`.
2. Run `ll-action capabilities --output json` — confirms `ll-action` is on `PATH` and returns `{host, binary, version, capabilities, hooks}` (capability flags, not skill names). If the command fails → return `False`.
3. Run `ll-action list --output json` — returns `[{name, description}, ...]` (58 entries); this populates the live skill catalog. Note: `ll-action list` accepts only `--output json` (no `stream-json` mode exists for this subcommand). Assert `len(skills) > 0`, not just successful exit code — `ll-action list` exits 0 but returns `[]` when the plugin root is not found. Populate `_skill_catalog` as a side effect. If the command fails or returns `[]` → return `False`.

```python
# Module-level catalog populated by check_fn as a side effect
_skill_catalog: list[dict] = []

def check_little_loops() -> bool:
    """Zero-arg availability gate; result is TTL-cached for 30 seconds."""
    global _skill_catalog
    if not shutil.which("ll-loop"):
        return False
    try:
        r = subprocess.run(
            ["ll-action", "capabilities", "--output", "json"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    try:
        r = subprocess.run(
            ["ll-action", "list", "--output", "json"],
            capture_output=True, text=True, timeout=10
        )
        skills = json.loads(r.stdout)
        if not skills:  # exits 0 but returns [] when plugin root not found
            logger.warning("ll-action list returned empty skill catalog — is the plugin registered?")
            return False
        _skill_catalog = skills
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False
    return True
```

Tests required: gate returns `False` when `ll-loop` binary is absent (mock `PATH`); gate returns `False` when `ll-action` binary is absent (separate test); gate returns `False` when `ll-action list --output json` returns `[]` (mock subprocess output); gate populates `_skill_catalog` from `ll-action list --output json` with entries having `{name, description}` keys.

### Handler Pattern

Two handler shapes — direct CLI and bridged via `ll-action invoke`. Both produce a structured JSON envelope. Error paths are explicit. **All handlers accept `**kwargs`** — Hermes's `dispatch()` calls `handler(args, **kwargs)` where `kwargs` includes at minimum `task_id`. Handlers that omit `**kwargs` raise `TypeError` at dispatch time.

```python
import os
import signal
import subprocess
import json
import shutil

# Module-level in-memory session binding store.
# Key: task_id (str, session-scoped), Value: repo name or absolute path.
# Hermes does not expose session.metadata — this dict IS the session state.
_session_bindings: dict[str, str] = {}
_skill_catalog: list[dict] = []


def load_registered_repos() -> dict[str, str]:
    """Read from skills.config.little-loops.repos in ~/.hermes/config.yaml."""
    cfg = load_hermes_config()
    return cfg.get("skills", {}).get("config", {}).get("little-loops", {}).get("repos", {})


def resolve_repo(args: dict, task_id: str | None) -> str:
    """Resolve working directory via 4-level priority chain."""
    registered = load_registered_repos()
    explicit = args.get("repo")

    if explicit:
        if explicit in registered:
            path = registered[explicit]
        elif explicit.startswith("/"):
            path = explicit
        else:
            return json.dumps({
                "error": "unknown_repo",
                "repo": explicit,
                "registered": list(registered.keys()),
                "hint": "pass a registered name or an absolute path"
            })
    elif task_id and task_id in _session_bindings:
        name = _session_bindings[task_id]
        if name not in registered:
            return json.dumps({
                "error": "bound_repo_not_registered",
                "name": name,
                "hint": f"Re-bind with /project <name>; registered: {list(registered.keys())}"
            })
        path = registered[name]
    elif len(registered) == 1:
        path = next(iter(registered.values()))
    else:
        return json.dumps({
            "error": "ambiguous_repo",
            "registered": list(registered.keys()),
            "hint": "pass repo= or bind with /project <name>"
        })

    # R10: validate path exists on disk before shelling out (avoids cryptic errors)
    if not os.path.isdir(path):
        return json.dumps({
            "error": "repo_not_found",
            "path": path,
            "hint": "Check config: hermes config list little-loops.repos"
        })
    return path


def run_ll_loop(subcommand: str, args: dict, **kwargs) -> str:
    """Direct: ll-loop <subcommand> [args] — primary integration surface."""
    task_id = kwargs.get("task_id")
    cwd = resolve_repo(args, task_id)
    if isinstance(cwd, str) and cwd.startswith('{"error"'):
        return cwd  # propagate ambiguous-repo or repo-not-found error

    cmd_parts = ["ll-loop", subcommand]
    skip_keys = {"repo", "path"}
    # Translate snake_case tool params to kebab-case CLI flags
    flag_map = {"max_iterations": "max-iterations", "dry_run": "dry-run"}
    for key, value in args.items():
        if key in skip_keys:
            continue
        flag = flag_map.get(key, key.replace("_", "-"))
        if isinstance(value, bool) and value:
            cmd_parts.append(f"--{flag}")
        elif isinstance(value, bool):
            pass  # false booleans: omit flag
        elif value is not None:
            cmd_parts.extend([f"--{flag}", str(value)])

    is_background = args.get("background", False)
    # background=True: ll-loop forks a daemon and exits quickly — no Python timeout.
    # foreground: wait up to command_timeout seconds (configurable, default 300).
    timeout = None if is_background else 300
    return _run_subprocess(cmd_parts, cwd=cwd, timeout=timeout)


def run_ll_action(skill: str, args: dict, **kwargs) -> str:
    """Bridged: ll-action invoke <skill> --output json — wraps /ll:* slash commands.

    Always passes --output json (never stream-json); passes --timeout to give the CLI
    its own deadline, with a 30s Python-side buffer. R9: if the CLI exits non-zero and
    emits non-JSON to stdout (e.g. a crash traceback), the envelope's success=False and
    output contains the raw text — callers must not assume output is parseable JSON.

    --args uses nargs="+" (not action="append"): all key=value pairs are passed in a
    single --args invocation. Passing --args multiple times overwrites the previous
    value — only the last pair would reach the skill.
    """
    task_id = kwargs.get("task_id")
    timeout_seconds: int = kwargs.get("timeout_seconds", 600)
    cwd = resolve_repo(args, task_id)
    if isinstance(cwd, str) and cwd.startswith('{"error"'):
        return cwd

    cmd_parts = ["ll-action", "invoke", skill, "--output", "json",
                 "--timeout", str(timeout_seconds)]
    skip_keys = {"repo", "path"}

    # Collect all skill args and emit them in a single --args invocation.
    # ll-action invoke uses nargs="+" (not action="append"), so each additional
    # --args flag overwrites the previous one — only the last pair would reach
    # the skill if we called --args once per key.
    skill_args = [f"{k}={v}" for k, v in args.items()
                  if k not in skip_keys and v is not None]
    if skill_args:
        cmd_parts.extend(["--args"] + skill_args)

    return _run_subprocess(cmd_parts, cwd=cwd, timeout=timeout_seconds + 30)


def _run_subprocess(cmd_parts: list[str], cwd: str, timeout: int | None) -> str:
    """Run a subprocess and return a structured JSON envelope.

    Uses Popen + communicate() — NOT subprocess.run() — so that on TimeoutExpired
    we can call proc.kill() followed by proc.communicate() to flush pipe buffers
    and set returncode. Using subprocess.run() with exc.process.kill() leaves pipes
    unread and returncode unset, causing resource leaks.
    """
    try:
        proc = subprocess.Popen(
            cmd_parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd
        )
        try:
            outs, errs = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            outs, errs = proc.communicate()  # REQUIRED: flushes pipes, sets returncode
            return json.dumps({
                "success": False,
                "error": "timeout",
                "partial_output": (outs or "")[-4000:],
                "hint": "Loop may still be running in background. Poll with ll_loop_status.",
                "repo": cwd
            })

        result_dict = {
            "success": proc.returncode == 0,
            "output": outs[-8000:],
            "errors": errs[-2000:] if errs else None,
            "exit_code": proc.returncode,
            "repo": cwd
        }

        # Phase 3 (R8): surface stale PID files as a structured warning field
        if outs and "not running - stale PID file" in outs:
            result_dict["warning"] = "stale_pid"
            result_dict["hint"] = "Run ll_loop_stop to clear the stale lock"

        return json.dumps(result_dict)

    except FileNotFoundError:
        binary = cmd_parts[0]
        return json.dumps({
            "success": False,
            "error": "binary_not_found",
            "binary": binary,
            "hint": f"Install little-loops: pip install -e <path-to-little-loops>"
        })
```

### Tool Schema Examples

```json
{
    "name": "ll_loop_run",
    "description": "Execute an FSM loop in a registered repo. Loops are state machines with action+evaluate→route semantics. Use background=true for long-running loops (returns an instance ID you can poll with ll_loop_status). Use worktree=true for foreground runs that keep the working tree clean — recommended for cron, webhook, and foreground subagent contexts. IMPORTANT: background and worktree are mutually exclusive; the CLI raises an error if both are set. Use queue=true to wait for a conflicting loop (same scope) rather than failing. Use builtin=true to force loading the built-in version of a loop even if the repo has a local override.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Loop name (e.g. docs-sync, harness-optimize, dead-code-cleanup, autodev). Use ll_loop_list to discover available loops."
            },
            "repo": {
                "type": "string",
                "description": "Repo name (from config) or absolute path. Omit to use session-bound project."
            },
            "background": {
                "type": "boolean",
                "description": "Run as a background daemon. Returns instance ID immediately for later polling via ll_loop_status. Recommended for loops expected to take >2 minutes. Mutually exclusive with worktree — do not set both."
            },
            "worktree": {
                "type": "boolean",
                "description": "Run in an isolated git worktree (auto-cleanup on exit) under {project_root}/.worktrees/. Keeps the working tree clean during foreground runs. Mutually exclusive with background — do not set both. Default true for cron and foreground subagent contexts."
            },
            "max_iterations": {
                "type": "integer",
                "description": "Override the loop's default max_iterations. Translated to --max-iterations on the CLI."
            },
            "dry_run": {
                "type": "boolean",
                "description": "Show the plan without executing any actions."
            },
            "queue": {
                "type": "boolean",
                "description": "If another loop holds a conflicting scope lock, wait for it to finish rather than failing immediately. While waiting, a queue entry is written to .loops/.queue/<uuid>.json and cleaned up automatically on start or on crash. Useful when triggering multiple loops on the same repo sequentially."
            },
            "quiet": {
                "type": "boolean",
                "description": "Suppress progress output. Recommended for cron and subagent contexts where verbose output is noise."
            },
            "builtin": {
                "type": "boolean",
                "description": "Bypass project .loops/ lookup and force loading the built-in version of the loop from the installed package. Use when you want the stock behavior even if the repo has a local override."
            }
        },
        "required": ["name"]
    }
}
```

```json
{
    "name": "ll_loop_list",
    "description": "Discover loops available in a registered repo: project-local .loops/<name>.yaml files plus built-ins shipped in the package. The --json output includes {name, path, category, labels} for each loop; built-ins add built_in: true (the key is absent, not false, for project-local loops — treat missing built_in as false). Use ll-action list --output json to get human-readable descriptions. To see only running loops, pass running=true. To filter by category (e.g. harness, apo, code-quality), pass category. To filter by label, pass one or more labels.",
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repo name or absolute path. Omit to use session-bound project."
            },
            "builtin": {
                "type": "boolean",
                "description": "Include (or limit to) built-in loops shipped in the package. Maps to --builtin."
            },
            "running": {
                "type": "boolean",
                "description": "Filter to currently active instances only. Maps to --running."
            },
            "status": {
                "type": "string",
                "description": "Filter to loops in a specific lifecycle state (e.g. interrupted, awaiting_continuation, running). Maps to --status."
            },
            "category": {
                "type": "string",
                "description": "Filter to loops in a specific category (e.g. apo, harness, code-quality, issue-management, evaluation, rl). Maps to --category."
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter to loops that carry all listed labels. Each entry maps to a separate --label flag on the CLI."
            }
        },
        "required": []
    }
}
```

```json
{
    "name": "ll_loop_status",
    "description": "Show the current state, iteration count, and last verdict for all running instances of a named loop. Returns an array — one entry per instance with instance_id, current_state, iteration, pid, pid_source, log_file, and full LoopState fields. To list all running loops across all names, use ll_loop_list with running=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "loop_name": {
                "type": "string",
                "description": "The loop name to query (e.g. harness-optimize). Required — bare status with no name is not supported by the CLI."
            },
            "repo": {"type": "string", "description": "Repo name or path. Omit to use session-bound project."}
        },
        "required": ["loop_name"]
    }
}
```

```json
{
    "name": "ll_loop_stop",
    "description": "Halt all running instances of a named loop. Stops by loop name (not instance ID) — if multiple instances are running, all are stopped.",
    "parameters": {
        "type": "object",
        "properties": {
            "loop_name": {
                "type": "string",
                "description": "The loop name to stop (e.g. harness-optimize)."
            },
            "repo": {"type": "string", "description": "Repo name or path. Omit to use session-bound project."}
        },
        "required": ["loop_name"]
    }
}
```

```json
{
    "name": "ll_loop_history",
    "description": "Show past runs and verdicts for a named loop. Without run_id, returns a list of archived runs with status and duration. With run_id, returns the full event log for that run — useful for diagnosing why a loop converged or failed.",
    "parameters": {
        "type": "object",
        "properties": {
            "loop_name": {
                "type": "string",
                "description": "Loop name to query history for (e.g. harness-optimize, docs-sync)."
            },
            "run_id": {
                "type": "string",
                "description": "Optional run ID for event-level drill-down into a specific past run. Omit to list all archived runs."
            },
            "repo": {"type": "string", "description": "Repo name or path. Omit to use session-bound project."}
        },
        "required": ["loop_name"]
    }
}
```

```json
{
    "name": "ll_loop_simulate",
    "description": "Simulate a loop without executing real actions — great for messaging surfaces. If scenario is provided, interactive prompts are bypassed automatically, making this safe for cron and subagent contexts.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Loop name to simulate."
            },
            "scenario": {
                "type": "string",
                "enum": ["all-pass", "all-fail", "all-error", "first-fail", "alternating"],
                "description": "Inject a synthetic evaluation outcome to bypass interactive prompts. Required for non-interactive contexts (cron, subagent). Omit for interactive sessions where the model responds to each prompt."
            },
            "max_iterations": {
                "type": "integer",
                "description": "Override the loop's default max_iterations for the simulation. Capped at 20 by the simulator. Translated to --max-iterations/-n on the CLI."
            },
            "repo": {"type": "string", "description": "Repo name or path. Omit to use session-bound project."}
        },
        "required": ["name"]
    }
}
```

---

## Why Loops

FSM loops are the primitive that makes this integration worth building. They're not "one tool among many" — they're the load-bearing abstraction:

- **Action + Evaluate + Route.** Each state runs an action (shell command, slash command, or LLM prompt), evaluates the result with a deterministic or LLM evaluator, and routes to the next state. This cleanly separates "what happened?" from "where next?", making loops debuggable and resumable. Nine evaluator types exist: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `llm_structured`, `mcp_result`, `harbor_scorer`. Most loops are fully deterministic (no LLM cost per evaluation); `llm_structured` applies only when semantic judgment is needed and is the most expensive evaluator type. The deterministic majority means per-iteration cost is near-zero for most loops.
- **Persisted state.** `.loops/.running/<instance_id>.state.json` captures current state, iteration, captured variables, and last result. Foreground runs produce four files per instance: `.state.json`, `.events.jsonl` (append-only), `.lock` (scope lock + holder PID), `.pid`. Background daemon runs add a fifth: `.log` (stderr/stdout for the daemon process — absent on foreground runs). Instance IDs use `<loop-name>-<compact-timestamp>` format with a `T` separator, e.g. `harness-optimize-20260518T214700`. Loops can be interrupted, resumed, monitored, and halted — essential for cross-surface triggering.
- **Queued instances.** When `--queue` is passed and another loop holds a conflicting scope lock, the new run writes a queue entry to `.loops/.queue/<uuid>.json` and waits. On start (or on the holder's crash), stale queue entries from dead PIDs are cleaned up automatically — Hermes needs no recovery logic for this failure mode.
- **Sub-loop composition.** `loop: <name>` + `context_passthrough: true` (e.g. `sprint-build-and-validate.yaml:78-79`) invokes another loop as a subprocess step. `autodev` composes multiple smaller loops. Hermes inherits this composability for free.
- **Fragment libraries.** Loops import shared state-step bundles from five library files in `lib/`: `common.yaml`, `cli.yaml`, `benchmark.yaml`, `apo-base.yaml`, `score-plan-quality.yaml` — a second axis of composition beyond sub-loops. Users who customize a built-in loop install it first (`ll-loop install <name>`) and edit the local copy.
- **Scope-based locking.** Loops declare `scope: ["docs/", "*.md"]`; overlapping scopes serialize automatically via `.loops/.running/<instance>.lock`. Empty `scope:` normalizes to `["."]` (whole project). `--queue` makes a new run wait for the holder rather than erroring. Safe to trigger multiple loops on the same repo from different surfaces — *as long as scopes differ or `--queue` is used*.
- **`on_handoff: spawn` for long-running loops.** Exactly 34 of the 50 built-in loops (including `harness-optimize`, `autodev`, `docs-sync`, `general-task`, and 30 more) declare `on_handoff: spawn` — the loop re-spawns itself before the model's context window is exhausted. Hermes doesn't need to invent session-resume logic for these loops; they handle their own continuity. Hermes can safely treat most built-in loops as "long-delegation safe." Notable exception: `rn-plan` has no `on_handoff:` declaration (defaults to `pause`, not `spawn`, per `fsm/schema.py:808`; no explicit field in `rn-plan.yaml`) — when delegating `rn-plan` to a subagent, the subagent itself is responsible for continuity.
- **50+ built-in loops across 11 categories** — issue-management, code-quality, harness, evaluation, RL, APO (prompt optimization), planning, data, research, meta, optimization. Each one already works inside Claude Code; Hermes simply makes them reachable from any surface.

This is why Hermes integration is leverage, not duplication: every loop little-loops ever ships becomes a Hermes capability with no further work.

---

## User Flows

### Flow 1: Trigger a Loop from Telegram

```
User:  "I'm working on my-app today"
Hermes: Bound to my-app (/home/user/projects/my-app).

User:  "what loops are available?"
       → ll_loop_list()
       ← "12 project loops + 50 built-ins. Project: docs-sync, dead-code-cleanup,
          harness-optimize, autodev, fix-quality-and-tests, deep-research, ..."

User:  "run docs-sync"
       → ll_loop_run(name="docs-sync")
       ← "docs-sync complete. 3 stale references fixed across 5 files.
          Commit abc1234."

User:  "what should I run next?"
       → ll_loop_next()
       ← "Top suggestion: dead-code-cleanup (no run in 14 days, 28 unused
          symbols detected by last scan). Also: fix-quality-and-tests
          (3 failing tests since last green)."
```

### Flow 2: Background a Long-Running Loop, Poll from Anywhere

```
User:  "Run harness-optimize on blender-agents in the background"
       → ll_loop_run(name="harness-optimize", repo="blender-agents",
                     background=true)
       ← "Launched harness-optimize as instance
          harness-optimize-20260518T214700.
          (Running in main working tree — worktree isolation not available
          with --background. Commit any in-progress changes first.)
          Poll with ll_loop_status(loop_name='harness-optimize',
                                   repo='blender-agents')."

(20 minutes later, from Discord)

User:  "how's harness-optimize going?"
       → ll_loop_status(loop_name="harness-optimize", repo="blender-agents")
       ← "harness-optimize-20260518T214700: iteration 7/20,
          state=evaluate_change, last_verdict=improved (score 0.83→0.86).
          ETA ~25 min."

(Later)

User:  "stop it, we have what we need"
       → ll_loop_stop(loop_name="harness-optimize", repo="blender-agents")
       ← "Halted. Final score 0.86 (+0.03). Changes committed to main branch."
```

### Flow 3: Overnight Cron Across Repos

```bash
# Hermes not on PyPI — install from GitHub first:
# pip install git+https://github.com/NousResearch/hermes-agent.git

hermes cron create "0 2 * * *" \
  --prompt "For each registered repo, run docs-sync and dead-code-cleanup
            in foreground with worktree=true and quiet=true. In the morning,
            summarize: which loops improved state, which found nothing, which
            failed. Send the briefing to Telegram." \
  --toolsets little-loops,messaging \
  --deliver telegram
```

```bash
hermes cron create "0 7 * * 1-5" \
  --prompt "For each registered repo: ll_scan_codebase, then ll_loop_run
            autodev on the top P0 issue with worktree=true and quiet=true.
            Send a morning briefing with what was attempted and what landed." \
  --toolsets little-loops,messaging \
  --deliver telegram
```

**Cron session restriction:** The `cronjob` toolset is **explicitly disabled** in cron-triggered sessions (Hermes hard restriction — not configurable). FSM loops running inside cron sessions cannot use `cronjob` to create follow-up cron jobs. Loops that need self-continuation must use `on_handoff: spawn` (which 34 of 50 built-in loops already declare). Do not design cron prompts that expect to schedule follow-up jobs from within the cron execution.

### Flow 4: Simulate Before Committing

```
User:  "Show me what dead-code-cleanup would do on work-api without
        running it"
       → ll_loop_simulate(name="dead-code-cleanup", repo="work-api",
                          scenario="all-pass")
       ← "Simulation: would remove 14 symbols across 6 files. Highest-risk
          removal: scripts/legacy/old_auth.py:authenticate_v1 (3 incoming
          edges from test files only). Run for real with ll_loop_run."

User:  "go for it"
       → ll_loop_run(name="dead-code-cleanup", repo="work-api",
                     worktree=true)
       ← "Complete. 14 symbols removed. Tests still green. PR-ready."
```

### Flow 5: Issue-Driven (Scaffolding Around Loops)

```
User:  "switch to my-app, scan and ship the top issue"
       → ll_scan_codebase()        # via ll-action invoke
       → ll_prioritize_issues()    # via ll-action invoke
       → ll_loop_run(name="autodev")  # consumes the prioritized issues
       ← "autodev: BUG-003 complete. Commit abc1234. Tests green. Want a PR?"

User:  "yes"
       → ll_open_pr()              # via ll-action invoke
       ← "PR #47 opened: fix-auth-bypass."
```

### Flow 6: Delegated Loop Work via Subagent

```
User:  "Run harness-optimize on my-app and the rn-plan loop on work-api in
        parallel. Don't bother me until both finish."

Hermes spawns two subagents in parallel:
  delegate_task(
    goal="Run harness-optimize on my-app to convergence",
    toolsets=["little-loops", "file", "terminal"],
    context="Repo: my-app. Use worktree=true, quiet=true. harness-optimize
             has no declared scope and defaults to the whole project — do NOT
             run another whole-project loop on my-app concurrently. The
             subagent IS the background context; run synchronously and return
             when complete. harness-optimize declares on_handoff: spawn, so
             it self-continues across context windows."
  )
  delegate_task(
    goal="Run rn-plan on work-api for the v2-launch initiative",
    toolsets=["little-loops", "file", "terminal"],
    context="Repo: work-api. Use worktree=true, quiet=true. rn-plan has no
             declared scope and defaults to whole-project. Do not combine
             background=true with worktree=true — the CLI forbids it. Note:
             rn-plan has no on_handoff: declaration (defaults to pause, not
             spawn), so the subagent must handle re-invocation if its context
             window is exhausted before the loop completes."
  )

Note: the two loops are parallel only because the repos differ.
Same-repo parallelism for whole-project-scope loops would block on the
scope lock; use --queue or choose non-overlapping-scope loops instead.

Each subagent autonomously:
  1. ll_loop_run(name=<loop>, repo=<repo>, worktree=true, quiet=true)
     # Runs synchronously; subagent itself is the async delegation unit
  2. Returns summary to parent when the loop reaches a terminal state
  → Parent notifies user when both complete
```

---

## Implementation Phases

### Phase 1: Skill Pack (Week 1)

Ship a Hermes skill pack that wraps the highest-value loop commands via `terminal()` calls. No native tool registration. Gets something functional into users' hands immediately.

**Prerequisites:**
- Hermes is not on PyPI. Install from GitHub: `pip install git+https://github.com/NousResearch/hermes-agent.git`
- little-loops must be installed and `ll-loop` / `ll-action` must be on `PATH`: `pip install -e <path-to-little-loops>`

**Deliverables:**
1. Create `skills/little-loops/SKILL.md` with the following frontmatter and content:
   ```yaml
   ---
   name: little-loops
   description: FSM-driven automation loops + issue/sprint scaffolding
   version: 1.0.0
   metadata:
     hermes:
       tags: [Development, Automation]
       requires_tools: [terminal]
       config:
         - key: little-loops.repos
           description: "Named repo mappings (name: /abs/path)"
         - key: little-loops.command_timeout
           description: "Default subprocess timeout in seconds"
           default: "300"
   ---
   ```
   The `requires_tools: [terminal]` declaration hides the skill on surfaces that lack terminal access. The skill body must document:
   - The Phase 1 repo= constraint: in Phase 1 there is no `/project` command or session binding, so users must pass `repo=` explicitly on every call or have exactly one repo registered for the single-repo fallback to apply. State this constraint prominently.
   - The `ll-action invoke` bridge syntax, including the `--output json` requirement and the `background`/`worktree` mutual-exclusivity constraint.
2. Create individual skill files for: `ll-loop run`, `ll-loop list`, `ll-loop status <loop_name>`, `ll-loop resume <loop_name>`, `ll-parallel`, `ll-auto`, and `ll-action invoke <skill> --output json`.
3. Open a PR to the `hermes-skills` repository following its contribution guide (skill frontmatter, README entry, example prompts). The PR description must include a working demo transcript covering at least: `ll-loop list`, `ll-loop run docs-sync --dry-run`, and `ll-loop status docs-sync`.
4. After PR merge, confirm `hermes skills install little-loops` completes without error on a clean Hermes install (installed from the GitHub URL above).

**Phase 1 fallback (if hermes-skills hub is inaccessible or PR is blocked):** Clone the little-loops repo, copy `skills/little-loops/SKILL.md` to `~/.hermes/skills/little-loops/SKILL.md` (Hermes's local skills directory), and confirm `hermes skills list` shows `little-loops`. This fallback achieves the same Phase 1 functionality without the hub dependency and provides a working path regardless of hub availability.

**Phase 1 is done when:**
- `hermes skills install little-loops` completes without error (or the fallback local install succeeds).
- A user on a fresh Hermes install can trigger `ll-loop run docs-sync --dry-run` from a Telegram message and receive a non-error response. (Because Phase 1 has no session binding, the user must either register exactly one repo or pass `repo=` explicitly in their message.)
- Skill documentation explicitly covers: the `repo=` requirement and the single-repo-fallback limitation, the `--output json` requirement for `ll-action invoke`, and the `background`/`worktree` mutual-exclusivity constraint.

**Value:** Proves the concept. Users can trigger loops from Hermes today. Feedback on the repo resolution UX.

### Phase 2: Native Toolset (Week 2–3)

Register tools in Hermes's tool registry with proper schemas. Repo config in `config.yaml`. Session binding via `/project` command or natural language.

**Deliverables:**
1. Create `tools/little_loops_tool.py` with:
   - Module-level `_session_bindings: dict[str, str] = {}` (in-memory session binding store keyed by `task_id` — **not** `session.metadata`, which does not exist in the Hermes API).
   - Module-level `_skill_catalog: list[dict] = []` (populated by `check_little_loops()` as a side effect).
   - `load_registered_repos()` reading from `config["skills"]["config"]["little-loops"]["repos"]` in `~/.hermes/config.yaml` (the `skills.config` namespace — `hermes config set little-loops.repos.my-app /path` writes here).
   - `resolve_repo(args, task_id)` implementing the 4-level priority chain and `os.path.isdir()` validation (R10).
   - `run_ll_loop(subcommand, args, **kwargs)` with `task_id = kwargs.get("task_id")`, snake_case→kebab-case flag translation (via `flag_map`), and `timeout=None` for background calls.
   - `run_ll_action(skill, args, **kwargs)` with `task_id = kwargs.get("task_id")`; collects all skill args into a single `--args key1=val1 key2=val2 ...` invocation (not one `--args` per key); docstring notes callers must not assume `output` is valid JSON when `success=False` (R9).
   - `_run_subprocess(cmd_parts, cwd, timeout)` using `Popen` + `communicate(timeout)` — **not** `subprocess.run()`. On `TimeoutExpired`: call `proc.kill()`, then `proc.communicate()` (required to flush pipes and set returncode), then return structured timeout envelope.
   - `set_project_binding(task_id, name)` writing `_session_bindings[task_id] = name` for use by the `/project` command.
2. Register all 22 tools via `registry.register()` calls in `tools/little_loops_tool.py`. Do **not** edit `toolsets.py` dict — tools self-register at module import time. Each call follows the pattern: `registry.register(name=..., toolset="little-loops", schema=..., handler=lambda args, **kw: ..., check_fn=check_little_loops, is_async=False)`.
3. Add `little-loops.repos`, `little-loops.command_timeout` (default: 300), and `little-loops.auto_bind_single` (default: true) to Hermes config schema with documented defaults. Note in docs: all keys are set via `hermes config set little-loops.<key> <value>` and read from `skills.config.little-loops.<key>` in `~/.hermes/config.yaml`.
4. Add `/project <name>` slash command that calls `set_project_binding(task_id, name)` where `task_id` is received via `**kwargs`.
5. Add `/project list` to show all registered repos and the currently bound repo for this session.
6. Implement `check_little_loops()` as a **zero-argument callable** (required by Hermes's `registry.register(check_fn=...)`). Results are TTL-cached for **30 seconds** (hardcoded in Hermes; not configurable). Three sequential checks: (a) `shutil.which("ll-loop")`, (b) `ll-action capabilities --output json` (binary present + host info; returns `{host, binary, version, capabilities, hooks}`), (c) `ll-action list --output json` (populates `_skill_catalog` as `[{name, description}]`; assert both `exit_code == 0` AND `len(skills) > 0`). Log a warning and return `False` if any check fails or if the skill list is empty.

**Phase 2 is done when all of the following pass (13 acceptance tests in `tests/hermes/test_little_loops.py`):**
- `ll_loop_run` handler calls `ll-loop run general-task --dry-run` against a fixture repo and returns `{"success": true, "output": <non-empty>}`.
- `ll_loop_status(loop_name="general-task")` against a repo with no `.loops/.running/` directory returns `{"success": false, "error": ...}` (graceful empty-state), not an unhandled exception.
- `resolve_repo()` unit tests — 5 tests, one per case:
  1. Explicit `repo=` wins over `_session_bindings[task_id]`.
  2. `_session_bindings[task_id]` wins over single-repo fallback (set binding via `_session_bindings[task_id] = "my-app"` before calling).
  3. Single-repo fallback fires when exactly one repo is registered and no binding exists.
  4. Structured `ambiguous_repo` error fires when two repos are registered with no session binding.
  5. `repo_not_found` error fires when the resolved path does not exist on disk (mock `os.path.isdir` to return `False`).
- `check_little_loops()` returns `False` when `ll-loop` binary is missing (test with `PATH` mocked to empty).
- `check_little_loops()` returns `False` when `ll-action` binary is missing (separate test, `PATH` mocked).
- `check_little_loops()` returns `False` when `ll-action list --output json` returns `[]` (mock subprocess output to `[]`).
- `check_little_loops()` populates `_skill_catalog` from `ll-action list --output json` — assert `_skill_catalog[0]` has `{name, description}` keys (not from `ll-action capabilities`).
- `run_ll_action` builds the command as `["ll-action", "invoke", skill, "--output", "json", "--timeout", str(n)]` (assert on `cmd_parts`).
- `run_ll_action` with `args={"issue_id": "BUG-001", "priority": "P0"}` builds `["ll-action", "invoke", skill, "--output", "json", "--timeout", str(n), "--args", "issue_id=BUG-001", "priority=P0"]` — assert that `"--args"` appears exactly once and both key=value pairs follow it in the same invocation (not two separate `--args` flags).
- `max_iterations=5` in tool args produces `--max-iterations 5` (not `--max_iterations 5`) in the subprocess command.
- `subprocess.TimeoutExpired` is handled by `Popen.kill()` + `Popen.communicate()` and returns `{"success": false, "error": "timeout", "hint": "..."}` — not an uncaught exception and not a call to `exc.process.kill()` (verify the Popen pattern is used, not `subprocess.run`).

**Value:** Native composability. The model autonomously chooses to use loops. Subagent and cron scoping works.

### Phase 3: Discovery and Polish (Week 4)

Auto-discovery of repos, status reporting, loop discovery, structured error surfacing, and integration test coverage for non-interactive surfaces.

**Deliverables:**
1. Auto-discovery: on Hermes startup, scan `little-loops.discovery_paths` (if set in config) for directories containing `.ll/ll-config.json`; add found repos to the session registry without overwriting explicitly configured entries. Implemented in `tools/little_loops_tool.py:discover_repos()`.
2. `/project list` — show registered repos + status (git branch, last loop run, open issue count).
3. `/project status` — show running loops + issue state for current repo.
4. `/loops` — list available loops in current repo's `.loops/` plus built-ins; annotate loops that declare `on_handoff: spawn` as "safe for long delegation." Since `ll-loop list --json` does not include loop descriptions, supplement with a follow-up `ll-action list --output json` call to attach human-readable descriptions to the output.
5. Output truncation: cap `output` at 8,000 chars and `errors` at 2,000 chars in `_run_subprocess()` (already in handler code). Verify by unit test: when subprocess emits 10,000 chars of stdout, the `output` field in the envelope is exactly 8,000 chars.
6. Stale-PID surfacing: in `_run_subprocess()`, after collecting stdout, check if the output contains the string `"not running - stale PID file"`. If so, return a supplemental `warning` field: `{"warning": "stale_pid", "hint": "Run ll_loop_stop to clear the stale lock"}` merged into the response envelope rather than treating it as a clean success response.
7. Runtime schema-drift probe: implement `_check_schema_drift(skills: list[dict]) -> None` in `tools/little_loops_tool.py`. Call it at the end of `check_little_loops()` after populating `_skill_catalog`. It asserts each entry has `name: str` and `description: str` fields; logs a `WARNING`-level message (not an error, and not a toolset disable) if the shape changes, so maintainers are alerted to `ll-action list` format drift without breaking the toolset.
8. `built_in` field guard: in the `ll_loop_list` handler, when parsing `ll-loop list --json` output, treat a missing `built_in` key as `False` (not a KeyError). The field is present only for built-in loops (`built_in: true`); project-local loops omit it entirely. Unit test: a mock `ll-loop list --json` response with one entry lacking `built_in` is parsed successfully with `built_in` defaulting to `False`.
9. Integration smoke tests for non-interactive surfaces:
   - Cron simulation (`tests/hermes/test_cron_integration.py`): use a mock Hermes cron runner to execute the Flow 3 cron prompt against two fixture repos; assert both `docs-sync --dry-run` and `dead-code-cleanup --dry-run` are called with `worktree=true` and `quiet=true`; assert the returned briefing JSON contains entries for both repos; assert no `cronjob` tool calls are made within the cron execution (Hermes disables this toolset in cron sessions).
   - Multi-repo subagent simulation (`tests/hermes/test_subagent_integration.py`): use a mock `delegate_task` harness to execute Flow 6's two-subagent pattern; assert `harness-optimize` runs against `my-app` with `worktree=true` and `rn-plan` runs against `work-api` with `worktree=true`; assert neither call sets both `background=true` and `worktree=true`.

**Phase 3 is done when:**
- Auto-discovery finds repos in paths listed in `discovery_paths` that contain `.ll/` and adds them to the session registry without user configuration, verified in `tests/hermes/test_repo_discovery.py`.
- `/loops` output distinguishes project-local loops from built-ins, annotates `on_handoff: spawn` loops as "safe for long delegation," and includes human-readable descriptions.
- Output truncation unit test passes: 10,000-char stdout → `output` field is exactly 8,000 chars, verified in `tests/hermes/test_subprocess_handler.py`.
- The stale-PID warning field (`{"warning": "stale_pid", "hint": ...}`) is present in the envelope when `ll-loop status` emits "stale PID file" text, verified in `tests/hermes/test_stale_pid.py`.
- The schema-drift probe (`_check_schema_drift`) runs on startup, logs a WARNING when `ll-action list` output shape changes, and does not disable the toolset, verified in `tests/hermes/test_schema_drift.py`.
- The `built_in` field guard unit test passes: missing `built_in` key in `ll-loop list --json` output is parsed as `False` without error, verified in `tests/hermes/test_loop_list_handler.py`.
- Cron integration smoke test passes: Flow 3 prompt produces `worktree=true, quiet=true` calls for both repos and no `cronjob` tool invocations, verified in `tests/hermes/test_cron_integration.py`.
- Multi-repo subagent smoke test passes: Flow 6 pattern produces no calls with both `background=true` and `worktree=true`, verified in `tests/hermes/test_subagent_integration.py`.

---

## Config Schema

```yaml
little-loops:
  # Named repos — the core of multi-repo support
  repos:
    my-app: /home/user/projects/my-app
    work-api: /home/user/work/api-service

  # Optional: auto-discover repos by scanning these paths for .ll/ directories
  # discovery_paths:
  #   - /home/user/projects
  #   - /home/user/work

  # Default timeout for ll-* commands (seconds). ll-action invoke uses this
  # plus 30s as the Python subprocess timeout (the CLI enforces its own deadline).
  command_timeout: 300

  # Whether to auto-bind to the only registered repo on session start
  auto_bind_single: true
```

All keys are set via `hermes config set little-loops.<key> <value>`. Values are read from the `skills.config.little-loops` namespace in `~/.hermes/config.yaml` — not from a top-level `little-loops` key.

---

## Risk Mitigation

### R1: `subprocess.TimeoutExpired` for long loops

**Risk:** `ll-loop run` for loops like `harness-optimize` or `autodev` can run for hours. A Python-side timeout will kill foreground waits.

**Mitigation:**
- Use `Popen` + `communicate(timeout)` — **not** `subprocess.run()`. When `TimeoutExpired` fires, `subprocess.run()` leaves pipe buffers unread and `returncode` unset. The correct pattern:
  ```python
  proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True, cwd=cwd)
  try:
      outs, errs = proc.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
      proc.kill()
      outs, errs = proc.communicate()  # REQUIRED: flushes pipes, sets returncode
      return json.dumps({"success": False, "error": "timeout", ...})
  ```
- For `background=true` calls: pass `timeout=None` to `proc.communicate()` — the call returns as soon as the daemon forks and writes its PID file. Return the instance ID line from stdout immediately.
- For foreground calls: set timeout to `command_timeout` from config. On `TimeoutExpired`, follow the pattern above, return `{"success": false, "error": "timeout", "partial_output": ..., "hint": "Poll via ll_loop_status."}`.

### R2: `ll-action` output format mismatch

**Risk:** `ll-action invoke` defaults to `--output stream-json` (NDJSON event stream). A handler that omits `--output json` receives an unparseable stream.

**Mitigation:** Always explicitly pass `--output json` in `run_ll_action()`. Add a unit test that asserts `cmd_parts` contains `["--output", "json"]`. Reserve `--output stream-json` for future streaming surfaces only, and document the distinction in the skill pack.

### R3: `ll-loop status` and `ll-loop stop` require a loop name

**Risk:** The plan originally modeled these as accepting an instance ID. The actual CLI takes a loop name and operates on all matching instances.

**Mitigation:** Tool schemas use `loop_name` (required) + optional `instance_id` (for future disambiguation). Tool description states: "if multiple instances are running, all are stopped." For the "what's running?" surface query, use `ll_loop_list` with `running=true` (maps to `ll-loop list --running`), not `ll_loop_status`.

### R4: Scope-lock collisions for whole-project loops

**Risk:** Loops with no declared `scope:` normalize to `["."]` (whole project). `harness-optimize` and `rn-plan` are examples. Triggering two such loops on the same repo from different Hermes surfaces (e.g., a cron job and an interactive session) means the second blocks on the lock.

**Mitigation:**
- Document `--queue` (`queue=true` in the tool schema) as the resolution: the second loop writes a queue entry to `.loops/.queue/<uuid>.json` and waits for the holder.
- In cron prompts, include the instruction: "use `queue=true` when triggering multiple loops on the same repo."
- In Flow 6 context strings, note that same-repo whole-project loops must be serialized.

### R5: `--background` and `--worktree` are mutually exclusive

**Risk:** The CLI (`scripts/little_loops/cli/loop/run.py:199-200`) raises `SystemExit` if both `--worktree` and `--background` are set. Any handler that passes both flags will fail immediately with a non-zero exit code.

**Mitigation:**
- **Foreground runs** (interactive, cron, subagent-delegated): use `worktree=true`. The loop runs synchronously in an isolated worktree under `{project_root}/.worktrees/`. The worktree branch name format is `<YYYYMMDD>-<HHMMSS>-<loop-name>` (dashes throughout; e.g. `20260518-214700-harness-optimize`). This is distinct from the instance ID format (`harness-optimize-20260518T214700`), which leads with the loop name and uses `T` as the date/time separator.
- **Background daemon runs**: use `background=true` only. The loop runs in the main working tree. Advise users to commit any in-progress work before launching a background daemon (see also: Open Question 3).
- Tool schema descriptions for both `background` and `worktree` explicitly state the mutual-exclusivity constraint. Cron prompt templates (Flow 3) use `worktree=true, quiet=true` without `background=true`. Subagent context strings (Flow 6) warn against combining the two.

### R6: Multi-repo ambiguity at runtime

**Risk:** User triggers a tool without a `repo=` argument and two or more repos are registered with no session binding.

**Mitigation:** Return a structured error immediately (not a generic exception):
```json
{"error": "ambiguous_repo",
 "registered": ["my-app", "work-api"],
 "hint": "pass repo= or bind with /project <name>"}
```
The model receives this as a tool result and can prompt the user to disambiguate without an unhandled error or a confusing traceback.

### R7: Git authentication for push/PR operations

**Risk:** `ll-action invoke open-pr` and `ll-action invoke commit` may need git credentials that aren't present in the Hermes process environment.

**Mitigation (open, not yet resolved):** `ll-*` commands inherit the process environment. If git credentials are set up in the user's shell (SSH keys, git credential helper), they flow through automatically. Hermes installation docs should advise: "ensure git credentials are configured system-wide, not only in your interactive shell (Hermes is installed from `pip install git+https://github.com/NousResearch/hermes-agent.git` and runs outside your interactive shell profile)." If this proves insufficient, a future phase can add `git_env_passthrough` config.

### R8: Stale PID and lock files after daemon crashes

**Risk:** If a background `ll-loop` daemon crashes without cleanup, `.pid` and `.lock` files persist. `ll-loop status` reports "not running - stale PID file"; `ll-loop stop` has recovery logic for orphaned locks.

**Mitigation:** Hermes handlers do not attempt to clean stale files — `ll-loop`'s own CLI handles recovery. When `ll-loop status` output contains "stale PID file", `_run_subprocess()` surfaces this as a structured warning field (`{"warning": "stale_pid", "hint": "Run ll_loop_stop to clear the stale lock"}`) rather than treating it as a clean status. Phase 3 deliverable 6 implements this.

### R9: Malformed or non-JSON output from `ll-action invoke`

**Risk:** If `ll-action invoke` exits non-zero before it can wrap output in JSON format (e.g., an unhandled crash in the skill), its stdout may be a plain-text traceback. A handler that assumes `output` is always parseable JSON will fail silently or produce a confusing model response.

**Mitigation:** `run_ll_action()` docstring makes the contract explicit: callers must not assume `output` is valid JSON when `success=False`. Handlers that need to pass inner output to the model should check `success` first; if false, treat `output` as opaque diagnostic text. Add a unit test: when `ll-action invoke` returns exit code 1 with non-JSON stdout, the envelope is `{"success": false, "output": "<raw text>", ...}` and the handler does not raise.

### R10: Missing or invalid repo path on disk

**Risk:** A registered repo path may no longer exist (deleted, moved, or not mounted). Without an explicit check, the subprocess call fails with a confusing `FileNotFoundError` or `subprocess.CalledProcessError`, with no indication to the model about which repo was the problem.

**Mitigation:** After `resolve_repo()` determines a candidate path, call `os.path.isdir(path)` before returning. If the directory does not exist, return a structured error: `{"error": "repo_not_found", "path": path, "hint": "Check config: hermes config list little-loops.repos"}`. Unit test: `resolve_repo()` returns `repo_not_found` when the resolved path does not exist on disk (mock `os.path.isdir` to return `False`). This is the fifth test in the Phase 2 acceptance suite.

---

## Open Questions

1. **Loop run output streaming.** `ll-loop run` emits JSONL events to `.events.jsonl` for the duration of a run. For messaging surfaces, should Hermes tail this file and post incremental updates? Tentative: yes for foreground loops under ~30 seconds; use `--background` + periodic `ll_loop_status` polling for longer runs. A future `ll_loop_tail` tool could expose the events file directly. Note: `ll-action invoke` already supports `--output stream-json` for incremental output from skills, which is a related pattern.

2. **`/project` vs natural language.** Is a `/project` slash command worth adding to the Hermes command registry, or should this be handled entirely through the model's understanding of "switch to X"? Current plan: ship both — natural language for casual use, `/project` for precision. No decision needed before Phase 2 ships.

3. **Repo health pre-check for background runs.** `worktree=true` sidesteps dirty-tree issues for foreground runs (R5). For background daemon runs (`background=true`), the loop operates in the main working tree. Should Hermes warn if the repo has uncommitted changes before launching a background daemon? Defer to Phase 3 — add an optional `preflight_check` config that runs `git status --short` before `background=true` launches and surfaces a structured warning (not a hard block) if changes are detected.

---

## Success Metrics

- A Hermes user can install little-loops, register a repo, and trigger a loop (e.g. `docs-sync`) from Telegram within 5 minutes of setup.
- Cron jobs successfully run nightly loops (`docs-sync`, `harness-optimize`, `dead-code-cleanup`) across multiple repos with morning briefings delivered to a messaging surface.
- Subagents complete loop execution autonomously (synchronous foreground run with `worktree=true`), including returning structured summaries to the parent agent, without manual intervention.
- Phase 2 acceptance tests (13 tests in `tests/hermes/test_little_loops.py`) all pass in CI.
- Phase 3 integration smoke tests (cron and multi-repo subagent flows) pass in CI.
- At least one community-shared loop YAML is contributed for use with Hermes.

---

## Related

- [[_Index|Little-Loops Project Index]]
- [[ll-harness CLI planning]]
- [[ll-loop parallelism tradeoffs]]

Up: [[_Index|Little-Loops]] | [[Personal/_Meta/MOC-Personal-Home|Personal Home]]
