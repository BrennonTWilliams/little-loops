# BUG-008: Merge coordination stash pop failure loses local changes - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-008-stash-pop-failure-loses-local-changes.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

### Key Discoveries
- Stash pop failures are detected at `merge_coordinator.py:213`
- Failures are logged with `logger.warning()` at `merge_coordinator.py:214` and `merge_coordinator.py:249-252`
- `_pop_stash()` returns `False` on failure at `merge_coordinator.py:253`
- **However, this return value is never used** - `_process_merge()` calls `_pop_stash()` at line 708 but ignores the return value
- Stash pop failures are NOT tracked in any state or reported in the final summary
- The orchestrator's `_report_results()` at `orchestrator.py:562-590` only reports completed/failed issues, not warnings

### Current Behavior
1. `_stash_local_changes()` stashes tracked files before merge
2. After merge (success or failure), `_pop_stash()` is called in the `finally` block
3. If pop fails, conflicts are cleaned up and a warning is logged
4. The warning scrolls by during execution and is easily missed
5. No record is kept that stash pop failed for a particular issue

### Root Cause
The stash pop failure is logged but not tracked anywhere that survives to the final summary. Users can easily miss the warning during execution and lose their local changes.

## Desired End State

When stash pop fails:
1. The failure should be tracked in `MergeCoordinator` state
2. The final summary should include a "Warnings" section listing any stash pop failures
3. Each warning should include the issue ID and guidance on recovery
4. The information should be prominent enough that users notice it

### How to Verify
- Create a test that simulates stash pop conflict and verifies tracking
- Verify `stash_pop_failures` property returns failure info
- Manually test by running with local changes that would conflict after merge

## What We're NOT Doing

- Not changing the merge preservation logic (merge should still succeed even if stash pop fails)
- Not attempting automatic recovery strategies beyond current cleanup
- Not making stash pop failure cause the issue to be marked as failed (the implementation succeeded)
- Not adding complex stash management (this is a simple warning/tracking improvement)

## Problem Analysis

The bug is that stash pop failures are transient - they're logged during execution but:
1. The return value of `_pop_stash()` is ignored
2. No state tracks which issues had stash pop failures
3. The final report has no section for warnings

## Solution Approach

1. Add a `_stash_pop_failures` dict to `MergeCoordinator` to track failures
2. Capture the failure in `_pop_stash()` and associate it with the current issue
3. Add a property to expose failures to the orchestrator
4. Modify `_report_results()` to include a warnings section for stash pop failures

## Implementation Phases

### Phase 1: Track Stash Pop Failures in MergeCoordinator

#### Overview
Add state tracking for stash pop failures and capture them when they occur.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

1. Add `_stash_pop_failures` dict to track failures (near line 69):
```python
self._stash_pop_failures: dict[str, str] = {}  # issue_id -> stash info
```

2. Add `_current_issue_id` to track which issue is being processed (near line 69):
```python
self._current_issue_id: str | None = None  # Track current issue for stash failure attribution
```

3. Set `_current_issue_id` at start of `_process_merge()` (after line 543):
```python
self._current_issue_id = result.issue_id
```

4. Clear `_current_issue_id` at end of `_process_merge()` (add to finally block after line 710):
```python
self._current_issue_id = None
```

5. In `_pop_stash()`, record the failure when it occurs (after line 253, before return):
```python
# Record this failure for reporting
if self._current_issue_id:
    with self._lock:
        self._stash_pop_failures[self._current_issue_id] = (
            "Local changes could not be restored after merge. "
            "Run 'git stash list' and 'git stash pop' to recover manually."
        )
```

6. Add property to expose failures (after line 953):
```python
@property
def stash_pop_failures(self) -> dict[str, str]:
    """Mapping of issue IDs to stash pop failure messages."""
    with self._lock:
        return dict(self._stash_pop_failures)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

**Manual Verification**:
- [ ] Verify `stash_pop_failures` property is accessible from MergeCoordinator instance

---

### Phase 2: Report Stash Pop Failures in Final Summary

#### Overview
Modify the orchestrator to include stash pop warnings in the final report.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`

1. In `_report_results()`, add warnings section after failed issues (after line 589):
```python
# Report stash pop warnings
stash_warnings = self.merge_coordinator.stash_pop_failures
if stash_warnings:
    self.logger.info("")
    self.logger.warning("Stash recovery warnings (local changes need manual restoration):")
    for issue_id, message in stash_warnings.items():
        self.logger.warning(f"  - {issue_id}: {message}")
    self.logger.warning("")
    self.logger.warning(
        "To recover: Run 'git stash list' to find your changes, "
        "then 'git stash pop' or 'git stash apply stash@{N}'"
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`

**Manual Verification**:
- [ ] Run ll-parallel with local changes that would conflict after merge
- [ ] Verify warnings section appears in final summary

---

### Phase 3: Add Tests for Stash Pop Failure Tracking

#### Overview
Add unit tests to verify stash pop failures are tracked and exposed correctly.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`

Add new test class after `TestPopStash`:

```python
class TestStashPopFailureTracking:
    """Tests for stash pop failure tracking."""

    def test_tracks_stash_pop_failure(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should track stash pop failure with issue ID."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a stash
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified content")
        coordinator._stash_local_changes()

        # Simulate stash pop failure by creating a conflicting change
        # First, modify the same file differently
        test_file.write_text("conflicting content")

        # Set the current issue ID (normally set by _process_merge)
        coordinator._current_issue_id = "TEST-001"

        # Attempt pop (will fail due to conflict)
        result = coordinator._pop_stash()

        # Should return False and track the failure
        assert result is False
        assert "TEST-001" in coordinator.stash_pop_failures
        assert "manually" in coordinator.stash_pop_failures["TEST-001"].lower()

    def test_stash_pop_failures_property_is_thread_safe(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Property should return a copy to prevent external modification."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Manually add a failure
        coordinator._stash_pop_failures["TEST-001"] = "test message"

        # Get the property
        failures = coordinator.stash_pop_failures

        # Modify the returned dict
        failures["TEST-002"] = "should not appear"

        # Original should be unchanged
        assert "TEST-002" not in coordinator.stash_pop_failures
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestStashPopFailureTracking -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/tests/test_merge_coordinator.py`

---

## Testing Strategy

### Unit Tests
- Test that stash pop failure is tracked with correct issue ID
- Test that property returns thread-safe copy
- Test that failure message contains recovery guidance

### Integration Tests
- Existing `TestProcessMergeStashIntegration` tests verify stash is popped on success/failure
- Add test to verify failure tracking during full merge flow

## References

- Original issue: `.issues/bugs/P2-BUG-008-stash-pop-failure-loses-local-changes.md`
- Merge coordinator: `scripts/little_loops/parallel/merge_coordinator.py`
- Orchestrator report: `scripts/little_loops/parallel/orchestrator.py:562-590`
- Similar pattern: `_failed` dict tracking at `merge_coordinator.py:67,905-906`
