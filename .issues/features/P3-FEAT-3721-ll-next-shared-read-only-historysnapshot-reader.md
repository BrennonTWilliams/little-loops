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
- BUG-3737
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

No ll-next history reader exists. Existing high-level readers either create/migrate stores or use write-capable telemetry helpers. The strict `SqliteBackend.connect_readonly` primitive exists, but both its ordinary and deadline branches interpolate an unescaped filesystem path into a SQLite URI. A temporary-store reproduction on 2026-10-05 showed `hash#name.db` and `query?name.db` opened newly created truncated-path files instead of the intended DB; `percent%23name.db` failed to open. BUG-3737 owns the independent literal-path repair for existing readers and supplies the safe primitive this slice requires.

## Expected Behavior

- `read_history_snapshot(store, *, as_of, requests, now) -> HistorySnapshot` opens the resolved local store read-only through the existing backend chokepoint, never creates/migrates a store, honors `LL_HISTORY_DB` and explicit project-root resolution, and returns typed per-source/table availability plus diagnostics. An empty request list returns an empty snapshot without resolving/opening history. Resolve the target once with `resolve_history_target(..., root=project_root)` and pass that typed target through; do not resolve it again from cwd. Remote (libsql/Hrana) targets report `unavailable(remote_unsupported_v1)` before any remote connection or access/cache operation; remote activation requires a separately scoped consumer feature; the completed ENH-3720 deadline does not activate it.
- Preserve the resolver's existing relative-override policy: a relative `LL_HISTORY_DB` is relative to the invocation's original cwd, whereas a configured `history.db_path` and the default store are project-root-relative. Freeze the resolved local path to an absolute spelling at the CLI boundary before any later cwd change, and retain resolution provenance. This explicit cwd-relative override is a documented exception to follow-on history-source equivalence between root and subdirectory invocations; the history-free core's root/config equivalence remains intact. Do not silently reinterpret the environment override or change the shared resolver. Ownership checks compare physical paths and still reject an unscoped redirected store.
- One UTC `as_of` and one read transaction for a consistent view across requested tables. Pass `timeout=0.25` explicitly to `backend.connect_readonly`; its current default is **5 seconds**, and ENH-3679's CLI-writer timeout does not apply to this reader. ENH-3720 is done: construct one `Deadline.after(1.0)` before opening, pass it through `connect_readonly(..., timeout=0.25, deadline=deadline)`, and share it across metadata probes, queries and fetches without resetting it per source/page. Recheck after decoding/before reporting success. Retain finite primary-key pages/visited-row budgets and avoid residual scans/sorts. Deadline enforcement is not a universal hard wall-time guarantee: filesystem stalls, JSON decoding and SQLite user-defined functions are not preempted; preserve the primitive's documented progress-handler granularity. Writes and remote activation remain outside this slice.
- Finite **visited-row** bounds, not just returned-match limits. If a cap or deadline prevents proving the newest qualified activity, return `partial` with observed coverage and leave exact latest-run recency unknown. Retain completely read rows as observed witnesses for FEAT-3713's explicitly limited witness-based axis; partial data never proves the actual latest run or never-run state. Missing tables are independent of a source's exhausted budget. Unexpected query/decode failures remain unavailable; only intentional bounded truncation can supply trusted earlier witnesses.
- Missing file/table, old schema, suppressed backend or lock timeout yields unavailable data, not an exception or guessed negative evidence. A missing `recommendation_events` table cannot erase valid `cli_events` data when that later request is added.
- No application-created cache/marker files, telemetry, schema/main-DB mutation or directory creation; no `connect_telemetry`. SQLite `mode=ro` can create `-wal`/`-shm` coordination files for an existing WAL-mode DB, even with `query_only`. Document that narrow SQLite-managed exception to the filesystem no-write wording in reader/feedback/explain modes; do not use `immutable=1` to suppress it because that ignores live WAL/concurrency. Tests compare main-DB content and application files and explicitly account for possible WAL sidecars. This does not permit application writes or a writable history connection.
- Treat a resolved local target as a literal filesystem path, never caller-supplied URI syntax. Reuse BUG-3737's corrected backend and shared percent-encoded absolute file-URI builder; do not duplicate URI construction here. Preserve the already-resolved target and timeout/deadline behavior; literal `#`, `?`, `%`, spaces and Unicode must identify the intended file. A missing special-character path must fail without creating either that file or a truncated/decoded alias. FEAT-3711 reuses that builder for its existing-file `mode=rw` seam.

