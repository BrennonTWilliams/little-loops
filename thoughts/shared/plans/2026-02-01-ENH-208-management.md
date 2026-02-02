# ENH-208: Improve merge_coordinator.py test coverage from 66% to 80%+ - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P1-ENH-208-improve-merge-coordinator-py-test-coverage.md`
- **Type**: enhancement
- **Priority**: P1
- **Action**: improve

## Current State Analysis

### Coverage Baseline
- **Current Coverage**: 64% (439 statements, 157 missing)
- **Target Coverage**: 80%+ (needs to cover ~88 additional statements)
- **Test File**: `scripts/tests/test_merge_coordinator.py` (1658 lines, 53 tests, 14 test classes)

### Research Findings Summary

#### Key Discoveries
1. **Missing lines grouped by feature**:
   - Thread lifecycle (start/shutdown): Lines 83-93, 102-111, 119-121
   - Stash operations: Lines 221-222, 265-275
   - State file tracking: Lines 320-332, 343-358
   - Error detection: Lines 498-503
   - Rebase conflict handling: Lines 522-538, 791-842
   - Index recovery: Lines 591-592, 599-612, 623-624, 641-644, 649-651
   - Hard reset: Lines 661-671
   - Circuit breaker: Lines 705-710, 716-724, 734-735
   - Checkout recovery: Lines 749-773
   - Pull error handling: Lines 845-851, 857
   - Merge conflict routing: Lines 880-883, 887-888
   - Worktree stash/rebase: Lines 967-978, 1003, 1012-1030
   - Untracked conflict: Lines 1071-1075
   - Cleanup fallback: Line 1148
   - Thread-safe properties: Lines 1172-1173, 1178-1179

2. **Testability categories**:
   - **EASILY TESTABLE** (15 groups): Pure string matching, direct method calls
   - **TESTABLE WITH MOCKING** (9 groups): Git command failures via mocking
   - **TESTABLE WITH REAL GIT** (4 groups): Integration tests with real repos
   - **COMPLEX BUT TESTABLE** (2 groups): Multi-step integration tests

3. **Existing test patterns** (from `test_merge_coordinator.py:20-1658`):
   - `temp_git_repo` fixture creates temporary git repos
   - Worktree creation pattern with `git worktree add -b`
   - Conflict simulation by modifying same file in different branches
   - Git state simulation (MERGE_HEAD, rebase-merge) via manual file creation
   - Mock patterns for subprocess failures
   - Thread safety testing with execution order tracking

### Current Uncovered Line Details

| Lines | Feature | Testability | Estimated Tests |
|-------|---------|-------------|-----------------|
| 83-93, 102-111, 119-121 | Thread lifecycle | Easy | 3 |
| 221-222 | Stash failure | Mocking | 1 |
| 265-275 | Stash pop conflict | Real git | 1 |
| 320-332, 343-358 | State file tracking errors | Mocking | 2 |
| 379, 384 | Lifecycle edge cases | Easy | 2 |
| 448-453 | Lifecycle commit edge | Moderate | 1 |
| 498-503 | Index error detection | Easy | 1 |
| 522-538 | Rebase abort fallback | Mocking | 1 |
| 591-592, 599-612, 623-624 | Index recovery failures | Mocking | 3 |
| 641-644, 649-651 | MERGE_HEAD persistence | Mocking | 2 |
| 661-671 | Hard reset failure | Mocking | 1 |
| 675-688 | Merge loop errors | Moderate | 1 |
| 705-710 | Circuit breaker pause | Easy | 1 |
| 716-724 | Circuit breaker trip | Easy | 1 |
| 734-735 | Lifecycle commit failure | Easy | 1 |
| 749-773 | Checkout error recovery | Mocking | 2 |
| 791-842 | Pull rebase conflicts | Complex | 2 |
| 845-851 | Pull re-stash | Real git | 1 |
| 857 | Safety check | Easy | 1 |
| 880-883, 887-888 | Merge conflict routing | Mocking | 2 |
| 967-978, 1003, 1012-1030 | Worktree stash/rebase | Real git | 3 |
| 1071-1075 | Untracked parsing failure | Easy | 1 |
| 1148 | Cleanup fallback | Easy | 1 |
| 1172-1173, 1178-1179 | Thread-safe properties | Easy | 2 |

**Total estimated new tests: ~38 tests**

## Desired End State

