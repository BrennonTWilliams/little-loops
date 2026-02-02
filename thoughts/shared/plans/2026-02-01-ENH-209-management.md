# ENH-209: Improve orchestrator.py test coverage from 74% to 80%+ - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P1-ENH-209-improve-orchestrator-py-test-coverage.md`
- **Type**: enhancement
- **Priority**: P1
- **Action**: improve

## Current State Analysis

The orchestrator module (`scripts/little_loops/parallel/orchestrator.py`) is currently at 74% test coverage (498 total statements, 130 missing).

### Key Discoveries
- **Current coverage**: 74% (368/498 statements covered, 130 missing)
- **Test file**: `scripts/tests/test_orchestrator.py` (68 tests, 1453 lines)
- **Missing lines by area**:
  - Signal handling: lines 113, 146, 207
  - Git operations: lines 255-256, 354, 365-366, 386-392
  - Issue dispatch: lines 430-439
  - Main execution loop: lines 567-595
  - Sequential processing error handling: lines 605, 656-658
  - Parallel processing overlap detection: lines 668-683
  - Worker completion overlap handling: lines 696-698, 702-705, 724-727
  - Deferred issue re-queueing: lines 756-772
  - Merge operations: lines 795, 836, 850, 859
  - State file operations: lines 875-878
  - Cleanup operations: lines 882-918
  - Worktree management: lines 926, 960-1047

### Pattern Discovery
From analyzing recent coverage improvements (ENH-207, ENH-208):
- Use descriptive test class names grouped by functionality
- Test both success and failure paths
- Use `threading.Event()` for thread coordination
- Use `MagicMock()` for flexible mocking
- Return `subprocess.CompletedProcess` objects for subprocess mocking
- Track coverage improvement with before/after metrics

## Desired End State

- **Target coverage**: 80%+ (at least 398/498 statements)
- **Improvement needed**: Cover at least 30 additional statements
- **Test areas**: Signal handling, worker pool edge cases, concurrent state access, orchestration flows

### How to Verify
```bash
python -m pytest scripts/tests/test_orchestrator.py --cov=scripts/little_loops/parallel/orchestrator --cov-report=term-missing
```
Expected output: Coverage >= 80%

## What We're NOT Doing

- Not modifying the orchestrator.py source code (only adding tests)
- Not testing integration with actual git operations (mock all git calls)
- Not adding tests for WorkerPool or MergeCoordinator (they have their own test files)
- Not changing the test file structure or existing tests
- Not adding tests for the FSM system (separate coverage)

## Problem Analysis

The orchestrator module has 130 missing statements across these categories:

1. **Signal Handling (3 lines)**: Edge cases in shutdown flow
2. **Git Operations (12 lines)**: Worktree inspection and cleanup paths
3. **Issue Dispatch (10 lines)**: Overlap detection and deferred issue handling
4. **Main Execution Loop (29 lines)**: Core dispatch logic, state saving, max_issues handling
5. **Sequential Processing (4 lines)**: Error handling paths
6. **Parallel Processing (16 lines)**: Overlap detection, deferred issues
7. **Worker Completion (14 lines)**: Overlap unregistration, re-queueing, interrupt handling
8. **Merge Operations (4 lines)**: Edge cases in merge coordination
9. **State File Operations (4 lines)**: Edge cases in state persistence
10. **Cleanup Operations (37 lines)**: Worktree cleanup paths
11. **Worktree Management (88 lines)**: Health checks, stale worktree detection

## Solution Approach

Add new test classes to cover the missing statement groups:

1. **TestShutdownHandling** - Cover signal handler edge cases
2. **TestWorkerPoolIntegration** - Cover worker pool interactions
3. **TestOverlapDetection** - Cover overlap detection and deferred issues
4. **TestConcurrentExecution** - Cover concurrent state access
5. **TestWorktreeManagement** - Cover worktree cleanup paths
6. **TestExecuteLoop** - Cover main execution loop branches

## Implementation Phases

### Phase 1: Signal Handling and Shutdown (Target: +3 statements)

#### Overview
Add tests for signal handler edge cases in the shutdown flow.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add `TestShutdownHandling` class with tests for:
- Signal handler when already shutdown
- Shutdown during worker execution
- Shutdown with pending merges

