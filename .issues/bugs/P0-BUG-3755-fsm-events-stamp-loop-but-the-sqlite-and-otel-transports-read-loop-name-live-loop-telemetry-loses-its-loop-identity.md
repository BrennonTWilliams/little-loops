---
id: 3755
title: 'FSM events stamp ''loop'' but the SQLite and OTel transports read ''loop_name'': live loop telemetry loses its loop identity'
type: BUG
priority: P0
status: open
discovered_date: '2026-10-05'
labels:
- telemetry
- transport
- history-db
---

## Summary

FSM events carry the loop's name under `loop`, but two of the event transports read `loop_name`. Any user who enables the sqlite or otel transport gets loop telemetry with no loop identity.

ENH-3345 (done) made `FSMExecutor._emit` stamp `run_id` and `loop` on every event (`scripts/little_loops/fsm/executor.py`, `_emit`, around line 4175). `PersistentExecutor._handle_event` forwards events to the bus unchanged (`fsm/persistence.py`, the `event_bus.emit(event)` call). But:

- `SQLiteTransport.send` reads `event.get("loop_name")` (`session_store/writers.py`, around line 3087), so every live `loop_events` row is written with `loop_name` NULL.
- `OTelTransport._handle_loop_start` and `_handle_loop_resume` read `event.get("loop_name", "ll-loop")` (`transport.py`, around lines 1784 and 1791), so every OTel loop span is named `ll-loop`.
- The sqlite writer also stores only `event.get("state")`, and a `route` event carries `from`/`to`, so route rows lose their transition entirely.

The transport tests hand-feed `{"loop_name": ...}` (for example `test_transport.py` and `test_session_store_writers.py`), a shape the executor never emits, so the suites stay green. Consumers that group live rows by `loop_name` (ll-logs, agent_quality, quality_regressions) undercount live runs, which skews the longitudinal quality metrics and regression attribution built on `history.db`.

The transports are the egress contract every quality layer above them trusts for event shape; a key mismatch between producer and transport is exactly the drift a conformance test against real executor output should catch.

## Acceptance Criteria

Acceptance: (a) the sqlite and otel transports take the loop name from `loop`, falling back to `loop_name` for older payloads; (b) a test drives a real FSMExecutor/PersistentExecutor through the event bus into each transport and asserts a non-null loop name and a span named after the loop, replacing reliance on hand-built dicts; (c) sqlite `route` rows keep `from` as `state` and record `to`, as an additive nullable column through `_MIGRATIONS`; (d) existing transport and session-store suites pass.

## Related

- ENH-2463 (done) noted that `loop_complete` once lacked `loop_name`; that predates ENH-3345's stamping and is a different gap.

Verified against main 4c6be4c26 on 2026-10-05.