### Coverage Goals
- Target: 80%+ coverage (351+ statements covered)
- Current: 64% (282 statements covered)
- Need: Cover ~69 more statements
- Plan: Add ~38 tests targeting ~90 statements (buffer for some being harder than expected)

### Test Categories to Add
1. **Thread lifecycle tests** (3 tests): start() no-op when alive, shutdown() without thread, shutdown() with wait
2. **Error detection tests** (4 tests): _is_index_error patterns, lifecycle edge cases
3. **Circuit breaker tests** (3 tests): Pause behavior, trip on consecutive failures, lifecycle commit failure
4. **Git operation failure tests** (10 tests): Stash failures, state file tracking errors, rebase abort, index recovery, hard reset, checkout recovery
5. **Merge conflict routing tests** (4 tests): Untracked conflict, conflict routing to handlers
6. **Worktree stash/rebase tests** (3 tests): Stash before rebase, pop after success, restore on failure
7. **Integration tests** (6 tests): Pull rebase conflicts, stash pop conflicts, pull re-stash
8. **Property tests** (2 tests): Thread-safe property copies
9. **Edge case tests** (3 tests): Untracked parsing failure, cleanup fallback, safety check

## What We're NOT Doing

- Not modifying `merge_coordinator.py` source code - only adding tests
- Not changing existing test behavior - all existing tests must continue to pass
- Not adding test framework dependencies - using existing pytest and unittest.mock patterns
- Not testing UI/CLI output - focusing on core merge coordinator logic
- Not adding property-based or fuzz testing - too complex for this scope
- Not testing performance/load characteristics - out of scope for coverage improvement

## Problem Analysis

### Root Cause of Low Coverage
The `merge_coordinator.py` module has complex error handling paths and edge cases that are difficult to trigger in normal operation:
- Git state corruption recovery (index issues, rebase aborts, hard resets)
- Circuit breaker logic for consecutive failures
- Thread lifecycle edge cases
- Integration scenarios (pull conflicts, worktree rebase with stash)
- Error routing (differentiating local changes vs untracked vs conflicts)

### Why These Paths Matter
- **Index corruption recovery**: Prevents merge coordinator from getting stuck in bad git state
- **Circuit breaker**: Stops runaway failure loops that could corrupt repository
- **Thread safety**: Prevents race conditions in concurrent parallel execution
- **Conflict routing**: Ensures appropriate handler is used for each conflict type

## Solution Approach

### Testing Strategy
1. **Layered approach**: Start with easy unit tests, build up to integration tests
2. **Mocking for failures**: Use `unittest.mock.patch` to simulate git command failures
3. **Real git for integration**: Use temp repos for realistic conflict scenarios
4. **Follow existing patterns**: Reuse fixtures and patterns from `test_merge_coordinator.py`

### Implementation Order
1. **Phase 1** (Quick wins): Easy unit tests - error detection, properties, edge cases (~12 tests)
2. **Phase 2** (Error paths): Mocked git failures - stash, index recovery, checkout (~10 tests)
3. **Phase 3** (Circuit breaker): Circuit breaker logic tests (~3 tests)
4. **Phase 4** (Integration): Real git scenarios - conflicts, stash, rebase (~10 tests)
5. **Phase 5** (Complex): Multi-step integration tests (~3 tests)

## Implementation Phases

### Phase 1: Thread Lifecycle and Property Tests

