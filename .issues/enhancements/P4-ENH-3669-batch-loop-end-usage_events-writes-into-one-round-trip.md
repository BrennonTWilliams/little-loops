---
id: ENH-3669
type: ENH
title: Batch loop-end usage_events writes into one round-trip
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T23:04:53Z'
relates_to:
- BUG-3652
---

# ENH-3669: Batch loop-end usage_events writes into one round-trip

## Summary

Batch the loop-end `usage_events` writes in `fsm/executor.py:_finish` into one round-trip. Split out of BUG-3652 (sixth `/ll:advise` review, 2026-09-29), which keeps the per-row `record_usage_event` loop and only drops the `resolve_history_db()` pre-resolve.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

`_usage_events_collected` gets one row per action invocation, so a long run holds hundreds of rows, and `_finish` calls `record_usage_event` once per row, each on its own telemetry connection. Under a live remote backend that is K sequential Hrana round-trips on the FSM thread at loop end (300 rows at 200 ms is about 60 s). A dead endpoint is already bounded by the unreachable marker. Before BUG-3652 remote users wrote zero rows, so this is a latency cost, not a regression. Do this only after measuring round-trip time against a real endpoint.

## Proposed Solution

- Add `record_usage_events(db, rows)` in `session_store/writers.py`: one `_connect_telemetry` and one `conn.executemany(INSERT, rows)`. `LibsqlConnection.executemany` (`libsql.py`) already sends one Hrana batch; local SQLite runs it in one transaction. Do not hand-build a multi-row INSERT (17 params × 200 rows exceeds the 999-variable limit on SQLite older than 3.32).
- State the behavior change in the docstring: the batch is all-or-nothing, where the per-row loop keeps rows written before a failure.
- Re-export from `session_store/__init__.py` (import and `__all__`); the executor imports it inside `try/except: pass`, so a missing export silently drops every usage row.
- Rewrite `test_fsm_executor.py:4050-4128` (patches of `record_usage_event`) to patch `record_usage_events` and assert one call with K rows; check `test_enh3538_token_observations.py` and `test_enh3543_usage_coverage.py`. Add the function to `docs/reference/API.md`.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] Measured round-trip cost against a real remote endpoint is recorded in this issue before implementation.
- [ ] With K rows and the Hrana stub, `_finish` sends the same number of requests for K=1 and K=300 (pin the measured count).
- [ ] Local behavior: K rows identical to K single `record_usage_event` writes.
- [ ] `record_usage_events` is importable from the `session_store` package.

## Related

- BUG-3652 (keeps the per-row loop; blocks nothing here).

## Status

**Open** | Created: 2026-09-29 | Priority: P4
