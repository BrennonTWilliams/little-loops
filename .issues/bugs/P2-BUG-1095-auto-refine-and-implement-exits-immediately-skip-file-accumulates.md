---
discovered_date: 2026-04-13
discovered_by: capture-issue
---

# BUG-1095: auto-refine-and-implement exits immediately after skip file accumulates

## Summary

The `auto-refine-and-implement` loop exits immediately on every run once its skip file (`.loops/tmp/auto-refine-and-implement-skipped.txt`) has accumulated skipped issue IDs from a prior run. The file is never cleared between runs, so `ll-issues next-issue --skip "$SKIPPED"` returns nothing (exit code 1), routing the loop to the `done` terminal state without processing any issues.

## Current Behavior

After a first full run that skips any issues:

1. Skipped IDs are written to `.loops/tmp/auto-refine-and-implement-skipped.txt`
2. On the next run, `get_next_issue` reads the accumulated skip list
3. All active issues are in the skip list → `ll-issues next-issue --skip` returns nothing
4. Loop routes to `done` immediately — no issues are processed

The bug is dormant until at least one issue has been skipped; once any ID accumulates, the loop becomes permanently stuck on subsequent runs.

## Expected Behavior

Each invocation of `ll-loop run auto-refine-and-implement` should start with a fresh skip file, processing the full backlog in priority order. Implemented issues are already in `completed/` and won't be returned by `ll-issues next-issue` regardless of the skip list.

## Root Cause

**File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`

The loop's `initial` state is `get_next_issue`. There is no `init` state to truncate session-scoped temp files before the run begins. The skip file persists across invocations.

```yaml
# Current — no init state
initial: get_next_issue
```

The skip file was designed for within-run deduplication (avoid re-processing a decomposed parent in the same session), but it also gates the very first action of the next run.

## Proposed Solution

Add an `init` state before `get_next_issue` that truncates the skip file and impl queue:

```yaml
initial: init

states:
  init:
    action: |
      mkdir -p .loops/tmp
      : > .loops/tmp/auto-refine-and-implement-skipped.txt
      : > .loops/tmp/auto-refine-and-implement-impl-queue.txt
    action_type: shell
    next: get_next_issue
```

This is safe because:
- Implemented issues are in `completed/` — `ll-issues next-issue` never returns them
- Decomposed parents should also be in `completed/` (see BUG-1096); fix #2 is a prerequisite for this fix to be fully correct
- Failed-refinement issues get a fresh attempt on each run (desirable)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — add `init` state, change `initial`

### Dependent Files
- `.loops/tmp/auto-refine-and-implement-skipped.txt` — cleared on each run start
- `.loops/tmp/auto-refine-and-implement-impl-queue.txt` — cleared on each run start
- BUG-1096 (`recursive-refine` decomposed parents not moved to `completed/`) — should be fixed first so cleared skip file does not cause re-decomposition

### Tests
- Verify loop processes at least one issue after a prior run that accumulated skipped IDs
- Verify loop does not re-process implemented issues (they are in `completed/`)

## Implementation Steps

1. In `auto-refine-and-implement.yaml`, change `initial: get_next_issue` to `initial: init`
2. Add `init` state (before `get_next_issue`) that truncates both temp files with `: >`
3. Confirm BUG-1096 is also fixed so decomposed parents are in `completed/` before this runs
4. Run the loop twice: first run should process issues, second run should pick up any new issues created by decomposition, not exit immediately

## Impact

- **Priority**: P2 — Loop is functionally broken after first use; silently does nothing
- **Effort**: Minimal — Two-line YAML change
- **Risk**: Low — Additive state; no logic changes to processing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `auto-refine-and-implement`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6681d3d-2446-482f-83ae-c425d516d2ac.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P2
