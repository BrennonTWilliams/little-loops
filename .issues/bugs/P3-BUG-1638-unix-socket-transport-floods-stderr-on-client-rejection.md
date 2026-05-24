---
id: BUG-1638
type: BUG
priority: P3
status: done
captured_at: 2026-05-23T12:00:00Z
completed_at: 2026-05-24T19:22:25Z
discovered_date: 2026-05-23
discovered_by: capture-issue
---

# BUG-1638: `UnixSocketTransport` floods stderr with `rejecting client; max_clients=8 reached`

## Summary

In a single `harness-exploratory-user-eval` run, `UnixSocketTransport` logged ~140 `rejecting client; max_clients=8 reached` warnings across three execute states (~12, ~57, ~70 rejections). The `max_clients=8` default is too low for modern viz/Playwright workflows where a browser session opens multiple SSE/websocket bridges and Playwright spawns fresh contexts. Rejections are silent to the loop runner — no telemetry counter, no surfaced warning — and the warning floods stderr.

## Motivation

- Loss of live UI updates in loop-viz cockpits when a single browser session breaks the 8-client cap.
- Stderr flood drowns out signal during debugging.
- No way for a loop author to discover they're hitting the cap short of grepping stderr.

## Steps to Reproduce

1. Run a loop that opens a loop-viz cockpit driving multiple SSE/websocket bridges (e.g. `ll-loop run harness-exploratory-user-eval`).
2. Allow Playwright (or the viz UI) to spawn 9+ concurrent connections to the `UnixSocketTransport` socket.
3. Tail stderr (or the loop run log) and observe repeated `UnixSocketTransport: rejecting client; max_clients=8 reached` lines — one per rejected attempt, no rate limiting, no summary counter.

## Root Cause

- **File**: `scripts/little_loops/transport.py`
- **Anchor**: `UnixSocketTransport.__init__`, line 136 (constructor parameter default, not a dataclass field)
- The cap `max_clients=8` is the default for the `__init__` parameter. The **config-layer default** also lives in `scripts/little_loops/config/features.py:SocketEventsConfig.max_clients` (line 415) and in `SocketEventsConfig.from_dict()` (line ~420 fallback). Both must be bumped.
- At runtime, `wire_transports()` (transport.py line 619) passes `config.socket.max_clients` to the constructor, so the `SocketEventsConfig` default governs unconfigured deployments.
- The accept-rejection log path (lines 183–190, in `_accept_loop`) has no rate limiting, unlike the slow-client drop path which uses `_DROP_LOG_INTERVAL_SEC = 5.0` (line 48) via `_record_drop()` (lines 235–254).
- There is no `LoopMetrics` class in the codebase. Per-client counters (`dropped_total`, `dropped_since_log`) are plain int attributes on `_SocketClient`. A transport-level stats dict/property on `UnixSocketTransport` would need to be added.

## Current Behavior

`UnixSocketTransport` accepts up to 8 concurrent clients. The 9th and subsequent connection attempts log `UnixSocketTransport: rejecting client; max_clients=8 reached` per attempt with no rate limit. Loop runner has no signal that this is happening.

## Expected Behavior

- Default `max_clients` accommodates modern viz/playwright workflows (≥32).
- Rejection log is rate-limited (one line per interval, with rejected-since-last-log count).
- Loop runner can surface "you are hitting the client cap" in the run summary via a transport stats counter.

## Proposed Solution

1. Bump the dataclass default for `max_clients` from 8 to 32 in `transport.py` (around line 136).
2. Add rate-limiting to the accept-rejection log path (around lines 183–186) mirroring the existing `_DROP_LOG_INTERVAL_SEC` pattern at lines 248–254.
3. Expose a `client_rejections` counter on the transport stats / `LoopMetrics` so the loop runner can include "client cap hit N times" in the run summary.

## Implementation Steps

1. **Bump config default (two locations)**:
   - `scripts/little_loops/config/features.py:SocketEventsConfig` — change `max_clients: int = 8` field default (line 415) and `from_dict()` fallback (line ~420) to `32`.
   - `scripts/little_loops/transport.py:UnixSocketTransport.__init__` — change `max_clients: int = 8` parameter default (line 136) to `32` for callers that construct directly rather than via `wire_transports`.
