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

little-loops runs **FSM-driven automation loops** — long-horizon, eval-gated workflows like `harness-optimize`, `docs-sync`, `deep-research`, `autodev`, and `rn-plan`. Each loop is a state machine with deterministic action+evaluate→route semantics and a single LLM call point per iteration. There are ~50 built-in loops spanning issue management, code quality, harness optimization, RL training, prompt optimization, planning, and research.

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
5. Zero changes to the `ll-*` CLI interface — Hermes wraps via subprocess; slash-command-only features are bridged through `ll-action`.

## Non-Goals

- little-loops does not become part of the Hermes codebase
- No new `ll-*` commands created specifically for Hermes
- No shared state format between Hermes sessions and little-loops loops
- **Hermes does not become a loop authoring environment.** Loop YAMLs are created via `/ll:create-loop` inside Claude Code; Hermes triggers and observes them.
- Level 3 shared abstractions (unified issue model, loop engine as Hermes primitive) are out of scope for v1

---

## Architecture

### Repo Registration (Option B)

A config-level mapping between human-friendly names and filesystem paths:

```yaml
# ~/.hermes/config.yaml
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

### Session-Scoped Project Binding (Option C)

A conversation-level "current project" that persists across turns. The model can switch projects mid-conversation, but defaults to the bound one.

**Mechanism:**
- Natural language: "I'm working on my-app today" → model detects intent, binds session
- Slash command: `/project my-app` (explicit)
- Implicit: if only one repo registered, auto-bind
- Override: any tool call with explicit `repo` parameter overrides the session binding

**Storage:** Session metadata (`session.metadata["little-loops-repo"]`). Not memory — this is ephemeral per conversation.

### Repo Resolution Logic

Every little-loops tool handler resolves the working directory through a priority chain:

```
1. Explicit `repo` parameter on the tool call (name or path)
2. Session binding (session metadata)
3. Single-repo fallback (only one registered → use it)
4. Error: "Multiple repos registered — specify which one or bind with /project"
```

### Tool Registration

Each high-value little-loops capability becomes a registered Hermes tool. Two routing paths exist:

- **Direct CLI:** Real `ll-*` executables (`ll-loop`, `ll-parallel`, `ll-auto`) are invoked via subprocess. This is the primary integration surface.
- **`ll-action` bridge:** Slash commands (`/ll:scan-codebase`, `/ll:manage-issue`, `/ll:commit`, ...) have no CLI counterpart, but `ll-action <skill>` (already shipped in little-loops' CLI surface at `scripts/little_loops/cli/`) exposes any `/ll:*` skill as a one-shot CLI with JSON-structured output. Hermes shells out uniformly.

**Tools (organized by tier):**

| Tier | Tool Name | CLI Command / Bridge | What It Does |
|------|-----------|----------------------|--------------|
| **Loops (primary surface)** | `ll_loop_run` | `ll-loop run <name>` | Execute an FSM loop (supports `--background`, `--worktree`, `--max-iterations`, `--dry-run`, `--context K=V`) |
|  | `ll_loop_list` | `ll-loop list` | Discover available loops in `.loops/` and built-ins |
|  | `ll_loop_status` | `ll-loop status` | Show running loops, current state, iteration count |
|  | `ll_loop_stop` | `ll-loop stop <instance>` | Halt a running loop |
|  | `ll_loop_resume` | `ll-loop resume <instance>` | Resume an interrupted loop from its persisted state |
|  | `ll_loop_history` | `ll-loop history` | Past loop runs with verdicts |
|  | `ll_loop_show` | `ll-loop show <name>` | Inspect a loop's FSM (states, transitions, schema) |
|  | `ll_loop_simulate` | `ll-loop simulate <name>` | Interactive dry-run — great for messaging surfaces |
|  | `ll_loop_validate` | `ll-loop validate <name>` | Validate loop YAML |
|  | `ll_loop_next` | `ll-loop next-loop` | Suggest a loop based on repo history |
| **Orchestration** | `ll_parallel` | `ll-parallel` | Fan out N workers in isolated worktrees (often used to parallelize loops over issues) |
|  | `ll_auto` | `ll-auto` | Sequential issue pipeline with auto-continuation |
| **Issue/sprint scaffolding (loop inputs)** | `ll_scan_codebase` | `ll-action scan-codebase` | Scan for issues that loops can consume |
|  | `ll_manage_issue` | `ll-action manage-issue` | Plan→implement→verify cycle |
|  | `ll_prioritize_issues` | `ll-action prioritize-issues` | Auto-assign P0–P5 priorities |
|  | `ll_verify_issues` | `ll-action verify-issues` | Test issue claims against code |
|  | `ll_sprint_create` | `ll-action create-sprint` | Create a sprint from curated issues |
|  | `ll_commit` | `ll-action commit` | Structured commit with issue linkage |
|  | `ll_open_pr` | `ll-action open-pr` | Open a PR with generated description |
|  | `ll_handoff` | `ll-action handoff` | Generate session continuation prompt |
|  | `ll_run_tests` | `ll-action run-tests` | Run project test suite |

**Toolset definition:**

```python
# In toolsets.py
"little-loops": {
    "description": "FSM-driven automation loops + issue/sprint scaffolding — trigger, schedule, monitor, and resume long-horizon coding workflows",
    "tools": [
        # Loops (primary)
        "ll_loop_run", "ll_loop_list", "ll_loop_status", "ll_loop_stop",
        "ll_loop_resume", "ll_loop_history", "ll_loop_show",
        "ll_loop_simulate", "ll_loop_validate", "ll_loop_next",
        # Orchestration
        "ll_parallel", "ll_auto",
        # Issue/sprint scaffolding (bridged via ll-action)
        "ll_scan_codebase", "ll_manage_issue", "ll_prioritize_issues",
        "ll_verify_issues", "ll_sprint_create", "ll_commit",
        "ll_open_pr", "ll_handoff", "ll_run_tests",
    ],
    "includes": ["terminal"]
}
```

**Availability gate (`check_fn`):** Tool appears only when `shutil.which("ll-loop")` AND `shutil.which("ll-action")` both return paths. Zero footprint if little-loops isn't installed.

### Handler Pattern

Two handler shapes — direct CLI and bridged via `ll-action`:

```python
def run_ll_loop(subcommand: str, args: dict, session_metadata: dict = None) -> str:
    """Direct: ll-loop <subcommand> [args] — primary integration surface."""
    cwd = resolve_repo(args, session_metadata)
    cmd_parts = ["ll-loop", subcommand]
    for flag, value in args.items():
        if flag in ("repo", "path"):
            continue
        if isinstance(value, bool) and value:
            cmd_parts.append(f"--{flag}")
        elif value is not None:
            cmd_parts.extend([f"--{flag}", str(value)])
    return run_subprocess(cmd_parts, cwd=cwd, timeout=300)


