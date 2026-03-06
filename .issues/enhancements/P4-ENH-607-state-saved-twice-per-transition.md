---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# ENH-607: `PersistentExecutor` writes state file twice per state transition

## Summary

`PersistentExecutor._handle_event` triggers `_save_state()` for `state_enter`, `route`, and `loop_complete` events. A single state transition emits both `route` and `state_enter` in sequence, causing two consecutive JSON serializations and file writes per transition. The `route` write is redundant because `state_enter` fires immediately after with the same `current_state` data.

## Current Behavior

Each state transition produces two `_save_state()` calls (one for `route`, one for `state_enter`). For a loop with 50 iterations and 2 transitions each, that's 200 JSON serializations + 200 file writes for in-progress state saves alone.

## Expected Behavior

Remove `route` from the trigger set to halve the number of in-progress state writes. The `route` event's destination state matches the upcoming `state_enter`'s state — no information is lost.

## Scope Boundaries

- **In scope**: Removing `route` from the `_save_state` trigger condition
- **Out of scope**: Batching or debouncing state writes, changing event emission order

## Proposed Solution

Change the trigger condition in `_handle_event` at `persistence.py:284-287`:

```python
# Before:
if event_type in ("state_enter", "route", "loop_complete"):
    self._save_state()

# After:
if event_type in ("state_enter", "loop_complete"):
    self._save_state()
```

The crash window between `route` and `state_enter` is extremely narrow (microseconds, same thread). If resumed after a crash in that window, the state would be re-entered from the same `current_state`, which is correct behavior.

## Impact

- **Priority**: P4 - Performance improvement, reduces I/O by ~50% for state persistence
- **Effort**: Small - One-line change
- **Risk**: Low - Narrow crash window is the only theoretical concern
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `performance`

---

**Open** | Created: 2026-03-06 | Priority: P4