## Proposed Solution

### Consumer-specific requests and query bounds

This slice reads only `cli_events` for FEAT-3713 sprint-recency evidence. FEAT-3711 adds its recommendation point-lookup request and schema-readiness probe alongside the migration, reusing this transaction/availability/deadline seam. `loop_runs` and `orchestration_runs` have no consumer in these two slices and are not eagerly loaded; FEAT-3561 uses filesystem loop history and the backtest FEAT-3712 is cancelled. Existing `skill_events` cannot establish completed exact-scope scans, so scan freshness remains unavailable on the current schema; do not add an unused scan/producer reader here.

- Pin the currently consumed request vocabulary: `RecentSprintInvocations` (project root for ownership qualification, candidate sprint names and bounded ID-history window). FEAT-3711 owns the later `RecommendationLookup` and readiness-probe request definitions, SQL, column contract and fixtures together with its table; do not preimplement those against a synthetic future schema here. Extend the typed request union/dispatch in that child without caller-provided SQL. SQL identifiers come from registered typed requests and values are bound parameters. Pin internal recent-source limits of a 50,000-ID span, windows of at most 200 IDs, and at most 2,000 returned CLI rows before decoding. These are fixed work bounds, not a new config framework. Keep the existing shared 1-second deadline; do not spend it anew for each window.
- `cli_event_context` limits args to 50 entries but does not cap each string. Guard the SQL projection of `args` with a fixed 64 KiB UTF-8 byte limit before transferring/decoding it (for example a conditional projection using `length(CAST(args AS BLOB))`); do not fetch unrestricted args and then check their size. An oversized potentially relevant row is skipped with `partial(payload_limit)` and cannot establish an exact latest-run result. Previously complete, qualified witnesses may still be used under FEAT-3713's limited observed-witness policy. The fixed row/page bounds also bound total argument transfer, and only the requested bounded CLI rows enter the snapshot. Keep this guard local to the CLI request: no generic payload-budget framework, recommendation-offer truncation/size policy, producer change or new user configuration. Deadline/SQLite/filesystem nonpreemptive limits still apply.
- Current `cli_events` has no binary/time index. Under the transaction's fixed maximum ID, walk descending primary-key **ranges** of width at most 200 and apply `binary = 'll-sprint'` in SQL within each range. Advance by the range boundary, including empty ranges, so sparse/deleted IDs cannot cause repeated work. The bounded range width caps underlying rows visited; `LIMIT` on matching rows alone does not. Record ID span walked, visited-row upper bound, returned/skipped rows and truncation reason; do not report range width as an exact visited-row count. IDs are ingestion order, not guaranteed timestamp/end-time order; the first matching ID is never an exact latest invocation. Normalize and qualify every returned row needed to choose the newest observed ended witness, with completion/argument qualification owned by FEAT-3713. Do not use unbounded `WHERE binary=? ORDER BY ts LIMIT N` scans/sorts. This issue adds no index or migration.
- The v1 sprint request has an as_of upper-time boundary and the fixed ID-history work window, with no invented lower timestamp cutoff. The sprint curve's 30-day age saturation is not a scan lookback or proof that older runs never happened. The request carries project_root explicitly for physical-store ownership qualification; a LocalTarget path alone does not establish which project requested it. FEAT-3713 owns argument/completion qualification over the returned bounded rows.
- Per-request results remain independently available/partial/unavailable. Preserve this seam when FEAT-3711 adds point lookups; a generic latest-N event snapshot is not a substitute for its exact identity query. Recommendation index/old-ID tests belong to FEAT-3711.
- `cli_events` has no project/cwd column. A default project-local store can supply project-local sprint evidence only after resolving its physical path; a symlink/redirect to a different store is not owned merely because the textual path is `.ll/history.db`; a redirected `LL_HISTORY_DB`/`history.db_path` store with no independently verified ownership yields `partial(unscoped_store)` for sprint recency. A matching sprint name alone cannot attribute another project's run. This does not prevent an exact project-keyed recommendation lookup in the same shared store.
- Inspect only the columns needed by each source; a newer/older schema is usable when those columns exist. Absent or incompatible recommendation columns do not erase valid CLI data, and vice versa. Normalize timestamps before comparison; ISO strings with differing offsets must not be ordered lexically as UTC. `as_of` filters time-window evidence, not the later exact-ID lookup. The history transaction is internally consistent but is not atomic with the earlier issue/git/filesystem ProjectState; disclose this boundary rather than promising a cross-source transaction. Mutable CLI duration fields have no completion-observed timestamp, so the reader supports present observed snapshots, not reconstruction of past database knowledge from a timestamp filter.
- Query/decode/fetch errors become per-source availability/diagnostics through existing backend error translation. Never use an unavailable or partial source to assert that a sprint never ran or an acknowledgement is absent. Exact lookup storage failure is distinct from a successfully queried unknown ID.

