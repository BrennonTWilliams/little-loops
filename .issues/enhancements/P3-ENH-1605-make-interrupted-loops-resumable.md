---
id: ENH-1605
title: "Make interrupted loops resumable"
type: ENH
priority: P3
status: open
captured_at: "2026-05-18T05:35:25Z"
discovered_date: "2026-05-18"
discovered_by: capture-issue
---

# ENH-1605: Make interrupted loops resumable

## Summary

`ll-loop stop` and clean Ctrl-C (SIGINT) write `status = "interrupted"`, which `ll-loop resume` currently refuses to pick up. Only `"running"` and `"awaiting_continuation"` are treated as resumable. This creates a counterintuitive inversion: a hard kill/crash leaves a loop in `"running"` status (resumable), while a graceful stop produces `"interrupted"` (not resumable). The fix is to add `"interrupted"` to the resumable-status set so a clean pause is at least as recoverable as a crash.

## Current Behavior

In `scripts/little_loops/fsm/persistence.py:607`:

```python
if state.status not in ("running", "awaiting_continuation"):
    return None  # not resumable
```

`ll-loop stop` and first-Ctrl-C write `status = "interrupted"` and then archive the run. `ll-loop resume` silently declines to resume it.

A crash/SIGKILL leaves `status = "running"` on disk, which IS resumable — meaning the accidental path is more recoverable than the intentional one.

## Expected Behavior

`ll-loop resume <name>` should resume a loop that was stopped via `ll-loop stop` or Ctrl-C, re-entering the FSM at `current_state` exactly as it does for `"running"` and `"awaiting_continuation"` loops.

## Motivation

Users who stop a loop intentionally (to free resources, handle a distraction, or end a session) should be able to pick it up later. The current behavior punishes clean shutdowns. The graceful stop is the right path — it should be the most recoverable one.

## Proposed Solution

1. Add `"interrupted"` to the resumable-status check in `PersistentExecutor.resume()` (`persistence.py:607`).
2. Stop archiving the run in `PersistentExecutor.run()` when `terminated_by == "signal"` — or defer archiving until after the user has had a chance to resume. Currently `persistence.archive_run()` is called immediately after writing `"interrupted"`, which moves the state file to `.loops/.history/` and makes it invisible to `_find_instances()` (which only scans `.loops/.running/`).
3. Optionally surface `"interrupted"` loops in the `ll-loop list` output with a distinct `[paused]` label to hint that `resume` is available.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.resume()` line 607 (resumable-status check), `PersistentExecutor.run()` (archive-on-signal logic near line 569)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()` may need to skip or defer `archive_run()` so the state file stays in `.loops/.running/` for `_find_instances()` to find

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `_find_instances()` then `executor.resume()`
- `scripts/little_loops/fsm/persistence.py` — `_reconcile_stale_runs()` treats `"interrupted"` as terminal; needs updating if we want stale interrupted runs kept longer

### Similar Patterns
- `"awaiting_continuation"` is already resumable and uses the same restore path — the interrupted resume follows the same code path

### Tests
- `scripts/tests/test_persistence.py` (or equivalent) — add test: stop a loop, assert `_find_instances()` returns it, assert `resume()` succeeds
- `scripts/tests/test_loop_lifecycle.py` — add test for the Ctrl-C → resume round-trip

### Documentation
- `docs/reference/API.md` — update status value table if it documents resumability
- Any `ll-loop` man page / help text that lists resumable statuses

### Configuration
- N/A

## Implementation Steps

1. Change the resumable-status guard in `PersistentExecutor.resume()` to include `"interrupted"`.
2. Stop calling `persistence.archive_run()` immediately after writing `"interrupted"` — either skip it entirely (archive only on explicit `ll-loop clear`) or move it to a separate cleanup command.
3. Update `_reconcile_stale_runs()` so it does not treat `"interrupted"` + dead-PID as stale (it should stay available for resume).
4. Run existing persistence tests; add new round-trip test.
5. Update help text / docs to reflect that interrupted loops are resumable.

## Scope Boundaries

**In scope:**
- Adding `"interrupted"` to the resumable-status set in `PersistentExecutor.resume()`
- Fixing archive timing so interrupted loops remain in `.loops/.running/` for `_find_instances()` to discover
- Updating `_reconcile_stale_runs()` to not treat `"interrupted"` + dead-PID as stale (keep available for resume)
- Optionally surfacing `"interrupted"` loops in `ll-loop list` with a `[paused]` label

**Out of scope:**
- Changing crash/SIGKILL recovery behavior (already handled via `"running"` status)
- Introducing new loop status values beyond adding `"interrupted"` to the resumable set
- Modifying FSM state-transition logic or execution behavior during the loop run
- Changing semantics of terminal statuses (`"completed"`, `"failed"`, `"cancelled"`)

## API/Interface

```python
# persistence.py — updated resumable check
RESUMABLE_STATUSES = {"running", "awaiting_continuation", "interrupted"}

def resume(self) -> ExecutionResult | None:
    state = self.persistence.load_state()
    if state is None or state.status not in RESUMABLE_STATUSES:
        return None
    ...
```

## Impact

- **Priority**: P3 - Quality-of-life fix; no data loss, but frustrating when discovered
- **Effort**: Small - Two-line logic change + archive-timing adjustment + tests
- **Risk**: Low - Additive change; existing resumable paths unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`fsm-loops`, `loop-lifecycle`, `captured`

## Status

**Open** | Created: 2026-05-18 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-18T05:38:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ddc6287-f781-4278-a8a4-03871998cfc3.jsonl`

- `/ll:capture-issue` - 2026-05-18T05:35:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a80e31cf-a675-4c97-bce5-05347c0aadf2.jsonl`