```python
class TestShutdownHandling:
    """Tests for graceful shutdown signal handling edge cases."""

    def test_signal_handler_idempotent(self, orchestrator: ParallelOrchestrator) -> None:
        """_signal_handler is idempotent - can be called multiple times."""
        orchestrator._signal_handler(signal.SIGINT, None)
        orchestrator._signal_handler(signal.SIGTERM, None)

        assert orchestrator._shutdown_requested is True
        # Should only propagate once
        assert orchestrator.worker_pool.set_shutdown_requested.call_count == 1

    def test_shutdown_with_active_workers(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """Shutdown during active worker execution waits for completion."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 2  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        # Set shutdown after scan
        def set_shutdown(*args: object, **kwargs: object) -> list[MagicMock]:
            orchestrator._shutdown_requested = True
            return [mock_issue]

        with patch.object(orchestrator, "_scan_issues", side_effect=set_shutdown):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    exit_code = orchestrator._execute()

        assert exit_code == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestShutdownHandling -v`
- [ ] Coverage increases to at least 75% (cover lines 113, 146, 207)

### Phase 2: Worker Pool Edge Cases (Target: +8 statements)

#### Overview
Add tests for worker pool edge cases including empty scenarios, timeout handling, and worker failures.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add `TestWorkerPoolEdgeCases` class with tests for:
- Sequential processing waits for active workers
- Sequential processing timeout
- Parallel dispatch with unavailable workers
- Worker pool termination on timeout

```python
class TestWorkerPoolEdgeCases:
    """Tests for worker pool edge cases."""

    def test_process_sequential_waits_indefinitely(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_sequential waits for workers to become available."""
        mock_issue.priority = "P0"

        # Simulate workers that never finish
        type(orchestrator.worker_pool).active_count = property(lambda self: 999)  # type: ignore[method-assign,assignment]

        mock_future: Future[WorkerResult] = Future()
        orchestrator.worker_pool.submit.return_value = mock_future  # type: ignore[attr-defined]

        timeout_reached = [False]

        def mock_wait(*args: object, **kwargs: object) -> Future[WorkerResult]:
            timeout_reached[0] = True
            raise TimeoutError("Timeout")

        mock_future.result = mock_wait

        with patch("time.sleep"):
            try:
                orchestrator._process_sequential(mock_issue)
            except TimeoutError:
                pass

        assert timeout_reached[0]

    def test_wait_for_completion_terminates_on_timeout(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_wait_for_completion terminates all processes on timeout."""
        orchestrator.parallel_config.orchestrator_timeout = 1

        type(orchestrator.worker_pool).active_count = property(lambda self: 1)  # type: ignore[method-assign,assignment]
        orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch("time.time") as mock_time:
            mock_time.side_effect = [0, 0.5, 1.5, 2.5]
            with patch("time.sleep"):
                orchestrator._wait_for_completion()

        orchestrator.worker_pool.terminate_all_processes.assert_called_once()  # type: ignore[attr-defined]

    def test_wait_for_completion_waits_for_merges(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_wait_for_completion waits for pending merges after workers."""
        type(orchestrator.worker_pool).active_count = property(lambda self: 0)  # type: ignore[method-assign,assignment]

        # Merge coordinator has pending merges
        merge_completed = [False]

        def mock_wait(*args: object, **kwargs: object) -> bool:
            merge_completed[0] = True
            return True

        orchestrator.merge_coordinator.wait_for_completion = mock_wait  # type: ignore[method-assign]
        orchestrator.merge_coordinator.merged_ids = ["BUG-001"]  # type: ignore[misc]
        orchestrator.merge_coordinator.failed_merges = []  # type: ignore[misc,assignment]

        with patch.object(orchestrator, "_complete_issue_lifecycle_if_needed"):
            orchestrator._wait_for_completion()

        assert merge_completed[0]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestWorkerPoolEdgeCases -v`
- [ ] Coverage increases to at least 76% (cover timeout and wait paths)

### Phase 3: Overlap Detection and Deferred Issues (Target: +10 statements)

#### Overview
Add tests for overlap detection and deferred issue re-queueing (ENH-143).

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add `TestOverlapDetection` class with tests for:
- Overlap detection before dispatch
- Deferring overlapping issues
- Re-queueing when overlap clears
- Unregistration on completion

