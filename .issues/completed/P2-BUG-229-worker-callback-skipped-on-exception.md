---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-229: Worker callback skipped on exception; issue stuck in-progress

## Summary

When a parallel worker thread throws an exception, `future.result()` raises in `_handle_completion`, causing the `callback(result)` to never be called. The orchestrator relies on this callback to mark the issue as failed and dequeue the next issue. Without it, the issue remains permanently stuck in `_in_progress`, potentially causing `ll-parallel` to hang indefinitely.

## Location

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Line(s)**: 191-207 (at scan commit: a8f4144)
- **Anchor**: `in method WorkerPool._handle_completion`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/parallel/worker_pool.py#L191-L207)
- **Code**:
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
        result = future.result()   # can raise if worker threw
        callback(result)           # never reached on exception
    except Exception as e:
        self.logger.error(f"Worker completion callback failed: {e}")
    finally:
        with self._callback_lock:
            self._pending_callbacks.discard(issue_id)
```

## Current Behavior

The `_handle_completion` except block catches all exceptions but only logs the error — it does not construct a failure `WorkerResult` or invoke the callback. While `_process_issue` has its own top-level `except Exception` that returns a `WorkerResult(success=False)` (preventing most worker exceptions from propagating to `future.result()`), the callback can still be skipped if:

1. `future.result()` raises a `CancelledError` (e.g., future cancelled during shutdown)
2. The `callback(result)` itself raises an exception (callback failure is conflated with future failure in the except block)

In either case, the orchestrator's completion callback is not invoked with a failure result, which can leave an issue stuck in `_in_progress`.

## Expected Behavior

When `future.result()` raises (e.g., `CancelledError`), a failure `WorkerResult` should be constructed and passed to the callback so the orchestrator can properly handle the failure and continue processing remaining issues.

## Reproduction Steps

1. Run `ll-parallel` with an issue that causes the worker to throw an unhandled exception
2. Observe the issue remains in `_in_progress` forever
3. The orchestrator's main loop stalls because it waits for in-progress issues to complete

## Proposed Solution

In the except block, construct a failure `WorkerResult` and invoke the callback:
```python
except Exception as e:
    self.logger.error(f"Worker completion callback failed: {e}")
    failure_result = WorkerResult(
        issue_id=issue_id,
        success=False,
        error=str(e),
    )
    try:
        callback(failure_result)
    except Exception:
        pass
```

## Impact

- **Severity**: Medium (defensive fix; primary scenario mitigated by _process_issue's own exception handling)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Completed** | Created: 2026-02-06T03:41:30Z | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/worker_pool.py`: Separated `_handle_completion` error handling into two distinct try/except blocks — one for `future.result()` and one for `callback(result)`. When `future.result()` raises, a failure `WorkerResult` is now constructed and passed to the callback so the orchestrator can properly transition the issue out of `_in_progress`.
- `scripts/tests/test_worker_pool.py`: Added 3 tests covering future exception, cancelled future, and callback exception scenarios.

### Verification Results
- Tests: PASS (2458 passed)
- Lint: PASS
- Types: PASS
