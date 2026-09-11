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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- **Files to Modify**:
  - `scripts/little_loops/transport.py` — reap-block guard (line ~1105: `if not reader.forwarded_any and elapsed < rescan_s:`) compared against the new immediate-EOF window instead; new `_FANIN_IMMEDIATE_EOF_S` module constant alongside `_FANIN_CONNECT_TIMEOUT`/`_FANIN_MAX_BACKOFF_S` under the `# FEAT-3323: SseBridge (ll-artifact serve) constants.` header (transport.py:87-92); `_fan_in_producer_sockets` docstring "dies within one `rescan_s` of connecting" (transport.py:1080-1084) reworded to the new window
  - `scripts/tests/test_feat3323_sse_bridge.py` — rewrite `test_producer_at_max_clients_backs_off_sub_linearly` (:323-348): the two-window `second_window_rejections < 10` assertion (:344) becomes a ≥3-window decay-shape comparison
- **Dependent Files (Callers/Importers)**:
  - `scripts/little_loops/cli/artifact/serve.py:34,193` — only construction path of `SseBridge`/`serve_sse_bridge`; unchanged by the fix but its blast radius
  - `scripts/little_loops/cli/loop/runner.py:541` — consumes `get_stats().get("client_rejections", 0)` into loop-run log suffixes; today that counter balloons at rescan cadence per at-cap producer — after the fix it flattens, changing what operators see in that log line (no code change needed)
  - `scripts/little_loops/config/features.py:1318` — `BridgeEventsConfig.rescan_s: float = 2.0` feeds the fan-in thread arg (transport.py:1301); unchanged
- **Conventions in Force**:
  - Rate-limit/threshold windows are dedicated module constants sized independently of the loop's poll period, never the poll period itself — evidence: `_REJECT_LOG_INTERVAL_SEC = 5.0` (transport.py:66) compared as `now - last_log_ts >= _REJECT_LOG_INTERVAL_SEC` inside loops that poll at `_ACCEPT_POLL_TIMEOUT = 1.0` / `_CLIENT_QUEUE_POLL_TIMEOUT = 0.5`; the current `elapsed < rescan_s` guard is the one site in the file violating this rule
  - Backoff constants spell seconds with an `_S` suffix and live as module constants under a component header — `_FANIN_MAX_BACKOFF_S` (transport.py:92), `_WEBHOOK_RETRY_BASE_S`/`_WEBHOOK_RETRY_MAX_S` (:76-77); the `_SEC` spelling exists only in the older log-interval constants (:65-66), so `_FANIN_IMMEDIATE_EOF_S` follows the backoff-family spelling
  - Every backoff site owns its own `min(base * 2^n, cap)` expression; no shared utility exists — asserted deliberate in the `compute_backoff_s()` docstring (queue_store.py:194-197)
  - transport.py docstrings cite FEAT-3323 design bullets via `§ <Section> → <bullet>` markers — `§ Fan-in → Backoff` at transport.py:958, 969, 1082; keep the marker on the reworded flap sentence
- **Mirror sites describing the (currently dead) backoff contract — must move with the fix or they keep documenting the unsatisfiable `rescan_s` window**:
  - `scripts/little_loops/config-schema.json:1730` — `rescan_s` description: "Also the base of the per-path connect-then-immediate-EOF backoff (doubles per consecutive flap, capped at 60s)"
  - `docs/reference/API.md:11197` — Fan-in paragraph: "A reader that dies within one `rescan_s` of connecting without forwarding a single line (a producer at `max_clients` accepting-then-closing) marks its path 'flapping'"
  - `docs/reference/CONFIGURATION.md:1752` — `events.bridge.rescan_s` row repeats the schema text verbatim
- **Tests**:
  - `scripts/tests/test_feat3323_sse_bridge.py` — primary file: `TestSseBridgeFanIn` (:197), the failing test (:323), `_make_config` seam (:105, takes `rescan_s`), holder-socket pattern (:328-330, raw `socket.socket(AF_UNIX)` occupying the `max_clients=1` slot + `_wait_until(lambda: _client_count(producer) == 1)`), teardown order bridge → holder → producer (:345-348)
  - `scripts/tests/test_transport.py` — `test_max_clients_cap_rejects_extra_connection` (:512) and `test_rejection_logging_is_rate_limited` (:543) pin the producer-side rejection behavior the fix must not disturb
  - `scripts/tests/test_config.py:2537-2550` and `scripts/tests/test_config_schema.py:842-847` — pin `rescan_s` default 2 / `max_clients` default 8; unaffected (they assert defaults, not the description text)
- **Documentation**: `docs/ARCHITECTURE.md:630` describes the fan-in pipeline at behavior level with no window mention — verify after the fix, likely no edit needed
- **Configuration**: no `events.bridge` override exists in `.ll/ll-config.json` (this project runs on code defaults); `rescan_s` default originates in `BridgeEventsConfig` (features.py:1318)

