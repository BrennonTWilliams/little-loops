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
confidence_score: 100
outcome_confidence: 96
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 24
score_change_surface: 24
---

# BUG-3437: SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s forever

## Summary

In `_fan_in_producer_sockets` (transport.py:1060) the flap guard `elapsed <
rescan_s` (line 1105) is unsatisfiable: `now` is sampled once at loop top,
`reader.connected_at` is overwritten with that same `now`, and a dead reader
is only reaped one full `stop.wait(rescan_s)` later, so `elapsed` at reap time
is always ≥ `rescan_s`. The doubling branch is dead code and the interval
resets every cycle. Fix by measuring the reader's actual lifetime (real
connect time → real thread-exit time) against a small, loop-independent
immediate-EOF constant, and rewrite
`test_producer_at_max_clients_backs_off_sub_linearly` to assert a
deterministic classification signal (the once-per-path warning) plus a
logarithmic rejection bound instead of the brittle absolute `< 10`. Fails
locally and on CI (B1 in `thoughts/ci-unit-test-failures-2026-09-10.md`).

## Current Behavior

In `_fan_in_producer_sockets` (scripts/little_loops/transport.py:1060),
`now` is sampled once at loop top (line 1091) and reused as
`reader.connected_at` for every socket connected that iteration (line 1142,
overwriting the real `time.monotonic()` that `_ProducerReader.__init__` set
at line 964). A dead reader is only detected via `reader.thread.is_alive()`
on the rescan *after* `stop.wait(timeout=rescan_s)` (line 1162), so at reap
time `elapsed = now - reader.connected_at` (line 1104) is always
≥ `rescan_s`. The guard `if not reader.forwarded_any and elapsed < rescan_s`
(line 1105) is therefore unsatisfiable: the doubling branch
(`state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)`, line
1106) is dead code, and the `else` branch (line 1115) resets
`state.interval = rescan_s` every cycle.

A producer at `max_clients` (accept-then-close, transport.py:256-262) is
consequently re-probed once per `rescan_s` forever — B1 forensics measured a
flat 9–10 rejections/s over six one-second windows at the test's
`rescan_s=0.05` — and the "closed the connection immediately; at
max_clients?" warning (lines 1108-1112), living inside the dead branch, never
logs.

## Expected Behavior

A connect-then-immediate-EOF rejection (producer at `max_clients`) is
classified as a flap using the reader's **actual lifetime**: the real
connect timestamp (kept from `_ProducerReader.__init__`) and the timestamp
the reader thread exited (new `died_at`, recorded by the reader itself). A
true at-cap rejection measures as a few milliseconds regardless of
`rescan_s`, so the threshold is a small dedicated module constant
(`_FANIN_IMMEDIATE_EOF_S`) that does not depend on the loop's poll period.

On each consecutive flap `state.interval` doubles, capped at
`_FANIN_MAX_BACKOFF_S` (60s, transport.py:92); the warning logs once per
path (`state.warned` latch); the interval resets to `rescan_s` on the first
forwarded line (`_on_forward`, lines 1145-1151) or on a non-flap reader
death (line 1115). A legitimate short-lived producer that connects, has
nothing but its (filtered) `state_change` seed to send, and exits a second
or more later is **not** a flap — it must not double the interval or log
the misleading `max_clients` warning.

The rewritten `test_producer_at_max_clients_backs_off_sub_linearly` asserts
(a) the warning fires exactly once for the path (deterministic proof the
branch is reachable) and (b) total rejections over a fixed span stay under
a logarithmic bound, replacing the absolute `< 10` threshold.

## Steps to Reproduce

1. Run
   `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -k backs_off_sub_linearly -v`
   (fails locally and on CI — failure B1 in
   `thoughts/ci-unit-test-failures-2026-09-10.md`).
2. Mechanism: start a `UnixSocketTransport` producer with `max_clients=1`
   and occupy its single slot with a holder socket
   (test_feat3323_sse_bridge.py:327-330), then start an `SseBridge` with
   `_make_config(rescan_s=0.05)` (lines 332-334). Every rescan connects,
   gets immediately closed by the at-cap producer (counted in
   `client_rejections`), and the reader dies on EOF.