#### Overview
Add tests for thread lifecycle management and thread-safe property accessors.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestThreadLifecycle` and `TestThreadSafeProperties`

```python
class TestThreadLifecycle:
    """Tests for thread lifecycle management."""

    def test_start_when_already_running(self, default_config, mock_logger, temp_git_repo):
        """Should not start new thread if one is already running."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator.start()
        first_thread = coordinator._thread

        # Start again
        coordinator.start()
        second_thread = coordinator._thread

        assert first_thread is second_thread
        assert first_thread.is_alive()

    def test_shutdown_without_start(self, default_config, mock_logger, temp_git_repo):
        """Should handle shutdown gracefully when never started."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        # Should not raise
        coordinator.shutdown()
        assert coordinator._thread is None

    def test_shutdown_waits_for_completion(self, default_config, mock_logger, temp_git_repo):
        """Should wait for merge loop to complete when wait=True."""
        import time
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator.start()

        # Queue a merge
        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=temp_git_repo / ".worktrees/fake",
            success=True,
        )
        coordinator.queue_merge(worker_result)

        # Shutdown with wait
        coordinator.shutdown(wait=True, timeout=5.0)

        assert coordinator._thread is None or not coordinator._thread.is_alive()

    def test_queue_merge_increases_queue_size(self, default_config, mock_logger, temp_git_repo):
        """Queuing a merge should increase the pending count."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        initial_count = coordinator.pending_count

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=temp_git_repo / ".worktrees/fake",
            success=True,
        )
        coordinator.queue_merge(worker_result)

        assert coordinator.pending_count == initial_count + 1


class TestThreadSafeProperties:
    """Tests for thread-safe property accessors."""

    def test_merged_ids_returns_copy(self, default_config, mock_logger, temp_git_repo):
        """merged_ids property should return a copy, not the internal list."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator._merged = ["BUG-001", "BUG-002"]

        merged = coordinator.merged_ids
        merged.append("BUG-003")

        assert coordinator.merged_ids == ["BUG-001", "BUG-002"]
        assert len(coordinator.merged_ids) == 2

    def test_failed_merges_returns_copy(self, default_config, mock_logger, temp_git_repo):
        """failed_merges property should return a copy, not the internal dict."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator._failed = {"BUG-001": "conflict", "BUG-002": "error"}

        failed = coordinator.failed_merges
        failed["BUG-003"] = "new error"

        assert coordinator.failed_merges == {"BUG-001": "conflict", "BUG-002": "error"}
        assert "BUG-003" not in coordinator.failed_merges
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -k "TestThreadLifecycle or TestThreadSafeProperties" -v`
- [ ] Coverage increases by ~10 statements

---

### Phase 2: Error Detection and Edge Case Tests

#### Overview
Add tests for error detection helper methods and edge cases in lifecycle handling.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestIsIndexError` and expand `TestLifecycleFileMoveExclusion`

```python
class TestIsIndexError:
    """Tests for _is_index_error detection."""

    def test_detects_need_to_resolve_index_error(self, default_config, mock_logger, temp_git_repo):
        """Should detect 'need to resolve your current index first' error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        assert coordinator._is_index_error("you need to resolve your current index first") is True

    def test_detects_partial_commit_during_merge_error(self, default_config, mock_logger, temp_git_repo):
        """Should detect 'cannot do a partial commit during a merge' error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        assert coordinator._is_index_error("fatal: cannot do a partial commit during a merge") is True

    def test_detects_not_concluded_merge_error(self, default_config, mock_logger, temp_git_repo):
        """Should detect 'you have not concluded your merge' error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        assert coordinator._is_index_error("error: you have not concluded your merge") is True


# Add to TestLifecycleFileMoveExclusion:
def test_handles_rename_without_arrow(self, default_config, mock_logger, temp_git_repo):
    """Should handle malformed rename entry without ' -> ' separator."""
    coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
    # Line 379: "R  file.txt" (no arrow) - returns False
    assert coordinator._is_lifecycle_file_move("R  file.txt") is False

def test_handles_rename_with_malformed_parts(self, default_config, mock_logger, temp_git_repo):
    """Should handle rename entry with malformed parts after splitting."""
    coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
    # Line 384: Malformed parts after split - returns False
    assert coordinator._is_lifecycle_file_move("R  weird -> format -> here") is False
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestIsIndexError -v`
- [ ] Coverage increases by ~6 statements (lines 498-503)

---

### Phase 3: Circuit Breaker Tests

#### Overview
Add tests for circuit breaker pause behavior and trip logic.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestCircuitBreaker`

```python
class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_pause_skips_merges(self, default_config, mock_logger, temp_git_repo):
        """When paused, should skip merge requests with circuit breaker error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Set paused state
        coordinator._paused = True

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        coordinator._process_merge(request)

        assert request.status == MergeStatus.FAILED
        assert "circuit breaker" in request.error.lower()

    def test_consecutive_failures_trip_circuit_breaker(self, default_config, mock_logger, temp_git_repo):
        """Three consecutive failures should trip circuit breaker."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        # Mock _check_and_recover_index to fail
        def mock_index_failure():
            coordinator._consecutive_failures += 1
            return False

        coordinator._check_and_recover_index = mock_index_failure

        # First two failures
        worker_result = WorkerResult(
            issue_id=f"TEST-{i}",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )

        for i in range(3):
            request = MergeRequest(worker_result=WorkerResult(
                issue_id=f"TEST-{i}",
                branch_name="parallel/test",
                worktree_path=worktree_path,
                success=True,
            ))
            coordinator._process_merge(request)

        # After 3rd failure, circuit breaker should trip
        assert coordinator._paused is True
        assert coordinator._consecutive_failures == 3

    def test_lifecycle_commit_failure_handles_gracefully(self, default_config, mock_logger, temp_git_repo):
        """Lifecycle commit failure should fail the merge."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Mock _commit_pending_lifecycle_moves to return False
        coordinator._commit_pending_lifecycle_moves = lambda: False

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        coordinator._process_merge(request)

        assert request.status == MergeStatus.FAILED
        assert "lifecycle" in request.error.lower()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestCircuitBreaker -v`
