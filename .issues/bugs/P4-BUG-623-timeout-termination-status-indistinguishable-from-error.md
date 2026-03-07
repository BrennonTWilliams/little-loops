---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-623: `timeout` termination produces `status: "failed"` indistinguishable from error in state file

## Summary

`PersistentExecutor.run()` maps `terminated_by` values to a `final_status` string written to the state file. `terminated_by == "timeout"` falls through both `if` guards and maps to `"failed"` — the same status produced by a hard error (`terminated_by == "error"`). A user inspecting the state file cannot distinguish a timed-out loop from a loop that crashed, and there is no way to resume or handle a timed-out loop differently.

## Location

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Line(s)**: 351–356 (at scan commit: 12a6af0)
- **Anchor**: `in class PersistentExecutor, method run()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/persistence.py#L351-L356)
- **Code**:
```python
final_status = "completed" if result.terminated_by == "terminal" else "failed"
if result.terminated_by in ("max_iterations", "signal"):
    final_status = "interrupted"
if result.terminated_by == "handoff":
    final_status = "awaiting_continuation"
# "timeout" falls through to "failed" — same as "error"
```

## Current Behavior

Running `ll-loop status` after a timed-out loop shows `status: failed`. This is visually indistinguishable from an error-terminated loop. The `ll-loop history` output shows a `loop_complete` event but the reason is buried in the event detail.

## Expected Behavior

A timed-out loop should produce `status: "timed_out"` (or similar), distinguishable from `status: "failed"`.

## Steps to Reproduce

1. Create a loop with a short `timeout` (e.g., 2 seconds) and a long-running action.
2. Run the loop.
3. Run `ll-loop status <loop-name>` and observe `status: failed`.
4. Compare with a loop that errors — both show `status: failed`.

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in class PersistentExecutor, method run()`
- **Cause**: `"timeout"` was not added to the `final_status` mapping when timeout termination was implemented.

## Proposed Solution

Add an explicit mapping for `"timeout"`:

```python
final_status = "completed" if result.terminated_by == "terminal" else "failed"
if result.terminated_by in ("max_iterations", "signal"):
    final_status = "interrupted"
if result.terminated_by == "handoff":
    final_status = "awaiting_continuation"
if result.terminated_by == "timeout":
    final_status = "timed_out"
```

Also update `cmd_status` and `cmd_history` display logic if they have hardcoded status comparisons.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.run()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `cmd_status()` reads and displays `state.status`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` checks `state.status`

### Tests
- `scripts/tests/test_fsm_persistence.py` — add test verifying `status == "timed_out"` for timeout termination

### Documentation
- N/A

## Implementation Steps

1. Add `if result.terminated_by == "timeout": final_status = "timed_out"` in `PersistentExecutor.run()`
2. Update `cmd_status` display and any `state.status` comparisons to handle `"timed_out"`
3. Add test

## Impact

- **Priority**: P4 — UX/observability issue; doesn't affect correctness of loop execution
- **Effort**: Small — Small mapping addition plus display update
- **Risk**: Low — No logic changes; purely a status label improvement
- **Breaking Change**: No (new status value `"timed_out"` is additive)

## Labels

`bug`, `fsm`, `persistence`, `observability`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4