3. Wait ≥1.5s (test sleeps 0.5s + 1.0s, lines 336-341) and sample
   `producer.get_stats()["client_rejections"]` across two windows.
4. Observe: rejections keep accumulating at full rescan cadence in every
   window — no backoff ever engages — so
   `assert second_window_rejections < 10` (line 344) fails (`assert 10 < 10`
   on CI). Note the broken loop nearly *passed*: a slow runner halves the
   rescan cadence, so any absolute threshold can mask this regression.

## Root Cause

- **File**: `scripts/little_loops/transport.py`
- **Anchor**: `_fan_in_producer_sockets()`, reap block (lines 1090-1117); guard at line 1105; `connected_at` overwrite at line 1142
- **Cause**: The flap classifier conflates the loop's detection granularity
  (`rescan_s` as the `stop.wait` period) with the classification threshold
  (`rescan_s` as the flap window). Both endpoints of `elapsed` are
  loop-top samples — `connected_at` is overwritten with the iteration's
  `now` (line 1142) and death is observed only on the next iteration — so
  `elapsed` is quantised to whole `rescan_s` periods and `elapsed < rescan_s`
  is structurally unsatisfiable. Any fix that keeps reap-time `now` as the
  end timestamp and compares against a fixed constant re-creates the bug
  whenever `rescan_s` ≥ that constant (the production default is
  `rescan_s = 2.0`, features.py:1318).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10; revised 2026-09-11 after design review:_

- **Files to Modify**:
  - `scripts/little_loops/transport.py`
    - `_ProducerReader` (:955-965) — add `died_at: float | None = None`
    - `_read_producer_socket` (:979) — record `time.monotonic()` on every exit path (EOF, `OSError`, `stop` set); simplest is a `try/finally` around the loop body or a thin thread-target wrapper that sets `reader.died_at`
    - reap block (:1090-1117) — classify on `reader.died_at - reader.connected_at < _FANIN_IMMEDIATE_EOF_S` (fall back to reap-time `now` only if `died_at` is somehow `None`)
    - delete line 1142 (`reader.connected_at = now`) so the real connect time from `__init__` survives
    - new `_FANIN_IMMEDIATE_EOF_S` constant alongside `_FANIN_CONNECT_TIMEOUT`/`_FANIN_MAX_BACKOFF_S` under the `# FEAT-3323: SseBridge (ll-artifact serve) constants.` header (:87-92)
    - `_fan_in_producer_sockets` docstring "dies within one `rescan_s` of connecting" (:1080-1084) reworded to the lifetime window; keep the `§ Fan-in → Backoff` marker
  - `scripts/tests/test_feat3323_sse_bridge.py` — rewrite `test_producer_at_max_clients_backs_off_sub_linearly` (:323-348), see Program Design
- **Dependent Files (Callers/Importers)**:
  - `scripts/little_loops/cli/artifact/serve.py:34,193` — only construction path of `SseBridge`/`serve_sse_bridge`; unchanged
  - `scripts/little_loops/cli/loop/runner.py:541` — consumes `get_stats().get("client_rejections", 0)` into loop-run log suffixes; the counter flattens after the fix (no code change)
  - `scripts/little_loops/config/features.py:1318` — `BridgeEventsConfig.rescan_s: float = 2.0` feeds the fan-in thread arg (transport.py:1301); unchanged
- **Conventions in Force**:
  - Rate-limit/threshold windows are dedicated module constants sized independently of the loop's poll period — evidence: `_REJECT_LOG_INTERVAL_SEC = 5.0` (:66) compared inside loops polling at `_ACCEPT_POLL_TIMEOUT = 1.0` / `_CLIENT_QUEUE_POLL_TIMEOUT = 0.5`. The lifetime-based classifier restores this convention; a reap-time comparison cannot
  - Backoff constants spell seconds with an `_S` suffix — `_FANIN_MAX_BACKOFF_S` (:92), `_WEBHOOK_RETRY_BASE_S`/`_WEBHOOK_RETRY_MAX_S` (:76-77)
  - Every backoff site owns its own `min(base * 2^n, cap)` expression; no shared utility (asserted deliberate in `compute_backoff_s()` docstring, queue_store.py:194-197)
  - transport.py docstrings cite FEAT-3323 design bullets via `§ <Section> → <bullet>` markers (:958, :969, :1082)