### Wiring Findings

_Wiring pass added by `/ll:wire-issue` — 2026-09-10 — 3-agent tracing (caller/importer, side-effect, test-gap); every mapped path grep-confirmed:_

- **Dependent Files (Callers/Importers) — verified, no edit needed**: `scripts/little_loops/__init__.py:68-76` re-exports only unchanged transport symbols (`SseBridge`/`serve_sse_bridge` are not package-level exports); `scripts/little_loops/events.py:23` and `scripts/little_loops/cli/loop/lifecycle.py:720` import `Transport`/`wire_transports` only; `scripts/little_loops/cli/artifact/__init__.py` (:21-23 docstring, :50 import, :189 subparser registration, :212-213 dispatch) describes the fan-in at behavior level with no backoff/window text; `scripts/little_loops/config/core.py:990-993` `to_dict()` serializes `rescan_s` as a value only; `scripts/little_loops/templates/dashboard.llat/manifest.yaml:44` references the serve path without backoff semantics
- **Mirror site beyond the three named above**: `.issues/features/P3-FEAT-3323-live-event-stream-substrate-localhost-sse-bridge-over-the-eventbus.md` — the `§ Fan-in → Backoff` source that the transport.py docstring markers (:958, :969, :1082) cite — describes the flap window as `rescan_s`-relative in five places (Backoff design bullet :239-253, Tests bullet :631-635, config-key table :726, Implementation Step 4 :748-751, Resolved Decisions :935-937); decide living-mirror reword vs historical record (issue files carry Session Logs and dated decisions, so historical-record is defensible)
- **Tests (update/re-verify)**: `scripts/tests/test_feat3323_sse_bridge.py:302` — `test_producer_eof_then_reconnect_on_next_rescan`: its first producer never forwards a line, so post-fix its EOF death classifies as a flap — the doubling branch engages (0.05→0.1) and `state.warned` latches; still expected to pass inside its 3.0s `_wait_until` budget, but must be re-run and its name/docstring ("reconnect_on_next_rescan") checked for semantic drift
- **Tests (new, optional coverage)**: no test anywhere asserts the warning, the non-flap death reset (`state.interval = rescan_s`, transport.py:1115), or the `_on_forward` reset (:1145-1151) — candidates in `TestSseBridgeFanIn` following the `caplog.at_level(logging.WARNING, logger="little_loops.transport")` + substring-filter convention of `test_transport.py:562-582`; filter on "closed the connection immediately", not "max_clients" — the producer-side rejection warning shares that substring on the same logger
- **Verified no-edit**: `docs/reference/CLI.md:5014-5090` (ll-artifact serve section covers fan-in/max_clients/seeding/exit codes, no backoff semantics), `docs/reference/EVENT-SCHEMA.md:1699-1704` (`client_rejections` contract, no rate claim), `serve.py` CLI help text, `BridgeEventsConfig` docstring (features.py:1299-1330), `.ll/ll-config.json` (no `events.bridge` override — re-verified); no consumer of `client_rejections` exists in `hooks/`, `skills/`, `commands/`, `agents/`, or loop YAMLs beyond `cli/loop/runner.py:541`; informational — `.issues/enhancements/P1-ENH-3416-...md:270` cites `transport.py:1106` as a backoff example (currently dead code; becomes accurate post-fix)

## Program Design

### Signatures

- `_fan_in_producer_sockets(socket_path: Path, out: Queue[bytes], stop: threading.Event, rescan_s: float = 2.0, *, readers: dict[Path, _ProducerReader] | None = None, on_drop: Callable[[], None] | None = None) -> None` (transport.py:1060, existing — reap-block guard change only)
- `_FANIN_IMMEDIATE_EOF_S: float` (transport.py, **new** module constant) — dedicated connected_at-relative immediate-EOF window, sized > one `rescan_s` so a first-rescan reap of a connect-then-EOF reader qualifies (exact value is an implementation decision, e.g. `max(2.0, 2 * rescan_s)`)
- `_FANIN_MAX_BACKOFF_S = 60.0` (transport.py:92, existing cap — unchanged)
- `_FanInPathState` (transport.py:968, existing — slots unchanged)

### Call Path

`SseBridge` fan-in thread (`threading.Thread(target=_fan_in_producer_sockets, ...)` at transport.py:1300-1301) -> reap block -> flap classification (`elapsed < _FANIN_IMMEDIATE_EOF_S`) -> `state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)` -> `_candidate_producer_paths()` probe gated by `state.next_attempt` (line 1124)