def run_ll_action(skill: str, args: dict, session_metadata: dict = None) -> str:
    """Bridged: ll-action <skill> — wraps /ll:* slash commands with JSON output."""
    cwd = resolve_repo(args, session_metadata)
    cmd_parts = ["ll-action", skill, "--json"]
    for flag, value in args.items():
        if flag in ("repo", "path"):
            continue
        if isinstance(value, bool) and value:
            cmd_parts.append(f"--{flag}")
        elif value is not None:
            cmd_parts.extend([f"--{flag}", str(value)])
    # Slash commands can take longer than direct CLI work
    return run_subprocess(cmd_parts, cwd=cwd, timeout=600)


def run_subprocess(cmd_parts, cwd, timeout):
    result = subprocess.run(
        cmd_parts, capture_output=True, text=True,
        cwd=cwd, timeout=timeout
    )
    return json.dumps({
        "success": result.returncode == 0,
        "output": result.stdout[-8000:],
        "errors": result.stderr[-2000:] if result.stderr else None,
        "exit_code": result.returncode,
        "repo": cwd
    })
```

### Tool Schema Example

```json
{
    "name": "ll_loop_run",
    "description": "Execute an FSM loop in a registered repo. Loops are state machines with action+evaluate→route semantics and a single LLM call point per iteration. Use --background for long-running loops (returns an instance ID you can poll with ll_loop_status). Use --worktree for isolation when the loop modifies files.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Loop name (e.g. docs-sync, harness-optimize, dead-code-cleanup, autodev). Use ll_loop_list to discover."
            },
            "repo": {
                "type": "string",
                "description": "Repo name (from config) or absolute path. Omit to use session-bound project."
            },
            "background": {
                "type": "boolean",
                "description": "Run as a daemon. Returns instance ID for later polling. Recommended for loops expected to take >2 minutes."
            },
            "worktree": {
                "type": "boolean",
                "description": "Run in an isolated git worktree (auto-cleanup on exit). Keeps the user's working tree clean."
            },
            "max_iterations": {
                "type": "integer",
                "description": "Override the loop's default max_iterations."
            },
            "dry_run": {
                "type": "boolean",
                "description": "Show the plan without executing."
            }
        },
        "required": ["name"]
    }
}
```

---

## Why Loops

FSM loops are the primitive that makes this integration worth building. They're not "one tool among many" — they're the load-bearing abstraction:

- **Action + Evaluate + Route.** Each state runs an action (shell command, slash command, or LLM prompt), evaluates the result with a deterministic or LLM evaluator, and routes to the next state. This cleanly separates "what happened?" from "where next?", making loops debuggable and resumable.
- **One LLM call point per iteration.** The `llm_structured` evaluator is the single LLM touchpoint; everything else is deterministic. Cost stays predictable (~$0.001/eval, 300–800ms latency), and loops can run for hours without runaway spend.
- **Persisted state.** `.loops/.running/<instance>.state.json` captures current state, iteration, captured variables, and last result. Loops can be interrupted, resumed, monitored, halted — essential for cross-surface triggering (start from Telegram, check status from Discord, resume from a cron job).
- **Sub-loop composition.** Loops invoke other loops via `loop:` + `context_passthrough`. `sprint-build-and-validate` calls `recursive-refine` as a sub-loop; `autodev` composes multiple smaller loops. Hermes inherits this composability for free.
- **Scope-based locking.** Loops declare `scope: ["docs/", "*.md"]`; overlapping scopes serialize automatically. Safe to trigger multiple loops on the same repo from different surfaces.
- **50+ built-in loops across 11 categories** — issue-management, code-quality, harness, evaluation, RL, APO (prompt optimization), planning, data, research, meta, optimization. Each one already works inside Claude Code; Hermes simply makes them reachable.

This is why Hermes integration is leverage, not duplication: every loop little-loops ever ships becomes a Hermes capability with no further work.

---

## User Flows

### Flow 1: Trigger a Loop from Telegram

```
User:  "I'm working on my-app today"
Hermes: Bound to my-app (/home/user/projects/my-app).