2. **Add rejection rate-limiting to `transport.py`**:
   - Add `_REJECT_LOG_INTERVAL_SEC = 5.0` module-level constant (alongside `_DROP_LOG_INTERVAL_SEC` at line 48).
   - Add `self._rejections_total: int = 0`, `self._rejections_since_log: int = 0`, `self._last_reject_log_ts: float = 0.0`, `self._first_reject_logged: bool = False` to `UnixSocketTransport.__init__`.
   - Replace the bare `logger.warning(...)` in `_accept_loop` (lines 183–190) with a rate-limited gate mirroring `_record_drop`: fire immediately on first rejection, then suppress and batch until `_REJECT_LOG_INTERVAL_SEC` elapses.
3. **Expose transport stats**:
   - Add `def get_stats(self) -> dict[str, int]: return {"client_rejections": self._rejections_total}` to `UnixSocketTransport`.
   - In `scripts/little_loops/cli/loop/_helpers.py:run_foreground()` (lines 986–1002): after the result is returned, call `transport.get_stats()` (transport is accessible as a local in `run_foreground` or can be returned from `wire_transports`) and append `", {N} client rejections"` to the completion line if `client_rejections > 0`.
4. **Test**: Augment `test_max_clients_cap_rejects_extra_connection` in `scripts/tests/test_transport.py` to assert rate-limited logging (one `caplog` WARNING per window) and `transport.get_stats()["client_rejections"]` equals total rejected count.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — bump `__init__` parameter default for `max_clients` (line 136), add module-level `_REJECT_LOG_INTERVAL_SEC` constant (mirror of `_DROP_LOG_INTERVAL_SEC` at line 48), add transport-level `_rejections_total`/`_rejections_since_log`/`_last_reject_log_ts` fields to `UnixSocketTransport.__init__`, rate-limit the rejection warning in `_accept_loop` (lines 183–190), add `get_stats()` method returning `{"client_rejections": int}`.
- `scripts/little_loops/config/features.py` — bump `max_clients` default in `SocketEventsConfig` (field default at line 415 AND `from_dict` fallback at line ~420) from 8 to 32.
- `scripts/little_loops/cli/loop/_helpers.py` — surface `client_rejections` in the loop completion summary printed by `run_foreground()` (lines 986–1002); call `transport.get_stats()` if the transport is accessible, or thread the count through the result.

Note: `scripts/little_loops/fsm/executor.py` is NOT where the run summary is printed. The terminal output comes from `run_foreground()` in `_helpers.py`; `executor.py:FSMExecutor._finish()` only emits the `loop_complete` event and returns `ExecutionResult` (fields: `final_state`, `iterations`, `terminated_by`, `duration_ms`, `captured`, `error`). Adding a transport-stats field to `ExecutionResult` is optional; printing from `run_foreground()` after checking the transport directly is simpler.

### Dependent Files (Callers/Importers)
- Any module constructing `UnixSocketTransport` or reading its stats — grep `UnixSocketTransport` and `max_clients` to confirm.

### Similar Patterns
- `_DROP_LOG_INTERVAL_SEC = 5.0` (transport.py line 48) + `_record_drop()` (lines 235–254) — the exact pattern to mirror for the rejection-log path. Key: `first_drop_logged` boolean fires immediately on first event; subsequent logs are gate-checked with `now - last_log_ts >= _DROP_LOG_INTERVAL_SEC`; batched count resets to 0 after each timed log.
- `_SocketClient.dropped_total` / `dropped_since_log` / `last_drop_log_ts` / `first_drop_logged` — per-client int attributes (lines 108–111) showing the counter field pattern; add analogous transport-level fields (`_rejections_total`, `_rejections_since_log`, `_last_reject_log_ts`) directly to `UnixSocketTransport` (not `_SocketClient`, since rejections are transport-level not client-level).
- `parallel/orchestrator.py:_maybe_report_status()` (lines 672–683) — simpler `time.time()` throttle pattern without a `first_logged` flag, useful reference for the `get_stats()` aggregation approach.

