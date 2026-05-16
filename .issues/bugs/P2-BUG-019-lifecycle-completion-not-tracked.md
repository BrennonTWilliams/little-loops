---
discovered_commit: 8279174
discovered_date: 2026-01-12
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-019: Lifecycle completion missing for successfully merged issues

## Summary

Issues that are successfully merged are being reported as "failed" in the final summary because their lifecycle (issue file move to completed/) was never completed. The merge succeeds, but the issue file is not moved, and the issue ID appears in the failed list.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
**Occurrences**: 1
**Affected External Issues**: BUG-642

### Sample Log Output

```
[12:17:01] Processing BUG-642 sequentially (P0)
[12:25:56] Found 2 file(s) changed: ['src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py', 'tests/unit/test_ooda_prompt.py']
[12:25:56] Queued merge for BUG-642 (branch: parallel/bug-642-20260112-121701)
[12:25:56] Processing merge for BUG-642
[12:25:58] Merged BUG-642 successfully

... (no lifecycle completion for BUG-642 anywhere in log) ...

[13:01:47] Failed issues:
[13:01:47]   - BUG-642
```

## Current Behavior

1. BUG-642 is processed sequentially (P0 priority)
2. Work is completed - 2 files changed
3. Merge is queued and processed successfully at 12:25:58
4. No lifecycle completion is performed (no `git mv` for issue file)
5. BUG-642 appears in "Failed issues" list at end of run
6. The work is actually completed and merged, but status reporting is incorrect

## Expected Behavior

1. After successful merge, the issue file should be moved to `completed/`
2. The issue should appear in "Completed" count, not "Failed" count
3. If lifecycle completion can't be performed immediately, it should be queued and completed later (as happens for some issues like ENH-625)

## Affected Components

- **Tool**: ll-parallel
- **Primary Bug Location**: `scripts/little_loops/parallel/merge_coordinator.py:1095-1109` (`wait_for_completion` method)
- **Caller Location**: `scripts/little_loops/parallel/orchestrator.py:522-530` (`_merge_sequential` method)
- **Changes Required**:
  - `merge_coordinator.py`: Fix `wait_for_completion()` to also check `_current_issue_id` (line 1105)
  - Note: `_current_issue_id` is already cleared in `_process_merge` finally block (line 838)

## Root Cause Analysis

**CONFIRMED**: Race condition in `MergeCoordinator.wait_for_completion()`.

Comparing BUG-642 (missing lifecycle) with ENH-625 (lifecycle completed):

**ENH-625** (lifecycle worked):
```
[12:38:43] ENH-625 completed in 6.6 minutes
[12:38:43] Queued merge for ENH-625 (branch: ...)
...
[13:01:46] Completing lifecycle for ENH-625 (merged but file not moved)
[13:01:47] Completed lifecycle for ENH-625: 67da44a1
```

**BUG-642** (lifecycle missing):
```
[12:25:58] Merged BUG-642 successfully
... (no lifecycle completion ever)
```

### Race Condition Details

The bug is in `scripts/little_loops/parallel/merge_coordinator.py:1095-1109`:

```python
def wait_for_completion(self, timeout: float | None = None) -> bool:
    start_time = time.time()
    while not self._queue.empty():  # BUG: Only checks if queue is empty
        if timeout and (time.time() - start_time) > timeout:
            return False
        time.sleep(0.5)
    return True
```

**The problem**: `wait_for_completion` returns as soon as the queue is empty, but this happens when the merge thread **picks up** the item from the queue (at line 641: `request = self._queue.get()`), NOT when the merge is **finished processing**.

**Sequence in `_merge_sequential` (orchestrator.py:522-530)**:
1. `queue_merge(result)` - puts merge request in queue
2. `wait_for_completion(timeout=60)` - waits for queue to be empty
3. Queue becomes empty when merge thread calls `self._queue.get()` (item picked up)
4. `wait_for_completion` returns immediately
5. Check `result.issue_id in self.merge_coordinator.merged_ids` - merge hasn't finished!
6. Issue not in `merged_ids` → marked as FAILED (line 530)
7. Meanwhile, merge thread continues and eventually logs "Merged BUG-642 successfully"

**Why ENH-625 worked**: ENH-625 was processed in parallel (not P0), so lifecycle completion happened in `_wait_for_completion()` at the end of the run (lines 554-557), which gives more time for merges to complete.

## Proposed Fix

**Primary Fix**: Update `wait_for_completion()` to wait for actual merge completion, not just queue emptiness.

Options:
1. **Add a "processing" flag/counter**: Track when merge thread is actively processing
2. **Use completion events**: Have `_finalize_merge` and `_handle_failure` signal completion
3. **Track pending vs completed**: Add `_processing` set alongside `_merged` and `_failed`

Recommended approach: Use `_current_issue_id` which is already:
- Set at merge start (line 662)
- Cleared in `_process_merge` finally block (line 838)

**Simple one-line fix** at `merge_coordinator.py:1105`:

```python
# Before (bug):
while not self._queue.empty():

# After (fix):
while not self._queue.empty() or self._current_issue_id:
```

No other changes required - `_current_issue_id` lifecycle is already correct.

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in single run (affects P0 sequential issues)
- **Data Risk**: Low - work is completed and merged, only reporting is incorrect

## Reproduction Steps

1. Run ll-parallel with a P0 (critical) priority issue
2. The P0 issue will be processed sequentially, not via worker pool
3. Let the issue complete and merge successfully
4. Observe that the issue appears in "Failed" list despite successful merge

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/merge_coordinator.py`: Fixed `wait_for_completion()` at line 1109 to wait for both queue emptiness AND active processing completion by adding `or self._current_issue_id` to the wait condition
- `scripts/tests/test_merge_coordinator.py`: Added `TestWaitForCompletion` test class with 4 tests to verify the fix

### Verification Results
- Tests: PASS (497 passed)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

---

## Status
**Completed** | Created: 2026-01-12 | Completed: 2026-01-12 | Priority: P2
