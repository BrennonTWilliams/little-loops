# Web Research Findings

## Key Documentation (External — Hermes Agent Framework)

Sources confirmed from NousResearch/hermes-agent (GitHub, released February 2026):

- **GitHub**: https://github.com/NousResearch/hermes-agent
- **Docs**: https://hermes-agent.nousresearch.com/
- **CLI Reference**: https://hermes-agent.nousresearch.com/docs/reference/cli-commands
- **Adding Tools**: https://hermes-agent.nousresearch.com/docs/developer-guide/adding-tools/
- **Creating Skills**: https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills
- **Cron Internals**: https://hermes-agent.nousresearch.com/docs/developer-guide/cron-internals
- **Session Storage**: https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage
- **Python Library**: https://hermes-agent.nousresearch.com/docs/guides/python-library/

### Python Subprocess
- **Official docs**: https://docs.python.org/3/library/subprocess.html
- **Leaky timeout (AWS CodeGuru)**: https://docs.aws.amazon.com/codeguru/detector-library/python/leaky-subprocess-timeout/
- **Kill process group**: https://alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/

---

## Best Practices (Hermes-specific)

### Tool Registration
Tools self-register via `registry.register()` at module import time — discovered by `discover_builtin_tools()` which AST-scans `tools/*.py`. Not by editing `TOOLSETS` dict directly:

```python
from tools.registry import registry, tool_error, tool_result

registry.register(
    name="ll_loop_run",
    toolset="little-loops",
    schema=LL_LOOP_RUN_SCHEMA,          # standard JSON Schema function-calling format
    handler=lambda args, **kw: run_ll_loop("run", args, kw.get("task_id")),
    check_fn=check_little_loops,         # zero-arg callable returning bool
    is_async=False,
)
```

`tool_error(message)` and `tool_result(...)` are provided helpers that return properly-formatted JSON strings. **Handlers must return strings, never raw dicts.** `registry.dispatch()` wraps all exceptions as `{"error": "..."}` JSON, so the model always sees structured JSON even on crash.

### `check_fn` Caching
- Zero-argument callable, returns bool.
- Results are TTL-cached for **30 seconds** (thread-safe; `_CHECK_FN_TTL_SECONDS = 30.0`, hardcoded — not configurable without a code change).
- Cache is invalidated only by `hermes tools enable/disable` commands.
- Implication: if `ll-loop` or `ll-action` is installed mid-session, the toolset won't become available until 30s TTL expires. Document in setup instructions: restart Hermes after installing little-loops.

### Handler Signature Must Accept `**kwargs`
Hermes's `dispatch()` calls `handler(args, **kwargs)` where `kwargs` includes at minimum `task_id`. Handlers that omit `**kwargs` raise `TypeError`. The plan's current handler signatures (`def run_ll_loop(subcommand, args, session_metadata=None)`) need adaptation:

```python
def run_ll_loop(subcommand: str, args: dict, **kwargs) -> str:
    task_id = kwargs.get("task_id")      # session-scoped binding lookup key
    ...
```

### Session Metadata — Critical Design Gap
**`session.metadata` as a named dict does not exist in Hermes's public API.** Session data is stored in SQLite at `~/.hermes/state.db` (fields: `id`, `source`, `user_id`, `model`, `parent_session_id`, `started_at`, etc.). Handlers receive context only via `task_id` in `**kwargs`.

The plan's Phase 2 `/project` session binding via `session.metadata["little-loops-repo"]` must be redesigned. Concrete options:
1. **In-memory dict keyed by `task_id`** — ephemeral, survives per-session only.
2. **Write to `~/.hermes/config.yaml`** via `hermes config set` — durable but makes binding persistent across sessions (probably not desired).
3. **Sidecar SQLite table in `~/.hermes/state.db`** keyed by `session_id` — durable per session, cleaned up on session end.

Option 1 (in-memory) is the simplest and most correct semantics for "session-scoped."

### SKILL.md Frontmatter for Phase 1
Skills can declare `requires_tools` to hide when dependencies are absent:

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

### Cron Sessions — Hard Constraint
The `cronjob` toolset is **explicitly disabled** in cron-triggered sessions (Hermes hard restriction, not config). FSM loops running inside cron sessions cannot use the `cronjob` tool to create follow-up cron jobs. Loops that need self-continuation must use `on_handoff: spawn` (which 34 of 50 built-in loops already declare).