`test_producer_at_max_clients_backs_off_sub_linearly` (test_feat3323_sse_bridge.py:323) -> sample `producer.get_stats()["client_rejections"]` across ≥3 windows -> assert window N+1 < window N (decay shape)

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- The flap classifier engages: in `_fan_in_producer_sockets`'s reap block (transport.py:1090-1117), `elapsed = now - reader.connected_at` is compared against the new dedicated `_FANIN_IMMEDIATE_EOF_S` window (connected_at-relative), not against `rescan_s`. The window must exceed one loop detection period — death is detected only on the rescan *after* `stop.wait(timeout=rescan_s)` (transport.py:1162), so a first-rescan reap of a connect-then-EOF reader lands at `elapsed >= rescan_s` and must still qualify
- Doubling/cap/reset semantics are unchanged once reachable: `state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)` (transport.py:1106), `state.next_attempt` probe gating (:1117, :1124), `_on_forward` reset to `rescan_s` on first forwarded line (:1145-1151), non-flap death resets to `rescan_s` (:1115)
- The "closed the connection immediately; at max_clients?" warning (transport.py:1108-1112) logs once per flapping path via the `state.warned` latch — dead code today, observable after the fix
- `test_producer_at_max_clients_backs_off_sub_linearly` (test_feat3323_sse_bridge.py:323-348) asserts decay shape — rejections in window N+1 < window N across ≥3 sampled windows — instead of the absolute `second_window_rejections < 10` (:344); verified by `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -k backs_off_sub_linearly -v`
- Mirror sites reworded to the new window so none still documents the `rescan_s`-relative flap rule: transport.py docstring (:1080-1084), config-schema.json `rescan_s` description (:1730), API.md Fan-in paragraph (:11197), CONFIGURATION.md `events.bridge.rescan_s` row (:1752)
- No regression in producer-side rejection behavior: `python -m pytest scripts/tests/test_transport.py -k "max_clients or rejection" -v` passes unchanged; full gate `python -m pytest scripts/tests/` exits 0
- Timing-robustness constraints for the rewritten test (suite conventions, evidence: `_wait_until` docstring test_transport.py:94; raised-budget comments test_feat3323_sse_bridge.py:210-231): `_wait_until` is for setup conditions only (holder-socket occupancy), never for measurement windows; window boundaries use `time.monotonic()` deadlines; budgets carry load-justifying comments (CI unit runner is 4-CPU vs 14 local; B1 forensics measured a flat 9-10 rejections/s over 6 one-second windows, thoughts/ci-unit-test-failures-2026-09-10.md §B1); real time + `_make_config` knobs are the transport-test idiom — no test in the suite patches a transport.py module constant (constant-patching is the fsm.executor convention, test_fsm_executor.py:7836); the test stays unmarked (no `integration`/`slow` mark) so it runs in the CI unit gate

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Re-verify `scripts/tests/test_feat3323_sse_bridge.py:302` (`test_producer_eof_then_reconnect_on_next_rescan`) after the guard change — its never-forwarding reader now classifies as a flap (doubling engages, `state.warned` latches); re-run it and touch up name/docstring if the "reconnect_on_next_rescan" semantics drift
- Decide FEAT-3323 design-doc mirror treatment — `.issues/features/P3-FEAT-3323-live-event-stream-substrate-localhost-sse-bridge-over-the-eventbus.md` (§ Fan-in → Backoff :239-253 plus :631-635, :726, :748-751, :935-937) still documents the flap window as `rescan_s`-relative; reword to the `_FANIN_IMMEDIATE_EOF_S` window or record the file as a historical design record
- Optional coverage in `TestSseBridgeFanIn` (follows the caplog convention of `test_transport.py:562-582`): warning-fires-once-per-path latch; non-flap death reset; `_on_forward` reset

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
- `/ll:wire-issue` - 2026-09-11T00:08:42 - `38e69540-569a-4d83-90fc-f4d237d70095.jsonl`
- `/ll:refine-issue` - 2026-09-10T22:52:59 - `748bc362-b07a-4742-bc35-52128c70dda1.jsonl`
- `/ll:format-issue` - 2026-09-10T21:53:10 - `c062bf88-70c8-43b9-ac0c-360218fcb6ff.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -k backs_off_sub_linearly -v` passes, asserting rejections in window N+1 < window N across ≥3 sampled windows with `rescan_s=0.05` and an occupied `max_clients=1` producer
- Doubling is live: consecutive flap rejections of one path produce monotonically decreasing per-window counts (interval growth toward `_FANIN_MAX_BACKOFF_S`), not the flat ~rescan-cadence accumulation measured in B1
- The "closed the connection immediately; at max_clients?" warning logs exactly once per flapping path (`state.warned` latch, transport.py:1108-1112)
- Interval resets to `rescan_s` on first forwarded line (`_on_forward`, transport.py:1145-1151) and on a non-flap reader death (:1115) — existing semantics preserved
- Mirror documentation matches the new window: transport.py `_fan_in_producer_sockets` docstring, config-schema.json `rescan_s` description, API.md Fan-in paragraph, CONFIGURATION.md `events.bridge.rescan_s` row — none still describes the flap threshold as `rescan_s`-relative
- `python -m pytest scripts/tests/` exits 0 (the authoritative CI gate per CLAUDE.md), with `test_transport.py` rejection/cap tests passing unchanged
