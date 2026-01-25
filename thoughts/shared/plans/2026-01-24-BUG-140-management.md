# BUG-140: Race condition between worktree creation and merge operations - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-140-worktree-merge-race-condition.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

### Key Discoveries

1. **Asynchronous queue_merge()** (`merge_coordinator.py:113-123`): The `queue_merge()` method puts a merge request on a `Queue` and returns immediately. The merge is processed in a background thread.

2. **Main loop dispatches immediately** (`orchestrator.py:548-578`): After `_on_worker_complete()` returns (which includes calling `queue_merge()`), the main loop continues. At line 561, it checks `worker_pool.active_count < max_workers` and dispatches the next worker immediately if a slot is available.

3. **Worktree creation includes file operations without GitLock** (`worker_pool.py:455-474`):
   - Line 460: `shutil.copytree(claude_dir, dest_claude_dir)` - No lock
   - Lines 469-471: `shutil.copy2(src, dest)` - No lock

   These file operations can run concurrently with merge processing and affect what `git status` sees.

4. **GitLock serializes individual commands, not sequences** (`git_lock.py:101`): The lock is acquired per-command via `run()`, so worktree creation (multiple git commands + file copies) and merge processing (multiple git commands) interleave.

5. **Existing wait_for_completion() method** (`merge_coordinator.py:1181-1199`): Already exists and is used in `_merge_sequential()` at `orchestrator.py:731-733` for P0 issues.

### Current Behavior

```
Timeline of Concurrent Operations:
Thread 1 (Orchestrator/Worker):          Thread 2 (Merge Coordinator):
───────────────────────────────────      ───────────────────────────────────
queue_merge(result) returns [line 697]
                                         _queue.get() receives request
Main loop continues [line 548]
                                         git status --porcelain (LOCKED)
queue.get() returns next issue
                                         (lock released)
_process_parallel() dispatches
                                         git stash push (LOCKED)
worker_pool.submit()
                                         (lock released)
_setup_worktree() starts
                                         git checkout main (LOCKED)
git worktree add (LOCKED)
                                         (lock released)
(lock released)
shutil.copytree(.claude/) (NO LOCK)      git status --porcelain (LOCKED)
                                         ← Sees files from copytree!
git config read (LOCKED)                 CONFLICT detected
```

## Desired End State

Worktree creation and merge processing should not overlap. When a worker completes and queues a merge, the next worker should not be dispatched until the merge completes, ensuring git sees a stable repository state.

### How to Verify
- Run ll-parallel with multiple issues that complete close together
- Observe no merge conflicts from concurrent operations
- Merges succeed on first attempt without retries (for clean changes)

## What We're NOT Doing

- **Not wrapping worktree creation in GitLock for file operations** - This would hold the lock for extended periods including file copies, blocking all git operations. The fix at the orchestrator level is cleaner.
- **Not adding a separate lock for worktree creation** - This adds complexity. The issue suggests waiting for merge completion, which is simpler.
- **Not changing MergeCoordinator's asynchronous design** - The async design is correct for throughput. The fix should be in the orchestrator's dispatch timing.

## Problem Analysis

The root cause is that `_on_worker_complete()` is called from the worker pool's callback, and after `queue_merge()` returns, control flows back to the orchestrator's main loop which can immediately dispatch a new worker. The merge hasn't completed yet.

The issue suggests two approaches:
1. Wait for merge completion before dispatching next worker
2. Use GitLock during worktree creation

Approach 1 is cleaner because:
- It doesn't require holding the git lock for extended periods
- It matches the existing pattern used for P0 sequential processing
- It's a minimal change with clear semantics

## Solution Approach

Modify `_on_worker_complete()` to wait for the queued merge to complete before returning. This ensures the next worker isn't dispatched until the merge finishes.

Since `_on_worker_complete()` is a callback invoked from the worker pool's executor thread, waiting here blocks that particular thread but doesn't block the main loop's polling. However, the main loop only dispatches when `worker_pool.active_count < max_workers`, and the worker count isn't decremented until the callback completes. This creates the desired serialization.

**Alternative considered**: Wait in the main loop before dispatching. This would require tracking "pending merges" separately and complicates the main loop logic. Waiting in the callback is simpler and leverages existing mechanisms.

## Implementation Phases

### Phase 1: Add merge wait after queue_merge in parallel callback

#### Overview
Modify `_on_worker_complete()` to wait for the queued merge to complete before returning.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Add `wait_for_completion()` call after `queue_merge()` for parallel workers

