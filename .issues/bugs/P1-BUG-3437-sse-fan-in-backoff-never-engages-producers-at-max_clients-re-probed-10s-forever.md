---
id: BUG-3437
type: BUG
title: SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s
  forever
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3437: SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s forever

## Summary

In _fan_in_producer_sockets (transport.py ~1105) the guard `elapsed < rescan_s` is unsatisfiable because `now` is sampled at loop-top and dead readers are reaped one full `stop.wait(rescan_s)` later, so the doubling branch is dead code and interval resets every cycle. Compare elapsed against a dedicated immediate-EOF window (connected_at-relative), and rewrite test_producer_at_max_clients_backs_off_sub_linearly to assert decay shape (window N+1 < window N) instead of the brittle `< 10` absolute threshold. Fails locally and on CI (B1 in thoughts/ci-unit-test-failures-2026-09-10.md).

## Current Behavior

In `_fan_in_producer_sockets` (scripts/little_loops/transport.py:1060),
`now` is sampled once at loop top (line 1091) and a dead reader is only
reaped on the rescan *after* `stop.wait(timeout=rescan_s)` (line 1162), so
at reap time `elapsed = now - reader.connected_at` (line 1104) is always
≥ `rescan_s`. The flap guard `if not reader.forwarded_any and elapsed <
rescan_s` (line 1105) is therefore unsatisfiable: the doubling branch
(`state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)`, line
1106) is dead code, and the `else` branch (line 1115) resets
`state.interval = rescan_s` every cycle. A producer at `max_clients`
(connect accepted, then immediately closed) is consequently re-probed once
per `rescan_s` forever — at the test's `rescan_s=0.05` that is ~20
connect/reject cycles per second, unbounded — and the "closed the
connection immediately; at max_clients?" warning (lines 1108-1112), living
inside the dead branch, never logs.

## Expected Behavior

A connect-then-immediate-EOF rejection (producer at `max_clients`) should
be classified as a flap: `elapsed` must be compared against a dedicated
immediate-EOF window measured from `reader.connected_at`, not against
`rescan_s` (whose loop sampling makes that comparison unsatisfiable). On
each consecutive flap `state.interval` doubles, capped at
`_FANIN_MAX_BACKOFF_S` (60s, transport.py:92); the "closed the connection
immediately; at max_clients?" warning logs once per path; and the interval
resets to `rescan_s` on the first forwarded line (`_on_forward`, lines
1145-1151) or on a non-flap reader death. The rewritten
`test_producer_at_max_clients_backs_off_sub_linearly` should assert decay
shape — rejections in window N+1 < rejections in window N — instead of the
brittle absolute `< 10` threshold.

## Steps to Reproduce

1. Run
   `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -k backs_off_sub_linearly -v`
   (fails locally and on CI — failure B1 in
   `thoughts/ci-unit-test-failures-2026-09-10.md`).
2. Mechanism: start a `UnixSocketTransport` producer with `max_clients=1`
   and occupy its single slot with a holder socket
   (test_feat3323_sse_bridge.py:327-330), then start an `SseBridge` with
   `_make_config(rescan_s=0.05)` (line 332-334). Every rescan connects,
   gets immediately closed by the at-cap producer (counted in
   `client_rejections`), and the reader dies on EOF.
3. Wait ≥1.5s (test sleeps 0.5s + 1.0s, lines 336-341) and sample
   `producer.get_stats()["client_rejections"]` across two windows.
4. Observe: rejections keep accumulating at full rescan cadence (~20/s)
   in every window — no backoff ever engages — so
   `assert second_window_rejections < 10` (line 344) fails.

## Root Cause

- **File**: `scripts/little_loops/transport.py`
- **Anchor**: in `_fan_in_producer_sockets()`, reap block (lines 1090-1117); guard at line 1105
- **Cause**: `now = time.monotonic()` is sampled at loop top (line 1091)
  and reused as `reader.connected_at` for sockets connected that iteration
  (line 1142). Reader death is detected via `reader.thread.is_alive()` only
  on the *next* rescan — one full `stop.wait(timeout=rescan_s)` (line 1162)
  after connect — so `elapsed` at reap time is always ≥ `rescan_s`. The
  flap classifier conflates the loop's detection granularity (`rescan_s`
  as the wait period) with the classification threshold (`rescan_s` as the
  flap window), making the comparison structurally unsatisfiable.

## Program Design

### Signatures

- `_fan_in_producer_sockets(socket_path: Path, out: Queue[bytes], stop: threading.Event, rescan_s: float = 2.0, *, readers: dict[Path, _ProducerReader] | None = None, on_drop: Callable[[], None] | None = None) -> None` (transport.py:1060, existing — reap-block guard change only)
- `_FANIN_IMMEDIATE_EOF_S: float` (transport.py, **new** module constant) — dedicated connected_at-relative immediate-EOF window, sized > one `rescan_s` so a first-rescan reap of a connect-then-EOF reader qualifies (exact value is an implementation decision, e.g. `max(2.0, 2 * rescan_s)`)
- `_FANIN_MAX_BACKOFF_S = 60.0` (transport.py:92, existing cap — unchanged)
- `_FanInPathState` (transport.py:968, existing — slots unchanged)

### Call Path

`SseBridge` fan-in thread (`threading.Thread(target=_fan_in_producer_sockets, ...)` at transport.py:1300-1301) -> reap block -> flap classification (`elapsed < _FANIN_IMMEDIATE_EOF_S`) -> `state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)` -> `_candidate_producer_paths()` probe gated by `state.next_attempt` (line 1124)

`test_producer_at_max_clients_backs_off_sub_linearly` (test_feat3323_sse_bridge.py:323) -> sample `producer.get_stats()["client_rejections"]` across ≥3 windows -> assert window N+1 < window N (decay shape)

## Impact

- **Priority**: P1 - red on the local unit suite and CI
  (`python -m pytest scripts/tests/` gate) today; beyond the failing test,
  the unbounded re-probe burns a connect/accept/reject cycle per rescan per
  at-cap producer for as long as the bridge runs, and the `max_clients`
  warning the operator would rely on never logs.
- **Effort**: Small - one guard comparison plus one module constant in
  `_fan_in_producer_sockets`, and a rewrite of one test's assertion from an
  absolute threshold to a decay-shape comparison.
- **Risk**: Low - change is confined to the flap-classification branch;
  non-flap deaths still reset `state.interval = rescan_s` and the
  `_on_forward` reset path is untouched. The timing-based test rewrite
  needs enough windows to stay robust on a loaded CI runner.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P1


## Session Log
- `/ll:format-issue` - 2026-09-10T21:53:10 - `c062bf88-70c8-43b9-ac0c-360218fcb6ff.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
