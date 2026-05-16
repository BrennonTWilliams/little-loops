---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
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

## Acceptance Criteria

- [x] `ll-loop status <loop-name>` shows `Status: timed_out` after a timeout termination
- [x] `ll-loop status <loop-name>` still shows `Status: failed` after an error termination (no regression)
- [x] Existing state files with `status: "failed"` are unaffected (no migration needed)
- [x] `test_fsm_persistence.py` passes with a new test asserting `state.status == "timed_out"` when `terminated_by == "timeout"`

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

1. Add `if result.terminated_by == "timeout": final_status = "timed_out"` in `PersistentExecutor.run()` (`persistence.py:351–356`)
2. Verify callers handle the new value — `lifecycle.py:cmd_status` prints `state.status` directly (line 63, no change needed); `lifecycle.py:cmd_resume` only checks `"awaiting_continuation"` (line 180, no change needed); scan for any other hardcoded `"failed"` comparisons that would incorrectly match `"timed_out"`
3. Add test in `scripts/tests/test_fsm_persistence.py` verifying `state.status == "timed_out"` when `terminated_by == "timeout"`

## Impact

- **Priority**: P4 — UX/observability issue; doesn't affect correctness of loop execution
- **Effort**: Small — Small mapping addition plus display update
- **Risk**: Low — No logic changes; purely a status label improvement
- **Breaking Change**: No (new status value `"timed_out"` is additive)

## Labels

`bug`, `fsm`, `persistence`, `observability`, `captured`

## Verification Notes

- **Verified**: 2026-03-07 — VALID
- Code at `persistence.py:352–356` matches the quoted snippet exactly; `"timeout"` still falls through to `"failed"`.
- `cmd_status()` (`lifecycle.py:63`) and `cmd_resume()` (`lifecycle.py:188`) are safe — no hardcoded `"failed"` comparisons that would regress.
- `test_fsm_persistence.py` exists but has no `"timed_out"` test case (line 895 only covers `"completed"`, `"failed"`).
- Minor: `persistence.py:64` docstring and `:79` inline comment both omit `"timed_out"` — should be updated alongside the fix.

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ca2eb1f-9d78-4680-b741-5613ecbf49b3.jsonl`
- `/ll:verify-issues BUG-623` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f1264d4-d8b5-4093-9023-f666be376885.jsonl`
- `/ll:confidence-check BUG-623` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/960ba0d2-07ee-46e5-849e-e84d12bd490f.jsonl`
- `/ll:manage-issue bug fix BUG-623` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Resolution

- **Status**: Completed
- **Resolved**: 2026-03-07
- **Changes**:
  - `scripts/little_loops/fsm/persistence.py`: Added `if result.terminated_by == "timeout": final_status = "timed_out"` mapping in `PersistentExecutor.run()`; updated docstring and inline comment to include `"timed_out"`
  - `scripts/tests/test_fsm_persistence.py`: Added `test_final_status_timed_out_on_timeout` test verifying `state.status == "timed_out"` when `terminated_by == "timeout"`
- **Verification**: 3371 tests pass, 0 regressions

---

**Completed** | Created: 2026-03-07 | Priority: P4
