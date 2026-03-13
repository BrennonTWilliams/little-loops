---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# BUG-689: `_current_issue_id` read without lock in `MergeCoordinator.wait_for_completion`

## Summary

`MergeCoordinator._current_issue_id` is written by the merge background thread in `_process_merge` and read without any lock by the caller thread in `wait_for_completion`. The `self._lock` guards `_merged` and `_failed` but not `_current_issue_id`. Under CPython's GIL the reference itself won't corrupt, but ordering is not guaranteed — a thread may observe a stale `None` and exit the wait loop early while a merge is still in progress.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 710, 925, 1232 (at scan commit: 3e9beea)
- **Anchor**: `in methods MergeCoordinator._process_merge()` and `MergeCoordinator.wait_for_completion()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/parallel/merge_coordinator.py#L1232)
- **Code**:
```python
# wait_for_completion reads without lock
while not self._queue.empty() or self._current_issue_id:
```

## Current Behavior

`_current_issue_id` is set/cleared by the merge thread and read by the main thread without synchronization. If the main thread reads a stale `None` value, it could exit `wait_for_completion` prematurely while a merge is actively in progress, leading to race conditions in the orchestrator's lifecycle completion logic.

## Expected Behavior

`_current_issue_id` reads and writes should be protected by `self._lock`, consistent with how `_merged` and `_failed` are already protected.

## Steps to Reproduce

1. Run `ll-parallel` with issues that trigger merges
2. The main thread calls `wait_for_completion`
3. The merge thread writes `_current_issue_id` concurrently
4. Main thread may read stale value and exit early

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in method wait_for_completion()`
- **Cause**: `_current_issue_id` was not included in the locking discipline applied to `_merged` and `_failed`.

## Proposed Solution

Add `with self._lock:` guard around `_current_issue_id` reads in `wait_for_completion` and writes in `_process_merge`.

## Impact

- **Priority**: P2 - Could cause premature wait termination leading to incomplete merges
- **Effort**: Small - Add lock guards to 3 locations
- **Risk**: Low - Standard thread-safety fix
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `thread-safety`, `merge-coordinator`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P2
