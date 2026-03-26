---
discovered_date: "2026-03-26"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-890: Add /ll:cleanup-loops Skill for Stuck/Failed Loop Management

## Summary

Create a new `/ll:cleanup-loops` skill that finds running loops via `ll-loop list --running`, investigates their status, identifies stuck or stale loops, kills any associated processes, cleans them up, and for stuck/failed loops investigates the state file to report where the loop got stuck and what went wrong.

## Current Behavior

There is no dedicated tool for diagnosing or cleaning up stuck or stale `ll-loop` processes. Users must manually run `ll-loop list --running`, inspect individual loop statuses, find and kill PIDs, and dig through state files to understand failures. This is error-prone and time-consuming, especially when a loop is stuck mid-state after a crash or interrupt.

## Expected Behavior

Running `/ll:cleanup-loops` should:
1. Run `ll-loop list --running` to enumerate all currently running loops
2. Run `ll-loop status <loop>` on each to assess their state
3. Identify loops that are stuck (long-running, no progress) or stale (process dead but state file unclean)
4. Kill any live processes for stuck/stale loops and clean them up via `ll-loop stop`
5. For each cleaned-up loop, inspect its state file to identify where it got stuck and what went wrong, then present a clear summary to the user

## Motivation

Stuck loops are a recurring operational hazard: a loop crashes mid-state, the state file is dirty, and the next run either fails or replays from a bad state. Currently there is no skill for this — users have to manually piece together the diagnosis. A dedicated skill reduces friction, surfaces root causes, and prevents repeated failures.

## Use Case

A developer notices their terminal has been idle for 30 minutes. They run `/ll:cleanup-loops` and discover two loops that have been "running" for hours with no activity — one stuck in a `waiting` state because its Claude subprocess exited without updating state, and one with a dead PID whose lock file was never cleaned. The skill kills both, removes the stale state, and tells the developer exactly which state each loop was stuck in and the last event that was recorded before the failure.

## Proposed Solution

Follow the pattern of `/ll:cleanup-worktrees` (`skills/cleanup-worktrees/`): a skill that shells out to the CLI tools, interprets results, and interacts with the user.

**Key steps:**

```bash
# Step 1: Discover running loops
ll-loop list --running --json

# Step 2: For each loop, get detailed status
ll-loop status <loop-name> --json

# Step 3: Heuristics for "stuck" classification
# - Process no longer alive (kill -0 $PID fails)
# - Loop has been in same state for > N minutes (compare updated_at to now)
# - Status is "interrupted" or "awaiting_continuation" with a dead PID

# Step 4: Stop and clean up
ll-loop stop <loop-name>

# Step 5: Inspect state file for root cause
# State files live in .loops/state/<loop-name>*.json or similar
```

The skill should present a summary table of discovered loops with their status, then prompt the user to confirm cleanup before killing anything.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`ll-loop list --running --json` behavior:** Returns ALL state files in `.loops/.running/` (not just `status=running`). The `--running` flag name is misleading — it calls `list_running_loops()` which globs `*.state.json` without status filtering. The skill must filter status itself (see "Stuck heuristics" below). Note: `ll-loop list --running --status running --json` can be used to get only truly-running loops (applies filter at `info.py:51-52`), but cleanup needs to also surface `interrupted`/`awaiting_continuation` loops with dirty state — so use `--running --json` without `--status` and filter manually.

**`ll-loop stop` limitation:** `cmd_stop` (`lifecycle.py:86`) returns exit code 1 if `state.status != "running"`. For loops already in `interrupted`, `awaiting_continuation`, `failed`, or `timed_out` status with dirty state files, the skill must clean up manually: remove the `.pid` file (if present) and either call `ll-loop stop` (which will only update status to `interrupted`) or directly archive the state. Alternatively, for non-running stale loops, the skill can skip `ll-loop stop` and just report them without killing.

