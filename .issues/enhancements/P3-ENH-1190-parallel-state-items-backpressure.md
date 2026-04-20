---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075]
---

# ENH-1190: Backpressure for Large `items:` Lists (Streamed Dispatch)

## Summary

FEAT-1075 does not specify whether futures for a parallel state's `items:` list are pre-allocated (one `submit()` per item, up front) or streamed (new items submitted as completed ones free a slot). For small lists (typical case ≤ 50) this doesn't matter. For large lists (thousands of items, e.g., scanning every file in a monorepo through a sub-loop), pre-allocation could hold 10,000+ `Future` objects plus per-item `parent_context` deep-copies in memory simultaneously. Spec and implement a streamed dispatch so memory is bounded by `max_workers`, not `len(items)`.

## Current Behavior (as of FEAT-1075)

The spec implies `as_completed()` iteration over a list of futures, which is consistent with either strategy. The code that lands will likely use the simpler pattern:

```python
futures = [executor.submit(worker, item, i) for i, item in enumerate(items)]
for future in as_completed(futures):
    ...
```

This pre-allocates all futures. For `items` of length N with `max_workers = M`, memory is O(N) not O(M). `parent_context` deep-copies happen only when the worker body starts (inside `worker`), so that's naturally bounded — but the Future objects themselves plus any bookkeeping (item-index slots, results list) scale with N.

## Expected Behavior

Streamed dispatch: only `max_workers` futures live at once. As one completes, the next is submitted. Memory is O(max_workers), not O(len(items)).

Pattern (sketch):

```python
iter_items = enumerate(items)
in_flight: dict[Future, int] = {}
# Seed the pool
for _ in range(max_workers):
    try:
        i, item = next(iter_items)
        in_flight[executor.submit(worker, item, i)] = i
    except StopIteration:
        break

while in_flight:
    done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
    for future in done:
        i = in_flight.pop(future)
        results[i] = future.result()
        try:
            j, next_item = next(iter_items)
            in_flight[executor.submit(worker, next_item, j)] = j
        except StopIteration:
            pass
```

Plus a sanity bound: `len(items)` validated against `ParallelStateConfig.max_items_warning_threshold` (default 1000) — emits a single INFO log saying "fanning out over N items with max_workers=M; streamed dispatch active."

## Proposed Solution

1. Replace the pre-allocation pattern in `ParallelRunner.run()` with the streamed pattern above.
2. Preserve the ordering guarantee (FEAT-1075): `results[i]` still corresponds to `items[i]` regardless of completion order; the streamed loop writes into pre-allocated `results[i]` slots (the list itself is pre-allocated to `len(items)`; that's O(N) in slots but only dict/Result references, not Future objects or context copies).
3. Add optional `max_items_warning_threshold: int = 1000` to `ParallelStateConfig` for the INFO-log threshold. Not a hard cap — that's ENH-1176's scope.
4. Unit test: submit `items` of length 100 with `max_workers=2`; instrument `executor.submit` to count concurrent in-flight futures. Assert it never exceeds 2.

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — streamed dispatch
- `scripts/little_loops/fsm/schema.py` — optional `max_items_warning_threshold` field
- `scripts/tests/test_parallel_runner.py` — concurrency bound + order-preserved-under-streaming tests

## Acceptance Criteria

- `ParallelRunner.run()` uses streamed dispatch: concurrent `submit()` calls never exceed `max_workers`
- Ordering guarantee preserved under streamed dispatch — assert `result.all_results[i].item == items[i]` for all i
- `max_items_warning_threshold` field round-trips and emits an INFO log once when exceeded
- Unit test with 100 items, `max_workers=2`, instruments `executor.submit` and asserts at most 2 concurrent in-flight futures at any moment
- Memory footprint test (optional, may be flaky): fan out over 10000 no-op items with `max_workers=4`; assert `tracemalloc` peak growth is bounded (e.g., < 10 MB) — tag `@pytest.mark.slow` if noisy

## Impact

- **Priority**: P3 — Not a v1 correctness blocker; typical users fan out over < 50 items. Becomes a real issue when the feature is adopted for large-scale batch processing (scanning, bulk refactors).
- **Effort**: Small — one rewrite of the dispatch loop + 1-2 tests
- **Risk**: Low — ordering guarantee must be preserved; test gates it
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `performance`, `memory`

## Related / See Also

- **FEAT-1075** — `ParallelRunner` where the dispatch loop lives
- **ENH-1176** — resource-limit family; hard items-count cap is tracked there
- **ENH-1186** — v1 scope doc; streamed dispatch is worth documenting as a v1 property

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. Dispatch pattern was underspecified; writing down streamed semantics prevents a future memory regression.

---

**Open** | Created: 2026-04-20 | Priority: P3