- [ ] Coverage increases by ~9 statements (lines 705-710, 716-724, 734-735)

---

### Phase 4: Git Operation Failure Tests (Mocking)

#### Overview
Add tests for git operation failures using mocking.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestGitOperationFailures`

```python
class TestGitOperationFailures:
    """Tests for git operation failure handling."""

    def test_stash_failure_returns_false(self, default_config, mock_logger, temp_git_repo):
        """Stash command failure should return False and log error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Modify a file
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("modified")

        # Mock git_lock.run to fail stash
        def mock_run(cmd, **kwargs):
            if "stash" in cmd:
                return subprocess.CompletedProcess(
                    cmd, returncode=1, stdout="", stderr="stash failed"
                )
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._stash_local_changes()

        assert result is False
        assert coordinator._stash_active is False

    def test_mark_state_file_assume_unchanged_failure(self, default_config, mock_logger, temp_git_repo):
        """update-index failure should return False."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create state file as tracked
        state_file = temp_git_repo / ".parallel-state.json"
        state_file.write_text("{}")
        subprocess.run(["git", "add", str(state_file)], cwd=temp_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add state"], cwd=temp_git_repo, capture_output=True)

        # Mock to fail
        def mock_run(cmd, **kwargs):
            if "assume-unchanged" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=1, stderr="failed")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._mark_state_file_assume_unchanged()

        assert result is False

    def test_restore_state_file_tracking_failure(self, default_config, mock_logger, temp_git_repo):
        """no-assume-unchanged failure should return False."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)
        coordinator._assume_unchanged_active = True

        # Mock to fail
        def mock_run(cmd, **kwargs):
            if "no-assume-unchanged" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=1, stderr="failed")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._restore_state_file_tracking()

        assert result is False

    def test_hard_reset_failure(self, default_config, mock_logger, temp_git_repo):
        """reset --hard failure should return False."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Mock to fail
        def mock_run(cmd, **kwargs):
            if "reset" in cmd and "--hard" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=1, stderr="reset failed")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._attempt_hard_reset()

        assert result is False

    def test_checkout_index_error_recovery(self, default_config, mock_logger, temp_git_repo):
        """Checkout with index error should attempt recovery."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create a worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        # Track calls
        checkout_calls = []
        recovery_called = []

        def mock_run(cmd, **kwargs):
            if "checkout" in cmd and "main" in cmd:
                checkout_calls.append(cmd)
                # First call fails with index error
                if len(checkout_calls) == 1:
                    return subprocess.CompletedProcess(
                        cmd, returncode=1,
                        stderr="you need to resolve your current index first"
                    )
                # Second call succeeds
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        def mock_recover():
            recovery_called.append(True)
            return True

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            with patch.object(coordinator, '_check_and_recover_index', side_effect=mock_recover):
                coordinator._checkout_main()

        assert len(checkout_calls) == 2
        assert len(recovery_called) == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestGitOperationFailures -v`
- [ ] Coverage increases by ~15 statements

---

### Phase 5: Index Recovery Tests

#### Overview
Add tests for index recovery failure scenarios.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestIndexRecoveryFailures`

```python
class TestIndexRecoveryFailures:
    """Tests for index recovery failure handling."""

    def test_merge_abort_failure(self, default_config, mock_logger, temp_git_repo):
        """merge --abort failure should return False."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create MERGE_HEAD
        merge_head = temp_git_repo / ".git" / "MERGE_HEAD"
        merge_head.write_text("abc123")

        # Mock abort to fail
        def mock_run(cmd, **kwargs):
            if "abort" in cmd:
                return subprocess.CompletedProcess(cmd, returncode=1, stderr="abort failed")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._check_and_recover_index()

        assert result is False

    def test_rebase_abort_failure_triggers_hard_reset(self, default_config, mock_logger, temp_git_repo):
        """rebase --abort failure should fallback to hard reset."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create rebase-merge directory
        rebase_dir = temp_git_repo / ".git" / "rebase-merge"
        rebase_dir.mkdir(parents=True)

        abort_calls = []
        reset_called = []

        def mock_run(cmd, **kwargs):
            if "rebase" in cmd and "abort" in cmd:
                abort_calls.append(cmd)
                return subprocess.CompletedProcess(cmd, returncode=1, stderr="abort failed")
            if "reset" in cmd and "--hard" in cmd:
                reset_called.append(cmd)
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            result = coordinator._check_and_recover_index()

        assert len(abort_calls) == 1
        assert len(reset_called) == 1
        assert result is True  # Hard reset succeeded

    def test_persistent_merge_head_triggers_final_reset(self, default_config, mock_logger, temp_git_repo):
        """MERGE_HEAD persisting after recovery should trigger final reset."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create MERGE_HEAD
        merge_head = temp_git_repo / ".git" / "MERGE_HEAD"
        merge_head.write_text("abc123")

        reset_count = []

        def mock_run(cmd, **kwargs):
            if "reset" in cmd:
                reset_count.append(cmd)
                # Keep MERGE_HEAD around to trigger final check
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        # Mock exists to always return True
        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            with patch("pathlib.Path.exists", return_value=True):
                result = coordinator._check_and_recover_index()

        assert len(reset_count) >= 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestIndexRecoveryFailures -v`
- [ ] Coverage increases by ~12 statements

---

### Phase 6: Merge Conflict Routing Tests

#### Overview
Add tests for routing merge conflicts to appropriate handlers.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestMergeConflictRouting`