- **Mirror sites that document the (currently dead) `rescan_s`-relative contract — reword with the fix**:
  - `scripts/little_loops/config-schema.json:1730` — `rescan_s` description: "Also the base of the per-path connect-then-immediate-EOF backoff (doubles per consecutive flap, capped at 60s)" — the *base* claim stays true (interval starts at `rescan_s`); drop any implication that `rescan_s` is the flap window
  - `docs/reference/API.md:11197` — Fan-in paragraph: "A reader that dies within one `rescan_s` of connecting without forwarding a single line …"
  - `docs/reference/CONFIGURATION.md:1752` — `events.bridge.rescan_s` row repeats the schema text
- **Tests**:
  - `scripts/tests/test_feat3323_sse_bridge.py` — `TestSseBridgeFanIn` (:197), the failing test (:323), `_make_config` seam (:105, takes `rescan_s`), holder-socket pattern (:328-330), teardown order bridge → holder → producer (:345-348)
  - `scripts/tests/test_transport.py` — `test_max_clients_cap_rejects_extra_connection` (:512) and `test_rejection_logging_is_rate_limited` (:543) pin producer-side rejection behavior; must not change. `caplog.at_level(logging.WARNING, logger="little_loops.transport")` + substring filter convention at :562-582
  - `scripts/tests/test_config.py:2537-2550`, `scripts/tests/test_config_schema.py:842-847` — pin `rescan_s`/`max_clients` defaults only; unaffected
- **Documentation**: `docs/ARCHITECTURE.md:630` describes the fan-in at behavior level with no window mention — no edit expected
- **Configuration**: no `events.bridge` override in `.ll/ll-config.json`; `rescan_s` default from `BridgeEventsConfig` (features.py:1318)

### Wiring Findings

_Wiring pass by `/ll:wire-issue` — 2026-09-10 — grep-confirmed; decisions resolved 2026-09-11:_

- **Verified no-edit**: `scripts/little_loops/__init__.py:68-76` (re-exports unchanged symbols only); `scripts/little_loops/events.py:23`, `scripts/little_loops/cli/loop/lifecycle.py:720` (import `Transport`/`wire_transports` only); `scripts/little_loops/cli/artifact/__init__.py` (:21-23, :50, :189, :212-213 — behavior-level fan-in text, no window); `scripts/little_loops/config/core.py:990-993` (`to_dict()` serializes `rescan_s` value only); `scripts/little_loops/templates/dashboard.llat/manifest.yaml:44`; `docs/reference/CLI.md:5014-5090`; `docs/reference/EVENT-SCHEMA.md:1699-1704` (`client_rejections` contract, no rate claim); `BridgeEventsConfig` docstring (features.py:1299-1330). No consumer of `client_rejections` outside `cli/loop/runner.py:541`
- **FEAT-3323 design doc — DECIDED: historical record.** `.issues/features/P3-FEAT-3323-live-event-stream-substrate-localhost-sse-bridge-over-the-eventbus.md` describes the flap window as `rescan_s`-relative in five places (:239-253, :631-635, :726, :748-751, :935-937). Do not rewrite those sections; add a single note under its `§ Fan-in → Backoff` bullet: "Flap window revised by BUG-3437 (reader lifetime vs `_FANIN_IMMEDIATE_EOF_S`, not `rescan_s`)."
- **`test_producer_eof_then_reconnect_on_next_rescan`** (test_feat3323_sse_bridge.py:302): its first producer is closed by the test after the bridge connects, typically well over `_FANIN_IMMEDIATE_EOF_S` after connect, so with the lifetime-based classifier it stays a non-flap death and reconnects on the next rescan. Re-run it; if it ever measures under the window on a loaded runner the 3.0s `_wait_until` budget still absorbs one doubling (0.05→0.1). No rename expected
- **Informational**: `.issues/enhancements/P1-ENH-3416-...md:270` cites `transport.py:1106` as a backoff example — becomes accurate post-fix
- **Out of scope (do not fix in passing)**: `path_state` is never pruned, so a path that disappears keeps its backoff state for the bridge's lifetime. Pre-existing; file separately if wanted