```python
class TestOverlapDetection:
    """Tests for overlap detection and deferred issue handling (ENH-143)."""

    def test_process_parallel_checks_overlap_when_enabled(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_parallel checks for overlaps when detection enabled."""
        orchestrator.parallel_config.overlap_detection = True
        orchestrator.parallel_config.serialize_overlapping = True

        # Create mock overlap detector
        mock_detector = MagicMock()
        mock_detector.check_overlap.return_value = ["BUG-001"]  # Existing overlap
        orchestrator.overlap_detector = mock_detector

        orchestrator._process_parallel(mock_issue)

        # Should check overlap
        mock_detector.check_overlap.assert_called_once()

    def test_process_parallel_defers_overlapping_issues(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_process_parallel defers overlapping issues when configured."""
        orchestrator.parallel_config.overlap_detection = True
        orchestrator.parallel_config.serialize_overlapping = True

        mock_detector = MagicMock()
        mock_detector.check_overlap.return_value = ["BUG-001"]  # Has overlap
        orchestrator.overlap_detector = mock_detector

        orchestrator._process_parallel(mock_issue)

        # Should defer the issue (not submit)
        orchestrator.worker_pool.submit.assert_not_called()  # type: ignore[attr-defined]
        assert len(orchestrator._deferred_issues) == 1

    def test_on_worker_complete_unregisters_from_detector(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete unregisters issue from overlap detector."""
        orchestrator.parallel_config.overlap_detection = True
        mock_detector = MagicMock()
        orchestrator.overlap_detector = mock_detector

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        orchestrator._on_worker_complete(result)

        mock_detector.unregister_issue.assert_called_once_with("BUG-001")

    def test_on_worker_complete_requeues_deferred_issues(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete re-queues issues that were waiting on this one."""
        orchestrator.parallel_config.overlap_detection = True
        mock_detector = MagicMock()
        mock_detector.get_waiting_on.return_value = ["BUG-002"]
        orchestrator.overlap_detector = mock_detector

        # Add a deferred issue
        mock_deferred = MagicMock(spec=IssueInfo)
        mock_deferred.issue_id = "BUG-002"
        orchestrator._deferred_issues.append(mock_deferred)

        result = WorkerResult(
            issue_id="BUG-001",
            success=True,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
        )

        with patch.object(orchestrator, "_process_parallel"):
            orchestrator._on_worker_complete(result)

        # Should re-queue the deferred issue
        mock_detector.get_waiting_on.assert_called_once_with("BUG-001")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestOverlapDetection -v`
- [ ] Coverage increases to at least 78% (cover lines 668-683, 696-698, 756-772)

### Phase 4: Interrupted Worker Handling (Target: +5 statements)

#### Overview
Add tests for interrupted worker handling (ENH-036).

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add `TestInterruptedWorkers` class with tests for:
- Interrupted workers not marked as failed
- Interrupted issues tracked separately
- Interrupted handling in sequential processing

```python
class TestInterruptedWorkers:
    """Tests for interrupted worker handling (ENH-036)."""

    def test_on_worker_complete_tracks_interrupted(
        self, orchestrator: ParallelOrchestrator
    ) -> None:
        """_on_worker_complete tracks interrupted workers separately."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            interrupted=True,
            error="Worker interrupted",
        )

        orchestrator._on_worker_complete(result)

        # Should track in interrupted list, not mark as failed
        assert "BUG-001" in orchestrator._interrupted_issues
        orchestrator.queue.mark_failed.assert_not_called()  # type: ignore[attr-defined]

    def test_on_worker_complete_interrupted_with_close_verdict(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_on_worker_complete handles interrupted + close verdict combo."""
        result = WorkerResult(
            issue_id="BUG-001",
            success=False,
            branch_name="parallel/bug-001",
            worktree_path=Path("/tmp/worktree"),
            interrupted=True,
            should_close=True,
            close_reason="interrupted",
        )

        orchestrator._issue_info_by_id["BUG-001"] = mock_issue

        with patch("little_loops.issue_lifecycle.close_issue", return_value=True):
            orchestrator._on_worker_complete(result)

        # Interrupted workers with close verdict should be marked completed
        orchestrator.queue.mark_completed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestInterruptedWorkers -v`
- [ ] Coverage increases to at least 79% (cover lines 702-705, 724-727)

### Phase 5: Main Execution Loop (Target: +15 statements)

#### Overview
Add tests for main execution loop branches including dispatch logic, state saving, and max_issues handling.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add `TestExecuteLoop` class with tests for:
- Dispatch when workers available
- Dispatch when no workers available
- Max issues limit enforcement
- State saving during execution
- Loop completion conditions

