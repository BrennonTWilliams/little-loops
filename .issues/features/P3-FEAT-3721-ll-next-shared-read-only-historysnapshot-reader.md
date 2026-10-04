---
id: FEAT-3721
type: FEAT
title: ll-next shared read-only HistorySnapshot reader
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:29:51Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
blocks:
- FEAT-3711
- FEAT-3713
relates_to:
- ENH-3720
- ENH-3679
---

# FEAT-3721: ll-next shared read-only HistorySnapshot reader

## Summary

Add one injected, **local-SQLite-only** (v1) read-only `HistorySnapshot` reader for ll-next consumers. Split out of FEAT-3711 (Opus review, 2026-10-03) so FEAT-3713 (sprint recency from `cli_events`) and FEAT-3711 (`recommendation_events` lookup) share it without FEAT-3713 depending on FEAT-3711's migration/events work. FEAT-3561 stays history-free; this slice is where the first history read enters.

## Current Behavior

No ll-next history reader exists. Existing readers either create/migrate stores or use write-capable telemetry helpers.

## Expected Behavior

- `read_history_snapshot(store, *, as_of, requests) -> HistorySnapshot` opens the resolved local store read-only through the existing backend chokepoint, never creates/migrates a store, honors `LL_HISTORY_DB` and explicit project-root resolution, and returns typed per-source/table availability plus diagnostics. Resolve the target once with `resolve_history_target(..., root=project_root)` and pass that typed target through; do not resolve it again from cwd. Remote (libsql/Hrana) targets report `unavailable(remote_unsupported_v1)` before any remote connection or access/cache operation; remote support follows ENH-3720.
- One UTC `as_of` and one read transaction for a consistent view across requested tables. Pass `timeout=0.25` explicitly to `backend.connect_readonly`; its current default is **5 seconds**, and ENH-3679's CLI-writer timeout does not apply to this reader. Bound work with finite primary-key pages/visited-row budgets and avoid residual SQL scans/sorts. These are per-lock/work bounds, not a hard total deadline; query cancellation and backend-wide deadline machinery remain ENH-3720.
- Finite **visited-row** budgets, not just returned-match limits. If a cap or deadline prevents proving the newest qualified activity, return `partial` with observed coverage and leave the exact recency axis unknown. Missing tables are independent of a source's exhausted budget.
- Missing file/table, old schema, suppressed backend or lock timeout yields unavailable data, not an exception or guessed negative evidence. A missing `recommendation_events` table cannot erase valid `cli_events`/`loop_runs` data.
- No cache/marker file writes; no `connect_telemetry`.

## Proposed Solution

### Consumer-specific requests and query bounds

v1 reads only `cli_events` for FEAT-3713 sprint-recency evidence and, when present, `recommendation_events` for FEAT-3711 feedback. `loop_runs` and `orchestration_runs` have no consumer in these two slices and are not eagerly loaded; FEAT-3561 uses filesystem loop history and the backtest FEAT-3712 is cancelled. Existing `skill_events` cannot establish completed exact-scope scans, so scan freshness remains unavailable on the current schema; do not add an unused scan/producer reader here.

- Pin a closed request vocabulary: `RecentSprintInvocations` (candidate sprint names, bounded history window/visited-row limit) and `RecommendationLookup` (project key, exact recommendation UUID). FEAT-3711 extends the recommendation source with a schema-readiness probe for recording; it reads only the version stamp/required table columns and performs no setup. SQL identifiers come from that vocabulary and values are bound parameters. Default recent-source budget is 2,000 visited rows, read in pages of at most 200; it is an internal bound, not a new config framework.
- Current `cli_events` has no binary/time index. Walk descending primary-key `id` pages under the transaction's fixed maximum ID, apply argument/time qualification to those bounded rows, and retain an explicit coverage limitation when the walk is incomplete. IDs are ingestion order, **not** guaranteed timestamp order; backfill/out-of-order/future rows must not make the first matching ID an exact latest event. Do not use `WHERE binary=? ORDER BY ts LIMIT N` and claim the result limit bounds the underlying scan/sort. This issue adds no index or migration.
- A feedback lookup uses FEAT-3711's `UNIQUE(rec_id, kind)` index and verifies `project_key`, bounded to the shown/accepted rows. An old recommendation must remain findable even when recent CLI activity saturates its own budget. A generic latest-N event snapshot is not a valid feedback API.
- `cli_events` has no project/cwd column. A default project-local store can supply project-local sprint evidence; a redirected `LL_HISTORY_DB`/`history.db_path` store with no independently verified ownership yields `partial(unscoped_store)` for sprint recency. A matching sprint name alone cannot attribute another project's run. This does not prevent an exact project-keyed recommendation lookup in the same shared store.
- Inspect only the columns needed by each source; a newer/older schema is usable when those columns exist. Absent or incompatible recommendation columns do not erase valid CLI data, and vice versa. Normalize timestamps before comparison; ISO strings with differing offsets must not be ordered lexically as UTC.
- Query/decode/fetch errors become per-source availability/diagnostics through existing backend error translation. Never use an unavailable or partial source to assert that a sprint never ran or an acknowledgement is absent. Exact lookup storage failure is distinct from a successfully queried unknown ID.