User:  "what loops are available?"
       → ll_loop_list()
       ← "12 loops: docs-sync, dead-code-cleanup, harness-optimize, autodev,
          fix-quality-and-tests, deep-research, ..."

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
                     background=true, worktree=true)
       ← "Launched harness-optimize as instance ho-2026-05-18-2147.
          Worktree: /tmp/ll-wt-ho-2026-05-18-2147. Poll with ll_loop_status."

(20 minutes later, from Discord)

User:  "how's harness-optimize going?"
       → ll_loop_status()
       ← "ho-2026-05-18-2147: iteration 7/20, state=evaluate_change,
          last_verdict=improved (score 0.83 → 0.86). ETA ~25 min."

(Later)

User:  "stop it, we have what we need"
       → ll_loop_stop(instance="ho-2026-05-18-2147")
       ← "Halted. Final score 0.86 (+0.03). Changes preserved in worktree."
```

### Flow 3: Overnight Cron Across Repos

```bash
hermes cron create "0 2 * * *" \
  --prompt "For each registered repo, run docs-sync and dead-code-cleanup
            in background with --worktree. In the morning, summarize:
            which loops improved state, which found nothing, which failed.
            Send the briefing to Telegram." \
  --toolsets little-loops,messaging
```

```bash
hermes cron create "0 7 * * 1-5" \
  --prompt "For each registered repo: ll_scan_codebase, then ll_loop_run
            autodev on the top P0 issue. Send a morning briefing with what
            was attempted and what landed." \
  --toolsets little-loops,messaging
```

### Flow 4: Simulate Before Committing

```
User:  "Show me what dead-code-cleanup would do on work-api without
        running it"
       → ll_loop_simulate(name="dead-code-cleanup", repo="work-api")
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
       → ll_scan_codebase()        # via ll-action
       → ll_prioritize_issues()    # via ll-action
       → ll_loop_run(name="autodev")  # consumes the prioritized issues
       ← "autodev: BUG-003 complete. Commit abc1234. Tests green. Want a PR?"

