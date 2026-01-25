# BUG-142: Worktree Deleted While Worker Still Running - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-142-worktree-deleted-while-worker-running.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The ll-parallel system has four distinct worktree cleanup paths, but none of them check if a worker is actively using a worktree before deletion.

### Key Discoveries

1. **`cleanup_all_worktrees()` at worker_pool.py:975-985** iterates ALL `worker-*` directories and cleans them without checking if workers are running:
   ```python
   for worktree_dir in worktree_base.iterdir():
       if worktree_dir.is_dir() and worktree_dir.name.startswith("worker-"):
           self._cleanup_worktree(worktree_dir)  # No active check!
   ```

2. **`_cleanup_orphaned_worktrees()` at orchestrator.py:195-246** runs at startup and removes ALL `worker-*` directories - appropriate for startup but uses the same unsafe pattern.

3. **Worker tracking exists via `_active_workers` dict** (worker_pool.py:81) mapping `issue_id -> Future`, but there's no mapping from `worktree_path -> active state`.

4. **Existing tracking patterns to follow**:
   - `_active_workers: dict[str, Future[WorkerResult]]` (worker_pool.py:81)
   - `_active_processes: dict[str, subprocess.Popen[str]]` (worker_pool.py:83)
   - `_current_issue_id` tracking in MergeCoordinator (merge_coordinator.py:74)

## Desired End State

All worktree cleanup operations check if a worker is actively using the worktree before attempting deletion. Cleanup operations should:
1. Skip worktrees that are in active use by a running worker
2. Log a warning when skipping an active worktree during cleanup
3. Only clean up worktrees after their associated worker has completed

### How to Verify
- Unit tests verify cleanup skips active worktrees
- Unit tests verify cleanup logs warning for skipped worktrees
- Unit tests verify worktree tracking is maintained correctly

## What We're NOT Doing

- Not changing the worktree creation logic
- Not changing the merge coordinator's cleanup (it uses `WorkerResult.worktree_path` which is correct)
- Not adding distributed locking (single process)
- Not adding file-based worktree locks (overkill for this scenario)

## Problem Analysis

The root cause is that `cleanup_all_worktrees()` in WorkerPool iterates over filesystem directories without consulting the `_active_workers` tracking that already exists. The fix is to:

1. Add a new `_active_worktrees: set[Path]` to track worktrees that are in active use
2. Update `_process_issue()` to register/unregister worktrees in this set
3. Update `_cleanup_worktree()` to skip paths that are in `_active_worktrees`

## Solution Approach

Add explicit worktree ownership tracking using a thread-safe set that cleanup operations consult before deletion. This follows the existing `_active_workers` and `_active_processes` patterns.

## Implementation Phases

### Phase 1: Add Active Worktree Tracking to WorkerPool

#### Overview
Add a thread-safe set to track which worktree paths are currently in use by running workers.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`

**Change 1**: Add `_active_worktrees` set in `__init__` (around line 83, after `_active_processes`):

```python
# Track active worktree paths to prevent cleanup while in use (BUG-142)
self._active_worktrees: set[Path] = set()
```

**Change 2**: Register worktree at start of `_process_issue()` (after line 231, after worktree is created):

```python
# Register worktree as active to prevent cleanup (BUG-142)
with self._process_lock:
    self._active_worktrees.add(worktree_path)
```

**Change 3**: Unregister worktree in finally block of `_process_issue()` (in the existing finally block around line 405):

```python
finally:
    # Unregister worktree as no longer active (BUG-142)
    with self._process_lock:
        self._active_worktrees.discard(worktree_path)
```

**Change 4**: Add guard in `_cleanup_worktree()` (at the beginning, after the existence check around line 535):

```python
# Skip cleanup if worktree is actively in use (BUG-142)
with self._process_lock:
    if worktree_path in self._active_worktrees:
        self.logger.warning(
            f"Skipping cleanup of {worktree_path.name}: worktree is in active use"
        )
        return
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 2: Add Unit Tests for Active Worktree Protection

#### Overview
Add tests that verify cleanup operations skip active worktrees and log warnings.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`

Add new test class after `TestWorkerPoolWorktreeManagement`:

```python
class TestActiveWorktreeProtection:
    """Tests for BUG-142: Prevent cleanup of worktrees in active use."""

    def test_cleanup_worktree_skips_active_worktree(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """_cleanup_worktree() should skip worktrees in _active_worktrees set."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-test-001"
        worktree_path.mkdir(parents=True)

        # Register as active
        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(worktree_path)

        # Attempt cleanup - should skip
        worker_pool._cleanup_worktree(worktree_path)

        # Worktree should still exist
        assert worktree_path.exists()

        # Cleanup
        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(worktree_path)

    def test_cleanup_worktree_logs_warning_for_active(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """_cleanup_worktree() should log warning when skipping active worktree."""
        worktree_path = temp_repo_with_config / ".worktrees" / "worker-test-002"
        worktree_path.mkdir(parents=True)

        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(worktree_path)

        worker_pool._cleanup_worktree(worktree_path)

        assert "worktree is in active use" in caplog.text

        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(worktree_path)

    def test_cleanup_all_worktrees_skips_active(
        self,
        worker_pool: WorkerPool,
        temp_repo_with_config: Path,
    ) -> None:
        """cleanup_all_worktrees() should skip worktrees in _active_worktrees."""
        worktree_base = temp_repo_with_config / ".worktrees"
        worktree_base.mkdir(parents=True)

        active_path = worktree_base / "worker-active-001"
        inactive_path = worktree_base / "worker-inactive-002"
        active_path.mkdir()
        inactive_path.mkdir()

        # Mark one as active
        with worker_pool._process_lock:
            worker_pool._active_worktrees.add(active_path)

        # Mock git operations to avoid actual git calls
        worker_pool._git_lock.run = MagicMock(return_value=MagicMock(returncode=0))

        worker_pool.cleanup_all_worktrees()

        # Active should still exist, inactive should be gone
        assert active_path.exists()
        # Note: inactive_path cleanup depends on git worktree remove mock

        with worker_pool._process_lock:
            worker_pool._active_worktrees.discard(active_path)
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_worker_pool.py::TestActiveWorktreeProtection -v`
- [ ] All worker pool tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_worker_pool.py`

---

### Phase 3: Final Verification

#### Overview
Run the complete test suite to ensure no regressions.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test that `_cleanup_worktree()` skips paths in `_active_worktrees`
- Test that warning is logged when skipping active worktree
- Test that `cleanup_all_worktrees()` respects `_active_worktrees`
- Test that worktree is registered/unregistered correctly during `_process_issue()`

### Integration Tests
- The existing test suite covers worktree lifecycle
- The fix is defensive and won't break existing behavior

## References

- Original issue: `.issues/bugs/P2-BUG-142-worktree-deleted-while-worker-running.md`
- Related fix: BUG-140 merge race condition (already completed)
- Worker tracking pattern: `worker_pool.py:81` (`_active_workers`)
- Process tracking pattern: `worker_pool.py:83` (`_active_processes`)