### Subprocess — Correct Timeout Pattern
The plan's `_run_subprocess` uses `subprocess.run()` with `exc.process.kill()` on `TimeoutExpired`. This is leaky — after `kill()`, pipe buffers are not flushed and `returncode` is not set. The canonical pattern:

```python
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
try:
    outs, errs = proc.communicate(timeout=timeout)
except subprocess.TimeoutExpired:
    proc.kill()
    outs, errs = proc.communicate()   # REQUIRED: flushes pipes, sets returncode
```

For background daemon launches (where the child forks its own subprocess group), use `start_new_session=True` to kill the full process tree:

```python
proc = subprocess.Popen(cmd, start_new_session=True, ...)
except subprocess.TimeoutExpired:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    proc.wait()
```

---

## Pitfalls & Constraints (External — Hermes API)

**1. No PyPI package.** Hermes is not on PyPI. Install must be from GitHub:
```bash
pip install git+https://github.com/NousResearch/hermes-agent.git
```
Setup instructions must reference the GitHub URL, not `pip install hermes-agent`.

**2. `session.metadata` does not exist** (see Best Practices above). This is the biggest API mismatch between the plan and the real Hermes API. Must be resolved before Phase 2 implementation.

**3. Cron sessions cannot create cron jobs.** The `cronjob` toolset is disabled inside cron-triggered agent sessions. Loops running in cron cannot self-schedule follow-up cron jobs; they must use `on_handoff: spawn`.

**4. `check_fn` TTL is 30s and hardcoded.** Not configurable without code change. Restart Hermes after installing/updating little-loops.

**5. `subprocess.run()` + `TimeoutExpired` leaks.** The plan's current `_run_subprocess` calling `exc.process.kill()` without a follow-up `proc.communicate()` may leave pipe buffers unread. Switch to `Popen` + `communicate()` pattern (see above).

**6. Cron delivery targets.** Cron `deliver` field accepts: `"origin"`, `"local"`, `"telegram"`, `"discord"`, `"slack"`, `"all"`. Output is saved to `~/.hermes/cron/output/{job_id}/{timestamp}.md`. The Flow 3 cron prompts are consistent with this but should specify a `deliver` target explicitly in the cron creation example.

**7. `config set` writes to `skills.config` namespace.** `hermes config set little-loops.repos.my-app /path` writes to `skills.config.little-loops.repos.my-app` in `~/.hermes/config.yaml`. The `resolve_repo()` function must read from this path in config.yaml — not from a separate file or environment variable.

---

# File Research Findings

Research focused on CLI surface claims, risk mitigation gaps, and testability specifics. A previous pass flagged testability and risk_mitigation as MEDIUM; this pass adds a critical new gap (worktree/background incompatibility), corrects the `ll-action capabilities` misconception, and adds verified line numbers throughout.

## Verified References

- **Loop catalog size and categories.**
  - 50 `.yaml` loops in `scripts/little_loops/loops/` (plus `lib/`, `oracles/`, `__init__.py`, `README.md`, `yaml_state_editor.py`). Plan's "~50 built-in loops" is correct.
  - 11 distinct `category:` values across the loop YAMLs: `apo`, `code-quality`, `data`, `evaluation`, `harness`, `issue-management`, `meta`, `optimization`, `planning`, `research`, `rl`. Matches the plan's "11 categories" claim exactly.

- **CLI entry points** (`scripts/pyproject.toml:50-66`): `ll-loop`, `ll-action`, `ll-parallel`, `ll-auto`, `ll-sprint`, `ll-history`, `ll-issues`, `ll-doctor`, `ll-sync`, plus internal/migration tools. All wired through `little_loops.cli:main_*` functions.

- **`ll-loop` subcommands** (`scripts/little_loops/cli/loop/__init__.py:39-64`): `run`, `validate`, `list`, `status`, `stop`, `resume`, `history`, `test`, `simulate`, `install`, `show`, `fragments`, `next-loop`. The plan's tool entries map cleanly onto these.

