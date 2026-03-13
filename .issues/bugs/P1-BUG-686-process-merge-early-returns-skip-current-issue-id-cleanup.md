---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# BUG-686: Early returns in `_process_merge` skip `_current_issue_id` cleanup causing infinite hang

## Summary

In `MergeCoordinator._process_merge`, `_current_issue_id` is set to `result.issue_id` early in the method, but two early-return paths (circuit breaker tripped and lifecycle moves failed) exit before the `try/finally` block that clears it. This leaves `_current_issue_id` permanently set, causing `wait_for_completion` to spin forever since its loop condition checks `self._current_issue_id`.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 710-745, 925 (at scan commit: 3e9beea)
- **Anchor**: `in method MergeCoordinator._process_merge()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/parallel/merge_coordinator.py#L710-L745)
- **Code**:
```python
self._current_issue_id = result.issue_id   # line 710

if self._paused:
    self._handle_failure(...)
    return                                  # _current_issue_id stays set

if not self._commit_pending_lifecycle_moves():
    self._handle_failure(...)
    return                                  # _current_issue_id stays set

try:
    ...
finally:
    ...
    self._current_issue_id = None           # line 925
```

## Current Behavior

When `_process_merge` hits either early return (circuit breaker or lifecycle failure), `_current_issue_id` is left pointing to the failed issue's ID. The `wait_for_completion` loop at line 1232 checks `while not self._queue.empty() or self._current_issue_id:` and never terminates because `_current_issue_id` is never cleared. The orchestrator hangs.

## Expected Behavior

`_current_issue_id` should always be cleared when `_process_merge` exits, regardless of which path is taken. The `wait_for_completion` loop should terminate normally after all merges complete or fail.

## Steps to Reproduce

1. Run `ll-parallel` with multiple issues
2. Trigger the circuit breaker (e.g., 3+ consecutive merge failures)
3. The next merge attempt hits `self._paused` check and returns early
4. `_current_issue_id` is never reset to `None`
5. `wait_for_completion` loops forever

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in method _process_merge()`
- **Cause**: The `_current_issue_id = None` cleanup is inside the `finally` block of a `try` statement that starts after the two early-return guards. The early returns bypass the `try/finally` entirely.

## Proposed Solution

Move `_current_issue_id` assignment into the `try` block, or add `_current_issue_id = None` to each early-return path. The cleanest approach is to wrap the entire method body in a `try/finally`:

```python
def _process_merge(self, result: WorkerResult) -> None:
    self._current_issue_id = result.issue_id
    try:
        if self._paused:
            self._handle_failure(...)
            return
        # ... rest of method
    finally:
        self._current_issue_id = None
```

## Implementation Steps

1. In `merge_coordinator.py`, locate `_process_merge` starting at line 710
2. Wrap the entire method body in `try/finally`, moving `self._current_issue_id = result.issue_id` inside the `try`
3. Ensure `self._current_issue_id = None` remains in the `finally` block, covering all exit paths
4. Verify `wait_for_completion` loop terminates correctly after circuit breaker and lifecycle failure paths

## Integration Map

- **Modified**: `scripts/little_loops/parallel/merge_coordinator.py` — `_process_merge()` (lines 710-745, 925)
- **Affected**: `scripts/little_loops/parallel/merge_coordinator.py` — `wait_for_completion()` (line 1232) reads `_current_issue_id`

## Impact

- **Priority**: P1 - Can cause the orchestrator to hang indefinitely, requiring manual kill of `ll-parallel`/`ll-sprint` runs
- **Effort**: Small - Restructure the try/finally to wrap the full method body
- **Risk**: Low - Only changes control flow for the failure path cleanup
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `merge-coordinator`

## Verification Notes

**Verdict: VALID** — Verified 2026-03-12

The bug is accurate and reproducible by code inspection:
- `_current_issue_id` is set at line 710, before the `try` block starting at line 750
- Three early-return paths (not two as stated) bypass the `finally` cleanup at line 925:
  1. Circuit breaker (`_paused`) — line 720
  2. Git index recovery failure (`_check_and_recover_index`) — line 734
  3. Lifecycle moves failure (`_commit_pending_lifecycle_moves`) — line 745
- `wait_for_completion` at line 1232 checks `self._current_issue_id` in its loop condition
- Minor discrepancy: issue says method signature is `result: WorkerResult` but it's now `request: MergeRequest` (with `result = request.worker_result` on line 709). Does not affect the bug.

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/000d1e34-e885-4aae-83d4-999718fb8e90.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01fe4a89-e3a7-4642-aa87-40682ae1517c.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P1