## Integration Map

- New reader/request/availability types under the FEAT-3561 arena modules, using `session_store/db.py` target resolution and `session_store/backend.py` strict read-only connect/error seams. BUG-3737 supplies the literal file-URI repair independently; FEAT-3711 owns the no-ensure writable seam.
- FEAT-3713 requests only recent sprint CLI evidence; FEAT-3711 requests one project-scoped recommendation identity. Neither performs live SQL inside pure generators/feedback lookup. Recommendation request/schema integration is owned by FEAT-3711.
- Focused read-only, query-plan/work-budget, transaction-consistency and degradation tests; `docs/reference/API.md` documents the request and partial-coverage contracts. No schema/manifest change in this slice.

## Scope Boundaries

- **In scope:** the reader, typed requests/availability/diagnostics and bounded CLI primary-key range walks; integration with BUG-3737's corrected literal-path primitive; tests for absent/compatible-old/incompatible/suppressed/locked/row-budget-saturated states.
- **Out of scope:** recommendation point-lookup/readiness requests, schema migration and events (FEAT-3711), producer/acceptance attribution and pressure (FEAT-3722, deferred), new deadline machinery, write deadlines and remote activation (reuse completed ENH-3720 for local reads).

## Program Design

### Types

- Immutable `HistorySnapshot(availability_by_source, rows_by_source, coverage_by_source, diagnostics, as_of, read_observed_at)`; availability is `available | partial | unavailable(reason)` per source. Coverage records the walked ID span/visited-row upper bound, returned/skipped rows, bounded argument payload bytes and truncation reason. Stamp read_observed_at once when the read transaction snapshot is established, using an injected UTC clock; it is observation provenance distinct from feature as_of.
- Typed `RecentSprintInvocations`; FEAT-3711 extends the request union/dispatch with its table-specific requests. No caller-provided SQL and no global history dump.

### Signatures

- `read_history_snapshot(store, *, as_of: datetime, requests: Sequence[HistoryReadRequest], now: Callable[[], datetime]) -> HistorySnapshot` — read-only, fail-soft; reads only the requested identities/time slices with independent budgets.

### Call Path

Existing `session_store.db.resolve_history_target(..., root=project_root)` → new `read_history_snapshot` → existing `session_store.backend.connect_readonly(..., timeout=0.25, deadline=deadline)` → one read transaction and bounded query/fetch stage → typed snapshot → new pure generator/feedback lookup.

## Implementation Steps

1. Implement after BUG-3737 and FEAT-3561. Pin the request, per-source coverage and compatible-column contracts; make remote rejection precede opening. Verify the corrected literal-path primitive through the new reader rather than repairing it again.
2. Implement explicit short-timeout connection, consistent transaction and bounded CLI ID paging; preserve independent source failures and reject unscoped shared-store recency.
3. Keep point-query/schema-readiness extension ownership in FEAT-3711; test independent request errors, empty-request no-open behavior and as-of/observation boundaries using only the existing CLI source here.
4. Add no-write, lock, out-of-order timestamp, mid-fetch error, redirected-store and concurrent-writer fixtures; document the API and limits.

## Acceptance Criteria

