---
id: 3755
title: 'FSM events stamp ''loop'' but the SQLite and OTel transports read ''loop_name'': live loop telemetry loses its loop identity'
type: BUG
priority: P0
status: done
completed_at: '2026-10-06T03:45:59Z'
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

## Resolution

- **Action**: fix
- **Completed**: 2026-10-05
- **Status**: Completed

### Changes Made
- `events.py`: `event_loop_name()` reads the executor-stamped `loop` key, falling back to `loop_name` for older payloads.
- `transport.py`: `OTelTransport._handle_loop_start` and `_handle_loop_resume` name the loop span through it, so spans are named after the loop instead of `ll-loop`.
- `session_store/writers.py`: `SQLiteTransport.send` records the loop name through it, so live `loop_events` rows are no longer NULL. A `route` row keeps `from` as `state` and records `to` in the new `to_state` column.
- `session_store/schema.py`: schema v60 adds nullable `loop_events.to_state` through `_MIGRATIONS`; manifest regenerated; HISTORY_SESSION_GUIDE version table updated.
- `scripts/tests/test_bug3755_transport_loop_identity.py`: drives a real `PersistentExecutor` through its event bus into both transports (fails without the fix); version assertions moved to 60.

### Verification
- New tests fail on the unfixed transports and pass with the fix.
- Full suite: 28,644 passed. The 4 failures are unrelated to this change: two adapter `tsc` checks that need `node_modules` (absent in a fresh worktree), and two issue-corpus gates (ENH-3751/3752 prose dependencies, ENH-3700 evidence quotes).