- **`ll-loop run` flags** (`__init__.py:99-179`): `--max-iterations/-n`, `--dry-run`, `--background/-b`, `--worktree`, `--context KEY=VALUE` (repeatable), `--no-llm`, `--llm-model`, `--queue/-q` (wait for conflicting loops), `--builtin` (bypass project `.loops/`), `--program-md`, `--delay`, `--quiet`, `--verbose`, `--show-diagrams`, `--clear`. Plan's listed flags (`--background`, `--worktree`, `--max-iterations`, `--dry-run`, `--context K=V`) are all real.

- **Persisted loop state.** `fsm/persistence.py:205-223` and module docstring at lines 12–17 confirm the layout:
  ```
  .loops/.running/<instance_id>.state.json       (LoopState JSON)
  .loops/.running/<instance_id>.events.jsonl     (append-only event stream)
  .loops/.running/<instance_id>.lock             (scope lock + holder PID)
  .loops/.running/<instance_id>.pid              (background daemon PID)
  .loops/.running/<instance_id>.log              (stderr/stdout for background runs)
  ```
  Instance IDs use `<loop-name>-<TIMESTAMP>` format (docstring example: `fix-types-20260503T122306`).

- **Sub-loop composition.** `loop: <name>` + `context_passthrough: true` exists verbatim in `loops/sprint-build-and-validate.yaml:78-79, 136-137`, calling `recursive-refine`. Composability claim is real.

- **Scope-based locking.** `fsm/concurrency.py` defines `ScopeLock` and `LockManager` (lines 48-145). Empty `scope:` is normalized to `["."]` (whole project) at lines 110-111. Lock file at `.loops/.running/<instance>.lock` blocks overlapping-scope acquisitions. `docs-sync.yaml:8-10` declares `scope: ["docs/", "*.md"]` — exactly the example the plan uses.

- **Evaluator types.** `fsm/schema.py:56-66` enumerates: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `llm_structured`, `mcp_result`, `harbor_scorer`. `llm_structured` is documented (schema.py:38) as the "default for slash" evaluators.

- **Loops dir is configurable.** `config/features.py:342` — `loops_dir: str = ".loops"`; `config/core.py:363` exposes `get_loops_dir()`. Plan's `.loops/` references are the default but not invariant.

- **ll-loop status / ll-loop list output.** Both support `--json` (`__init__.py:194-218`). `cmd_status` (`lifecycle.py:143-229`) emits a rich JSON payload per instance: `instance_id`, `status`, `current_state`, `iteration`, `pid`, `pid_source`, `log_file`, `log_updated_ago`, plus full `LoopState` fields. This is the structured output Hermes needs for messaging surfaces.

## Gaps Found

0. **CRITICAL: `--worktree` and `--background` are mutually exclusive.**
   `scripts/little_loops/cli/loop/run.py:199-200`:
   ```python
   if getattr(args, "worktree", False):
       raise SystemExit("--worktree and --background cannot be combined")
   ```
   The plan's Flow 2 calls `ll_loop_run(name="harness-optimize", background=true, worktree=true)`, and Flow 6 instructs subagents to use both flags together. Both will raise `SystemExit` immediately. The tool schema description also says "Default true for cron and subagent contexts" for `worktree`, while the risk section recommends `background=true` for long-running loops — these two recommendations are mutually exclusive by the CLI's own enforcement.
   **Required fix:** Remove `worktree=true` from Flow 2 and Flow 6 where `background=true` is also set. Update the tool schema description to state: "`background` and `worktree` are mutually exclusive — use `worktree=true` for foreground runs that keep the working tree clean; use `background=true` for daemon runs that return immediately with an instance ID." Update R5 accordingly.

1. **`ll-loop status` and `ll-loop stop` take loop names, not instance IDs.** This contradicts the plan in two places:
   - Tool table row `ll_loop_stop` documents `ll-loop stop <instance>` (plan.md:118). The real signature is `ll-loop stop <loop_name>` (`__init__.py:222`, `lifecycle.py:232-304`). When multiple instances of the same loop are running, `cmd_stop` stops *all* live ones for that name.
   - Flow 2 shows `ll_loop_status()` (no arg) and `ll_loop_stop(instance="ho-2026-05-18-2147")` (plan.md:298-308). `cmd_status` requires a loop name (`__init__.py:215`, `lifecycle.py:143-157`); a bare `ll-loop status` errors out.
   - The "show me everything running" UX the plan implies is actually `ll-loop list --running [--status interrupted|awaiting_continuation]` (`__init__.py:191-194`), not `ll-loop status`.
   - **Action:** rewrite the Hermes tool schemas so `ll_loop_status` and `ll_loop_stop` accept `loop_name` (required) + optional `instance_id` (used only when multiple instances exist). Add a separate `ll_loop_list_running` (or fold `--running` into `ll_loop_list`) for the surface-level "what's running?" question.

