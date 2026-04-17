# ENH-1148: 429 Resilience — Heartbeat Tests Executor Suite — Management Plan

**Date**: 2026-04-17
**Action**: improve
**Confidence**: 80/100 (gate threshold 70 — passes)

## Summary

Net-new work after refinement is minimal: add one test class `TestRateLimitHeartbeat` with a single cadence test `test_rate_limit_waiting_events_emitted_at_cadence` to `scripts/tests/test_fsm_executor.py`.

Pre-conditions confirmed in-place (ENH-1144 landed):
- `executor.py:66` defines `RATE_LIMIT_WAITING_EVENT`
- `executor.py:1007-1035` implements `_interruptible_sleep(on_heartbeat=...)`
- `executor.py:971-984` emits `RATE_LIMIT_WAITING_EVENT` from `_handle_rate_limit`'s long-wait tier
- `fsm/__init__.py:90-92`/`:146-148` re-exports both constants
- Package-import tests at `:4505-4515` already cover Step 5 of the parent — skipping duplication (option (a) per the issue).

Audit grep confirmed: no `len(events)` bare assertions exist.

## Design decision: real-time vs. mock-time

The issue's spec-style pseudocode patches `little_loops.fsm.executor.time.time`. Rejected: that patch leaks to `persistence._now_ms` (called multiple times per run) and the exact call ordering with a fixed-length array is fragile. Instead, mirror the proven pattern from `test_on_heartbeat_called_during_long_wait` at `:4517-4538`: patch `_RATE_LIMIT_HEARTBEAT_INTERVAL` to a tiny value and let a sub-second `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER` fire the heartbeat during real 100ms ticks. Total test time ~0.3s.

This trades the spec's determinism story for robustness against unrelated `_now_ms` call shifts — the observable contract (event emitted with payload keys) is what matters.

## Implementation Steps

### Phase 0: Write Test (Red)
Insert `TestRateLimitHeartbeat` class at `:4855` (between `TestRateLimitTwoTier` end `:4854` and `TestRateLimitCircuitIntegration` start `:4856`).

The test targets existing landed behavior (ENH-1144) — it will actually go straight to Green since the feature is already implemented. Red-phase validation is documented: if we deleted the `on_heartbeat` callback from `executor.py:973`, the test would fail with `len(waiting) >= 1` assertion.

### Phase 1: Verify
- `python -m pytest scripts/tests/test_fsm_executor.py::TestRateLimitHeartbeat -v`
- `python -m pytest scripts/tests/test_fsm_executor.py -v -k "rate_limit"` — confirm no regression in neighbors
- Full suite: `python -m pytest scripts/tests/`
- `ruff check scripts/` and `python -m mypy scripts/little_loops/`

## Acceptance Criteria
- [ ] `TestRateLimitHeartbeat.test_rate_limit_waiting_events_emitted_at_cadence` passes
- [ ] All existing rate-limit tests continue to pass
- [ ] Payload keys verified: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`
- [ ] Lint and type checks pass
