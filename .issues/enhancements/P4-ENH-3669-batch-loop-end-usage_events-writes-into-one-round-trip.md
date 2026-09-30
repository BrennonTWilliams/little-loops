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

`fsm/executor.py:_finish` calls `record_usage_event` once per collected `TokenUsage` row, each on its own telemetry connection: K sequential round-trips against a live remote store.

## Expected Behavior

Loop-end usage events reach a live remote store in a K-independent number of requests, with local SQLite behavior unchanged.

## Motivation

`_usage_events_collected` gets one row per action invocation, so a long run holds hundreds of rows, and `_finish` calls `record_usage_event` once per row, each on its own telemetry connection. Under a live remote backend that is K sequential Hrana round-trips on the FSM thread at loop end (300 rows at 200 ms is about 60 s). A dead endpoint is already bounded by the unreachable marker. Before BUG-3652 remote users wrote zero rows, so this is a latency cost, not a regression. Do this only after measuring round-trip time against a real endpoint.

## Proposed Solution

- Add `record_usage_events(db, rows)` in `session_store/writers.py`: one `_connect_telemetry` and one `conn.executemany(INSERT, rows)`. `LibsqlConnection.executemany` (`libsql.py`) already sends one Hrana batch; local SQLite runs it in one transaction. Do not hand-build a multi-row INSERT (17 params × 200 rows exceeds the 999-variable limit on SQLite older than 3.32).
- State the behavior change in the docstring: the batch is all-or-nothing, where the per-row loop keeps rows written before a failure. Verified 2026-09-30: `HranaClient.execute_many` (`hrana.py:313`) is an explicit `begin` / conditional-step / `commit` / conditional-`rollback` batch in one pipeline POST (atomic, one round trip); note `LibsqlConnection.commit()`/`rollback()` are no-ops, so atomicity comes from the batch, not the connection. The current `_finish` loop already stops at the first failed row (the surrounding `try/except`), so the behavior change is smaller than "keeps rows before a failure" implies. Chunk large K (e.g. 200-row chunks) and compute `cost_usd` per row before the batch (`estimate_cost_usd`), keeping `record_usage_event`'s per-row semantics.
- Add a learning-test claim (`ll:explore-api` / Learning Test Registry) that a Turso/sqld endpoint honors `cond_ok`/`rollback` batch atomicity; the code read proves the client side only. Do not sample or cap rows: cost accounting needs every row.
- Re-export from `session_store/__init__.py` (import and `__all__`); the executor imports it inside `try/except: pass`, so a missing export silently drops every usage row.
- Rewrite `test_fsm_executor.py:4050-4128` (patches of `record_usage_event`) to patch `record_usage_events` and assert one call with K rows; check `test_enh3538_token_observations.py` and `test_enh3543_usage_coverage.py`. Add the function to `docs/reference/API.md`.

## Impact

- **Priority**: P4 - latency only; remote users already get the rows via per-row writes after BUG-3652.
- **Effort**: Small - one writer, one re-export, one test rewrite.
- **Risk**: Low - the batch is all-or-nothing where the per-row loop keeps earlier rows; telemetry-only.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] (Note, not a gate) Record the measured round-trip cost against a real remote endpoint if one is available; the K-independent request count is the AC.
- [ ] A single-transaction test: with a failing K-th row, no rows from the batch are written; large K is chunked and each chunk is atomic.
- [ ] Learning-test claim for server-side batch atomicity is recorded and proven.
- [ ] With K rows and the Hrana stub, `_finish` sends the same number of requests for K=1 and K=300 (pin the measured count).
- [ ] Local behavior: K rows identical to K single `record_usage_event` writes.
- [ ] `record_usage_events` is importable from the `session_store` package.

## Related

- BUG-3652 (keeps the per-row loop; blocks nothing here).

## Status

**Open** | Created: 2026-09-29 | Priority: P4