## Integration Map

- New reader/request/availability types under the FEAT-3561 arena modules, using `session_store/db.py` target resolution and `session_store/backend.py` strict read-only connect/error seams.
- FEAT-3713 requests only recent sprint CLI evidence; FEAT-3711 requests one project-scoped recommendation identity. Neither performs live SQL inside pure generators/feedback lookup.
- Focused read-only, query-plan/work-budget, transaction-consistency and degradation tests; `docs/reference/API.md` documents the request and partial-coverage contracts. No schema/manifest change in this slice.

## Scope Boundaries

- **In scope:** the reader, typed requests/availability/diagnostics, bounded CLI primary-key walks and (once FEAT-3711 lands) recommendation point lookups; tests for absent/compatible-old/incompatible/suppressed/locked/row-budget-saturated states.
- **Out of scope:** schema migration and events (FEAT-3711), producer/acceptance attribution and pressure (FEAT-3722, deferred), remote deadline budget (ENH-3720).

## Program Design

### Types

- Immutable `HistorySnapshot(availability_by_source, rows_by_source, coverage_by_source, diagnostics, as_of)`; availability is `available | partial | unavailable(reason)` per source. Coverage records visited rows, ID/window bounds and truncation reason.
- Typed `RecentSprintInvocations` and `RecommendationLookup` requests; no caller-provided SQL and no global history dump.

### Signatures

- `read_history_snapshot(store, *, as_of: datetime, requests: Sequence[HistoryReadRequest]) -> HistorySnapshot` — read-only, fail-soft; reads only the requested identities/time slices with independent budgets.

### Call Path

Existing `session_store.db.resolve_history_target(..., root=project_root)` → new `read_history_snapshot` → existing `session_store.backend.connect_readonly(..., timeout=0.25)` → one read transaction and bounded query/fetch stage → typed snapshot → new pure generator/feedback lookup.

## Implementation Steps

1. Pin the request, per-source coverage and compatible-column contracts; make remote rejection precede opening.
2. Implement explicit short-timeout connection, consistent transaction and bounded CLI ID paging; preserve independent source failures and reject unscoped shared-store recency.
3. Add the optional recommendation point query against synthetic FEAT-3711-schema fixtures without adding that migration here. Test old identities outside the recent-source budget.
4. Add no-write, lock, out-of-order timestamp, mid-fetch error, redirected-store and concurrent-writer fixtures; document the API and limits.

## Acceptance Criteria

- [ ] Read-only; never creates/migrates a store or writes cache/marker files; honors `LL_HISTORY_DB`, root-aware target resolution and typed-target pass-through without cwd re-resolution.
- [ ] Per-source availability with tested absent/compatible-old/incompatible/suppressed/locked/remote-unsupported degradation; row-budget saturation cannot yield false exact results. Remote rejection performs no network/access/cache operation.
- [ ] Explicit 250 ms read-lock cap, finite visited-row budgets and one consistent read transaction are tested, including errors during fetching and concurrent writers; default backend behavior is unchanged and no total-deadline claim is made.
- [ ] Tests assert primary-key query plans and finite visited-row counts for the unindexed CLI source; out-of-order ingestion/timestamps cannot yield false newest evidence. No unbounded full-store scan/sort or index migration.
- [ ] Exact project/rec_id lookup remains available for an old ID when recent CLI data exceeds its budget; absent/incompatible recommendation tables do not invalidate other requested sources. Query failure never becomes unknown-ID or unaccepted evidence.
- [ ] A same-named sprint from a redirected/shared store without verified ownership cannot establish project-local recency; project-keyed feedback in that store still works.
- [ ] Documented in `API.md`; `python -m pytest scripts/tests/` passes.

## Impact

- **Priority**: P3 — shared seam for FEAT-3711 and FEAT-3713.
- **Effort**: Small–Medium.
- **Risk**: Low — read-only, fail-soft.
- **Breaking Change**: No.

## Use Case

A ready sprint can be recommended while its recent history is partial or unavailable. A feedback request for an older offer reads its exact project-scoped identity without loading unrelated activity or migrating history.

## Review Notes

- 2026-10-04: Code/schema audit and Opus critique (0.78) found `cli_events` and `skill_events` have no time/binary indexes, read-only connections default to a five-second lock wait, and CLI rows have no project identity. Replaced the impossible index promise with bounded primary-key walks, explicit local lock/work bounds, consistent snapshots and request-specific feedback lookups; removed unused history sources and rejected unscoped shared-store recency. Backend-wide deadlines and the events migration remain outside this slice.

## Status

**Open** | Created: 2026-10-04 | Priority: P3