```python
# At line 697, after:
            self.merge_coordinator.queue_merge(result)
# Add:
            # Wait for merge to complete before returning from callback.
            # This prevents dispatch of next worker while merge is in progress,
            # avoiding race conditions between worktree creation and merge ops.
            # (BUG-140: Race condition between worktree creation and merge)
            self.merge_coordinator.wait_for_completion(timeout=120)
```

The complete modified block (lines 686-700) becomes:

```python
        elif result.success:
            self.logger.success(
                f"{result.issue_id} completed in {format_duration(result.duration)}"
            )
            if result.was_corrected:
                self.logger.info(f"{result.issue_id} was auto-corrected during validation")
                # Log and store corrections for pattern analysis (ENH-010)
                for correction in result.corrections:
                    self.logger.info(f"  Correction: {correction}")
                if result.corrections:
                    self.state.corrections[result.issue_id] = result.corrections
            self.merge_coordinator.queue_merge(result)
            # Wait for merge to complete before returning from callback.
            # This prevents dispatch of next worker while merge is in progress,
            # avoiding race conditions between worktree creation and merge ops.
            # (BUG-140: Race condition between worktree creation and merge)
            self.merge_coordinator.wait_for_completion(timeout=120)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`

**Manual Verification**:
- [ ] Review that the wait doesn't cause deadlock (it shouldn't - merge coordinator runs in separate thread)

---

### Phase 2: Add test for merge completion before worker dispatch

#### Overview
Add a test that verifies merges complete before new workers are dispatched.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add test that verifies wait_for_completion is called after queue_merge in the parallel worker callback

```python
def test_on_worker_complete_waits_for_merge(
    mock_logger: MagicMock,
) -> None:
    """_on_worker_complete waits for merge completion before returning (BUG-140)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / ".claude").mkdir()
        (repo_path / ".claude" / "ll-config.json").write_text("{}")

        parallel_config = ParallelConfig(
            max_workers=2,
            worktree_base=Path(".worktrees"),
            state_file=Path(".parallel-state.json"),
            timeout_per_issue=1800,
        )
        br_config = BRConfig(repo_path)

        orchestrator = ParallelOrchestrator(
            parallel_config=parallel_config,
            br_config=br_config,
            repo_path=repo_path,
            verbose=False,
        )

        # Track calls
        queue_merge_called = threading.Event()
        wait_called = threading.Event()
        call_order: list[str] = []

        original_queue_merge = orchestrator.merge_coordinator.queue_merge
        original_wait = orchestrator.merge_coordinator.wait_for_completion

        def mock_queue_merge(result: WorkerResult) -> None:
            call_order.append("queue_merge")
            queue_merge_called.set()
            original_queue_merge(result)

        def mock_wait_for_completion(timeout: float | None = None) -> bool:
            call_order.append("wait_for_completion")
            wait_called.set()
            return True  # Simulate immediate completion

        orchestrator.merge_coordinator.queue_merge = mock_queue_merge
        orchestrator.merge_coordinator.wait_for_completion = mock_wait_for_completion

        # Create a successful worker result
        result = WorkerResult(
            issue_id="TEST-001",
            success=True,
            branch_name="parallel/TEST-001",
            worktree_path=repo_path / ".worktrees" / "TEST-001",
            duration=1.0,
        )

        # Call the callback
        orchestrator._on_worker_complete(result)

        # Verify both were called in order
        assert queue_merge_called.is_set()
        assert wait_called.is_set()
        assert call_order == ["queue_merge", "wait_for_completion"]
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_orchestrator.py::test_on_worker_complete_waits_for_merge -v`
- [ ] All orchestrator tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_orchestrator.py`

---

### Phase 3: Verify complete test suite and update issue

#### Overview
Run the full test suite to ensure no regressions, then complete the issue lifecycle.

#### Success Criteria

**Automated Verification**:
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Test that `_on_worker_complete()` calls `wait_for_completion()` after `queue_merge()`
- Test call ordering to ensure wait happens after queue

### Integration Tests
- The existing orchestrator integration tests should continue to pass
- The fix makes behavior more deterministic, so tests should be more stable

## References

- Original issue: `.issues/bugs/P2-BUG-140-worktree-merge-race-condition.md`
- Existing wait pattern: `orchestrator.py:731-733` (used for P0 sequential processing)
- wait_for_completion implementation: `merge_coordinator.py:1181-1199`
- GitLock serialization: `git_lock.py:101`
