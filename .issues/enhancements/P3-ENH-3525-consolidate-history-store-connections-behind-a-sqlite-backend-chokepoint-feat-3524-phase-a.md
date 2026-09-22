---
id: ENH-3525
type: ENH
title: Consolidate history-store connections behind a SQLite backend chokepoint (FEAT-3524
  Phase A)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T20:16:57Z'
blocks:
- FEAT-3524
---

# ENH-3525: Consolidate history-store connections behind a SQLite backend chokepoint (FEAT-3524 Phase A)

## Summary

Consolidate every classified history-store connection behind a single
`little_loops.session_store.backend` module with one SQLite adapter, a shared
`connect_readonly()` chokepoint, a backend-neutral error taxonomy, and
backend-aware connection entry points. Repair the known path-resolution bypasses.
No remote configuration key, no new dependency, no `history.backend` schema
change — this is the SQLite-only prerequisite that FEAT-3524 (remote libSQL
support) builds on.

## Current Behavior

- `session_store.schema.ensure_db()` and `connect()` open `sqlite3.connect(str(path))`
  directly; roughly 28 `sqlite3.connect(` call sites across ~15 modules do the same.
- Read-only opens are duplicated by mirroring, not shared: 11 raw
  `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` sites, including
  `issue_history/evolution.py:30`, `issue_history/workspace_quality.py:108-120`,
  `codequery/codegraph.py:81`, `cli/doctor.py:485,547`, `session_store/sessions.py:129,695`,
  `history_reader/_base.py:60`, and the one named wrapper
  `session_store/queries.py::_connect_readonly()` (`:191-200`).
- Two callers bypass `resolve_history_db()` entirely: `decisions.py:578-605`
  (`generate_from_completed()`) hardcodes `project_root / ".ll" / "history.db"` and
  gates on `.exists()`; `cli/doctor.py:542` (`_schema_drift_data()`) resolves
  `Path.cwd() / DEFAULT_DB_PATH`. Both silently ignore `LL_HISTORY_DB` and
  `history.db_path`.
- Every consumer catches raw `sqlite3.OperationalError` / `sqlite3.IntegrityError` /
  `sqlite3.Error` at its own call site (`schema.py:1458,1485`; `queries.py:56,212,379`;
  `lifecycle.py:1447`; `writers.py` `SQLiteTransport`); there is no shared error type.
- `history_reader/_base.py::_connect_readonly()` deliberately does not re-resolve an
  already-root-anchored absolute path (BUG-3181); `queries.py::_connect_readonly()`
  deliberately bypasses `connect()` because that path migrates-on-open (D19).

## Expected Behavior

- One `session_store/backend.py` module: a `Backend` protocol, a `SqliteBackend`,
  `resolve_backend()` (lazy `(module, class)` registry following
  `codequery.core.resolve_provider`, keyed by `provider`), `connect()`,
  `connect_readonly()`, `ensure_schema()`, `supports(capability)`.
- New backend-aware entry points `open_history()` / `open_history_readonly()` that
  every classified history consumer uses. Legacy `resolve_history_db() -> Path`,
  `ensure_db() -> Path`, and `connect(path)` keep their SQLite behavior and signatures.
- `connect_readonly()` never creates or migrates the store, honors the BUG-3181
  no-re-resolve contract for absolute paths, and honors the D19 no-migrate-on-open
  contract; a writable scratch DB may still be `ATTACH`ed by snapshot export.
- Explicit local targets remain explicit local targets: a caller passing a
  concrete path gets that path. Default-shaped arguments (`DEFAULT_DB_PATH`, `None`)
  select the configured history store via the existing precedence
  `explicit path > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`.
- Backend-neutral errors: `HistoryError` base with `HistoryUnavailable`
  (connect/open failure), `HistoryIntegrityError`, `HistoryUnsupported`
  (capability), and `HistoryOperationError` (other database failure). Adapters wrap
  narrowly around driver calls only; the sqlite adapter maps `sqlite3.IntegrityError`
  → `HistoryIntegrityError`, `sqlite3.OperationalError` on open → `HistoryUnavailable`,
  and any other `sqlite3.Error` → `HistoryOperationError`. Consumers never catch
  driver exception types or `ValueError` around whole operations.
- `decisions.py::generate_from_completed()` and `cli/doctor.py::_schema_drift_data()`
  resolve the store through the chokepoint.

## Motivation

History-store access is spread across ~28 raw `sqlite3.connect` sites and 11 mirrored
read-only opens, two of which bypass `LL_HISTORY_DB`/`history.db_path` entirely.
Every consumer branches on raw `sqlite3` exception types. FEAT-3524 (remote libSQL)
cannot be implemented safely on top of that, and the consolidation is independently
valuable: one place to audit path precedence, one read-only contract, one error
surface. Doing it SQLite-only first means it needs no remote endpoint, no new
dependency, and can land and soak before any remote adapter exists.

