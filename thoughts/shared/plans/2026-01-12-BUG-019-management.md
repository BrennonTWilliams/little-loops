# BUG-019: Lifecycle completion missing for successfully merged issues - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-019-lifecycle-completion-not-tracked.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `wait_for_completion()` method in `merge_coordinator.py:1095-1109` has a race condition that causes P0 (sequential) issues to be incorrectly marked as failed despite successful merges.

### Key Discoveries
- Race condition at `merge_coordinator.py:1105`: checks `self._queue.empty()` which becomes true when item is picked up, not when processing completes
- `_current_issue_id` already tracks active merge processing: set at line 662, cleared at line 838
- P0 issues use `_merge_sequential()` at `orchestrator.py:522-530` which calls `wait_for_completion(timeout=60)` immediately after queuing
- After wait returns, check at line 526 `result.issue_id in self.merge_coordinator.merged_ids` fails because merge hasn't finished yet
- Issue incorrectly marked as FAILED at line 530, preventing lifecycle completion

### Current Behavior (Buggy)
```
T+0.0s  queue_merge() - puts request in queue
T+0.5s  merge thread: get() - picks up request, QUEUE NOW EMPTY
T+0.5s  wait_for_completion returns (queue empty) - TOO EARLY
T+0.5s  Check merged_ids - issue not there yet → mark FAILED
T+8.0s  merge thread: _finalize_merge() - adds to merged_ids (TOO LATE)
```

### Patterns to Follow
- `worker_pool.py:852-861`: `active_count` property checks both running futures AND pending callbacks
- `orchestrator.py:353-356`: Main loop checks `queue.empty() AND worker_pool.active_count == 0 AND merge_coordinator.pending_count == 0`
- `orchestrator.py:428-429`: Waits `while self.worker_pool.active_count > 0`

## Desired End State

`wait_for_completion()` waits until:
1. Queue is empty (no pending requests), AND
2. No merge is actively being processed (`_current_issue_id` is None)

### How to Verify
- Run tests: `python -m pytest scripts/tests/ -v`
- Type check: `python -m mypy scripts/little_loops/`
- Lint: `ruff check scripts/`
- Sequential merge after fix waits for actual merge completion

## What We're NOT Doing

- Not changing the overall merge architecture
- Not adding new synchronization primitives (events, conditions)
- Not modifying `_process_merge()` or its `_current_issue_id` lifecycle
- Not changing P0 handling in orchestrator (the issue is purely in the wait logic)

## Problem Analysis

**Root Cause**: `wait_for_completion()` at line 1105 only checks `self._queue.empty()`, which becomes `True` the instant `Queue.get()` is called in the merge thread, not when `_process_merge()` completes.

**Why `_current_issue_id` solves this**:
- Set at line 662 immediately after picking up the merge request
- Cleared at line 838 in the finally block after ALL merge processing completes
- Already exists and has correct lifecycle - no new state tracking needed

## Solution Approach

Single line fix: Add `or self._current_issue_id` to the wait condition. This ensures the method waits until both:
1. Queue is empty (no items waiting)
2. No item is currently being processed

## Implementation Phases

### Phase 1: Fix wait_for_completion()

#### Overview
Modify the wait condition to also check if a merge is actively processing.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`
**Line**: 1105
**Changes**: Add check for `_current_issue_id` to the wait condition

```python
# Before (bug):
while not self._queue.empty():

# After (fix):
while not self._queue.empty() or self._current_issue_id:
```

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification** (requires human judgment):
- [ ] Code review confirms the fix addresses the race condition

---

### Phase 2: Add Test for Race Condition Fix

#### Overview
Add a test that verifies `wait_for_completion()` waits for active processing, not just queue emptiness.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add test for wait_for_completion with active processing

```python
def test_wait_for_completion_waits_for_active_processing(
    self,
    temp_git_repo: Path,
) -> None:
    """wait_for_completion waits until _current_issue_id is cleared."""
    config = ParallelConfig(
        repo_root=temp_git_repo,
        worktree_base=temp_git_repo / "worktrees",
        issues_dir=temp_git_repo / ".issues",
        max_workers=1,
    )
    coordinator = MergeCoordinator(config=config)

    # Simulate active processing (queue empty but processing in progress)
    coordinator._current_issue_id = "BUG-001"

    # wait_for_completion should not return immediately
    # Use a short timeout to verify it waits
    result = coordinator.wait_for_completion(timeout=0.2)

    # Should return False (timeout) because _current_issue_id is still set
    assert result is False

    # Clear the processing flag
    coordinator._current_issue_id = None

    # Now it should return True immediately
    result = coordinator.wait_for_completion(timeout=0.2)
    assert result is True
```

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] New test passes: `python -m pytest scripts/tests/test_merge_coordinator.py -v -k wait_for_completion`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- Test `wait_for_completion()` with `_current_issue_id` set (should wait/timeout)
- Test `wait_for_completion()` with `_current_issue_id` cleared (should return immediately)
- Test interaction: queue empty but `_current_issue_id` set

### Integration Tests
- Existing tests in `test_orchestrator.py` for `_merge_sequential` should continue to pass

## References

- Original issue: `.issues/bugs/P2-BUG-019-lifecycle-completion-not-tracked.md`
- Bug location: `scripts/little_loops/parallel/merge_coordinator.py:1105`
- Similar pattern: `scripts/little_loops/parallel/worker_pool.py:852` (`active_count` property)
- Caller: `scripts/little_loops/parallel/orchestrator.py:524`