## Program Design

### Signatures

- `_FANIN_IMMEDIATE_EOF_S: float = 0.5` (transport.py, **new** module constant) — reader lifetime under which a never-forwarding death is a flap. Must be independent of `rescan_s`; a true accept-then-close measures in milliseconds, and a legitimate producer that idles ≥ 0.5s before closing is not a flap
- `_ProducerReader.died_at: float | None` (transport.py:955, **new** attribute, default `None`) — `time.monotonic()` at reader-thread exit
- `_ProducerReader.connected_at` (transport.py:964, existing) — now authoritative; the loop-top overwrite at :1142 is removed
- `_read_producer_socket(sock, out, stop, *, on_forward=None, on_drop=None, on_exit: Callable[[], None] | None = None) -> None` (transport.py:979) — **or** keep the signature and wrap the target in `_fan_in_producer_sockets`; either way `died_at` is set on every exit path
- `_fan_in_producer_sockets(...)` (transport.py:1060, existing signature unchanged) — reap-block guard becomes
  `lifetime = (reader.died_at if reader.died_at is not None else now) - reader.connected_at`;
  `if not reader.forwarded_any and lifetime < _FANIN_IMMEDIATE_EOF_S:`
- `_FANIN_MAX_BACKOFF_S = 60.0` (:92), `_FanInPathState` (:968) — unchanged

### Call Path

`SseBridge` fan-in thread (`threading.Thread(target=_fan_in_producer_sockets, ...)`, transport.py:1300-1301) -> connect (`connected_at` = real time) -> reader thread exits on EOF, sets `died_at` -> next rescan reaps -> `lifetime < _FANIN_IMMEDIATE_EOF_S` -> `state.interval = min(state.interval * 2, _FANIN_MAX_BACKOFF_S)`, warn once -> `_candidate_producer_paths()` probe gated by `state.next_attempt` (:1124)

Effective retry cadence is still quantised to the loop period (`next_attempt` is only checked once per `rescan_s`), which is fine: the sequence at `rescan_s=0.05` is ≈ 0, 0.1, 0.3, 0.7, 1.5, 3.1s.

### Test Design

`test_producer_at_max_clients_backs_off_sub_linearly` (test_feat3323_sse_bridge.py:323), rewritten:

1. Same setup: `max_clients=1` producer, holder socket, `_wait_until` for occupancy (setup only — never `_wait_until` on a measurement).
2. Wrap the bridge lifetime in `caplog.at_level(logging.WARNING, logger="little_loops.transport")`.
3. Sleep a fixed `SPAN = 2.0` s measured with `time.monotonic()` deadlines.
4. Assert **classification**: exactly one record containing `"closed the connection immediately"` (filter on that substring, not `"max_clients"` — the producer-side rejection warning shares that word on the same logger).
5. Assert **rate**: `rejections <= ceil(log2(SPAN / rescan_s)) + 3` (≈ 9 at 0.05; the broken loop produces ≈ 20–40). Comment the load justification (CI unit runner is 4-CPU vs 14 local; B1 measured 9–10/s broken).

Do **not** assert strict per-window decrease: after the first second each fixed window holds 0 or 1 rejections, so `window N+1 < window N` flakes on a zero-zero pair. Real time + `_make_config` knobs remain the idiom; no test patches a transport.py module constant. Test stays unmarked so it runs in the CI unit gate.

Optional new coverage in `TestSseBridgeFanIn` (same caplog convention): non-flap death resets `state.interval` to `rescan_s`; `_on_forward` reset.

## Implementation Steps