```python
class TestMergeConflictRouting:
    """Tests for routing merge conflicts to appropriate handlers."""

    def test_untracked_files_routes_to_untracked_handler(self, default_config, mock_logger, temp_git_repo):
        """Merge failure due to untracked files should route to _handle_untracked_conflict."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Track handler calls
        untracked_called = []

        def mock_untracked(req, error):
            untracked_called.append(req)
            # Don't actually handle, just track

        coordinator._handle_untracked_conflict = mock_untracked

        # Mock merge to fail with untracked error
        def mock_run(cmd, **kwargs):
            if "merge" in cmd:
                return subprocess.CompletedProcess(
                    cmd, returncode=1,
                    stderr="error: The following untracked working tree files would be overwritten"
                )
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            coordinator._process_merge(request)

        assert len(untracked_called) == 1

    def test_merge_conflict_routes_to_conflict_handler(self, default_config, mock_logger, temp_git_repo):
        """Merge failure with conflict should route to _handle_conflict."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Track handler calls
        conflict_called = []

        def mock_conflict(req, used_merge=False):
            conflict_called.append(req)

        coordinator._handle_conflict = mock_conflict

        # Mock merge to fail with conflict
        def mock_run(cmd, **kwargs):
            if "merge" in cmd:
                return subprocess.CompletedProcess(
                    cmd, returncode=1,
                    stderr="CONFLICT (content): Merge conflict in test.txt"
                )
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            coordinator._process_merge(request)

        assert len(conflict_called) == 1

    def test_untracked_conflict_parsing_failure(self, default_config, mock_logger, temp_git_repo):
        """Untracked conflict without parseable file list should fail."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Malformed error message (no file list)
        error_output = "error: untracked files would be overwritten"

        coordinator._handle_untracked_conflict(request, error_output)

        assert request.status == MergeStatus.FAILED
        assert "parse" in request.error.lower()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestMergeConflictRouting -v`
- [ ] Coverage increases by ~8 statements

---

### Phase 7: Integration Tests with Real Git

