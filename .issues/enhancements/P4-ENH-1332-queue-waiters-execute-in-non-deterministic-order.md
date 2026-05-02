---
captured_at: "2026-05-02T19:56:20Z"
discovered_date: "2026-05-02"
discovered_by: capture-issue
decision_needed: false
---

# ENH-1332: `--queue` waiters execute in non-deterministic order

## Summary

When two or more `ll-loop run --queue` processes are waiting for the same scope, they are all released simultaneously when the running loop finishes. They race to call `acquire()`, so execution order is determined by OS scheduling, not by the time each process was enqueued. The `.queue/*.json` entries record queue membership for dashboard display but are never consulted to enforce FIFO ordering.

## Motivation

Users who start queued loops expect them to run in the order they were submitted — especially in scripted pipelines or multi-tab workflows where the submission sequence has semantic meaning (e.g., "run A, then B, then C" in that order). The current race-based dispatch violates that expectation silently.

## Current Behavior

1. Loop A holds the scope lock.
2. Loops B and C start with `--queue`; both enter `wait_for_scope`, polling every second.
3. Loop A finishes; `release()` removes its lock file.
4. On the next poll tick, B and C both see `conflict is None` and both call `acquire()`.
5. `acquire()` uses `fcntl.flock(LOCK_EX)` on `.acquire.lock` — one wins, one retries.
6. Which one wins is determined by OS lock-grant order, not enqueue time.

The comment at `cli/loop/run.py:246` acknowledges this: *"when N waiters are released simultaneously, only one wins acquire(); losers loop back and wait again rather than exiting."*

## Expected Behavior

Waiters acquire the scope lock in the order they were enqueued (FIFO). The process that called `wait_for_scope` first should be the first to run after the active loop finishes.

## Proposed Solution

Use the existing `.queue/<id>.json` files (already written at `run.py:231–242`) as the ordering source:

1. Each queue entry already contains `enqueuedAt` (ISO 8601 timestamp).
2. Before calling `acquire()`, each waiter reads all `.queue/*.json` files, sorts by `enqueuedAt`, and checks whether its own `entry_id` is the earliest entry.
3. If it is the earliest, it attempts `acquire()`.
4. If it is not, it sleeps and retries — yielding to the earlier waiter.

This keeps the lock mechanism unchanged and adds only a lightweight file-read + sort step to the retry loop. No new files or infrastructure needed.

### Alternative

A simpler approximation: after winning `acquire()`, sleep briefly (e.g., 50 ms) and re-check whether any queue entry with an earlier `enqueuedAt` exists. If so, release and re-queue. This is less rigorous but avoids the coordination read on every poll tick.

## Implementation Steps

1. Extract the queue-entry sort-and-check logic into a helper in `cli/loop/_helpers.py` (e.g., `_is_earliest_waiter(entry_id, queue_dir) -> bool`).
2. In `cmd_run` (`cli/loop/run.py:246–265`), after `wait_for_scope` returns `True`, call `_is_earliest_waiter` before attempting `acquire()`. If not the earliest, sleep 1 s and loop without attempting `acquire()`.
3. Add a test in `scripts/tests/test_cli_loop_queue.py` that enqueues two waiters with different `enqueuedAt` values and asserts the earlier one acquires first.
4. Update `cli/loop/layout.py` (dashboard) if queue position is displayed — no behavioral change, but sort order now reflects true sequence.

## Files to Modify

- `scripts/little_loops/cli/loop/run.py:246–265` — add earliest-waiter check in retry loop
- `scripts/little_loops/cli/loop/_helpers.py` — add `_is_earliest_waiter()` helper
- `scripts/tests/test_cli_loop_queue.py` — add FIFO ordering test

## Acceptance Criteria

- When loops B (enqueued first) and C (enqueued second) are both waiting behind loop A, B always runs before C after A finishes.
- When only one loop is queued, behavior is unchanged.
- Existing `test_cli_loop_queue.py` tests continue to pass.

## Impact

- **Priority**: P4 — cosmetic correctness; non-deterministic ordering rarely causes failures in practice
- **Effort**: Small — adds a file-read/sort step to an existing retry loop
- **Risk**: Low — no change to the lock mechanism itself
- **Breaking Change**: No

## Labels

`loop`, `queue`, `concurrency`, `reliability`

## Session Log
- `/ll:capture-issue` - 2026-05-02T19:56:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c7505b5-ede1-476a-a6b7-a18e3c4c8571.jsonl`