1. Add `_FANIN_IMMEDIATE_EOF_S = 0.5` under the FEAT-3323 constants header (transport.py:87-92).
2. Add `died_at: float | None = None` to `_ProducerReader.__init__` (:960-965).
3. Make the reader record `died_at` on every exit path — `try/finally` in `_read_producer_socket` via an `on_exit` callback, or a wrapper thread target in `_fan_in_producer_sockets` (:1153-1160).
4. Delete `reader.connected_at = now` (:1142).
5. Replace the guard at :1104-1105 with the lifetime comparison from Program Design; leave doubling/warn/reset bodies (:1106-1117) untouched.
6. Reword the `_fan_in_producer_sockets` docstring (:1080-1084) — keep the `§ Fan-in → Backoff` marker.
7. Rewrite `test_producer_at_max_clients_backs_off_sub_linearly` per Test Design; add the optional reset tests if cheap.
8. Reword mirror sites: config-schema.json:1730, API.md:11197, CONFIGURATION.md:1752. Add the one-line BUG-3437 note to FEAT-3323's `§ Fan-in → Backoff` bullet (historical record, no rewrite).
9. Re-run `test_producer_eof_then_reconnect_on_next_rescan` and `python -m pytest scripts/tests/test_transport.py -k "max_clients or rejection" -v`; then the full gate `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P1 - red on the local unit suite and CI today; beyond the
  failing test, the unbounded re-probe burns a connect/accept/reject cycle
  per rescan per at-cap producer for as long as the bridge runs, and the
  `max_clients` warning the operator would rely on never logs.
- **Effort**: Small - one constant, one attribute, one timestamp write, one
  guard change, one deleted line, one test rewrite, three doc rewords.
- **Risk**: Low - confined to flap classification. Non-flap deaths still
  reset to `rescan_s`; `_on_forward` reset untouched; producer-side
  rejection code untouched. The lifetime-based measurement removes the
  dependency on `rescan_s`, so the fix holds at the production default
  (2.0s) as well as the test value (0.05s).
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-11T01:01:30 - `f21b2f19-932a-4549-8711-81b75b733db6.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:52:21 - `9093c96d-29e3-4de9-b547-725e14459020.jsonl`
- manual review - 2026-09-11 - folded design review: lifetime-based classifier, constant independent of `rescan_s`, log-bound test, FEAT-3323 mirror decided as historical record
- `/ll:wire-issue` - 2026-09-11T00:08:42 - `38e69540-569a-4d83-90fc-f4d237d70095.jsonl`
- `/ll:refine-issue` - 2026-09-10T22:52:59 - `748bc362-b07a-4742-bc35-52128c70dda1.jsonl`
- `/ll:format-issue` - 2026-09-10T21:53:10 - `c062bf88-70c8-43b9-ac0c-360218fcb6ff.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`

## Acceptance Criteria

- `python -m pytest scripts/tests/test_feat3323_sse_bridge.py -k backs_off_sub_linearly -v` passes with `rescan_s=0.05` and an occupied `max_clients=1` producer, asserting both the once-per-path warning and `rejections <= ceil(log2(SPAN / rescan_s)) + 3` over a 2s span
- Flap classification uses reader lifetime (`died_at - connected_at`) against `_FANIN_IMMEDIATE_EOF_S`; neither endpoint is a loop-top `now`, and the threshold does not reference `rescan_s`. Verified by reading the guard, and by the test above still passing if `rescan_s` is raised to 2.0 in a one-off local run (backoff must engage at the production default)
- The "closed the connection immediately; at max_clients?" warning logs exactly once per flapping path (`state.warned` latch)
- A never-forwarding reader whose lifetime is ≥ `_FANIN_IMMEDIATE_EOF_S` is a non-flap death: interval resets to `rescan_s`, no warning. `test_producer_eof_then_reconnect_on_next_rescan` passes unchanged
- Interval resets to `rescan_s` on first forwarded line (`_on_forward`) — existing semantics preserved
- Mirror documentation no longer describes the flap threshold as `rescan_s`-relative: transport.py docstring, config-schema.json `rescan_s` description, API.md Fan-in paragraph, CONFIGURATION.md `events.bridge.rescan_s` row; FEAT-3323 carries a one-line BUG-3437 note and is otherwise untouched
- `python -m pytest scripts/tests/` exits 0, with `test_transport.py` rejection/cap tests passing unchanged