2. **`ll-action` invocation syntax is wrong in the plan.** Plan's handler (plan.md:181-191) builds `["ll-action", skill, "--json", ...]`. The real CLI (`scripts/little_loops/cli/action.py:183-256`) is:
   ```
   ll-action invoke <skill> [--args ARG ...] [--timeout SECONDS] [--output stream-json|json]
   ll-action capabilities [--output json]
   ll-action list         [--output json]
   ```
   - The skill name is the positional arg of the `invoke` subcommand, not a top-level positional.
   - There is no `--json` flag. The flag is `--output json` (or `--output stream-json`, the default).
   - **Action:** rewrite `run_ll_action()` to `["ll-action", "invoke", skill, "--args", *args, "--output", "json"]` and propagate timeouts via `--timeout` rather than just the Python subprocess `timeout=` (the CLI has its own deadline).

3. **`stream-json` default is unmentioned but materially useful.** `ll-action invoke` defaults to streaming NDJSON events (`action.py:75, 224-227`). This is exactly the "incremental updates to messaging" pattern raised in Open Question 1. The plan currently treats `ll-action` as a single-shot subprocess; it could instead be tailed.

4. **Plan's "One LLM call point per iteration" oversimplifies.** Most loops use deterministic evaluators (`exit_code`, `output_contains`, `diff_stall`, etc.). `llm_structured` is just one of nine. The cost/latency claim ("~$0.001/eval, 300–800ms") is therefore upper-bound; many loops have zero LLM cost per iteration. Worth tightening the wording.

5. **`max_iterations` parameter naming mismatch.** Plan's JSON schema (plan.md:233) uses `max_iterations` (snake_case). The CLI flag is `--max-iterations`. Handler must translate.

6. **Existing concurrency-handling flag the plan doesn't reference.** `ll-loop run --queue` (`__init__.py:148-150`) is the built-in answer to Open Question 2 ("should `ll_loop_status` surface pending-on-lock state?"). The mitigation already exists in-process: `--queue` makes the new run wait for the conflicting holder rather than failing. The plan should call this out and decide whether Hermes exposes it.

7. **`harness-optimize` does not declare a `scope:`.** `loops/harness-optimize.yaml` has no `scope:` field, which normalizes to `["."]` (whole project). The plan's Flow 6 spawns two subagents in parallel — `harness-optimize` on `my-app` and `rn-plan` on `work-api` — but assumes "parallel" semantics. They are parallel *only because the repos differ*; same-repo parallelism for these loops would block on the whole-project lock. Worth a sentence in Flow 6 and a note in Open Question 2.

8. **Instance ID format example.** Flow 2 uses `ho-2026-05-18-2147` (plan.md:297). Real instance IDs are `<loop-name>-<compact-timestamp>` (e.g. `harness-optimize-20260518T214700` per persistence.py:13). Cosmetic but worth fixing.

