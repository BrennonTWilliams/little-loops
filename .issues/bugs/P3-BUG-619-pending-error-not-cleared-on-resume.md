---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-619: `_pending_error` not cleared on resume, asymmetric with `_pending_handoff`

## Summary

`PersistentExecutor.resume()` resets `_pending_handoff` to `None` before resuming execution, but does not reset `_pending_error`. The two fields are symmetric pending signals on `FSMExecutor`. In the unlikely scenario where a `FATAL_ERROR` signal was detected during `_run_action` but the process crashed before the main loop processed it, a resume would immediately re-trigger error termination without re-running any action, and the executor would appear to have terminated due to a stale signal from the previous run.

## Location

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Line(s)**: 403–405 (at scan commit: 12a6af0)
- **Anchor**: `in class PersistentExecutor, method resume()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/persistence.py#L403-L405)
- **Code**:
```python
# Clear any pending handoff from previous run
self._executor._pending_handoff = None

# Emit resume event with continuation context if available
```

`_pending_error` is defined alongside `_pending_handoff` in `executor.py` but has no corresponding reset here.

## Current Behavior

`resume()` resets `_pending_handoff = None` but leaves `_pending_error` at whatever value it had during the previous run. In normal flow this is harmless (FATAL_ERROR terminates immediately before a state can be saved with `status: "running"`), but the omission creates an asymmetry that could cause subtle failures if the internal flow ever changes.

## Expected Behavior

Both `_pending_handoff` and `_pending_error` should be reset to `None` in `resume()` for consistency, since both are transient signals that belong to the current execution context, not the saved state.

## Steps to Reproduce

The scenario requires a state file saved with `status: "running"` during execution of a state whose output contained `FATAL_ERROR:`. This is unlikely in normal flow since `FATAL_ERROR` terminates immediately, but the structural gap is present.

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in class PersistentExecutor, method resume()`
- **Cause**: `_pending_error` was not included alongside `_pending_handoff` when the reset was added to `resume()`.

## Proposed Solution

Add one line to `resume()` alongside the existing `_pending_handoff` reset:

```python
# Clear any pending signals from previous run
self._executor._pending_handoff = None
self._executor._pending_error = None   # add this line
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.resume()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `PersistentExecutor.resume()`

### Tests
- `scripts/tests/test_fsm_persistence.py` — add test verifying `_pending_error` is `None` after resume

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `self._executor._pending_error = None` in `PersistentExecutor.resume()`
2. Add test in `test_fsm_persistence.py` verifying both `_pending_handoff` and `_pending_error` are cleared on resume

## Impact

- **Priority**: P3 — Structural inconsistency with low probability of real-world impact; worth fixing for correctness
- **Effort**: Small — One-line fix
- **Risk**: Low — Isolated to `PersistentExecutor.resume()`; only affects an edge case
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `persistence`, `resume`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P3
