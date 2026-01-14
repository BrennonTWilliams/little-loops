# ENH-036: Graceful shutdown - INTERRUPTED verdict for interrupted workers

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-036-graceful-shutdown-unknown-verdict.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

When ll-parallel receives a signal interrupt (Ctrl+C), workers that are mid-operation report failures with `ready_issue verdict: UNKNOWN - No output from ready_issue`. This is confusing because these workers were not actual failures - they were interrupted by user action.

### Key Discoveries
- `output_parsing.py:24` - VALID_VERDICTS tuple only contains: `("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW", "CLOSE")`
- `output_parsing.py:225` - Verdict defaults to "UNKNOWN" when parsing fails or output is empty
- `worker_pool.py:261-277` - UNKNOWN verdict handling generates error message "No output from ready_issue" for empty stdout
- `worker_pool.py:121-145` - `terminate_all_processes()` sends SIGTERM to workers, killing their subprocesses mid-execution
- `orchestrator.py:229-232` - Signal handler sets `_shutdown_requested` flag but workers have no access to it
- `orchestrator.py:549-551` - Timeout triggers `terminate_all_processes()`, killing workers
- `types.py:131-140` - `MergeStatus` enum provides pattern for status enums

### Flow During Shutdown
1. User presses Ctrl+C → SIGINT signal
2. `_signal_handler()` sets `_shutdown_requested = True`
3. Main loop exits, `_wait_for_completion()` starts with timeout
4. If timeout expires, `terminate_all_processes()` kills worker subprocesses
5. Killed processes return empty/partial stdout
6. `parse_ready_issue_output()` returns `verdict: "UNKNOWN"`
7. Worker creates `WorkerResult(success=False, error="ready_issue verdict: UNKNOWN - No output from ready_issue")`
8. Orchestrator counts this as a failure in final report

## Desired End State

Workers that are interrupted during shutdown should:
1. Be identified as interrupted (not failed)
2. Report with a distinct `INTERRUPTED` verdict/status
3. NOT be counted as failures in the final summary
4. Be shown separately in the results as "Interrupted (can retry)"

### How to Verify
1. Run `ll-parallel` with multiple issues
2. Wait for workers to start processing
3. Press Ctrl+C to interrupt
4. Observe that interrupted workers show as "Interrupted" not "Failed"
5. Final summary should show interrupted count separately from failed count

## What We're NOT Doing

- Not adding a formal Verdict enum (keeping string-based approach for backwards compatibility)
- Not changing the parsing strategies in `parse_ready_issue_output()` (INTERRUPTED is detected at worker level, not parsing level)
- Not implementing "graceful completion" where workers finish current operation (out of scope)
- Deferring full state machine for worker status to a future enhancement

## Problem Analysis

The root cause is that when a subprocess is killed during shutdown:
1. The subprocess exits with non-zero return code or produces empty output
2. The parsing system interprets empty output as UNKNOWN verdict
3. The worker pool treats UNKNOWN as a failure
4. There's no way to distinguish "genuinely unparseable output" from "killed during shutdown"

The solution is to:
1. Track whether the orchestrator has requested shutdown (already done via `_shutdown_requested`)
2. Pass shutdown awareness to worker pool so it can detect when processes were killed due to shutdown
3. Create a distinct state for interrupted workers that is NOT counted as failure

## Solution Approach

Add an `interrupted` flag to `WorkerResult` and update the result handling to:
1. Detect when a worker was interrupted during shutdown
2. Mark it with `interrupted=True` instead of `success=False`
3. Report interrupted workers separately in the final summary

## Implementation Phases

### Phase 1: Add `interrupted` flag to WorkerResult

#### Overview
Add `interrupted` field to `WorkerResult` dataclass to distinguish interrupted workers from failures.

#### Changes Required

**File**: `scripts/little_loops/parallel/types.py`
**Changes**: Add `interrupted` boolean field to WorkerResult dataclass

```python
# After line 87 (after close_status: str | None = None)
interrupted: bool = False
```

Also update `to_dict()` and `from_dict()` methods to include the new field.

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/parallel/types.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_types.py -v` (if exists, otherwise skip)

---

### Phase 2: Expose shutdown state to WorkerPool

#### Overview
Allow the worker pool to know when a shutdown has been requested so it can mark killed workers as interrupted.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**:
1. Add `_shutdown_requested` property/method that can be set by orchestrator
2. Update `terminate_all_processes()` to track which issues were terminated during shutdown

```python
# Add to __init__ (after line 86)
self._shutdown_requested = False
self._terminated_during_shutdown: set[str] = set()

# Add property
def set_shutdown_requested(self, value: bool = True) -> None:
    """Set the shutdown flag. Called by orchestrator during shutdown."""
    self._shutdown_requested = value

