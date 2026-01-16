# BUG-079: Post-merge rebase causes unnecessary merge failures - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-079-post-merge-rebase-causes-unnecessary-failures.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The merge coordinator has two separate logic paths for handling rebase conflicts:

1. **Pull phase** (`merge_coordinator.py:770-843`): Pulls latest changes from remote using `git pull --rebase`. If rebase conflicts occur with a known problematic commit, it falls back to `git pull --no-rebase` (merge strategy).

2. **Conflict handling phase** (`merge_coordinator.py:906-997`): After a merge conflict, the `_handle_conflict()` method always attempts to rebase the feature branch onto main, regardless of what strategy was used during the pull phase.

### Key Discoveries
- `_process_merge()` at line 795-809 switches to merge strategy when a known problematic commit causes repeated rebase conflicts
- No state is tracked to indicate that merge strategy was used during the pull
- `_handle_conflict()` at lines 922-962 unconditionally attempts rebase retry
- The `MergeRequest` dataclass (`types.py:146-162`) lacks a field to track pull strategy used
- The `_problematic_commits` set tracks commits causing conflicts but this info isn't passed to `_handle_conflict()`

### Timeline from bug report:
1. Initial `git pull --rebase` fails with conflict (commit ae3b85ec superseded)
2. System correctly detects conflict and switches to `git pull --no-rebase` (succeeds)
3. Merge of feature branch attempted
4. **Bug**: Merge conflicts, `_handle_conflict()` attempts rebase on ENH-828's branch
5. Rebase fails with conflict on commit 79c12c55
6. ENH-828 merge marked as failed despite successful merge strategy pull

## Desired End State

When merge strategy was used during the pull phase (because rebase would conflict), the conflict handler should **skip the rebase retry** and fail immediately with a clear message. The rebase retry only makes sense when the pull used rebase strategy (meaning main is already rebased and clean).

### How to Verify
- When `git pull --no-rebase` is used (merge strategy), subsequent merge conflicts should NOT trigger rebase retry
- Log should show: "Skipping rebase retry - merge strategy was used during pull"
- Merge should fail with clear message about the conflict, not a confusing rebase failure

## What We're NOT Doing

- Not changing the pull strategy logic (that works correctly)
- Not modifying the problematic commit tracking (that works correctly)
- Not changing when merge strategy is used vs rebase strategy
- Not adding persistence for the `used_merge_strategy` flag (per-merge is sufficient)

## Problem Analysis

The root cause is a **state propagation gap**: when the pull phase switches to merge strategy, this information is not communicated to the conflict handler. The conflict handler assumes rebase is always viable, but rebase will fail on the same commits that caused the initial conflict.

The fix is to:
1. Track when merge strategy was used during pull (per-merge, in local variable)
2. Pass this information to `_handle_conflict()`
3. Skip rebase retry when merge strategy was already used

## Solution Approach

Add a `used_merge_strategy` local variable in `_process_merge()` that tracks whether `git pull --no-rebase` was used. Pass this to `_handle_conflict()` and skip the rebase retry if merge strategy was already used (since rebase would fail on the same conflicts).

## Implementation Phases

### Phase 1: Add strategy tracking and skip rebase when merge strategy used

#### Overview
Modify `_process_merge()` to track when merge strategy is used, and modify `_handle_conflict()` to accept this flag and skip rebase retry when appropriate.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`

**Change 1**: Add `used_merge_strategy` tracking in `_process_merge()` around line 770

After the `had_local_changes = False` initialization (around line 768), add:
```python
used_merge_strategy = False  # Track if we used merge strategy during pull
```

**Change 2**: Set the flag when merge strategy pull succeeds (after line 809)

Change lines 806-809 from:
```python
                        else:
                            self.logger.info(
                                f"Merge strategy pull succeeded for {conflict_commit[:8]}"
                            )
```
To:
```python
                        else:
                            self.logger.info(
                                f"Merge strategy pull succeeded for {conflict_commit[:8]}"
                            )
                            used_merge_strategy = True
```

**Change 3**: Pass the flag to `_handle_conflict()` (around line 886)

Change:
```python
                    self._handle_conflict(request)
```
To:
```python
                    self._handle_conflict(request, used_merge_strategy)