## Proposed Solution

Promote the spike at `scripts/tests/spike/session_store_backend_dialect/` into
`session_store/backend.py`: a `@runtime_checkable` `Backend` protocol, a
`SqliteBackend`, and a lazy `(module, class)` registry `resolve_backend()` keyed by
`provider` (following `codequery.core.resolve_provider`; lazy because dialect
modules import shared types back from the core module). Add `open_history()` /
`open_history_readonly()` as the backend-aware entry points and a `HistoryError`
taxonomy raised only by narrow adapter wrappers around driver calls. Fold the 11
read-only opens into `connect_readonly()`, preserving `queries.py::_connect_readonly()`'s
no-migrate-on-open contract (D19) and `history_reader/_base.py`'s no-re-resolve
contract (BUG-3181). Route classified history consumers through the entry points;
leave `queue.db`, codegraph, and scratch stores untouched. Fix the `decisions.py`
and `cli/doctor.py` path bypasses. See "Compatibility guarantees and intentional
changes" below for what is and is not preserved.

## Integration Map

### Files to Modify
- New: `scripts/little_loops/session_store/backend.py`
- `little_loops/session_store/{__init__,db,schema,sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`, `little_loops/history_reader/digest.py`
- `little_loops/issue_history/{evolution,workspace_quality,workspace_activity,rework,quality_regressions,_utils,parsing}.py`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats,history_context,session,compact_session,backfill_worker,verify_kinds}.py`
- `little_loops/decisions.py:578-605`
- `docs/reference/API.md` (session-store signatures), `docs/ARCHITECTURE.md:89,636,832`

### Tests
- New: `scripts/tests/test_session_store_backend.py` — registry (every registered
  provider resolves, unknown provider raises typed error, per
  `test_codequery_core.py::TestResolveProvider`), protocol conformance, error
  mapping, `connect_readonly()` never creates/migrates, BUG-3181 and D19 contracts,
  explicit-path-vs-default precedence.
- Existing suites that must stay green: `test_session_store_{db,schema,lifecycle,queries,writers}.py`,
  `test_history_reader_*.py`, `test_cli_history.py`, `test_ll_logs.py`,
  `test_cli_doctor*.py`, `test_cli_ctx_stats.py`, `test_ll_session.py`,
  `test_compaction.py`, `test_transport.py`, `test_feat3304_artifact_dashboard.py`,
  `test_feat3323_sse_bridge.py`.
- New: `test_decisions_*` regression that `generate_from_completed()` honors
  `LL_HISTORY_DB`; doctor regression that `_schema_drift_data()` honors it.
- Promote from `scripts/tests/spike/session_store_backend_dialect/` the locking-sequence,
  idempotent-`ensure_schema`, concurrent-migration, and capability-gate tests.

## Implementation Steps

1. Land `session_store/backend.py` (protocol, `SqliteBackend`, registry, `HistoryError`
   taxonomy, `open_history()`/`open_history_readonly()`) with
   `test_session_store_backend.py`, promoting the spike's locking-sequence,
   idempotent-`ensure_schema`, concurrent-migration, and capability-gate tests.
2. Classify every `sqlite3.connect` site (history consumer vs. independent local store
   vs. scratch) and record the list in this issue; fold the 11 read-only opens into
   `connect_readonly()` with BUG-3181 and D19 contract tests.
3. Route classified consumers through the entry points; convert their `except sqlite3.*`
   branches to `HistoryError` subclasses; update the seven tests that assert on
   `sqlite3.OperationalError`/`sqlite3.Error` for "history failed" deliberately.
4. Fix `decisions.py::generate_from_completed()` and `cli/doctor.py::_schema_drift_data()`
   to resolve through the chokepoint, each with a regression test.
5. Update `docs/reference/API.md` signatures and `docs/ARCHITECTURE.md:89,636,832`;
   run the full suite and confirm every suite named under Tests stays green.

## Impact

- **Priority**: P3 - prerequisite for FEAT-3524; independently reduces duplicated
  connection and error-handling logic.
- **Effort**: Medium - one new module plus mechanical routing across ~15 modules;
  the spike already proves the locking sequence survives parameterization.
- **Risk**: Medium - the error-type change touches every consumer's degradation
  path; mitigated by the named existing suites and the intentional-change list.
- **Breaking Change**: No for the default store location and precedence; yes,
  intentionally, for the exception types history consumers raise (see
  "Compatibility guarantees and intentional changes").

## Compatibility guarantees and intentional changes

This is not a zero-behavior-change refactor. Guaranteed unchanged: default store
location, `LL_HISTORY_DB` / `history.db_path` precedence for every caller that
already honored it, migration sequence and locking (`BEGIN IMMEDIATE`, manual
`isolation_level`, `_split_sql_statements`), `meta.schema_version` semantics, FTS5 /
WAL / VACUUM behavior, `SQLiteTransport`'s best-effort disable-on-failure contract,
and the `ll-logs fleet-review` final-line-is-a-path and `ll-history summary`
exit-0-on-degraded contracts used by loop fragments.

Intentional changes, each with a regression test: (1) history-store consumers
raise `HistoryError` subclasses, with the original `sqlite3` exception preserved as
`__cause__`; tests asserting on `sqlite3.OperationalError` / `sqlite3.Error` for
"history failed" (`test_feat3323_sse_bridge.py:1198`, `test_hook_user_prompt_submit.py:143,302,604`,
`test_ll_issues_research_triage.py:145`, `test_set_status_cli.py:1309`,
`test_hook_post_tool_use.py:190`, `test_feat3445_workspace_activity.py:92`) are
updated deliberately; (2) `decisions.py::generate_from_completed()` now honors
`LL_HISTORY_DB` / `history.db_path` instead of the hardcoded default; (3)
`cli/doctor.py::_schema_drift_data()` now resolves via `resolve_history_db()`.

## Scope classification

Migrate only classified history-store consumers. Audit, but do not migrate:
`queue_store.py` (`queue.db`), `codequery/codegraph.py` (codegraph databases),
snapshot scratch outputs, and any test helper that opens a throwaway local DB on
purpose. Connection counts are the inventory to classify, not the scope.

## Program Design

### Types

- `BackendProvider: Literal["sqlite"]` (extended to `"libsql"` by FEAT-3524)
- `Backend` (`@runtime_checkable` Protocol): `provider: str`; `connect()`,
  `connect_readonly()`, `ensure_schema()`, `supports(capability)`
- `HistoryConnection`, `HistoryCursor`, `HistoryRow` protocols: `execute`,
  `executemany`, `commit`/`rollback`/`close`, `in_transaction`, fetch/iterate,
  `description`, `lastrowid`, `rowcount`, indexed and named row access
- `HistoryError(Exception)` with `HistoryUnavailable`, `HistoryIntegrityError`,
  `HistoryUnsupported`, `HistoryOperationError`

### Signatures

- `resolve_backend(config: dict | None = None) -> Backend` — lazy `(module_path, class_name)` registry keyed by `provider`; unknown provider raises a typed error listing available providers
- `open_history(target: Path | str | None = None) -> HistoryConnection` — explicit local target opens that file; default-shaped target resolves via `resolve_history_db()` precedence
- `open_history_readonly(target: Path | str | None = None) -> HistoryConnection` — never creates or migrates; absolute paths are not re-resolved (BUG-3181)
- `resolve_history_db(...) -> Path`, `ensure_db(...) -> Path`, `connect(path) -> sqlite3.Connection` — signatures unchanged

### Call Path

`resolve_history_db` (precedence) -> `resolve_backend` -> `SqliteBackend.connect` /
`connect_readonly` -> `open_history` / `open_history_readonly` -> history consumer.
`ensure_db` -> `SqliteBackend.ensure_schema` -> `_apply_migrations` (unchanged locking
sequence). `SQLiteTransport` -> `open_history` under its existing lock, catching
`HistoryError`.

## Scope Boundaries

In scope: `session_store/backend.py`, classified history consumers, the 11
read-only opens, the two path-bypass repairs, the `HistoryError` taxonomy and its
consumer catch sites, API/ARCHITECTURE doc updates. Out of scope: `history.backend`
config key, any remote provider or driver dependency, `queue.db`, codegraph
databases, snapshot scratch outputs, the `/ll:configure` history area, and any
change to migration SQL or locking.

## Acceptance Criteria

- [ ] `session_store/backend.py` exists with `Backend`, `SqliteBackend`, `resolve_backend()`
  keyed by `provider`, and `connect`/`connect_readonly`/`ensure_schema`/`supports`.
- [ ] All classified history-store connections (writes and the 11 read-only opens)
  go through the chokepoint; `queue.db`, codegraph, and scratch stores are audited
  and left local; the classification list is recorded in the issue.
- [ ] `connect_readonly()` has tests proving it never creates or migrates the store
  and preserves the BUG-3181 and D19 contracts.
- [ ] Explicit local targets are honored verbatim; default-shaped arguments follow
  `explicit > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`; both covered by tests.
- [ ] `decisions.py::generate_from_completed()` and `cli/doctor.py::_schema_drift_data()`
  resolve through the chokepoint, with regressions.
- [ ] `HistoryError` taxonomy is raised only by adapter wrappers around driver calls;
  `__cause__` preserves the driver exception; no consumer catches `ValueError` or a
  driver exception type for history-store failures.
- [ ] `SQLiteTransport` retains serialized cross-thread writes and best-effort
  disable-on-failure, now catching `HistoryError`.
- [ ] The compatibility-guarantee list above is enforced by the named existing
  suites staying green; each intentional change has a named regression test.
- [ ] No new dependency, no `history.backend` config key, no remote code path.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-22 | Priority: P3
