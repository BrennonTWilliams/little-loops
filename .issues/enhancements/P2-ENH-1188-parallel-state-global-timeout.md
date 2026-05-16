---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076, FEAT-1184]
status: deferred
---

# ENH-1188: Global Parallel-State Timeout and Hung-Worker Detection

## Summary

FEAT-1074 adds `timeout_seconds` at the per-worker level. There is no timeout at the **state** level — if one worker hangs just under its per-worker timeout repeatedly (or if workers are legitimately long but the aggregate is unbounded), the parallel state can run indefinitely. Add an optional `state_timeout_seconds` that bounds the entire state's wall-clock duration, plus a hung-worker detection path that surfaces workers making no progress.

## Current Behavior (as of FEAT-1074 / FEAT-1075)

- `ParallelStateConfig.timeout_seconds` is per-worker only.
- No aggregate / state-level timeout exists.
- A worker that hangs inside a single FSM state makes no progress events, and there is no detection mechanism — the worker runs until `timeout_seconds` fires (if set) or forever (if `None`).

## Expected Behavior

1. `ParallelStateConfig.state_timeout_seconds: int | None = None` — when set, the dispatcher enforces a wall-clock bound across the entire state. When exceeded, any in-flight workers are treated as cancelled (`terminated_by: "state_timeout"`) and the dispatcher proceeds to routing under `fail_mode`.
2. Semantics on expiry:
   - **collect**: in-flight workers are cancelled, their slots populated with `ParallelItemResult(verdict="no", terminated_by="state_timeout", …)`; completed workers keep their results; the verdict is derived from the mix.
   - **fail_fast**: same, but the verdict is `"no"` unconditionally.
3. **Mid-merge-back behavior**: if `state_timeout` fires while the dispatcher is holding `GitLock` for a merge-back, the current merge completes (it's serialized) and then the timeout takes effect before the next merge. Timeout does NOT interrupt a git operation in progress.
4. Schema validation: `state_timeout_seconds <= 0` fails validation; if both `timeout_seconds` (per-worker) and `state_timeout_seconds` (aggregate) are set, `state_timeout_seconds >= timeout_seconds` is required.
5. Hung-worker detection (log-only, no auto-action): if a worker emits no events for `state_timeout_seconds / 4` and `state_timeout_seconds` is set, log a WARNING identifying the worker's item index and seconds-since-last-event. No automatic cancellation on hang — detection only.

## Proposed Solution

1. Add `state_timeout_seconds: int | None = None` to `ParallelStateConfig` schema (FEAT-1074 style round-trip).
2. In `ParallelRunner.run()` (or in the dispatcher in `_execute_parallel_state()`, depending on cleanup-ownership boundary per FEAT-1184), wrap `as_completed()` iteration with a deadline: `timeout = max(0, deadline - time.monotonic())` passed to `future.result(timeout=timeout)`; on `concurrent.futures.TimeoutError`, cancel pending, mark in-flight as `state_timeout`, break loop.
3. Hung-worker detection: instrument the worker event callback path to record last-event-timestamp per worker; a lightweight monitor thread (or periodic check inside the `as_completed` poll loop) compares against `state_timeout_seconds / 4` and logs WARNING. No extra threads required if folded into the existing poll.
4. Document in `docs/generalized-fsm-loop.md` and `docs/reference/parallel-state-v1-scope.md` (ENH-1186).

## Files to Modify

- `scripts/little_loops/fsm/schema.py` — add field + validation
- `scripts/little_loops/fsm/parallel_runner.py` OR `scripts/little_loops/fsm/executor.py` — implement timeout enforcement (location depends on FEAT-1184 cleanup ownership)
- `scripts/tests/test_parallel_runner.py` — add tests for both semantics
- `scripts/tests/test_fsm_schema.py` — add validation test
- `docs/generalized-fsm-loop.md`, `docs/reference/parallel-state-v1-scope.md` — document

## Acceptance Criteria

- `state_timeout_seconds` round-trips through `to_dict`/`from_dict`
- `state_timeout_seconds <= 0` fails validation with a clear error
- `state_timeout_seconds >= timeout_seconds` (when both set) enforced at validation
- Unit test: 4 workers, state timeout 1s, workers each sleep 5s with `timeout_seconds=10` (per-worker would not trip). Assert state_timeout fires, all 4 slots have `terminated_by: "state_timeout"`, `fail_mode: collect` gives verdict `"no"`
- Unit test: mix of completed + state-timed-out workers, `fail_mode: collect` derives verdict correctly (any completed-yes + remaining-state_timeout → `"partial"`)
- Unit test: hung-worker WARNING fires when a worker emits no events for `state_timeout_seconds / 4` — capture log output
- Unit test: `state_timeout` firing mid-merge-back does NOT interrupt the current git operation (instrument `subprocess.run` with a controllable sleep, assert the subprocess completes before timeout cancellation is observed)
- Docs list `state_timeout_seconds` in schema reference and describe the relationship to per-worker `timeout_seconds`

## Impact

- **Priority**: P2 — Without a state-level timeout, a user whose workers collectively hang has no bound on wasted compute. Per-worker timeouts are necessary but not sufficient; the aggregate case is a real production risk.
- **Effort**: Small-to-Medium — schema + timeout wrapping + log-only hung detection + tests
- **Risk**: Low-Medium — firing a state timeout during git ops must not corrupt the repo; the "don't interrupt in-progress git" constraint is the only delicate piece
- **Breaking Change**: No — `None` default preserves existing behavior

## Labels

`fsm`, `parallel`, `timeout`, `safety`

## Related / See Also

- **FEAT-1074** — per-worker `timeout_seconds` field (this issue adds state-level timeout alongside)
- **FEAT-1184** — cleanup ownership contract (constrains where the timeout enforcement lives)
- **ENH-1176** — broader resource-limit family; state timeout is one specific limit
- **ENH-1186** — v1 scope doc updates to include state-level timeout behavior

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. Per-worker timeout alone is insufficient for workers that hang repeatedly or aggregate above a bound. Hung-worker detection is log-only in v1 (auto-action is post-v1).

---

**Open** | Created: 2026-04-20 | Priority: P2