#### Overview
Add integration tests using real git operations for complex scenarios.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestIntegrationScenarios`

```python
class TestIntegrationScenarios:
    """Integration tests with real git operations."""

    def test_stash_pop_with_conflict_cleanup(self, default_config, mock_logger, temp_git_repo):
        """Stash pop with conflicts should clean up and preserve merge."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create and commit initial file
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("initial")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_git_repo, capture_output=True)

        # Modify and stash
        test_file.write_text("stashed content")
        coordinator._stash_local_changes()

        # Create conflicting change
        test_file.write_text("conflicting content")

        # Pop stash (will conflict)
        result = coordinator._pop_stash()

        # Should fail but not raise
        assert result is False
        assert coordinator._stash_active is False

    def test_worktree_stash_before_rebase(self, default_config, mock_logger, temp_git_repo):
        """Rebase should stash worktree changes first."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test-branch"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        # Make uncommitted change in worktree
        worktree_file = worktree_path / "worktree.txt"
        worktree_file.write_text("uncommitted change")

        # Create worker result
        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Mock main repo merge to fail and trigger rebase
        def mock_run(cmd, **kwargs):
            if "merge" in cmd:
                return subprocess.CompletedProcess(
                    cmd, returncode=1, stderr="CONFLICT: content conflict"
                )
            # Let other commands run normally
            return subprocess.run(cmd, cwd=kwargs.get('cwd', temp_git_repo),
                               capture_output=True, text=True)

        # Track rebase attempts
        rebase_attempts = []

        original_run = coordinator._git_lock.run
        def track_rebase(cmd, **kwargs):
            if "rebase" in cmd:
                rebase_attempts.append(cmd)
            return mock_run(cmd, **kwargs)

        coordinator._git_lock.run = track_rebase
        coordinator._handle_conflict(request)

        # Rebase should have been attempted
        assert len(rebase_attempts) > 0

    def test_cleanup_worktree_nonexistent_path(self, default_config, mock_logger, temp_git_repo):
        """Cleanup with nonexistent worktree path should not error."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Call with nonexistent path
        coordinator._cleanup_worktree(
            temp_git_repo / ".worktrees" / "nonexistent",
            "parallel/ghost"
        )

        # Should not raise
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestIntegrationScenarios -v`
- [ ] Coverage increases by ~10 statements

---

### Phase 8: Pull Conflict Integration Tests

#### Overview
Add integration tests for pull rebase conflict handling.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add new test class `TestPullConflictHandling`

```python
class TestPullConflictHandling:
    """Tests for pull conflict handling with problematic commits."""

    def test_pull_with_local_changes_restash(self, default_config, mock_logger, temp_git_repo):
        """Pull failing due to local changes should re-stash and continue."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        # Create local change (to trigger re-stash)
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("local change")

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Mock: stash succeeds, pull fails with local changes error, re-stash succeeds
        call_sequence = []

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            call_sequence.append(cmd_str)

            if "stash" in cmd_str:
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            if "pull" in cmd_str and "rebase" in cmd_str:
                # First pull fails
                return subprocess.CompletedProcess(
                    cmd, returncode=1,
                    stderr="error: cannot pull with rebase: You have unstaged changes"
                )
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

        with patch.object(coordinator._git_lock, 'run', side_effect=mock_run):
            coordinator._process_merge(request)

        # Should have attempted stash at least twice
        stash_calls = [c for c in call_sequence if "stash" in c]
        assert len(stash_calls) >= 2

    def test_safety_check_before_merge(self, default_config, mock_logger, temp_git_repo):
        """Index recovery failure before merge should raise RuntimeError."""
        coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

        # Create worktree
        worktree_path = temp_git_repo / ".worktrees" / "test"
        worktree_path.mkdir(parents=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test", str(worktree_path)],
            cwd=temp_git_repo, capture_output=True, check=True,
        )

        worker_result = WorkerResult(
            issue_id="TEST-001",
            branch_name="parallel/test",
            worktree_path=worktree_path,
            success=True,
        )
        request = MergeRequest(worker_result=worker_result)

        # Mock index recovery to fail
        coordinator._check_and_recover_index = lambda: False

        # Process merge should handle the failure
        coordinator._process_merge(request)

        assert request.status == MergeStatus.FAILED
        assert "index" in request.error.lower()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py::TestPullConflictHandling -v`
- [ ] Coverage increases by ~8 statements

---

## Testing Strategy

### Unit Tests
- Focus on error detection helpers (string matching)
- Thread lifecycle state transitions
- Property accessor thread safety
- Circuit breaker logic

### Integration Tests
- Real git operations with temporary repositories
- Stash/pop conflict scenarios
- Worktree rebase with uncommitted changes
- Pull conflict with local changes

### Mocked Tests
- Git command failures via `unittest.mock.patch`
- Index recovery error paths
- State file tracking failures
- Checkout/rebase abort failures

## References

- Original issue: `.issues/enhancements/P1-ENH-208-improve-merge-coordinator-py-test-coverage.md`
- Source file: `scripts/little_loops/parallel/merge_coordinator.py`
- Test file: `scripts/tests/test_merge_coordinator.py`
- Existing test patterns: `test_merge_coordinator.py:20-1658`
- Coverage threshold: `scripts/pyproject.toml` (80%)