**State file schema (`LoopState.to_dict()`, `persistence.py:96-116`):**
| Field | Type | Stuck-detection use |
|---|---|---|
| `loop_name` | str | Loop identifier |
| `current_state` | str | Where the loop was stuck |
| `status` | str | `"running"`, `"interrupted"`, `"awaiting_continuation"`, `"failed"`, `"timed_out"` |
| `updated_at` | str (ISO 8601) | Staleness: compare to wall clock |
| `accumulated_ms` | int | Total elapsed time |
| `last_result` | object\|null | Last evaluation verdict and details |
| `continuation_prompt` | str | Only when `status == "awaiting_continuation"` |
| `retry_counts` | object | Map of state name → retry count (omitted from JSON when empty) |
| `active_sub_loop` | str\|null | Name of active nested sub-loop (omitted from JSON when null) |

**`ll-loop status <name> --json`** adds a `pid` field (int|null) from `.loops/.running/<name>.pid`. This is the canonical way to get the PID without reading the file directly.

**Stuck heuristics (precise):**
- **Dead process**: `pid` is non-null AND `os.kill(pid, 0)` raises `ESRCH`. The skill can detect this by checking `ll-loop status <name> --json` output: human-readable prints `"(not running - stale PID file)"`.
- **Stale state**: `updated_at` delta > threshold (suggest 15 minutes default) AND `status == "running"`.
- **Abandoned handoff**: `status == "awaiting_continuation"` with stale `updated_at`.
- **Unclean interrupt**: `status == "interrupted"` with a `.pid` file still present.

**Directory structure confirmed:**
```
.loops/
├── .running/
│   ├── <name>.state.json    # current state (JSON)
│   ├── <name>.events.jsonl  # event stream (append-only; last N lines = root cause)
│   ├── <name>.pid           # PID when running in background (optional)
│   └── <name>.lock          # concurrency scope lock (optional)
└── .history/
    └── <name>/<run-id>/
        ├── state.json
        └── events.jsonl
```

**Root cause from events file:** `.loops/.running/<name>.events.jsonl` contains the live event stream — the last few lines before a failure are the most useful for diagnosing what went wrong. Use `tail -20 .loops/.running/<name>.events.jsonl` in the skill's report.

**Plugin registration:** Skills are auto-discovered from the `./skills` directory (`plugin.json:20`). No manual registration needed — just create `skills/cleanup-loops/SKILL.md`.

## Integration Map

### Files to Modify
- N/A — new skill only