```python
class TestExecuteLoop:
    """Tests for main execution loop dispatch logic."""

    def test_execute_dispatches_when_workers_available(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute dispatches issues when workers available."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.get.return_value = mock_issue  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_process_parallel"):
                with patch.object(orchestrator, "_wait_for_completion"):
                    with patch.object(orchestrator, "_report_results"):
                        # Set shutdown after one iteration
                        def set_shutdown(*args: object) -> bool:
                            orchestrator._shutdown_requested = True
                            return False

                        orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                        orchestrator._execute()

        # Should have submitted the issue
        orchestrator.queue.get.assert_called_once_with(block=False)  # type: ignore[attr-defined]

    def test_execute_skips_dispatch_when_no_workers(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute skips dispatch when all workers busy."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 2  # type: ignore[misc]  # All busy
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_wait_for_completion"):
                with patch.object(orchestrator, "_report_results"):
                    # Set shutdown after one iteration
                    def set_shutdown(*args: object) -> bool:
                        orchestrator._shutdown_requested = True
                        return False

                    orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                    orchestrator._execute()

        # Should not call get() when no workers available
        orchestrator.queue.get.assert_not_called()  # type: ignore[attr-defined]

    def test_execute_saves_state_periodically(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute saves state during execution loop."""
        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 1  # type: ignore[attr-defined]
        orchestrator.queue.get.return_value = mock_issue  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=[mock_issue]):
            with patch.object(orchestrator, "_process_parallel"):
                with patch.object(orchestrator, "_save_state") as mock_save:
                    with patch.object(orchestrator, "_wait_for_completion"):
                        with patch.object(orchestrator, "_report_results"):
                            # Set shutdown after one iteration
                            def set_shutdown(*args: object) -> bool:
                                orchestrator._shutdown_requested = True
                                return False

                            orchestrator.queue.empty.side_effect = set_shutdown  # type: ignore[attr-defined]

                            orchestrator._execute()

        # State should be saved during execution
        assert mock_save.called

    def test_execute_respects_max_issues_limit(
        self, orchestrator: ParallelOrchestrator, mock_issue: MagicMock
    ) -> None:
        """_execute stops after processing max_issues."""
        orchestrator.parallel_config.max_issues = 2

        # Create 5 issues
        mock_issues = [MagicMock(spec=IssueInfo) for _ in range(5)]
        for i, m in enumerate(mock_issues):
            m.issue_id = f"BUG-{i:03d}"
            m.priority = "P1"

        orchestrator.queue.empty.return_value = False  # type: ignore[attr-defined]
        orchestrator.queue.add_many.return_value = 5  # type: ignore[attr-defined]

        # Track processed count
        processed = []

        def mock_process(issue: MagicMock) -> None:
            processed.append(issue.issue_id)
            if len(processed) >= 2:
                orchestrator._shutdown_requested = True

        orchestrator.queue.get.side_effect = mock_issues  # type: ignore[attr-defined]
        orchestrator.worker_pool.active_count = 0  # type: ignore[misc]
        orchestrator.merge_coordinator.pending_count = 0  # type: ignore[misc]

        with patch.object(orchestrator, "_scan_issues", return_value=mock_issues):
            with patch.object(orchestrator, "_process_parallel", side_effect=mock_process):
                with patch.object(orchestrator, "_wait_for_completion"):
                    with patch.object(orchestrator, "_report_results"):
                        orchestrator._execute()

        # Should have processed exactly 2 issues
        assert len(processed) == 2
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestExecuteLoop -v`
- [ ] Coverage increases to at least 80% (cover lines 567-595)

### Phase 6: Sequential Processing Error Handling (Target: +4 statements)

#### Overview
Add tests for sequential processing error handling paths.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add tests to `TestMergeSequential` for:
- Sequential merge failure marking
- Exception handling in sequential processing

```python
def test_merge_sequential_marks_failed_on_error(
    self, orchestrator: ParallelOrchestrator
) -> None:
    """_merge_sequential marks issue as failed when merge not in merged_ids."""
    result = WorkerResult(
        issue_id="BUG-001",
        success=True,
        branch_name="parallel/bug-001",
        worktree_path=Path("/tmp/worktree"),
    )

    # Merge not successful (not in merged_ids)
    orchestrator.merge_coordinator.merged_ids = []  # type: ignore[misc]

    orchestrator._merge_sequential(result)

    orchestrator.queue.mark_failed.assert_called_once_with("BUG-001")  # type: ignore[attr-defined]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py::TestMergeSequential -v`
- [ ] Coverage increases (cover lines 656-658)

## Testing Strategy

### Unit Tests
- New test classes grouped by functionality
- Mock all external dependencies (WorkerPool, MergeCoordinator, git operations)
- Use `MagicMock()` for flexibility
- Test both success and failure paths

### Integration Considerations
- Tests are integration-marked (pytestmark = pytest.mark.integration)
- Use fixtures for consistent setup
- Clean up mocks in teardown

## References

- Original issue: `.issues/enhancements/P1-ENH-209-improve-orchestrator-py-test-coverage.md`
- Source file: `scripts/little_loops/parallel/orchestrator.py`
- Test file: `scripts/tests/test_orchestrator.py`
- Similar improvements:
  - ENH-207: `issue_manager.py` to 87%
  - ENH-208: `merge_coordinator.py` to 80%
- Test patterns: `scripts/tests/test_merge_coordinator.py:1688-1767` (thread lifecycle)
- Signal handling: `scripts/tests/test_orchestrator.py:241-293`
- Concurrency tests: `scripts/tests/test_priority_queue.py:558-585`
