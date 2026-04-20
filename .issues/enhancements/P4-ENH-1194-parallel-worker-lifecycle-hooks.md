---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075]
---

# ENH-1194: Worker Lifecycle Hooks for Parallel States (before_worker / after_worker / on_worker_error)

## Summary

`ParallelRunner.run()` currently exposes only `on_worker_complete` (added in FEAT-1075 for checkpointing). Users who want to set up per-worker scratch directories, emit start/stop telemetry, or rotate credentials per worker have no general-purpose hook points. Add three optional lifecycle callbacks — `before_worker`, `after_worker`, and `on_worker_error` — so extension authors can instrument fan-out without monkey-patching the runner.

## Current Behavior (as of FEAT-1075)

`ParallelRunner.run()` signature (per FEAT-1075 after the 2026-04-20 edits):

```python
def run(
    self,
    items: list[Any],
    worker_fn: Callable[[Any, int], ParallelItemResult],
    on_worker_complete: Callable[[ParallelItemResult], None] | None = None,
    starting_item_index: int = 0,
) -> ParallelResult: ...
```

Only `on_worker_complete` is surfaced. It fires once the worker future resolves — too late to set up a worker-local temp dir, and insufficient to distinguish graceful completion from exception.

## Expected Behavior

Three new optional callbacks, all invoked from the runner's main thread (matching the `on_worker_complete` contract from FEAT-1075):

- `before_worker(item, item_index) -> None` — invoked just before the worker future is submitted to the executor. Use cases: create worker-scoped scratch dirs, emit a "worker started" event.
- `after_worker(result: ParallelItemResult) -> None` — invoked after `on_worker_complete`, regardless of verdict. Use cases: release per-worker resources, flush telemetry.
- `on_worker_error(item, item_index, exc: BaseException) -> None` — invoked when the worker future raises. Fires *before* `after_worker`. Use cases: structured error reporting, retry scheduling hand-off.

All three exceptions are logged and swallowed (same contract as `on_worker_complete`). Order of invocation per worker:

1. `before_worker` (main thread, pre-submit)
2. ... worker runs in thread/worktree ...
3. If raised: `on_worker_error` → `after_worker` (both main thread)
4. If success: `on_worker_complete` → `after_worker` (both main thread)

## Use Case

**Who**: Extension author writing a parallel-state observability plugin, or a user who needs per-worker scratch isolation in thread mode.

**Context**: FEAT-1189 shared-context mutation contract warns against workers writing to shared paths. A `before_worker` hook lets the extension mint a unique `/tmp/ll-parallel/<run-id>/worker-<i>/` directory and inject it into the worker's environment, eliminating an entire class of races without the runner itself needing to know about temp-dir layout.

**Outcome**: ENH-1177 (tagged observability) can be implemented as a thin wrapper over these hooks instead of being baked into the runner.

## Proposed Solution

1. Extend `ParallelRunner.run()` signature with three new optional parameters. Default `None`.
2. Invoke each from the runner's main thread at the documented point.
3. Wrap each hook call in `try/except BaseException as e: logger.exception(...)` — hook failures never fail the fan-out.
4. Document order and thread-of-invocation in `docs/generalized-fsm-loop.md` parallel-state chapter.

## API / Interface

```python
def run(
    self,
    items: list[Any],
    worker_fn: Callable[[Any, int], ParallelItemResult],
    on_worker_complete: Callable[[ParallelItemResult], None] | None = None,
    before_worker: Callable[[Any, int], None] | None = None,
    after_worker: Callable[[ParallelItemResult], None] | None = None,
    on_worker_error: Callable[[Any, int, BaseException], None] | None = None,
    starting_item_index: int = 0,
) -> ParallelResult: ...
```

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — add the three hook params, dispatch from main thread
- `scripts/tests/test_parallel_runner.py` — add hook-order test, hook-exception-swallowed test, error-path test
- `docs/generalized-fsm-loop.md` — parallel-state chapter: lifecycle hook table

## Dependencies

- **Hard blockers**: FEAT-1075 (callback-dispatch infra must land first)
- **Soft**: ENH-1177 may want to be refactored onto these hooks once both ship

## Acceptance Criteria

- Three hooks added to `ParallelRunner.run()` with documented order and thread-of-invocation
- All three invoked from the runner's main thread, exceptions logged-and-swallowed
- Test: `before_worker` fires once per item before worker execution
- Test: `on_worker_error` fires only on exception; `after_worker` fires regardless
- Test: a hook that raises does not fail the parallel state or other workers
- Docs enumerate the hook order and the "main-thread invocation, exceptions swallowed" contract

## Impact

- **Priority**: P4 — additive, not required for v1 parallel ship. Nice-to-have for extension authors.
- **Effort**: Small — additive params + 3 tests
- **Risk**: Low — fully backwards-compatible
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `extensibility`, `observability`

## Related / See Also

- **FEAT-1075** — `ParallelRunner` that grows these hooks
- **ENH-1177** — tagged observability (could be refactored to use `before_worker` / `after_worker`)
- **FEAT-1174** — per-worker checkpointing (uses `on_worker_complete`, which stays separate)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as a follow-up from the parallel-family review. User requested tracking even though deferred post-v1.

---

**Open** | Created: 2026-04-20 | Priority: P4