# Modify terminate_all_processes() to track terminated issues
def terminate_all_processes(self) -> None:
    """Forcefully terminate all active subprocesses."""
    with self._process_lock:
        for issue_id, process in list(self._active_processes.items()):
            if process.poll() is None:
                self.logger.warning(...)
                # Track that this issue was terminated during shutdown
                if self._shutdown_requested:
                    self._terminated_during_shutdown.add(issue_id)
                # ... rest of termination logic
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/parallel/worker_pool.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`

---

### Phase 3: Update worker to create interrupted results

#### Overview
When a worker completes after being terminated during shutdown, create a WorkerResult with `interrupted=True`.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: In `_process_issue()`, check if the issue was terminated during shutdown and return an interrupted result.

The key insight is that we need to check AFTER the subprocess completes if it was terminated during shutdown. The most reliable way is to check if the issue_id is in `_terminated_during_shutdown`.

```python
# After step 2 runs ready_issue (after line 236 return statement)
# Before checking verdict, check if this worker was killed during shutdown

# Check if worker was terminated during shutdown
if issue.issue_id in self._terminated_during_shutdown:
    return WorkerResult(
        issue_id=issue.issue_id,
        success=False,  # Not a success
        interrupted=True,  # But was interrupted
        branch_name=branch_name,
        worktree_path=worktree_path,
        duration=time.time() - start_time,
        error="Interrupted during shutdown",
        stdout=ready_result.stdout,
        stderr=ready_result.stderr,
    )
```

Also update the exception handler at the end of `_process_issue()` to handle interruption there too.

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/parallel/worker_pool.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`

---

### Phase 4: Update orchestrator to propagate shutdown flag

#### Overview
Orchestrator needs to tell the worker pool when shutdown is requested so it can track interrupted issues.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: In `_signal_handler()`, propagate the shutdown flag to worker pool.

```python
def _signal_handler(self, signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully."""
    self._shutdown_requested = True
    # Propagate to worker pool so it can track interrupted workers
    self.worker_pool.set_shutdown_requested(True)
    self.logger.warning(f"Received signal {signum}, shutting down gracefully...")
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/parallel/orchestrator.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`

---

### Phase 5: Update result handling and reporting

#### Overview
Handle interrupted results separately from failures in callbacks and final reporting.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**:

1. Add tracking for interrupted issues in `OrchestratorState` or directly in orchestrator
2. Update `_on_worker_complete()` to handle interrupted results
3. Update `_report_results()` to show interrupted count separately

```python
# Add to __init__ after state management (around line 94)
self._interrupted_issues: list[str] = []

# Update _on_worker_complete() (around line 455)
def _on_worker_complete(self, result: WorkerResult) -> None:
    """Callback when a worker completes."""
    # Handle interrupted workers (not counted as failed)
    if result.interrupted:
        self.logger.info(f"{result.issue_id} was interrupted during shutdown")
        self._interrupted_issues.append(result.issue_id)
        # Don't mark as failed - they can be retried
        return

    # ... rest of existing logic for success/failure/close
```

Update `_report_results()` to show interrupted separately:

```python
# In _report_results(), after showing completed/failed counts
if self._interrupted_issues:
    self.logger.info(f"Interrupted: {len(self._interrupted_issues)} (can retry)")
    for issue_id in self._interrupted_issues:
        self.logger.info(f"  - {issue_id}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/parallel/orchestrator.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`

---

### Phase 6: Add tests for interrupted behavior

#### Overview
Add tests to verify the interrupted handling behavior.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add tests for interrupted flag propagation

```python
class TestTerminateAllProcesses:
    def test_terminate_during_shutdown_tracks_issues(
        self, worker_pool: WorkerPool, mock_logger: MagicMock
    ) -> None:
        """terminate_all_processes() tracks issues when shutdown requested."""
        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.wait.return_value = None

        worker_pool._active_processes["BUG-001"] = mock_process
        worker_pool.set_shutdown_requested(True)

        worker_pool.terminate_all_processes()

        assert "BUG-001" in worker_pool._terminated_during_shutdown
```

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add test for signal handler propagating to worker pool

```python
def test_signal_handler_propagates_to_worker_pool(
    self,
    orchestrator: ParallelOrchestrator,
) -> None:
    """_signal_handler propagates shutdown to worker pool."""
    orchestrator._signal_handler(signal.SIGINT, None)

    assert orchestrator.worker_pool._shutdown_requested is True
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_worker_pool.py::TestTerminateAllProcesses -v`
- [ ] New tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v -k shutdown`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- Test that `WorkerResult.interrupted` defaults to False
- Test that `set_shutdown_requested()` sets the flag correctly
- Test that `terminate_all_processes()` tracks terminated issues when shutdown is requested
- Test that signal handler propagates shutdown flag to worker pool
- Test that interrupted results are not counted as failures

### Integration Tests
- Manual test: Run ll-parallel, interrupt with Ctrl+C, verify output shows "Interrupted" not "Failed"

## References

- Original issue: `.issues/enhancements/P3-ENH-036-graceful-shutdown-unknown-verdict.md`
- MergeStatus enum pattern: `scripts/little_loops/parallel/types.py:131-140`
- Signal handler: `scripts/little_loops/parallel/orchestrator.py:229-232`
- Process termination: `scripts/little_loops/parallel/worker_pool.py:121-145`
- UNKNOWN verdict handling: `scripts/little_loops/parallel/worker_pool.py:261-277`