User:  "yes"
       → ll_open_pr()              # via ll-action
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
    context="Repo: my-app. Use --worktree."
  )
  delegate_task(
    goal="Run rn-plan on work-api for the v2-launch initiative",
    toolsets=["little-loops", "file", "terminal"],
    context="Repo: work-api. Use --worktree."
  )

Each subagent autonomously:
  1. ll_loop_run(name=<loop>, repo=<repo>, worktree=true)
  2. Polls ll_loop_status until terminal
  3. Returns summary to parent
  → Parent notifies user when both complete
```

---

## Implementation Phases

### Phase 1: Skill Pack (Week 1)

Ship a Hermes skill pack that wraps the highest-value loop commands via `terminal()` calls. No native tool registration. Gets something functional into users' hands immediately.

**Deliverables:**
- `SKILL.md` with repo resolution logic documented
- Individual skill files for: `ll-loop run/list/status/resume`, `ll-parallel`, `ll-auto`, then issue/sprint commands via `ll-action`
- Published to Hermes skills hub
- Installable via `hermes skills install little-loops`

**Value:** Proves the concept. Users can trigger loops from Hermes today. Feedback on the repo resolution UX.

### Phase 2: Native Toolset (Week 2–3)

Register tools in Hermes's tool registry with proper schemas. Repo config in `config.yaml`. Session binding via `/project` command or natural language.

**Deliverables:**
- `tools/little_loops_tool.py` — tool registrations + handlers (both `run_ll_loop` and `run_ll_action`)
- Toolset entry in `toolsets.py`
- Repo config schema in config defaults
- `/project` slash command
- Session binding logic
- `check_fn` availability gate — probes for both `ll-loop` and `ll-action`

**Value:** Native composability. The model autonomously chooses to use loops. Subagent and cron scoping works.

### Phase 3: Discovery and Polish (Week 4)

Auto-discovery of repos, better error messages, status reporting, loop discovery.

**Deliverables:**
- Auto-discovery: scan for `.ll/` directories on startup
- `/project list` — show registered repos + status
- `/project status` — show running loops + issue state for current repo
- `/loops` — list available loops in current repo (`.loops/`) plus built-ins
- Error surfacing when `ll-*` commands fail
- Output truncation and formatting for messaging platforms

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

  # Default timeout for ll-* commands (seconds)
  command_timeout: 300

  # Whether to auto-bind to the only registered repo on session start
  auto_bind_single: true
```

---

## Open Questions

1. **Loop run output streaming.** `ll-loop run` emits JSONL events that can run for hours. Should Hermes tail the events file and post incremental updates to the messaging surface, or only summarize on completion? Likely both — `--background` for fire-and-forget with polling, foreground for sub-minute loops.
2. **Loop concurrency on a single repo.** Loops use scope-based locking (`scope: ["docs/"]`). If Hermes triggers two loops with overlapping scope, the second blocks. Should `ll_loop_status` surface pending-on-lock state explicitly? Probably yes.
3. **Cron-triggered loops and worktrees.** Should cron jobs always run loops with `--worktree` for isolation? Default to yes — keeps the user's working tree clean and avoids surprises at next interactive session.
4. **Authentication.** `ll-*` commands may need git auth for push/PR operations. Does Hermes's existing auth cover this, or does the user need to set up git credentials separately?
5. **Repo health.** Should the tools detect uncommitted changes, dirty working trees, or merge conflicts before running a loop that mutates files? (Loops with `--worktree` sidestep this.)
6. **`/project` vs natural language.** Is a slash command worth adding to the Hermes command registry, or should this be handled entirely through the model's understanding of "switch to X"?

---

## Success Metrics

- A Hermes user can install little-loops, register a repo, and trigger a loop (e.g. `docs-sync`) from Telegram within 5 minutes
- Cron jobs successfully run nightly loops (`docs-sync`, `harness-optimize`, `dead-code-cleanup`) across multiple repos
- Subagents complete loop execution autonomously, including background loops with status polling
- At least one community-shared loop YAML is contributed for use with Hermes
- The integration generates at least 3 community posts / word-of-mouth mentions from Hermes users

---

## Related

- [[_Index|Little-Loops Project Index]]
- [[ll-harness CLI planning]]
- [[ll-loop parallelism tradeoffs]]

Up: [[_Index|Little-Loops]] | [[Personal/_Meta/MOC-Personal-Home|Personal Home]]