- [ ] Read-only; never creates/migrates the main store or application cache/marker files; a WAL-mode fixture documents SQLite-managed sidecars without main-DB mutation or immutable reads; honors `LL_HISTORY_DB`, root-aware target resolution and typed-target pass-through without cwd re-resolution.
- [ ] BUG-3737 is landed; reader-level existing/missing special-character path fixtures prove DB identity and no truncated/decoded aliases through the corrected backend. Primitive ordinary/deadline branch tests belong to BUG-3737; no second URI implementation is added.
- [ ] Per-source availability with tested absent/compatible-old/incompatible/suppressed/locked/remote-unsupported degradation; range/returned-row-budget saturation cannot yield false exact results. Remote rejection performs no network/access/cache operation.
- [ ] Explicit 250 ms per-lock cap, one shared 1-second ENH-3720 deadline, finite visited-row budgets and one consistent read transaction are tested, including expiry between probes/pages and during fetching/decoding, concurrent writers and connection cleanup. Default backend behavior is unchanged; documented nonpreemptive limits and cross-source/as-of boundaries remain explicit.
- [ ] Tests assert primary-key query plans and finite primary-key-range visit upper bounds and returned-row counts for the unindexed CLI source; out-of-order ingestion/timestamps cannot yield false newest evidence. No unbounded full-store scan/sort or index migration.
- [ ] A multi-megabyte argument fixture proves the guarded SQL projection never transfers/decodes it in full; the returned-row/page caps bound aggregate argument transfer without a new framework. An oversized potentially matching row cannot establish an exact latest-run result. Intentional truncation retains only previously complete witnesses, with cap/coverage provenance; query/decode failure and unscoped ownership do not yield trusted scoring evidence.
- [ ] Request/table/decode failures remain isolated; empty requests open nothing. Recommendation point queries/readiness and old-ID/schema interoperability tests ship with FEAT-3711, not synthetic future columns in this slice.
- [ ] A same-named sprint from a redirected/shared store without verified ownership cannot establish project-local recency; FEAT-3711 can later add project-keyed feedback for that store without trusting its CLI ownership.
- [ ] Relative `LL_HISTORY_DB` fixtures invoke from root and subdirectory, pin cwd-relative resolution and its disclosed exception, and prove the frozen absolute target survives a later cwd change. Config/default paths retain root-relative behavior; typed targets are not re-resolved.
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

- 2026-10-05: Opus review (0.72) plus source audit moved table-specific point-lookup/probe ownership to FEAT-3711, adopted the now-landed ENH-3720 deadline, specified empty-request/no-open and cross-source observation boundaries, and qualified filesystem write claims after a temp-DB reproduction showed strict mode=ro creates WAL/SHM sidecars. Kept the consumed sprint reader and local-only scope.

- 2026-10-05 (additional review): A temporary-store reproduction confirmed that unescaped SQLite URI paths can create/open truncated aliases before query-only protection. Opus (0.76) corroborated the defect. Added independent prerequisite BUG-3737, which repairs existing literal-path opens without waiting for the core; this child reuses the corrected primitive and owns only reader-level integration fixtures. Ordinary/deadline primitive regressions and the shared encoded URI helper belong to the bug.

- 2026-10-05 (identity/bounded-history review): `/ll:advise` with Opus returned "CONDITIONAL GO" (0.78). Verified the local 10,098,544,640-byte store: at 18:40Z its maximum CLI ID was 488924, and the last 2,000-ID range covered about 7.5 hours. Same-connection range-query samples for 2,000/20,000/50,000 IDs took 0.0002/0.0018/0.0044 seconds; 50,000 IDs returned 393 binary-matching CLI rows with 6,569 argument bytes before qualification. These local cache-sensitive measurements are evidence for the initial 50,000-ID bound, not a portable timing guarantee; retain the 1-second deadline, 200-ID ranges and 2,000 returned-row limit. Added bounded SQL binary filtering, a narrow 64 KiB args projection guard and qualified-witness handoff instead of requiring whole-store completeness for every useful observation. A separate probe confirmed relative LL_HISTORY_DB remains cwd-relative; freeze its absolute target and disclose the exception rather than diverging from migrate/CLI producers. No general payload-budget or future recommendation-table framework was added.

## Status

**Open** | Created: 2026-10-04 | Priority: P3
