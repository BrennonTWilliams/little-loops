---
id: ENH-3669
type: ENH
title: Batch loop-end usage_events writes into bounded round trips
priority: P4
status: deferred
deferred_by: human
deferred_date: '2026-09-30T02:30:00Z'
deferred_reason: latency benefit unmeasured; re-open only if loop-end remote write latency is measured and material
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T23:04:53Z'
relates_to:
- BUG-3652
---

# ENH-3669: Batch loop-end usage_events writes into bounded round trips

> **2026-09-30 (`/ll:advise` Opus review): deferred.** Batching is equivalent to the per-row loop (verified: `record_usage_event` is one INSERT plus cost computation; `execute_many` is one begin/conditional/commit/rollback pipeline), but the benefit is unmeasured. Re-open only after measuring loop-end write latency against a live remote endpoint and finding it material.

## Summary

Batch the loop-end `usage_events` writes in `fsm/executor.py:_finish` into one request per bounded chunk. Split out of BUG-3652 (sixth `/ll:advise` review, 2026-09-29), which keeps the per-row `record_usage_event` loop and only drops the `resolve_history_db()` pre-resolve.

## Current Behavior

`fsm/executor.py:_finish` calls `record_usage_event` once per collected `TokenUsage` row, each on its own telemetry connection: K sequential round-trips against a live remote store.

## Expected Behavior

Loop-end usage events reach a live remote store in `ceil(K / chunk_size)` batch requests rather than K per-row requests, with local SQLite behavior unchanged.

## Motivation

`_usage_events_collected` gets one row per action invocation, so a long run holds hundreds of rows, and `_finish` calls `record_usage_event` once per row, each on its own telemetry connection. Under a live remote backend that is K sequential Hrana round-trips on the FSM thread at loop end (300 rows at 200 ms would be about 60 s). A dead endpoint is already bounded by the unreachable marker. The live-endpoint latency is still hypothetical: measure it when an endpoint is available, and defer this P4 optimization if the cost is not material.

## Proposed Solution

- Add `record_usage_events(db, rows)` in `session_store/writers.py`: one `_connect_telemetry` and one `conn.executemany(INSERT, rows)` per bounded chunk. `LibsqlConnection.executemany` (`libsql.py`) sends one Hrana batch per chunk; local SQLite runs each chunk in one transaction. Do not hand-build a multi-row INSERT: that creates a bound-variable limit absent from `executemany`.
- State the behavior change in the docstring: each chunk is all-or-nothing, but earlier committed chunks remain after a later chunk fails. Verified 2026-09-30: `HranaClient.execute_many` (`hrana.py:313`) sends an explicit `begin` / conditional-step / `commit` / conditional-`rollback` batch in one pipeline POST; `LibsqlConnection.commit()`/`rollback()` are no-ops, so remote atomicity relies on the server honoring that batch. The current `_finish` loop already stops at the first failed row. Chunk large K (e.g. 200-row chunks) to bound the remote payload and compute `cost_usd` per row before each batch.
- Add a learning-test claim (`ll:explore-api` / Learning Test Registry) for server-side `cond_ok`/`rollback` atomicity. Run it against a real Turso/sqld endpoint when available; until then, record the claim as unproven rather than marking it passed. Do not sample or cap rows: cost accounting needs every row.
- Re-export from `session_store/__init__.py` (import and `__all__`); the executor imports it inside `try/except: pass`, so a missing export silently drops every usage row.
- Rewrite `test_fsm_executor.py:4050-4128` (patches of `record_usage_event`) to patch `record_usage_events` and assert one call with K rows; check `test_enh3538_token_observations.py` and `test_enh3543_usage_coverage.py`. Add the function to `docs/reference/API.md`.

## Scope Boundaries

- **In scope:** loop-end live `usage_events` collected by `_finish`, one telemetry connection/batch per bounded chunk, tests, package export and API docs.
- **Out of scope:** other usage producers, sampling or dropping cost rows, and replacing the existing single-row `record_usage_event` API.

## Program Design

### Types

- `UsageEventRow` holds the already-computed values for one live observation, including its cost and identity/provenance columns.

### Signatures

- `record_usage_events(db: Path | str, rows: Sequence[UsageEventRow]) -> None` — writes bounded chunks without changing the single-row API.

### Call Path

Existing `_finish` → `record_usage_events` → `_connect_telemetry` → `LibsqlConnection.executemany` for remote batches, or the local SQLite connection for local chunks.

## Impact

- **Priority**: P4 - latency only; remote users already get the rows via per-row writes after BUG-3652.
- **Effort**: Small - one writer, one re-export, one test rewrite.
- **Risk**: Low - the batch is all-or-nothing where the per-row loop keeps earlier rows; telemetry-only.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Record real-endpoint round-trip latency if an endpoint is available; otherwise state that latency benefit remains unmeasured.
- [ ] A failure within the first chunk writes none of that chunk; a failure in a later chunk retains earlier committed chunks. Large K is chunked and each chunk is atomic in the local/stub test.
- [ ] The server-side batch-atomicity learning-test claim is proven against a real endpoint, or explicitly remains unproven and is not treated as a passed gate.
- [ ] With 200-row chunks and the Hrana stub, `_finish` sends one batch request for K=1 and K=200, and two for K=201 or K=300 (pin measured counts, excluding shared setup requests).
- [ ] Local behavior: K rows identical to K single `record_usage_event` writes.
- [ ] `record_usage_events` is importable from the `session_store` package.

## Related

- BUG-3652 (keeps the per-row loop; blocks nothing here).

## Status

**Deferred** | Created: 2026-09-29 | Priority: P4