```

**Change 4**: Update `_handle_conflict()` signature and add early exit (lines 906-927)

Change the method signature and add check at the start:
```python
def _handle_conflict(self, request: MergeRequest, used_merge_strategy: bool = False) -> None:
    """Handle a merge conflict with retry logic.

    Args:
        request: The merge request that conflicted
        used_merge_strategy: If True, merge strategy was used during pull and rebase
            retry should be skipped (rebase would fail on same conflicts)
    """
    result = request.worker_result
    request.retry_count += 1

    # Abort the failed merge
    self._git_lock.run(
        ["merge", "--abort"],
        cwd=self.repo_path,
        timeout=10,
    )

    # Skip rebase retry if merge strategy was used during pull
    # Rebase would fail on the same commits that caused the initial conflict
    if used_merge_strategy:
        self.logger.warning(
            f"Merge conflict for {result.issue_id}, "
            f"skipping rebase retry (merge strategy was used during pull)"
        )
        self._handle_failure(
            request,
            "Merge conflict - rebase not attempted (would fail on same conflicts that required merge strategy)",
        )
        return

    if request.retry_count <= self.config.max_merge_retries:
        # ... rest of existing code
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Verify new log message appears: "skipping rebase retry (merge strategy was used during pull)"

---

### Phase 2: Add unit test for the new behavior

#### Overview
Add a test that verifies rebase retry is skipped when merge strategy was used during pull.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`

Add a new test class after the existing `TestUnmergedFilesHandling` class:

```python
class TestMergeStrategySkipsRebaseRetry:
    """Tests for BUG-079: skip rebase retry when merge strategy was used during pull."""

    def test_conflict_handler_skips_rebase_when_merge_strategy_used(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should skip rebase retry when used_merge_strategy=True.

        When merge strategy was used during pull (because rebase would conflict),
        the conflict handler should fail immediately rather than attempting a
        rebase that would fail on the same conflicts.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a worktree for the test
        worktree_path = temp_git_repo / ".worktrees" / "test-branch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test-branch", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Create a worker result and merge request
        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test-branch",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Track if _handle_failure was called
        failure_called = []
        original_handle_failure = coordinator._handle_failure
        def mock_handle_failure(req: MergeRequest, error: str) -> None:
            failure_called.append(error)
        coordinator._handle_failure = mock_handle_failure

        # Call _handle_conflict with used_merge_strategy=True
        coordinator._handle_conflict(request, used_merge_strategy=True)

        # Verify failure was called with expected message
        assert len(failure_called) == 1
        assert "rebase not attempted" in failure_called[0]
        assert "merge strategy" in failure_called[0]

        # Verify retry count was incremented
        assert request.retry_count == 1

    def test_conflict_handler_attempts_rebase_when_merge_strategy_not_used(
        self,
        default_config: ParallelConfig,
        mock_logger: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """Should attempt rebase retry when used_merge_strategy=False (default).

        When rebase strategy was used during pull (the normal case), the conflict
        handler should attempt to rebase the feature branch as before.
        """
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a worktree for the test
        worktree_path = temp_git_repo / ".worktrees" / "test-branch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test-branch", str(worktree_path)],
            cwd=temp_git_repo,
            capture_output=True,
            check=True,
        )

        # Make a commit in the worktree so rebase has something to do
        test_file = worktree_path / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "test commit"],
            cwd=worktree_path,
            capture_output=True,
            check=True,
        )

        # Create a worker result and merge request
        worker_result = WorkerResult(
            issue_id="TEST-002",
            branch_name="parallel/test-branch",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Track if rebase was attempted (request gets re-queued on success)
        requeued = []
        original_put = coordinator._queue.put
        def mock_put(req: MergeRequest) -> None:
            requeued.append(req)
        coordinator._queue.put = mock_put

        # Call _handle_conflict with used_merge_strategy=False (default)
        coordinator._handle_conflict(request, used_merge_strategy=False)

        # With no actual conflict, rebase should succeed and request should be re-queued
        assert len(requeued) == 1
        assert requeued[0] is request
        assert request.status == MergeStatus.RETRYING
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestMergeStrategySkipsRebaseRetry -v`
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test that `_handle_conflict(request, used_merge_strategy=True)` skips rebase and fails immediately
- Test that `_handle_conflict(request, used_merge_strategy=False)` attempts rebase as before
- Test that the default value for `used_merge_strategy` is `False` (backward compatible)

### Integration Tests
- The existing test suite should continue to pass (no behavioral change when merge strategy isn't used)

## References

- Original issue: `.issues/bugs/P2-BUG-079-post-merge-rebase-causes-unnecessary-failures.md`
- Pull strategy code: `scripts/little_loops/parallel/merge_coordinator.py:770-843`
- Conflict handler: `scripts/little_loops/parallel/merge_coordinator.py:906-997`
- Related ENH-037: `.issues/completed/P3-ENH-037-smarter-pull-strategy-for-repeated-rebase-conflicts.md`