### Tests
- `scripts/tests/test_transport.py` — existing `test_max_clients_cap_rejects_extra_connection` (lines 459–485) already exercises the rejection path but does not assert on logging or counter value. Augment this test (or add a companion) to assert: (a) only one `WARNING` log matching `"max_clients"` is emitted per rate-limit window when multiple connections are rejected rapidly, and (b) transport `get_stats()["client_rejections"]` reflects the total rejection count.
- Test fixture: use `short_tmp_path` (lines 49–61) not `tmp_path` — required on macOS where `/private/var/folders/...` exceeds AF_UNIX 104-char `sun_path` limit.
- Class guard: `@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available")` (line 345) — apply to any new test class or inherit via `TestUnixSocketTransport`.

### Documentation
- `docs/reference/API.md` (if `UnixSocketTransport` stats are documented) — mention `client_rejections`.

### Configuration
- `config.socket.max_clients` (line ~618 in `transport.py`) — default change only; existing override still wins.

## Impact

- **Priority**: P3 — annoying log flood and a hidden silent-failure mode, but no functional break of the loop itself.
- **Effort**: Small — three localized changes in `transport.py` plus a counter surfaced in the runner summary and one load test.
- **Risk**: Low — change is additive (new counter, new rate-limit) plus a default bump; existing `config.socket.max_clients` overrides preserve behavior for callers that pin it.
- **Breaking Change**: No.

## Critical Files

- `scripts/little_loops/transport.py` — `UnixSocketTransport`
- `scripts/little_loops/fsm/executor.py` — loop runner summary (if surfacing counters there)
- `scripts/tests/` — transport load test

## Verification Plan

Load-test `UnixSocketTransport` with 16 concurrent connect attempts under the new default and confirm:

- All 16 connect successfully under the new default of 32.
- When forced under cap (e.g. `max_clients=4`, 16 connects), only one warning is logged per rate-limit window.
- `client_rejections` counter appears in the transport stats dump.

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 4). Observed lines: 286–297, 749–806, 1686–1754 of `harness-exploratory-user-eval-debug.txt`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `transport`, `logging`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-24T19:14:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8af4f12b-36ed-46dc-8671-77ac3007a4a0.jsonl`
- `/ll:refine-issue` - 2026-05-24T15:30:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2e7bf37-f8f2-40f5-a049-b975a301f9c6.jsonl`
- `/ll:verify-issues` - 2026-05-24T03:55:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86b55377-f187-4e58-9c10-c40043e89408.jsonl`
- `/ll:format-issue` - 2026-05-23T19:20:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76e6c26b-1969-49d5-91a6-84282f7c1ac2.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z
- `/ll:manage-issue` - 2026-05-24T19:22:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Resolution

Fixed in three localized changes:

1. **Bumped `max_clients` default from 8 → 32** in both `transport.py` (`UnixSocketTransport.__init__`) and `config/features.py` (`SocketEventsConfig` dataclass field + `from_dict()` fallback).
2. **Rate-limited rejection logging** — added `_REJECT_LOG_INTERVAL_SEC = 5.0`, transport-level counters (`_rejections_total`, `_rejections_since_log`, `_last_reject_log_ts`, `_first_reject_logged`), and `_record_rejection()` method that mirrors the existing `_record_drop()` pattern: fires immediately on first rejection, then batches with count until the interval elapses.
3. **Exposed `get_stats()`** — returns `{"client_rejections": int}`; surfaced in the `run_foreground()` completion line when count > 0 (e.g. `Loop completed: terminal (12 iterations, 3.4s, 7 client rejections)`).

Tests updated: `test_max_clients_cap_rejects_extra_connection` now asserts `get_stats()["client_rejections"] == 1`; new `test_rejection_logging_is_rate_limited` verifies exactly one WARNING per rate-limit window and correct total counter.

---

**Done** | Created: 2026-05-23 | Completed: 2026-05-24 | Priority: P3