9. **No host CLI abstraction note.** CLAUDE.md mandates `resolve_host()` in `scripts/little_loops/host_runner.py` for any host CLI invocation. Hermes-side handlers shelling out to `ll-loop` and `ll-action` are fine (these are ll's own CLIs). But if a Hermes handler ever invokes the upstream `claude`/`codex`/`opencode` CLI directly, it must route through that abstraction. Worth a one-line non-goal: "Hermes handlers wrap `ll-*` binaries only; never the underlying host CLI." The plan's Non-Goals section already has this — confirmed `resolve_host` exists at `scripts/little_loops/host_runner.py:751`.

10. **`ll-action capabilities` does NOT return a skill catalog.** The check_fn description says it "populates the live skill catalog (name, description, version) for the session." The actual output shape (`ll-action capabilities --help`) is `{host, binary, version, capabilities, hooks}` where `capabilities` is a list of host feature flags (`streaming`, `permission_skip`, etc.), not skill names. The skill catalog comes from `ll-action list --output json` → `[{name, description}]` (58 entries; no `version` field per skill). The check_fn must be two calls: `ll-action capabilities --output json` (confirms binary + gets host info) AND `ll-action list --output json` (populates skill catalog).

11. **`ll-loop history` requires a loop name.** The tool table maps `ll_loop_history` → `ll-loop history` with description "Past loop runs with verdicts" implying a bare call. The actual CLI signature is `ll-loop history <loop> [run_id]` where `loop` is a required positional (`ll-loop history --help`). The `ll_loop_history` tool schema must include `loop_name` as a required parameter.

12. **Worktree path is `.worktrees/` not `/tmp/ll-wt-*/`.** Flow 2 shows `Worktree: /tmp/ll-wt-harness-optimize-20260518T214700`. The actual worktree base is `{project_root}/.worktrees/` by default (`scripts/little_loops/config/automation.py:20`: `worktree_base: str = ".worktrees"`; `scripts/little_loops/config/core.py:371-373`). The worktree path for the example would be `{cwd}/.worktrees/20260518-214700-harness-optimize`.

13. **Worktree branch naming uses `-` not `T` in timestamp.** `scripts/little_loops/cli/loop/run.py:301-303`:
    ```python
    _timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    _branch_name = f"{_timestamp}-{_safe_name}"
    ```
    Branch name format: `20260518-214700-harness-optimize` (dashes throughout). Instance IDs use `T` separator: `harness-optimize-20260518T214700`. The plan conflates the two formats in the Flow 2 worktree example.

## New Discoveries

Concrete items the plan can pull in to lift the **testability** and **risk_mitigation** scores.

### Testability — concrete acceptance tests per phase

- **Existing test infra**: `scripts/tests/` with `python -m pytest scripts/tests/`. Phase deliverables can name specific test files (e.g. `tests/hermes/test_repo_resolve.py`, `tests/hermes/test_ll_loop_handler.py`).
- **Small loops usable as integration fixtures**:
  - `loops/general-task.yaml` (single-shot, no scope)
  - `loops/harness-single-shot.yaml` (deterministic, no LLM)
  - `loops/worktree-health.yaml` (read-only)
- **Phase 2 acceptance gates the plan should write down**:
  - `ll_loop_run` handler invokes `ll-loop run general-task --dry-run` and returns `success=True` with non-empty `output`.
  - `ll_loop_status` against a repo with no `.loops/.running/` returns the "no state found" error path, not a 500.
  - `resolve_repo()` prefers explicit `repo=` over session metadata over single-repo fallback (one unit test per priority level — the plan's resolution chain has four).
  - `check_fn` returns falsy when *either* `ll-loop` or `ll-action` is missing (two tests, not one).
- **Phase 3 acceptance gate**: a runtime probe that runs `ll-action list --output json` and asserts the schema (`{name, description, ...}` for each skill) so the discovery surface can't silently drift when `ll-action`'s output format changes.

### Risk mitigation — failure-mode coverage

These map onto specific failure modes the handler implementation must swallow gracefully. The plan's `run_subprocess` (plan.md:194-206) currently does only happy-path JSON envelope construction.

- **`subprocess.TimeoutExpired`** — the timeouts (300s / 600s) will fire for any real loop. The handler must catch this, kill the child, and return a structured "timed out, here's the partial stdout, poll via `ll_loop_status`" payload. For loops launched with `--background`, the right pattern is to *not* wait at all — fork the daemon, return the instance ID, never set a Python-side timeout.
- **`ll-action` exits non-zero with NDJSON on stderr.** Default output mode is `stream-json` (action.py:225). If a Hermes handler accidentally omits `--output json`, the subprocess output is event-stream NDJSON, not a JSON object. Plan should specify "always pass `--output json` for batched calls; reserve streaming for surfaces that can render incremental events."
- **Multiple running instances of the same loop name.** `cmd_status` and `cmd_stop` already aggregate (`lifecycle.py:159-229`, `247-303`). Hermes handlers need to decide: surface all of them, or require an `instance_id` disambiguator. Recommend: tool returns the array as-is and lets the model pick.
- **Stale `.pid` files** — `cmd_status` handles dead PIDs (line 218-222: "PID: N (not running - stale PID file)"). The tool should surface this cleanly rather than treating it as success.
- **Stale `.lock` files** — `cmd_stop` has a recovery path for orphaned locks held by live unrelated PIDs (`lifecycle.py:250-276`). Hermes should not duplicate this; just shell out and let `ll-loop` handle it.
- **Dirty working tree** (Open Question 5). `--worktree` sidesteps this. Mitigation: default `worktree=true` for any tool call originating from a non-interactive surface (cron, webhook, subagent). Make `worktree=false` an explicit override.
- **Multi-repo ambiguity error path.** Plan step 4 of resolution says "error". The error should be structured (`{"error": "ambiguous_repo", "registered": [...], "hint": "pass repo= or /project bind"}`) so the model can recover without re-prompting the user. Worth specifying in the schema.

### Loop ergonomics worth surfacing in Hermes

- **`--queue` flag** for scope-conflict serialization (Gap 6). Confirmed at `scripts/little_loops/cli/loop/__init__.py:148-150`.
- **`on_handoff: spawn`** appears on exactly **34** of the 50 built-in loops (confirmed with `grep -l "on_handoff: spawn" scripts/little_loops/loops/*.yaml | wc -l = 34`). The plan says "more than 35" — this is inaccurate; correct phrasing is "at least 34." The raw `loops/` tree grep returns 36 because it also hits `lib/apo-base.yaml` and `oracles/oracle-capture-issue.yaml`. Confirmed in `harness-optimize.yaml`, `autodev.yaml`, `docs-sync.yaml`, `general-task.yaml`, and 30 more. Hermes can treat "safe to delegate long-duration" as the default assumption for most built-in loops.
- **Fragment libraries.** `scripts/little_loops/loops/lib/` contains 5 files: `common.yaml`, `cli.yaml`, `benchmark.yaml`, `apo-base.yaml`, `score-plan-quality.yaml`. Plan mentions the first three correctly; `apo-base.yaml` and `score-plan-quality.yaml` are additional.
- **Oracles.** `loops/oracles/` contains separate evaluator-only YAMLs (e.g. `oracle-capture-issue.yaml`) — not full loops. These 1+ files are excluded from the 50 built-in count.
- **`ll-loop list --builtin`** vs project `.loops/`. The plan's `ll_loop_list` description doesn't say where loops come from. Reality: built-ins shipped in the package + project-local `.loops/<name>.yaml` overrides. Tool description should mention both so the model knows it can suggest "install this built-in to customize" via `ll-loop install <name>`.
- **`ll-action capabilities` + `ll-action list`** — the check_fn should use both: `capabilities` for the binary/host check (only accepts `--output json`) and `list` for the skill catalog (also `--output json` only). Do NOT rely on `capabilities` alone for skill discovery (Gap 10).
- **`rn-plan.yaml`** (used in Flow 6) has no declared `scope:` — defaults to whole-project lock, same as `harness-optimize`. Two whole-project-scope loops on the same repo will conflict unless `--queue` is passed or they run in separate repos.
- **`--quiet` flag on `ll-loop run`** is unmentioned in the plan but highly relevant to cron/subagent contexts (`--quiet` suppresses progress output). Consider adding to the `ll_loop_run` tool schema.

---

## Addendum: Third-Pass Findings (2026-05-18)

This pass verifies the *current* plan.md (post prior-pass updates) against the live codebase. Most prior gaps (0–13) have been resolved in the updated plan. New findings below.

### Prior Gaps Now Resolved in Current Plan

- **Gap 0** (`--worktree`/`--background` mutual exclusivity): Flow 2 now uses `background=true` only; Flow 6 uses `worktree=true` only. R5 explicitly documents the mutual-exclusivity constraint with the CLI citation `run.py:199-200`. ✓
- **Gap 1** (`ll-loop status`/`stop` require loop name): Tool schemas now use `loop_name` as required param. ✓
- **Gap 2** (`ll-action` invocation syntax): Handler now correctly builds `["ll-action", "invoke", skill, "--output", "json", "--timeout", N]`. ✓
- **Gap 3** (`stream-json` default): R2 explicitly addresses this; all handlers use `--output json`. ✓
- **Gap 4** (evaluator cost claim): Plan now correctly states most loops are deterministic with near-zero LLM cost per iteration. ✓
- **Gap 5** (`max_iterations` snake→kebab translation): `flag_map = {"max_iterations": "max-iterations", ...}` in `run_ll_loop()`. ✓
- **Gap 6** (`--queue` flag): Documented in R4 and the `ll_loop_run` tool schema. ✓
- **Gap 7** (`harness-optimize` whole-project scope): Flow 6 context strings explicitly warn about this. ✓
- **Gap 8** (Instance ID example): Plan now uses `harness-optimize-20260518T214700`. ✓
- **Gap 9** (`resolve_host()` non-goal): In Non-Goals section with path citation. ✓
- **Gap 10** (`capabilities` ≠ skill catalog): `check_fn` now uses two calls: `capabilities` (binary check) + `list` (skill catalog). ✓
- **Gap 11** (`ll-loop history` requires loop name): Tool schema has `loop_name` required. ✓
- **Gap 12** (worktree path): Plan now says `{project_root}/.worktrees/`. ✓
- **Gap 13** (branch format `<YYYYMMDD>-<HHMMSS>-<loop-name>`): Correctly documented in R5. ✓

### New Gaps in Current Plan Version

**N1: `run_ll_action` handler passes `--args` incorrectly for multi-key args.**
The handler builds:
```python
for key, value in args.items():
    cmd_parts.extend(["--args", f"{key}={value}"])
```
This produces `--args key1=val1 --args key2=val2 ...`. The `ll-action invoke` CLI declares `--args` with `nargs="+"` (`action.py:209-214`) and *no* `action="append"`. With `nargs="+"`, each re-occurrence of `--args` overwrites the previous — only the last key-value pair reaches the skill. Fix: collect all args first and emit a single `--args` flag:
```python
skill_args = [f"{k}={v}" for k, v in args.items() if k not in skip_keys and v is not None]
if skill_args:
    cmd_parts.extend(["--args"] + skill_args)
```

**N2: Contradictory `rn-plan` claims within the plan.**
- Line 448 (correct): "rn-plan has no `on_handoff:` declaration and defaults to `pause`"
- Line 583 (incorrect): "rn-plan *declares* on_handoff: pause (not spawn)"

`rn-plan.yaml` has no `on_handoff` field at all (`grep` returns no matches). It defaults to `"pause"` per `fsm/schema.py:808`. Line 583's word "declares" is factually wrong. Recommend changing to: "rn-plan has no `on_handoff:` declaration (defaults to `pause`, not `spawn`)..."

**N3: `ll-loop list` has `--category` and `--label` filters not in `ll_loop_list` tool schema.**
`__init__.py:197-210` adds `--category <name>` and `--label <label>` (repeatable) to the `list` subparser. These allow filtering to a single category (e.g., `apo`, `harness`) or a label tag. Useful for Hermes users doing "list all harness loops" without parsing the full catalog. Recommend adding optional `category: string` and `labels: [string]` to the `ll_loop_list` tool schema.

**N4: `ll-loop list --json` `built_in` field is conditionally absent (not always `false`).**
From `info.py:170-171`, `built_in: True` is only added to a JSON item when the loop is a built-in. For project-local loops, the key is *absent* (not `false`). Hermes handler code reading the catalog should treat a missing `built_in` key as `false`, not fail on its absence.

**N5: `ll-action list --output json` — `--output` is redundant but harmless.**
The `list` subparser accepts only `--output json` with `json` as the default (`action.py:250-256`). Passing `--output json` is correct but the flag is a no-op (no other mode exists for `list`). The plan's repeated `ll-action list --output json` is valid; just worth noting it cannot be `--output stream-json` unlike `invoke`.

**N6: `ll-loop simulate` also supports `--max-iterations`.**
`__init__.py:340-344` adds `--max-iterations/-n` to the `simulate` subparser (overrides loop's default, capped to 20 by the simulator). Not in the plan's `ll_loop_simulate` tool schema. Low priority but useful for Hermes to limit simulation length.

### Additional Verified Detail

- **`svg-textgrad.yaml`** is the *only* loop that **explicitly** sets `on_handoff: pause`. The other 15 non-spawn loops (including `rn-plan`) have no `on_handoff` field and default to `"pause"`. The plan's count of 34 spawn loops is correct; the phrasing "rn-plan *declares* on_handoff: pause" (line 583) is the only inaccuracy.

- **`ll-loop list` JSON confirmed**: exactly `{name, path, category, labels}` for project loops and `{name, path, category, labels, built_in: true}` for built-ins. No `description` in either case. `info.py:161-173`. ✓

- **58 skills confirmed**: `skills/*/SKILL.md` glob returns exactly 58 files. `ll-action list --output json` returns 58 entries. ✓

- **`resolve_host()` at `scripts/little_loops/host_runner.py:751`**: confirmed. ✓

---

## Addendum: Second-Pass Findings

### Corrected counts and verified details

- **`on_handoff: spawn` count**: verified at 34 main loops (see correction above in Loop ergonomics).
- **`rn-plan` `on_handoff` default**: `rn-plan.yaml` has no `on_handoff:` declaration → defaults to `pause` (`fsm/schema.py:808`). Plan Flow 6 is safe because the subagent itself handles continuity, but `rn-plan` is **not** a spawn loop.
- **Worktree branch name format confirmed**: `run.py:301-303` uses `strftime("%Y%m%d-%H%M%S")` and `re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)`. Example: `20260518-214700-harness-optimize`. This is **different** from the instance ID format `harness-optimize-20260518T214700` — the branch uses leading date, dashes throughout, no `T`; the instance ID leads with the loop name and uses `T` as the date/time separator.
- **`.log` file is background-only**: the plan says "five files per instance" unconditionally. The `.log` file at `.loops/.running/<instance_id>.log` is written only by `run_background()` (`_helpers.py:267`). Foreground runs have four files only (`.state.json`, `.events.jsonl`, `.lock`, `.pid`).
- **Queue entries in `.loops/.queue/`, not `.running/`**: `run.py:238-251` writes `<uuid>.json` queue files under `.loops/.queue/`. The plan describes waiting behavior without referencing this directory. Plan references to `.loops/.running/` for lock state are correct; queue state is a separate directory.

### New items not previously documented

- **`ll-loop simulate --scenario` automation** (`__init__.py:335-338`): choices `all-pass`, `all-fail`, `all-error`, `first-fail`, `alternating` skip interactive prompts. Essential for non-interactive Hermes contexts — expose as optional `scenario` param on `ll_loop_simulate` tool schema.
- **`ll-loop history <loop_name> [run_id]`** optional second positional (`__init__.py:271-309`): without `run_id` → lists archived runs (status/duration); with `run_id` → shows full event log including verdicts. The `ll_loop_history` Hermes tool schema should add optional `run_id: string` to allow event-level drill-down from messaging surfaces.
- **`ll-loop list` JSON excludes description** (`info.py:162-174`): JSON output fields are `{name, path, category, labels, built_in}` — no `description`. To get descriptions, use `ll-action list --output json` instead (returns `{name, description}`). Hermes `ll_loop_list` returns paths/categories but not human-readable descriptions.
- **`ll-loop test` subcommand** (`__init__.py:311-324`): single-iteration dry-run with exit-code injection (`--exit-code N`). Not in the plan's tool table. Useful for Hermes users who want to verify a loop is wired correctly before running it for real.
- **`ll-action list` depends on plugin root discovery**: `action.py:49-52` calls `_find_plugin_root()` to locate `skills/*/SKILL.md`. If the little-loops package is installed as a pip package but the plugin root can't be found (e.g., Claude Code plugin not registered), `ll-action list` exits 0 but returns `[]`. The `check_fn` Phase 2 acceptance test should assert `len(skills) > 0`, not just `exit_code == 0`.
- **Queue entry cleanup for dead PIDs** (`_helpers.py:73-100`): `_is_earliest_waiter` proactively removes queue entries from dead PIDs (BUG-1360). Stale queue files from crashed Hermes subagents that were waiting on `--queue` are cleaned up automatically. No Hermes-side recovery needed for this failure mode.
- **`ll-loop list --status` filter**: beyond `--running`, `ll-loop list --status interrupted` (etc.) can narrow to specific loop statuses (`awaiting_continuation`, `interrupted`, `running`). Useful for Hermes "what needs resuming?" queries.
- **`ll-loop run --builtin`** (`__init__.py:165-169`): bypasses project `.loops/` lookup and forces loading from the built-in package loops. Expose as optional `builtin: boolean` on `ll_loop_run` so Hermes can run stock loops even on repos that override built-in names.
