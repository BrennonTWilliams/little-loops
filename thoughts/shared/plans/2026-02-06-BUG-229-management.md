# BUG-229: Worker callback skipped on exception - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-229-worker-callback-skipped-on-exception.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `_handle_completion` method in `worker_pool.py:191-207` serves as an intermediary between `Future.add_done_callback` and the orchestrator's `_on_worker_complete` callback. It calls `future.result()` to get the `WorkerResult`, then passes it to the callback.

### Key Discoveries
- `_handle_completion` (worker_pool.py:191-207) catches `Exception` from both `future.result()` and `callback(result)` in the same except block, but only logs -- never constructs a failure `WorkerResult` or invokes the callback
- `_process_issue` (worker_pool.py:209-441) has its own `except Exception` at line 429 that catches worker-level exceptions and returns `WorkerResult(success=False)`, so `future.result()` rarely raises from worker errors
- The two scenarios where callback is skipped: (1) `CancelledError` from `future.result()` when a future is cancelled during shutdown, (2) `callback(result)` itself raises an exception
- The orchestrator's `_on_worker_complete` (orchestrator.py:688-752) is the sole mechanism for calling `queue.mark_failed()` or `queue.mark_completed()` -- if skipped, the issue stays stuck in `_in_progress`
- `WorkerResult` requires 4 positional args: `issue_id`, `success`, `branch_name`, `worktree_path` (types.py:74-77)

## Desired End State

When `future.result()` raises (e.g., `CancelledError`), a failure `WorkerResult` is constructed and passed to the callback so the orchestrator properly handles the failure. When `callback(result)` raises, the error is logged separately so the two failure modes are distinguishable.

### How to Verify
- New test: `_handle_completion` invokes callback with failure `WorkerResult` when `future.result()` raises
- New test: `_handle_completion` logs error when callback itself raises
- Existing tests continue to pass
- Lint and type checks pass

## What We're NOT Doing

- Not changing the orchestrator's `_on_worker_complete` -- it already handles `success=False` results correctly
- Not changing `_process_issue` exception handling -- it's already robust
- Not adding retry logic for failed callbacks -- a single attempt is sufficient
- Not changing the `WorkerResult` dataclass

## Problem Analysis

In `_handle_completion`:
1. `future.result()` at line 201 can raise `CancelledError` (or theoretically other exceptions)
2. When it raises, `callback(result)` at line 202 is never reached
3. The `except` block at line 203-204 only logs, does not invoke the callback with a failure result
4. The `finally` block cleans up `_pending_callbacks`, so `active_count` drops to 0
5. The issue remains in `queue._in_progress` permanently since neither `mark_failed` nor `mark_completed` is called

## Solution Approach

Separate the two failure cases in `_handle_completion`:
1. First, try to get the result from the future
2. If that fails, construct a minimal failure `WorkerResult` and invoke the callback with it
3. If the result is obtained successfully, invoke the callback
4. If the callback itself fails, log that separately (no retry needed -- the failure is in the orchestrator's handler, which is a separate concern)

## Implementation Phases

### Phase 1: Fix `_handle_completion`

#### Overview
Modify the except block to construct a failure `WorkerResult` and invoke the callback when `future.result()` raises. Also separate the error handling for `future.result()` failure vs `callback()` failure.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: Replace `_handle_completion` method (lines 191-207)

```python
def _handle_completion(
    self,
    future: Future[WorkerResult],
    callback: Callable[[WorkerResult], None],
    issue_id: str,
) -> None:
    """Handle worker completion and invoke callback."""
    with self._callback_lock:
        self._pending_callbacks.add(issue_id)
    try:
        try:
            result = future.result()
        except Exception as e:
            self.logger.error(f"Worker future failed for {issue_id}: {e}")
            result = WorkerResult(
                issue_id=issue_id,
                success=False,
                branch_name="",
                worktree_path=Path(),
                error=f"Worker future failed: {e}",
            )
        try:
            callback(result)
        except Exception as e:
            self.logger.error(
                f"Worker completion callback failed for {issue_id}: {e}"
            )
    finally:
        with self._callback_lock:
            self._pending_callbacks.discard(issue_id)
```

Key design decisions:
- `branch_name=""` and `worktree_path=Path()` for the failure result -- these are required fields but have no meaningful value when the future itself failed. The orchestrator's `_on_worker_complete` only uses `result.issue_id`, `result.success`, and `result.error` in the failure path (`queue.mark_failed(result.issue_id)`), so empty values are safe.
- Separate try/except blocks for `future.result()` and `callback(result)` so failures are distinguishable in logs.
- No retry of the callback on failure -- if `_on_worker_complete` raises, that's a bug in the orchestrator, not something we should silently retry.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 2: Add Tests

#### Overview
Add tests covering both failure scenarios: `future.result()` raises and `callback(result)` raises.

#### Changes Required

**File**: `scripts/tests/test_worker_pool.py`
**Changes**: Add tests to `TestWorkerPoolTaskSubmission` class (after the existing `test_handle_completion_tracks_pending_callbacks` test around line 538)

Test 1: `test_handle_completion_invokes_callback_on_future_exception`
- Create a `Future` and set an exception on it (e.g., `CancelledError`)
- Call `_handle_completion` with a mock callback
- Assert the callback was invoked with a `WorkerResult(success=False)` containing the error
- Assert `_pending_callbacks` is cleaned up

Test 2: `test_handle_completion_logs_callback_exception`
- Create a `Future` with a successful result
- Pass a callback that raises an exception
- Assert the error is logged
- Assert `_pending_callbacks` is cleaned up

Test 3: `test_handle_completion_invokes_callback_on_cancelled_future`
- Create a `Future` and cancel it
- Call `_handle_completion` with a mock callback
- Assert the callback was invoked with a failure `WorkerResult`

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v -k "handle_completion"`
- [ ] All worker pool tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Future raises exception -> callback invoked with failure WorkerResult
- Future cancelled -> callback invoked with failure WorkerResult
- Callback raises exception -> error logged, pending_callbacks cleaned up
- Existing tests still pass (regression)

## References

- Original issue: `.issues/bugs/P2-BUG-229-worker-callback-skipped-on-exception.md`
- Bug location: `scripts/little_loops/parallel/worker_pool.py:191-207`
- WorkerResult definition: `scripts/little_loops/parallel/types.py:51-89`
- Callback consumer: `scripts/little_loops/parallel/orchestrator.py:688-752`
- Existing tests: `scripts/tests/test_worker_pool.py:504-538`
- Minimal failure WorkerResult pattern: `scripts/little_loops/parallel/worker_pool.py:429-437`
