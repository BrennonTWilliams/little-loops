---
id: BUG-1638
type: BUG
priority: P3
status: open
captured_at: 2026-05-23T12:00:00Z
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
- **Anchor**: `UnixSocketTransport`, around lines 114–203
- The cap `max_clients=8` is a hard-coded dataclass default (around line 136). It is configurable via `config.socket.max_clients` (line ~618) but the default is too low.
- The accept-rejection log path (around lines 183–186) has no rate limiting, unlike the slow-client drop path which already uses `_DROP_LOG_INTERVAL_SEC` (lines ~248–254).
- No metric/counter on `LoopMetrics` for client rejections.

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

1. Change default `max_clients` to 32 in the `UnixSocketTransport` config dataclass.
2. Introduce `_REJECT_LOG_INTERVAL_SEC` (or reuse `_DROP_LOG_INTERVAL_SEC`) and a `_rejections_since_last_log` counter; emit one log per interval with the suppressed count.
3. Add `client_rejections` to the transport's stats and surface it in the loop runner summary.
4. Load-test with 16 concurrent connect attempts under the new default; confirm only one warning per rate-limit window and the counter reflects the rejections.

## Integration Map

### Files to Modify
- `scripts/little_loops/transport.py` — bump `max_clients` default, add reject-log rate limiting, expose `client_rejections` counter on `UnixSocketTransport` stats.
- `scripts/little_loops/fsm/executor.py` — surface `client_rejections` in the loop run summary.

### Dependent Files (Callers/Importers)
- Any module constructing `UnixSocketTransport` or reading its stats — grep `UnixSocketTransport` and `max_clients` to confirm.

### Similar Patterns
- `_DROP_LOG_INTERVAL_SEC` rate-limit pattern in `transport.py` (lines ~248–254) — mirror this for the new reject-log path.
- `LoopMetrics` counter pattern — extend with `client_rejections` consistently with sibling counters.

### Tests
- `scripts/tests/` — add a transport load test that opens >cap connections and asserts (a) the rate-limit window emits one log, (b) the counter increments per rejection.

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
- `/ll:verify-issues` - 2026-05-24T03:55:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86b55377-f187-4e58-9c10-c40043e89408.jsonl`
- `/ll:format-issue` - 2026-05-23T19:20:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76e6c26b-1969-49d5-91a6-84282f7c1ac2.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---

**Open** | Created: 2026-05-23 | Priority: P3
