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
verify_verdict: VALID
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- `session_store/schema.py::connect()` (`:1611`) opens **two** connections per call: `ensure_db(path)` (`:1570`) internally opens-and-closes one bare `sqlite3.connect(str(db_path))` (`:1602`) to migrate, then `connect()` opens a second bare `sqlite3.connect(str(db_path))` (`:1617`) for the live connection it returns. Both call `_configure_connection()` (`:1443`, best-effort `PRAGMA busy_timeout`/`journal_mode` wrapped in `try/except sqlite3.OperationalError`).
- Raw `sqlite3.connect(` call-site count confirmed at 27 across 15 modules (issue's "roughly 28" is a close, hedged estimate — not a correction, a confirmation within rounding).
- An existing backend-neutral-ish exception already exists and is a partial precedent for `HistoryError`: `issue_history/parsing.py::HistoryDbUnavailable(Exception)` (`:411`), raised at 4 call sites (`:452,458,497,509`) uniformly as `raise HistoryDbUnavailable(str(exc)) from exc` — matching the `__cause__`-preservation requirement in Expected Behavior. It is a single, non-hierarchical exception (no subclasses), and its `except` clauses are broad (`except Exception as exc:`), not narrowly scoped to `sqlite3.Error`/`sqlite3.OperationalError` — this diverges from the "adapters wrap narrowly around driver calls only" requirement. `decisions.py:600` already catches `HistoryDbUnavailable` specifically (separate from the raw-`sqlite3.*` catches the issue lists), so the new `HistoryError` taxonomy will coexist with or need to reconcile this existing exception.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- Prior precedent exists in this codebase for the "N raw call sites -> one chokepoint" strategy this issue applies to history-store connections: `host_runner.py::resolve_host()`/`project_child_env()` (line 2352) consolidated all host-CLI subprocess spawns the same way (CHANGELOG.md:3176; also a standing rule in this repo's own CLAUDE.md § "Host CLI Abstraction"). This is corroborating evidence the approach is established here, not novel to this issue.
- The lazy `(module_path, class_name)` registry pattern this issue names (`codequery.core.resolve_provider`) is not the only registry shape in this codebase: `host_runner.py::_HOST_RUNNER_REGISTRY` (line 2225) is an eager, in-module `dict[str, type[HostRunner]]` of class objects (no lazy import), because all runner classes already live in that same file with no circular-import pressure. `session_store/backend.py` does have the same "dialect modules import shared types back from the core module" circular-import pressure `codequery.core` has, so the lazy-tuple shape (already followed by the spike's `resolve_backend()`) remains the better-fitting precedent; noted here as the contested alternative, not a recommendation to switch.
- No existing exception hierarchy in this codebase has 3+ subclasses of a shared base wrapping distinct narrow driver-level errors — an unfiltered `class \w+Error(\w*Error)` / `class \w+(Exception):` sweep of `scripts/little_loops/` found only single-subclass or no-subclass hierarchies (e.g. `fsm/interpolation.py::InterpolationError`/`HeredocCollisionError`, `codequery/core.py::CodeQueryError`/`Unsupported`). The `HistoryError` taxonomy's 4-subclass shape (`HistoryUnavailable`, `HistoryIntegrityError`, `HistoryUnsupported`, `HistoryOperationError`) is a new shape for this codebase, not a reuse of an established one — implement with that in mind rather than searching for a template to copy.

## Integration Map

### Files to Modify
- New: `scripts/little_loops/session_store/backend.py`
- `little_loops/session_store/{__init__,db,schema,sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`, `little_loops/history_reader/digest.py`
- `little_loops/issue_history/{evolution,workspace_quality,workspace_activity,rework,quality_regressions,_utils,parsing}.py`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats,history_context,session,compact_session,backfill_worker,verify_kinds}.py`
- `little_loops/decisions.py:578-605`
- `docs/reference/API.md` (session-store signatures), `docs/ARCHITECTURE.md:89,636,832`

_Wiring pass added by `/ll:wire-issue`:_
- `little_loops/transport.py:2023-2026` — `wire_transports()`'s `elif name == "sqlite":` branch does `SQLiteTransport(base / "history.db")`, a **hardcoded literal path join that bypasses `resolve_history_db()` and `DEFAULT_DB_PATH` entirely** — a third path-resolution bypass alongside `decisions.py` and `cli/doctor.py`. [Agent 1 finding]
- `little_loops/issue_history/collisions.py:28,109` — imports and calls `_connect_readonly` from `little_loops.history_reader` directly; not previously classified under the `issue_history/{...}` list and not among the three `issue_history` call sites enumerated in the "~70 confirmed call sites" breakdown below. [Agent 1 finding]

### Dependent Files (Callers/Importers)

- `_connect_readonly()` (`history_reader/_base.py:60`) has ~70 confirmed call sites, almost
  entirely within `history_reader/{context,digest,events,__init__,search,harness,hooks,
  summary_dag,sessions,formatting,usage,runs}.py` (13 modules import it directly, all via
  `from little_loops.history_reader._base import ... _connect_readonly ...` or the
  `history_reader/__init__.py` re-export), plus `issue_history/rework.py:297`
  (`analyze_rework`), `issue_history/agent_quality.py:511` (`analyze_agent_quality`, imports
  at line 43 — **not currently listed** under Files to Modify above), and
  `session_store/queries.py:288` (`build_snapshot_db`). None of these need their own
  behavior changed if `_connect_readonly()`'s internal implementation is folded into
  `connect_readonly()` without a signature change; they are the regression surface the
  `test_history_reader_*.py` glob and `issue_history` test files already listed under Tests
  must keep covering. `issue_history/agent_quality.py` should be added to Files to Modify's
  classification list.
- `resolve_history_db()` has 50 confirmed callers repo-wide; `decisions.py` and
  `cli/doctor.py` are confirmed **absent** from that caller set, consistent with the two
  bypasses already named above.
- `generate_from_completed()` is called from `cli/issues/decisions.py:390` (`cmd_decisions`).
- `_schema_drift_data()` is called from `cli/doctor.py:625` (`_print_schema_drift_section`),
  `:636` (`_schema_drift_check`), `:1340` (`_print_report`).
- `session_store/queries.py::_connect_readonly()` (`:191-200`) is imported only via
  `session_store/__init__.py:106`'s re-export of `queries.py` symbols; confirmed importers of
  `queries.py` are `test_feat3304_artifact_dashboard.py`, `issue_history/workspace_quality.py`,
  `cli/artifact/dashboard.py`, and `session_store/__init__.py` itself.

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh:54-67,74-94` — a Claude Code hook shell script embeds inline
  `python3 -c` snippets calling `session_store.record_session_lifecycle_event()`,
  `resolve_history_db()` (line 56), and `record_context_pressure_event()`, `resolve_history_db()`
  (line 82). A `.py`-only sweep (the basis for the "50 confirmed callers" count above) misses this
  `.sh` call site; since `resolve_history_db()`'s signature stays unchanged, no code change is
  required here, but it belongs in the caller inventory and its test coverage should stay green.
  [Agent 1 finding]
- `SQLiteTransport` (9 total `.py` importers; `session_store/writers.py` and `session_store/__init__.py`
  already covered above) has 7 additional importers not yet listed: top-level
  `little_loops/__init__.py:75-79` (re-exports `SQLiteTransport`, `record_issue_snapshot`,
  `record_session_lifecycle_event` at the package root), `little_loops/transport.py` (constructs it —
  see the hardcoded-path bypass under Files to Modify), `little_loops/config/features.py`,
  `little_loops/cli/sprint/run.py:657,660,796,807` (two `SQLiteTransport(resolve_history_db())`
  sites), `little_loops/issue_manager.py:54,1742` (`SQLiteTransport(self.db_path)`),
  `little_loops/cli/parallel.py`, and `little_loops/cli/issues/set_status.py:163` (comment-only).
  `SQLiteTransport`'s best-effort disable-on-failure contract is guaranteed unchanged, so these are
  regression-coverage surface, not required code changes. [Agent 1 finding]
- `little_loops/mcp_server/tools.py::_tool_history_search` (`:149-174`) calls `resolve_history_db()`
  and `history_reader.search()` directly with no local `try/except`, relying entirely on
  `search()`'s internal `except sqlite3.OperationalError`/`except sqlite3.Error` catches
  (`history_reader/search.py:59,93,135`) to fail soft. Absent from this inventory until now.
  [Agent 2 finding]
- ~35 additional `cli/` files import `DEFAULT_DB_PATH` (`session_store/db.py:15`) directly rather
  than resolving through `resolve_history_db()` — notably `cli/action.py`, `cli/queue.py`,
  `cli/advise.py`, `cli/harness.py`, `cli/messages.py`, `cli/auto.py`, `cli/docs.py`, `cli/adapt.py`,
  `cli/parallel.py`, `cli/sync.py`, `cli/migrate.py`, seven `cli/verify_*.py` files,
  `cli/loop/__init__.py`, `cli/artifact/__init__.py`, `cli/issues/__init__.py`,
  `cli/sprint/__init__.py`, plus `advisor.py`, `mcp_server/tools.py`, `user_messages.py`,
  `init/cli.py`, `issue_manager.py`. Each direct-constant use is a candidate default-path bypass of
  the same shape found three times already (`decisions.py`, `cli/doctor.py`, `transport.py`) —
  Implementation Step 2's `sqlite3.connect` classification sweep should also enumerate
  `DEFAULT_DB_PATH` direct-import sites rather than treat this list as settled. [Agent 1 finding]
- `session_store/sessions.py:129` (`_query_threads_db`) and `:695` (`_list_codex_workspaces`),
  already counted in the "11 raw read-only opens" above, open read-only connections against
  `~/.codex/state_*.sqlite` — **Codex's own external session-index database, not `.ll/history.db`**.
  They never flow through `resolve_history_db()`/`LL_HISTORY_DB`/`history.db_path` precedence today.
  Folding them into `connect_readonly()` (whose BUG-3181/D19 contracts are specifically about the
  `.ll/history.db` store) is a classification nuance for Implementation Step 2 to resolve explicitly,
  not an assumption to inherit from the read-only-opens count. [Agent 2 finding]
- `HistoryDbUnavailable` (defined `issue_history/parsing.py:411`) reconciliation surface, beyond
  the 4 raise sites and `decisions.py`'s catch already noted: re-exported in `__all__` at
  `issue_history/__init__.py:163,267`; caught (untested) at `cli/history.py:499,507`. [Agent 1 +
  Agent 3 findings]

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

_Wiring pass added by `/ll:wire-issue`:_
- Existing suites that must stay green, not previously named: `test_issue_history_agent_quality.py`
  (21 test classes covering `agent_quality.py`, added to Files to Modify by the earlier
  research pass but its dedicated test file wasn't added to this Tests section);
  `test_mcp_server.py`, `test_feat_3149_mcp_mutation_tools.py`, `test_enh_3171_mcp_project_root.py`
  (regression surface for `mcp_server/tools.py::_tool_history_search`). [Agent 1 + Agent 3 findings]
- Test that may break: `test_issue_history_agent_quality.py::TestEmptyAndMissingDb::test_missing_db_returns_empty_analysis`
  (`:173-178`) depends on `_connect_readonly()`'s current "return `None` on open failure" contract
  (`history_reader/_base.py:60-84`), checked at `agent_quality.py:511-513`
  (`if conn is None: return empty`). If the consolidated `connect_readonly()` raises a `HistoryError`
  instead of returning `None`, this test's missing-db path breaks. [Agent 3 finding]
- `HistoryDbUnavailable` reconciliation regression: `test_issue_history_parsing.py:667-679`
  (`TestScanCompletedIssuesFromDb::test_raises_history_db_unavailable_on_open_failure`) is the only
  test in the repo asserting on `HistoryDbUnavailable` and is not in the 7-test
  "must be updated" list above — whatever the `HistoryError` taxonomy does to reconcile with
  `HistoryDbUnavailable` must keep this test meaningful (update it or confirm
  `HistoryDbUnavailable` keeps raising unchanged). [Agent 1 + Agent 3 findings]
- Searched, no findings (confirmed, not gaps): no existing test asserts on the two-connections-per-call
  behavior of `schema.py::connect()`/`ensure_db()` (safe to consolidate); no existing
  `test_cli_doctor_install_checks.py::TestSchemaDrift` or `test_decisions.py::TestGenerateFromCompleted`
  test sets `LL_HISTORY_DB`/`history.db_path` divergently from cwd, so fixing the two bypasses won't
  break any of the 13 existing tests in those classes. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- Test-pattern findings for the "### Tests" subsection above: the registry/protocol-conformance shape to model `test_session_store_backend.py` after (the issue's own citation of `test_codequery_core.py::TestResolveProvider` has a companion class worth reusing too): `TestResolveProvider` (known-key resolves, unknown-key raises the module's typed error, `isinstance(x, Protocol)` conformance) plus a separate `TestProtocolConformance` class parameterized off a `provider` fixture — its docstring explicitly invites a later provider to "extend this class or reuse its assertions against its own provider name" (`test_codequery_core.py`).
- Precedent for "`connect_readonly()` never creates or migrates" tests exists in two styles, both usable: a behavioral sha256-before/after hash comparison of the DB file (`test_feat3304_artifact_dashboard.py::TestSourceDbUntouched::test_history_db_byte_identical_after_export`, lines 444-459), and a source-text substring assertion pinned between two named function anchors in the target file, asserting the migrating opener's name is absent and the read-only URI marker is present (`test_snapshot_builder_never_uses_the_migrating_open_path` in the same class).
- Precedent for the BUG-3181 `root=` no-re-resolve contract tests: `test_session_store_db.py::test_root_anchors_default_away_from_cwd`, `::test_root_anchors_config_lookup`, `::test_env_still_outranks_root` (each asserts `resolve_history_db(None, root=project) == <expected>` under a `monkeypatch.chdir` to a *different* directory); the MCP-tool caller side of the same contract is documented at `test_enh_3171_mcp_project_root.py:182`.
- The spike's own test file (`scripts/tests/spike/session_store_backend_dialect/test_backend.py`) already has `TestDialectMigration`, `TestCapabilityGate` (asserts `UnsupportedCapability` with a `match=` regex on both capability name and backend kind), `TestConcurrentMigration` (4-thread `threading.Barrier` race against `ensure_schema()`, asserting a single `meta` row survives), and `TestSpikeIsolation::test_spike_does_not_import_production_session_store` (`ast.parse`/`ast.walk` asserting the spike imports no `little_loops.session_store` module) — these are the four tests "Implementation Steps" item 1 says to promote; their concrete names/locations are recorded here so the promotion is a rename/move, not a rewrite.

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
   > ⚠ Superseded — third bypass found: `transport.py:2023` (wire-issue)
5. Update `docs/reference/API.md` signatures and `docs/ARCHITECTURE.md:89,636,832`;
   run the full suite and confirm every suite named under Tests stays green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Fix `little_loops/transport.py:2023-2026`'s `wire_transports()` `"sqlite"` branch — it hardcodes
  `base / "history.db"`, bypassing `resolve_history_db()`/`DEFAULT_DB_PATH`, the same bug shape as
  the two bypasses already named in Expected Behavior and Acceptance Criteria.
- Route `little_loops/issue_history/collisions.py:28,109` through the new entry points — it
  currently calls `_connect_readonly` from `history_reader` directly, like `agent_quality.py` did
  before being added to Files to Modify.
- Explicitly classify `session_store/sessions.py:129,695` in Implementation Step 2's sqlite3.connect
  sweep as opening Codex's external `~/.codex/state_*.sqlite`, not `.ll/history.db` — decide whether
  these fold into `connect_readonly()` or stay a separate, un-migrated read-only path.
- Decide the `HistoryDbUnavailable` (`issue_history/parsing.py:411`) reconciliation: keep it raising
  unchanged (re-exported at `issue_history/__init__.py:163,267`, caught at `cli/history.py:499,507`,
  asserted by `test_issue_history_parsing.py:667-679`) or fold it into the `HistoryError` taxonomy —
  and update `agent_quality.py:511-513`'s `if conn is None: return empty` branch to match whatever
  `connect_readonly()` does on open failure, since `TestEmptyAndMissingDb::test_missing_db_returns_empty_analysis`
  depends on the current return-`None` contract.
- Widen Implementation Step 2's `sqlite3.connect` classification sweep to also enumerate
  `DEFAULT_DB_PATH` direct-import sites (~35 `cli/` files bypass `resolve_history_db()`'s precedence
  by importing the constant directly) rather than treating the connection-site count as the full
  inventory.

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
`cli/doctor.py::_schema_drift_data()` now resolves via `resolve_history_db()`;
(4) `little_loops/transport.py::wire_transports()`'s `"sqlite"` branch now resolves via
`resolve_history_db()` instead of hardcoding `base / "history.db"` — a third bypass
found by `/ll:wire-issue`, not previously named here.

_Wiring pass added by `/ll:wire-issue`:_ concrete gate consumers backing the generic
"loop fragments" reference above, none previously named individually: `ll-history summary`
is consumed by `scripts/little_loops/loops/backlog-flow-optimizer.yaml:35` and
`.../evaluation-quality.yaml:46` (pattern documented at `.../loops/lib/cli.yaml:64-66`);
`ll-logs fleet-review`'s final-line-is-a-path contract is consumed by
`.../loops/fleet-loop-improve.yaml:78,80`. Two further exit-code-degrade contracts on files
under active modification are not yet named as guarantees: `ll-history-context`
(backed by `cli/history_context.py`, in Files to Modify) is invoked via `2>/dev/null || true`
by `commands/refine-issue.md:153`, `commands/ready-issue.md:136`, and
`commands/create-sprint.md:366`; `ll-logs sequences --json` (backed by `cli/logs.py`) has an
explicit empty-array/nonzero-exit fallback documented in `commands/loop-suggester.md:309-312`.
Checked and cleared: `.loops/ll-logs-telemetry-digest.yaml`'s three grepped stderr strings
("No history.db found", "No sessions found for:", "No catalog skills found") all originate
from session-discovery/file-existence checks, not from catching a raw `sqlite3.*` exception,
so the `HistoryError` taxonomy change does not affect them. [Agent 2 finding]

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- Confirmed `codequery/core.py::resolve_provider()` signature: `resolve_provider(name: str = "auto") -> CodeQueryProvider` (`codequery/core.py:103`), backed by `_PROVIDER_MAP: dict[str, tuple[str, str]]` (`:97-100`) and `_instantiate()` (`:135-142`, plain `importlib.import_module` + `getattr` + zero-arg construction). This is the concrete shape `resolve_backend()` is meant to mirror.
- The spike's existing `resolve_backend()` (`scripts/tests/spike/session_store_backend_dialect/backend.py:52-58`) has a different signature than this section's own `### Signatures`: `resolve_backend(kind: str, db_path: Path) -> Backend` (two positional args), not `resolve_backend(config: dict | None = None) -> Backend`. Reconciling these — whether the promoted module keeps the spike's `(kind, db_path)` shape, adopts the config-dict shape written above, or does both — is an open implementation decision, not resolved by either the spike or this section as written.

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
  > ⚠ Superseded — third bypass found: `transport.py:2023` (wire-issue)
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


## Session Log
- `/ll:verify-issues` - 2026-09-22T20:50:47 - `d5913727-aee2-4da4-b9b6-0c7c106cc141.jsonl`
- `/ll:wire-issue` - 2026-09-22T20:46:38 - `5e6fdfe4-a051-499c-b448-1629fbe99667.jsonl`
- `/ll:refine-issue` - 2026-09-22T20:35:26 - `000d50cc-8e65-459d-9c90-7e440ec813a8.jsonl`