### New Files to Create
- `skills/cleanup-loops/SKILL.md` — skill definition
- `skills/cleanup-loops/references/` — supporting reference docs (if needed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` (line 41); `ll-loop list --running --json` globs `.loops/.running/*.state.json` and returns ALL state files regardless of live status; JSON output is `[LoopState.to_dict(), ...]`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status` (line 36) and `cmd_stop` (line 86); `cmd_status --json` adds a `pid` field (int|null) from the `.pid` file; `cmd_stop` only succeeds if `state.status == "running"` (returns exit code 1 otherwise)
- `scripts/little_loops/fsm/persistence.py` — `LoopState` dataclass (line 55), `to_dict()` (line 96), `list_running_loops()` (line 499); state files at `.loops/.running/<loop-name>.state.json`, events at `.loops/.running/<loop-name>.events.jsonl`
- `scripts/little_loops/fsm/concurrency.py` — `_process_alive(pid)` (line 26) uses `os.kill(pid, 0)`; lock files at `.loops/.running/<loop-name>.lock`

### Similar Patterns
- `commands/cleanup-worktrees.md` — primary structural pattern: list → check existence → dry-run gate → iterate + clean → summary report (no `AskUserQuestion`; uses `dry-run` arg as the gate)
- `skills/analyze-loop/SKILL.md` — `ll-loop list --running --json` parsing, `AskUserQuestion` confirm-before-act pattern, LoopState field usage
- `skills/review-loop/SKILL.md` — `AskUserQuestion` loop-picker format, `--dry-run` flag pattern

### Tests
- N/A — skill is prose/instructions for Claude; behavior tested manually

### Documentation
- `CLAUDE.md` — add `cleanup-loops` to the Automation & Loops command list

### Configuration
- N/A

## Implementation Steps

1. Read `commands/cleanup-worktrees.md` and `skills/analyze-loop/SKILL.md` for structural reference (note: `skills/cleanup-worktrees/` does not exist; the pattern is in `commands/`)
2. Read `scripts/little_loops/cli/loop/info.py:41-78` (`cmd_list`) and `scripts/little_loops/cli/loop/lifecycle.py:36-140` (`cmd_status`, `cmd_stop`) to confirm exact JSON field names before writing skill instructions
3. State files are at `.loops/.running/<name>.state.json`; events at `.loops/.running/<name>.events.jsonl` — the skill should `tail` the events file for root cause reporting
4. Write `skills/cleanup-loops/SKILL.md` covering: list all loops → assess stuck status (dead PID, stale `updated_at`, `status` check) → confirm with user → `ll-loop stop` for `status=running` loops / manual PID cleanup for others → tail events file for each cleaned loop → summary report
5. Update `CLAUDE.md` Automation & Loops line to add `cleanup-loops`^ (currently: `` `create-loop`^, `loop-suggester`, `review-loop`^, `analyze-loop`^, `workflow-automation-proposer`^ `` at line 56)

## API/Interface

```bash
# No arguments required — operates on all running loops
/ll:cleanup-loops

# Underlying CLI commands used internally
ll-loop list --running [--json]
ll-loop status <loop-name> [--json]
ll-loop stop <loop-name>
```

## Acceptance Criteria

- [x] `/ll:cleanup-loops` is a valid invocable skill
- [x] Skill lists all running loops via `ll-loop list --running`
- [x] Skill calls `ll-loop status` on each running loop and identifies stuck/stale ones
- [x] Stuck heuristics cover: dead PID, state stale for > threshold time, interrupted/awaiting states
- [x] Skill kills processes and cleans state for confirmed stuck loops
- [x] For each cleaned loop, skill reports the state where it got stuck and the last recorded event
- [x] User confirmation is required before any destructive action (kill / stop)
- [x] Skill handles the case where no loops are running (graceful no-op message)
- [ ] `CLAUDE.md` updated to list `cleanup-loops` under Automation & Loops — BLOCKED: `.claude/CLAUDE.md` is protected from automated edits; update manually

## Impact

- **Priority**: P3 - Useful operational tool; not blocking but saves time when loops get stuck
- **Effort**: Small - Skill only (prose instructions); no Python code changes needed
- **Risk**: Low - New skill file; no changes to existing code paths
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `automation`, `captured`

## Resolution

- Created `skills/cleanup-loops/SKILL.md` (285 lines) with 8-step workflow: enumerate loops → gather status → classify by stuck heuristics → display summary → confirm via AskUserQuestion → execute cleanup → inspect events for root cause → final report
- Supports `--dry-run` and `--threshold N` arguments
- Follows analyze-loop AskUserQuestion pattern and cleanup-worktrees structural pattern
- `.claude/CLAUDE.md` update blocked (protected file); must be updated manually: add `` `cleanup-loops`^ `` to the Automation & Loops line

## Session Log
- `/ll:manage-issue` - 2026-03-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-03-26T16:50:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1aa8b9f-1117-46b9-8eb0-95e808a743b7.jsonl`
- `/ll:refine-issue` - 2026-03-26T16:47:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/733ad6a6-f1d6-41f5-99a9-700614de197e.jsonl`
- `/ll:confidence-check` - 2026-03-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e645e05-6d7d-40dd-a939-2c506647b0d0.jsonl`
- `/ll:refine-issue` - 2026-03-26T16:38:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e645e05-6d7d-40dd-a939-2c506647b0d0.jsonl`
- `/ll:format-issue` - 2026-03-26T16:33:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e645e05-6d7d-40dd-a939-2c506647b0d0.jsonl`
- `/ll:capture-issue` - 2026-03-26T16:27:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a00d6993-c1c2-499f-9104-60507f2409e4.jsonl`

---

## Status

**Completed** | Created: 2026-03-26 | Resolved: 2026-03-26 | Priority: P3
