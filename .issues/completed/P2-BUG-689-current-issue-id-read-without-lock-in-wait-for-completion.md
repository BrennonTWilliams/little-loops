---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# BUG-689: `_current_issue_id` read without lock in `MergeCoordinator.wait_for_completion`

## Summary

`MergeCoordinator._current_issue_id` is written by the merge background thread in `_process_merge` and read without any lock by the caller thread in `wait_for_completion`. The `self._lock` guards `_merged` and `_failed` but not `_current_issue_id`. Under CPython's GIL the reference itself won't corrupt, but ordering is not guaranteed — a thread may observe a stale `None` and exit the wait loop early while a merge is still in progress.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 710, 926, 1233 (at scan commit: 3e9beea)
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

## Motivation

Thread-safety defects in `MergeCoordinator` can cause silent data loss — premature exit from `wait_for_completion` means the orchestrator considers work complete while an active merge is still running, resulting in incomplete or dropped merges. Fixing this prevents a hard-to-reproduce class of race conditions that only manifest under concurrent load in `ll-parallel`.

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

## Implementation Steps

1. In `MergeCoordinator._process_merge()`, wrap `self._current_issue_id = result.issue_id` write in `with self._lock:`
2. In the `finally` block of `MergeCoordinator._process_merge()`, wrap `self._current_issue_id = None` in `with self._lock:`
3. In `MergeCoordinator.wait_for_completion()`, wrap the `self._current_issue_id` read in `with self._lock:` before the loop condition check

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — `MergeCoordinator._process_merge()` (write/clear `_current_issue_id`), `MergeCoordinator.wait_for_completion()` (read `_current_issue_id`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — calls `wait_for_completion()` to block until all merges are done

### Similar Patterns
- `self._lock` already guards `_merged` and `_failed` in `MergeCoordinator` — extend the same discipline to `_current_issue_id`

### Tests
- `scripts/tests/test_merge_coordinator.py` — add thread-safety tests for concurrent `_process_merge` + `wait_for_completion` execution

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 - Could cause premature wait termination leading to incomplete merges
- **Effort**: Small - Add lock guards to 3 locations
- **Risk**: Low - Standard thread-safety fix
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `parallel`, `thread-safety`, `merge-coordinator`

## Verification Notes

- **Verdict**: VALID — bug confirmed against current codebase (file exists, all three unlocked access sites verified at lines 710, 925, 1232)
- **Additional finding**: Line 287 contains another unlocked read of `_current_issue_id` (`if self._current_issue_id:`) within `_handle_stash_conflict` or similar — also unprotected but not on the critical `wait_for_completion` path
- **Test file path corrected**: `scripts/tests/test_merge_coordinator.py` (not in a `parallel/` subdirectory)
- **Verified**: 2026-03-13

## Resolution

- **Status**: Fixed
- **Fixed in**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Changes**:
  - Wrapped `self._current_issue_id = result.issue_id` write in `_process_merge` with `with self._lock:`
  - Wrapped `self._current_issue_id = None` clear in `_process_merge` finally block with `with self._lock:`
  - Restructured `wait_for_completion` loop to read `_current_issue_id` under `with self._lock:` before evaluating the loop condition
  - Added `TestCurrentIssueIdLocking` test class with 3 thread-safety tests in `scripts/tests/test_merge_coordinator.py`
- **Tests**: 3335 passed, 4 skipped

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:format-issue` - 2026-03-13T01:35:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T01:35:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:ready-issue` - 2026-03-13T19:43:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cecfa03-19f5-4d9a-8854-ee9e4fc68966.jsonl`
- `/ll:manage-issue` - 2026-03-13T19:43:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/.ll-session-41181`

---

**Completed** | Created: 2026-03-13 | Priority: P2
