---
discovered_date: "2026-03-26"
discovered_by: capture-issue
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
# - Loop has been in same state for > N minutes (compare last_updated to now)
# - Status is "interrupted" or "awaiting_continuation" with a dead PID

# Step 4: Stop and clean up
ll-loop stop <loop-name>

# Step 5: Inspect state file for root cause
# State files live in .loops/state/<loop-name>*.json or similar
```

The skill should present a summary table of discovered loops with their status, then prompt the user to confirm cleanup before killing anything.

## Integration Map

### Files to Modify
- N/A — new skill only

### New Files to Create
- `skills/cleanup-loops/SKILL.md` — skill definition
- `skills/cleanup-loops/references/` — supporting reference docs (if needed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/list.py` — `ll-loop list --running` output format
- `scripts/little_loops/cli/loop/status.py` — `ll-loop status` output format
- `scripts/little_loops/cli/loop/stop.py` — `ll-loop stop` behavior

### Similar Patterns
- `skills/cleanup-worktrees/SKILL.md` — same pattern: shell out, identify stale items, confirm + clean up
- `skills/analyze-loop/SKILL.md` — loop state file inspection for root cause analysis

### Tests
- N/A — skill is prose/instructions for Claude; behavior tested manually

### Documentation
- `CLAUDE.md` — add `cleanup-loops` to the Automation & Loops command list

### Configuration
- N/A

## Implementation Steps

1. Read `skills/cleanup-worktrees/SKILL.md` and `skills/analyze-loop/SKILL.md` for structural reference
2. Investigate `ll-loop list --running` and `ll-loop status` output schemas (run with `--json` to confirm)
3. Locate where loop state files are written to understand what to inspect for root cause
4. Write `skills/cleanup-loops/SKILL.md` covering the full diagnosis → confirm → cleanup → report flow
5. Register the skill in `CLAUDE.md` under Automation & Loops

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

- [ ] `/ll:cleanup-loops` is a valid invocable skill
- [ ] Skill lists all running loops via `ll-loop list --running`
- [ ] Skill calls `ll-loop status` on each running loop and identifies stuck/stale ones
- [ ] Stuck heuristics cover: dead PID, state stale for > threshold time, interrupted/awaiting states
- [ ] Skill kills processes and cleans state for confirmed stuck loops
- [ ] For each cleaned loop, skill reports the state where it got stuck and the last recorded event
- [ ] User confirmation is required before any destructive action (kill / stop)
- [ ] Skill handles the case where no loops are running (graceful no-op message)
- [ ] `CLAUDE.md` updated to list `cleanup-loops` under Automation & Loops

## Impact

- **Priority**: P3 - Useful operational tool; not blocking but saves time when loops get stuck
- **Effort**: Small - Skill only (prose instructions); no Python code changes needed
- **Risk**: Low - New skill file; no changes to existing code paths
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `automation`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-26T16:27:27Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a00d6993-c1c2-499f-9104-60507f2409e4.jsonl`

---

## Status

**Open** | Created: 2026-03-26 | Priority: P3
