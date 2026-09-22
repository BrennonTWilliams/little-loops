---
id: ENH-3525
type: ENH
title: Consolidate history-store connections behind a SQLite backend chokepoint (FEAT-3524
  Phase A)
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-22'
captured_at: '2026-09-22T20:16:57Z'
completed_at: '2026-09-22T23:29:26Z'
verify_verdict: VALID
blocks:
- FEAT-3524
decomposed_into:
- ENH-3526
confidence_score: 100
outcome_confidence: 55
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
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
- Read-only opens are duplicated by mirroring, not shared. There are 10 raw
  `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` sites plus one read-only `ATTACH`
  (line numbers verified 2026-09-22):
  - **History-store (in scope, 7 opens + 1 ATTACH):** `issue_history/evolution.py:41`,
    `issue_history/workspace_quality.py:117` (+ `ATTACH … mode=ro` at `:209`),
    `cli/doctor.py:485,547`, `cli/doctor_trim.py:278`, `history_reader/_base.py:78`
    (inside `_connect_readonly()`, `:60`), and `session_store/queries.py::_connect_readonly()`
    (`:191-200`).
  - **Not history-store (audited, excluded):** `codequery/codegraph.py:86` (codegraph DB);
    `session_store/sessions.py:129,695` (Codex's own `~/.codex/state_*.sqlite` index).
- The two in-scope read-only openers have **different contracts**:
  - `history_reader/_base.py::_connect_readonly()` is not actually read-only end to end:
    it calls `ensure_db(db_path)` first (creates the file/dir and **applies migrations** over
    a writable connection), then opens `mode=ro`. On any `sqlite3.Error` it logs and
    **returns `None`**. Its ~70 callers therefore always read a store at the current schema.
  - `session_store/queries.py::_connect_readonly()` is strict read-only (never creates or
    migrates, D19) and **raises** on failure.
  - Latent bug in `_base`: it discards `ensure_db()`'s return value and opens `db_path` as
    given (BUG-3181), but `ensure_db()` re-resolves default-shaped paths through
    env/config — so for a default-shaped argument it can migrate a *different* file than the
    one it then opens.
- Three callers bypass `resolve_history_db()` entirely, silently ignoring `LL_HISTORY_DB`
  and `history.db_path`:
  - `decisions.py:578-605` (`generate_from_completed()`) hardcodes
    `project_root / ".ll" / "history.db"` and gates on `.exists()`.
  - `cli/doctor.py:542` (`_schema_drift_data()`) resolves `Path.cwd() / DEFAULT_DB_PATH`.
  - `transport.py:2023-2026` (`wire_transports()`'s `"sqlite"` branch) writes to
    `(log_dir or Path(".ll")) / "history.db"`, while the adjacent fallback in
    `cli/parallel.py:327` / `cli/sprint/run.py` uses `resolve_history_db()`. With
    `LL_HISTORY_DB` set, event rows land in a different DB depending on whether `"sqlite"`
    is listed in `events.transports`.
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
- Two named read-only contracts, each assigned explicitly per caller:
  - **Strict** — `connect_readonly(path)`: never creates, never migrates (D19). Used by
    `queries.py` snapshot export, `cli/doctor*.py`, and any caller that must not mutate the
    store. A writable scratch DB may still be `ATTACH`ed by snapshot export.
  - **Ensure-then-read** — `open_history_readonly(target, ensure=True)`: resolves the
    target **once**, runs `ensure_schema()` on that exact path over a separate writable
    connection, then opens the same path via `connect_readonly()`. This preserves today's
    `history_reader` behavior (callers read a current-schema store) and fixes the latent
    migrate-a-different-file bug.
  - Both honor the BUG-3181 no-re-resolve contract for already-resolved absolute paths.
- Read-only failure contract: `connect_readonly()` / `open_history_readonly()` **raise
  `HistoryUnavailable`**. `history_reader/_base.py::_connect_readonly()` stays as a thin
  compatibility wrapper (same signature) that catches `HistoryError`, logs, and returns
  `None`, so its ~70 callers are unchanged.
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
- The existing `issue_history/parsing.py::HistoryDbUnavailable` becomes a subclass of
  `HistoryUnavailable` (no rename). Existing catches (`decisions.py:600`,
  `cli/history.py:499,507`), the `issue_history/__init__.py` re-export, and
  `test_issue_history_parsing.py:667-679` keep working unchanged.
- `decisions.py::generate_from_completed()`, `cli/doctor.py::_schema_drift_data()`, and
  `transport.py::wire_transports()`'s `"sqlite"` branch resolve the store through the
  chokepoint. For `wire_transports()`: with no `log_dir`, use `resolve_history_db()`. An
  explicit `log_dir` is a log/transport directory, not a history-store target, so it no
  longer determines the history path either. The sqlite transport and the
  `parallel.py`/`sprint/run.py` fallback then always agree.

## Motivation

History-store access is spread across ~27 raw `sqlite3.connect` sites and 7 mirrored
history-store read-only opens with two incompatible contracts. Three callers bypass
`LL_HISTORY_DB`/`history.db_path` entirely.
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
taxonomy raised only by narrow adapter wrappers around driver calls. Fold the 7 in-scope
read-only opens (plus the `workspace_quality` read-only `ATTACH`) into the two named
read-only contracts (strict vs. ensure-then-read, see Expected Behavior), preserving
`queries.py::_connect_readonly()`'s no-migrate-on-open contract (D19),
`history_reader/_base.py`'s no-re-resolve contract (BUG-3181), and `history_reader`'s
migrate-before-read behavior. Route classified history consumers through the entry points;
leave `queue.db`, codegraph, Codex's `~/.codex` index, and scratch stores untouched. Fix
the three path bypasses (`decisions.py`, `cli/doctor.py`, `transport.py`). Add a gate test
so the chokepoint stays the only opener. See "Compatibility guarantees and intentional
changes" below for what is and is not preserved.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-22 — based on codebase analysis:_

- Prior precedent exists in this codebase for the "N raw call sites -> one chokepoint" strategy this issue applies to history-store connections: `host_runner.py::project_child_env()` (`:2352`) / `resolve_host()` (`:2535`) consolidated all host-CLI subprocess spawns the same way (CHANGELOG.md:3176; also a standing rule in this repo's own CLAUDE.md § "Host CLI Abstraction"). This is corroborating evidence the approach is established here, not novel to this issue.
- The lazy `(module_path, class_name)` registry pattern this issue names (`codequery.core.resolve_provider`) is not the only registry shape in this codebase: `host_runner.py::_HOST_RUNNER_REGISTRY` (line 2225) is an eager, in-module `dict[str, type[HostRunner]]` of class objects (no lazy import), because all runner classes already live in that same file with no circular-import pressure. `session_store/backend.py` does have the same "dialect modules import shared types back from the core module" circular-import pressure `codequery.core` has, so the lazy-tuple shape (already followed by the spike's `resolve_backend()`) remains the better-fitting precedent; noted here as the contested alternative, not a recommendation to switch.
- No existing exception hierarchy in this codebase has 3+ subclasses of a shared base wrapping distinct narrow driver-level errors — an unfiltered `class \w+Error(\w*Error)` / `class \w+(Exception):` sweep of `scripts/little_loops/` found only single-subclass or no-subclass hierarchies (e.g. `fsm/interpolation.py::InterpolationError`/`HeredocCollisionError`, `codequery/core.py::CodeQueryError`/`Unsupported`). The `HistoryError` taxonomy's 4-subclass shape (`HistoryUnavailable`, `HistoryIntegrityError`, `HistoryUnsupported`, `HistoryOperationError`) is a new shape for this codebase, not a reuse of an established one — implement with that in mind rather than searching for a template to copy.

## Integration Map

### Files to Modify
- New: `scripts/little_loops/session_store/backend.py`
- `little_loops/session_store/{__init__,db,schema,sessions,queries,lifecycle,writers}.py`
- `little_loops/history_reader/_base.py`, `little_loops/history_reader/digest.py`
- `little_loops/issue_history/{evolution,workspace_quality,workspace_activity,rework,quality_regressions,_utils,parsing}.py`
- `little_loops/cli/{history,logs,doctor,doctor_trim,ctx_stats,history_context,session,compact_session,backfill_worker,verify_kinds}.py`
  (`cli/doctor_trim.py:278` is an in-scope strict read-only open)
- `little_loops/issue_history/agent_quality.py`, `little_loops/issue_history/collisions.py`
- `little_loops/transport.py:2023-2026` (third path bypass)
- `little_loops/decisions.py:578-605`
- New: `scripts/tests/test_history_store_chokepoint_gate.py` (raw-open gate, see Tests)
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
  (listed as excluded in Current Behavior), open read-only connections against
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
  `LL_HISTORY_DB`; doctor regression that `_schema_drift_data()` honors it;
  `test_transport.py` regression that `wire_transports()` with `"sqlite"` writes to the
  `LL_HISTORY_DB` target, the same DB the `parallel.py` fallback would use.
- New: ensure-then-read regression. An old-schema store opened via
  `open_history_readonly(ensure=True)` is migrated first. A default-shaped argument migrates
  and opens the **same** file (latent `_base` bug). A strict `connect_readonly()` against a
  missing or old-schema store raises `HistoryUnavailable` and leaves the file byte-identical
  (sha256 before/after, per `test_feat3304_artifact_dashboard.py::TestSourceDbUntouched`).
- New: `_base._connect_readonly()` compatibility wrapper still returns `None` on open
  failure. Re-verify `test_issue_history_agent_quality.py::TestEmptyAndMissingDb::test_missing_db_returns_empty_analysis`:
  it passes today because `ensure_db()` *creates* the missing store, not via the `None` path.
- New: `HistoryDbUnavailable` is caught by `except HistoryUnavailable`.
- New gate: `scripts/tests/test_history_store_chokepoint_gate.py`. It AST/grep-scans
  `scripts/little_loops/` and fails on any raw `sqlite3.connect(` outside
  `session_store/backend.py` and a named allowlist: `queue_store.py`,
  `codequery/codegraph.py`, `session_store/sessions.py` (Codex index), and scratch/snapshot
  output sites, each with a one-line reason. This keeps the chokepoint from eroding, the same
  way the host-CLI rule is enforced.
- Promote from `scripts/tests/spike/session_store_backend_dialect/` the locking-sequence,
  idempotent-`ensure_schema`, concurrent-migration, and capability-gate tests.
- New: regression proving `session_store/queries.py::search()` still raises
  `ValueError` (not a `HistoryError` subclass) on malformed FTS5 query syntax after
  the taxonomy lands — its `except sqlite3.OperationalError` at `:56` is an
  explicit exclusion from the Step 5 conversion (see Compatibility guarantees;
  found by `/ll:verify-issues`, previously untested and unlisted).

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

> **Sizing:** ~30 files, a change to the exception types consumers raise, and seven
> deliberate test rewrites is more than "Medium". Steps are grouped into two
> independently landable commits (A1 / A2). If `/ll:issue-size-review` agrees, split A2
> into its own issue that also blocks FEAT-3524.

**A1 — chokepoint, contracts, bypass fixes (low risk, no consumer error-type changes)**

1. Land `session_store/backend.py` (protocol, `SqliteBackend`, registry, `HistoryError`
   taxonomy, `open_history()`/`open_history_readonly()`, strict `connect_readonly()`) with
   `test_session_store_backend.py`, promoting the spike's locking-sequence,
   idempotent-`ensure_schema`, concurrent-migration, and capability-gate tests. Make
   `HistoryDbUnavailable` subclass `HistoryUnavailable`.
2. Classify every `sqlite3.connect` site (history consumer vs. independent local store
   vs. scratch) and record the list in this issue. Fold the 7 in-scope read-only opens and
   the `workspace_quality` `ATTACH` into the strict or ensure-then-read contract, recording
   which caller gets which. Reimplement `history_reader/_base.py::_connect_readonly()` as
   the `None`-returning wrapper over ensure-then-read. Add BUG-3181, D19, and
   ensure-then-read contract tests.
3. Fix all three path bypasses, each with a regression test:
   `decisions.py::generate_from_completed()`, `cli/doctor.py::_schema_drift_data()`,
   `transport.py::wire_transports()` `"sqlite"` branch.
4. Add `test_history_store_chokepoint_gate.py` with the allowlist.

**A2 — consumer error-type conversion (carries the behavioral risk)**

5. Route remaining classified consumers through the entry points; convert their
   `except sqlite3.*` branches to `HistoryError` subclasses; update the seven tests that
   assert on `sqlite3.OperationalError`/`sqlite3.Error` for "history failed" deliberately.
6. Update `docs/reference/API.md` signatures and `docs/ARCHITECTURE.md:89,636,832`;
   run the full suite and confirm every suite named under Tests stays green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Fix `little_loops/transport.py:2023-2026`'s `wire_transports()` `"sqlite"` branch (now Step 3).
- Route `little_loops/issue_history/collisions.py:28,109` through the new entry points. It
  currently calls `_connect_readonly` from `history_reader` directly; the compatibility
  wrapper covers it, so no call-site change is required.
- **Decided:** `session_store/sessions.py:129,695` open Codex's external
  `~/.codex/state_*.sqlite`, not `.ll/history.db`. They are **excluded** and stay raw
  read-only opens, allowlisted in the gate test.
- **Decided:** `HistoryDbUnavailable` subclasses `HistoryUnavailable`, unchanged otherwise.
  `agent_quality.py:511-513`'s `if conn is None` branch is unchanged because `_base`'s
  wrapper keeps returning `None`.
- **Decided (bounded):** do not treat the ~35 `DEFAULT_DB_PATH` direct imports as bypasses
  by default. Most are argparse defaults, which count as default-shaped arguments and are
  resolved by the chokepoint. Step 2 audits only sites that **open or path-join a file
  without resolving it** (the `decisions`/`doctor`/`transport` shape) and records any hits
  here. It does not rewrite every import.

## Impact

- **Priority**: P3 - prerequisite for FEAT-3524; independently reduces duplicated
  connection and error-handling logic.
- **Effort**: Medium-Large. One new module, routing across ~30 files, a consumer
  error-type conversion, and seven deliberate test rewrites. It is staged as A1/A2 (see
  Implementation Steps). The spike already proves the locking sequence survives
  parameterization.
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
WAL / VACUUM behavior, `history_reader`'s migrate-before-read behavior and its
`_connect_readonly()` return-`None`-on-failure contract, `HistoryDbUnavailable`'s name and
catchability, `connect()`'s current two-connection open (deliberately out of scope),
`SQLiteTransport`'s best-effort disable-on-failure contract,
the `ll-logs fleet-review` final-line-is-a-path and `ll-history summary`
exit-0-on-degraded contracts used by loop fragments, and
`session_store/queries.py::search()`'s `sqlite3.OperationalError` ->
`ValueError(f"invalid FTS query {query!r}: ...")` translation (`:56`) on malformed
FTS5 query syntax — an input-validation contract, not a history-store-failure
signal, so it is excluded from item (1) below (found by `/ll:verify-issues`,
2026-09-22).

Intentional changes, each with a regression test: (1) history-store consumers
raise `HistoryError` subclasses, with the original `sqlite3` exception preserved as
`__cause__`, excluding `queries.py::search()`'s FTS-syntax `ValueError` translation
above; tests asserting on `sqlite3.OperationalError` / `sqlite3.Error` for
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
`queue_store.py` (`queue.db`), `codequery/codegraph.py:86` (codegraph databases),
`session_store/sessions.py:129,695` (Codex's `~/.codex/state_*.sqlite` index), snapshot
scratch outputs, and any test helper that opens a throwaway local DB on purpose. Each
exclusion appears in the gate test's allowlist with its reason. Connection counts are the
inventory to classify, not the scope.

## Program Design

### Types

- `BackendProvider: Literal["sqlite"]` (extended to `"libsql"` by FEAT-3524)
- `Backend` (`@runtime_checkable` Protocol): `provider: str`; `connect()`,
  `connect_readonly()`, `ensure_schema()`, `supports(capability)`
- `HistoryConnection`, `HistoryCursor`, `HistoryRow` protocols: `execute`,
  `executemany`, `commit`/`rollback`/`close`, `in_transaction`, fetch/iterate,
  `description`, `lastrowid`, `rowcount`, indexed and named row access
  - `open_history*` **set the row factory themselves**, so named row access is part of the
    contract. Consumers must not assign `conn.row_factory`: 8 files do today, and against a
    `HistoryConnection` return type that is a mypy error.
  - SQLite-only features used by consumers go behind `supports(capability)`, not the
    protocol: `"attach"` (`ATTACH`, 5 files incl. `workspace_quality.py:209` and snapshot
    export), `"vacuum"` (`VACUUM`, 4 files), and `"create_function"` (1 file). Callers
    check the capability or receive `HistoryUnsupported`. `SqliteBackend` supports all
    three. This is the seam FEAT-3524's libSQL remote (no `ATTACH`) needs.
- `HistoryError(Exception)` with `HistoryUnavailable`, `HistoryIntegrityError`,
  `HistoryUnsupported`, `HistoryOperationError`; `HistoryDbUnavailable(HistoryUnavailable)`

### Signatures

- `resolve_backend(provider: str = "sqlite") -> Backend` — **decided:** lazy `(module_path, class_name)` registry keyed by `provider`, zero-arg construction as in `codequery.core._instantiate()`; the store path is passed to `connect()`/`connect_readonly()`/`ensure_schema()`, not to the constructor. Replaces both the spike's `(kind, db_path)` shape and the earlier `config: dict` draft. Phase A has no config key; FEAT-3524 adds a config lookup that selects the `provider` string. Unknown provider raises a typed error listing available providers.
- `Backend.connect(path) / connect_readonly(path) / ensure_schema(path) / supports(capability: str) -> bool`
- `open_history(target: Path | str | None = None) -> HistoryConnection` — explicit local target opens that file; default-shaped target resolves via `resolve_history_db()` precedence
- `open_history_readonly(target: Path | str | None = None, *, ensure: bool = False) -> HistoryConnection` — resolves once. `ensure=False` is strict (never creates or migrates, D19). `ensure=True` runs `ensure_schema()` on the resolved path, then opens that same path read-only. Absolute paths are never re-resolved (BUG-3181). Raises `HistoryUnavailable` on open failure.
- `history_reader._base._connect_readonly(db_path) -> sqlite3.Connection | None` — signature unchanged; compatibility wrapper over `open_history_readonly(db_path, ensure=True)` that returns `None` on `HistoryError`
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
- The spike's existing `resolve_backend()` (`scripts/tests/spike/session_store_backend_dialect/backend.py:52-58`) has signature `resolve_backend(kind: str, db_path: Path) -> Backend`. **Resolved 2026-09-22:** the promoted module uses `resolve_backend(provider: str = "sqlite")`, with the path passed per call (see Signatures). Promoted spike tests are adapted to that shape.

## Scope Boundaries

In scope: `session_store/backend.py`, classified history consumers, the 7 in-scope
read-only opens plus the `workspace_quality` read-only `ATTACH`, the three path-bypass
repairs, the chokepoint gate test, the `HistoryError` taxonomy and its consumer catch sites,
API/ARCHITECTURE doc updates. Out of scope: `history.backend` config key, any remote
provider or driver dependency, `queue.db`, codegraph databases, Codex's `~/.codex` index,
snapshot scratch outputs, the `/ll:configure` history area, collapsing `connect()`'s
two-connection open, and any change to migration SQL or locking.

## Acceptance Criteria

> **Split 2026-09-22:** the A2-scoped items below (write-consumer routing and
> the `HistoryError` consumer conversion) are moved to
> [[ENH-3526]] rather than attempted in this issue — see "A2 Split" below.
> Items satisfied by A1 (landed in `bb2c9c2b3`) are checked.

- [x] `session_store/backend.py` exists with `Backend`, `SqliteBackend`, `resolve_backend()`
  keyed by `provider`, and `connect`/`connect_readonly`/`ensure_schema`/`supports`.
- [ ] All classified history-store connections (writes, the 7 in-scope read-only opens,
  and the `workspace_quality` read-only `ATTACH`) go through the chokepoint. `queue.db`,
  codegraph, Codex's `~/.codex` index, and scratch stores are audited and left local. The
  classification list, including which read-only callers are strict vs. ensure-then-read,
  is recorded in the issue.
  — **Read-only opens: done in A1.** Write consumers (`writers.py`,
  `lifecycle.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/history.py`):
  moved to [[ENH-3526]].
- [x] Strict `connect_readonly()` has tests proving it never creates or migrates the store
  (byte-identical before/after) and preserves the BUG-3181 and D19 contracts.
- [x] Ensure-then-read has tests proving it migrates and opens the **same** resolved file,
  and `history_reader`'s `_connect_readonly()` still returns `None` on failure.
- [x] Explicit local targets are honored verbatim; default-shaped arguments follow
  `explicit > LL_HISTORY_DB > history.db_path > DEFAULT_DB_PATH`; both covered by tests.
- [x] `decisions.py::generate_from_completed()`, `cli/doctor.py::_schema_drift_data()`, and
  `transport.py::wire_transports()`'s `"sqlite"` branch resolve through the chokepoint, each
  with an `LL_HISTORY_DB` regression.
- [x] `test_history_store_chokepoint_gate.py` fails on any raw `sqlite3.connect(` outside
  `backend.py` and the reasoned allowlist. (Allowlist still carries five provisional
  entries by design — [[ENH-3526]] shrinks it to zero.)
- [ ] `open_history*` set the row factory; no history consumer assigns `row_factory`.
  `ATTACH`/`VACUUM`/`create_function` use is gated by `supports()`.
  — Read paths done in A1 (`workspace_quality.py` ATTACH gated on
  `supports("attach")`). `lifecycle.py`'s VACUUM (`supports("vacuum")`)
  moved to [[ENH-3526]].
- [x] `HistoryDbUnavailable` subclasses `HistoryUnavailable`;
  `test_issue_history_parsing.py:667-679` passes unchanged.
- [ ] `HistoryError` taxonomy is raised only by adapter wrappers around driver calls;
  `__cause__` preserves the driver exception; no consumer catches `ValueError` or a
  driver exception type for history-store failures.
  — Moved to [[ENH-3526]], which also must resolve the sqlite3→`HistoryError`
  write-path translation design question discovered while scoping the split
  (`SqliteBackend.connect()` returns a raw `sqlite3.Connection`, unlike
  `connect_readonly()`).
- [ ] `SQLiteTransport` retains serialized cross-thread writes and best-effort
  disable-on-failure, now catching `HistoryError`.
  — Moved to [[ENH-3526]].
- [ ] The compatibility-guarantee list above is enforced by the named existing
  suites staying green; each intentional change has a named regression test.
  — A1's compatibility guarantees hold (full suite green, see "A1 Landed"
  below). The seven intentional-change test rewrites are [[ENH-3526]] scope.
- [x] No new dependency, no `history.backend` config key, no remote code path.

### A2 Split

Implementation Steps 5-6 (route remaining write consumers through the
entry points, convert their exception types, update docs) are split into
[[ENH-3526]], which also inherits this issue's `blocks: FEAT-3524`. Reasons,
both already on record in this issue before this pass:

1. **Sizing note** (Implementation Steps): "If `/ll:issue-size-review`
   agrees, split A2 into its own issue that also blocks FEAT-3524."
2. **Confidence Check Notes**: Outcome Confidence 55/100 (LOW), recommending
   "landing/soaking A1 first and re-running `/ll:confidence-check` before
   starting A2" — A2 "carries the behavioral risk" as a per-site behavioral
   change, not a uniform mechanical substitution.

Scoping the split surfaced a concrete, previously-undocumented design gap
supporting that risk assessment: `SqliteBackend.connect()` (`backend.py:146`)
returns a raw `sqlite3.Connection` with no error-translating wrapper, so
Step 5's "convert `except sqlite3.*` to `HistoryError`" cannot be a
mechanical catch-clause rename at the ~20 write call sites in `writers.py`/
`lifecycle.py`/`cli/{logs,ctx_stats,history}.py` — recorded in full in
[[ENH-3526]].

This issue (A1's chokepoint, contracts, and three path-bypass fixes) is
complete and is being closed as done; [[ENH-3526]] carries the remaining
scope forward against `FEAT-3524`.

## Related Key Documentation

- `docs/ARCHITECTURE.md` (`:89,636,832` — session-store / history.db architecture)
- `docs/reference/API.md` (`little_loops.session_store` signatures)
- FEAT-3524 (the remote libSQL feature this unblocks)

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-22:_

Verdict at time of check: **PROPOSAL_UNSOUND** (corrections below applied in the
same pass, so the issue as it now reads is up to date — this section is a record
of what was wrong and fixed, not an outstanding action item).

- **Graph**: provider=`codegraph` freshness=`fresh`.
- **Evidence-quote check** (`ll-verify-evidence --json`): clean, 0 findings.
- **Decisions log**: no active required rules; no `DECISIONS_VIOLATION`.
- **File existence**: every cited file exists except the new
  `session_store/backend.py` (expected — it's the issue's own proposed module).
- **Line-number spot-check** (~25 citations across `schema.py`,
  `history_reader/_base.py`, `queries.py`, `evolution.py`, `workspace_quality.py`
  (incl. the `:209` ATTACH), `cli/doctor.py`, `cli/doctor_trim.py`, `decisions.py`,
  `cli/issues/decisions.py`, `transport.py`, `issue_history/parsing.py`,
  `issue_history/collisions.py`, `codequery/core.py`, `host_runner.py`): all
  confirmed exact except one (see below).
- **Aggregate counts**: `grep -rn 'sqlite3\.connect('` gives exactly 27 sites
  across 15 modules — matches exactly, not just "close". The 10-raw-mode=ro-sites
  (7 in-scope + 3 excluded) plus 1 ATTACH breakdown also confirmed exact.
  `resolve_history_db()` confirmed absent (0 hits) from both `decisions.py` and
  `cli/doctor.py`.
- **Causal/identity claims**: independently re-read both `_connect_readonly()`
  implementations — `history_reader/_base.py:60` (calls `ensure_db()`, discards
  its return value, opens `db_path` as given, catches `sqlite3.Error`, returns
  `None`) vs. `session_store/queries.py:191` (no `ensure_db()` call, no
  try/except — raises naturally). Confirms the "different contracts" claim
  exactly. Re-ran the exception-hierarchy sweep independently: confirmed no
  existing hierarchy in this codebase has 3+ subclasses of a shared base.
- **Proposal-vs-code consequence check (B6)**: found one real gap, fixed in this
  pass — `session_store/queries.py::search()` (`:56`) deliberately translates
  `sqlite3.OperationalError` (malformed FTS5 query syntax) to `ValueError` as an
  input-validation contract, not a history-store-failure signal. Step 5 (convert
  consumer `except sqlite3.*` to `HistoryError` subclasses) didn't name this site
  as an exclusion, and no test anywhere in the suite covers it — applied literally,
  Step 5 would have silently broken `search()`'s malformed-query error message.
  Added an explicit exclusion to Compatibility Guarantees and a new Tests bullet.
- **Regression detection (§D)**: N/A — no completed issue already implements this
  chokepoint; this is a fresh capture, not a regression scenario.
- **Dependency references (§E)**: `FEAT-3524` exists and its `## Blocked By`
  section lists `ENH-3525` back — no `BROKEN_REF`, no `MISSING_BACKLINK`.
- **Minor correction applied**: the Proposed Solution's research note cited
  `host_runner.py::resolve_host()`/`project_child_env()` under one "line 2352" —
  only `project_child_env()` is at `:2352`; `resolve_host()` is at `:2535`.
  Corrected inline.

## A1 Landed (2026-09-22)

Implementation Steps 1-4 (chokepoint, contracts, bypass fixes) are done:

1. `session_store/backend.py` landed: `Backend` protocol, `SqliteBackend`,
   lazy `resolve_backend(provider="sqlite")` registry, `HistoryError`
   taxonomy (`HistoryUnavailable`/`HistoryIntegrityError`/`HistoryUnsupported`/
   `HistoryOperationError`), `open_history()`/`open_history_readonly()`,
   strict `connect_readonly()`. `HistoryDbUnavailable` now subclasses
   `HistoryUnavailable`. `test_session_store_backend.py` promotes the spike's
   dialect-migration, idempotent-`ensure_schema`, concurrent-migration, and
   capability-gate tests, plus new BUG-3181/D19/ensure-then-read contract
   tests.
2. The 7 in-scope read-only opens (`evolution.py::_open_db`,
   `workspace_quality.py::_open_member_readonly`,
   `cli/doctor.py::_history_db_data`/`_schema_drift_data`,
   `cli/doctor_trim.py::_usage_counts`,
   `history_reader/_base.py::_connect_readonly`) now route through
   `resolve_backend().connect_readonly(path)` or the module-level
   `open_history_readonly()`, and the `workspace_quality` ATTACH
   (`_open_union`) is gated on `backend.supports("attach")`.
   `session_store/queries.py::_connect_readonly()` is the one deliberate
   exception — left as a raw `mode=ro` open because
   `test_feat3304_artifact_dashboard.py::
   test_snapshot_builder_never_uses_the_migrating_open_path` pins its literal
   source text, and it already implements the strict contract's behavior
   exactly (D19-compliant). `history_reader/_base.py::_connect_readonly()` is
   now a thin wrapper over `open_history_readonly(db_path, ensure=True)`,
   fixing the latent migrate-a-different-file bug (BUG-3181) by resolving the
   target exactly once. That single-resolve fix required one refinement
   beyond the original design: `backend.py::_resolve_once()` only applies
   `resolve_history_db()` to a `None`/relative target — an already-absolute
   path is honored verbatim, never re-resolved. Without this, a caller that
   pre-resolves under an explicit `root=` (e.g.
   `mcp_server/tools.py::_tool_history_search`) would have its path silently
   redirected by a second, root-less resolution under a foreign cwd; this
   surfaced as a real regression in
   `test_enh_3171_mcp_project_root.py::test_history_search_reads_db_under_explicit_root_from_foreign_cwd`
   and is now fixed and covered.
3. All three path bypasses fixed, each with an `LL_HISTORY_DB` regression
   test: `decisions.py::generate_from_completed()`,
   `cli/doctor.py::_schema_drift_data()`, and
   `transport.py::wire_transports()`'s `"sqlite"` branch (which also no
   longer lets `log_dir` influence the history-store path at all, matching
   Expected Behavior).
4. `test_history_store_chokepoint_gate.py` added: AST-scans
   `scripts/little_loops/` for raw `sqlite3.connect(` and fails outside
   `session_store/backend.py` and a reasoned allowlist. The allowlist is
   wider than this issue's target end-state on purpose — it separates
   **permanent** exemptions (codegraph.py, queue_store.py, sessions.py's
   Codex index, `schema.py`'s own internal implementation, `queries.py`'s
   pinned strict opener, `workspace_quality.py`'s ATTACH scratch hosts) from
   **provisional** ones explicitly labeled "pending ENH-3525 A2"
   (`session_store/writers.py`'s `SQLiteTransport`, `session_store/
   lifecycle.py`'s VACUUM connections, `cli/logs.py`, `cli/ctx_stats.py`,
   `cli/history.py`) — real history.db write connections Step 5 still needs
   to route through the entry points. A2 should shrink this allowlist, not
   just add to it; `test_allowlist_entries_still_exist_and_still_have_raw_connects`
   catches an entry that should have been removed.

Not done (A2, Steps 5-6, deliberately deferred per the confidence-check
finding above): routing the ~70/~50 remaining consumers' `except sqlite3.*`
branches to `HistoryError` subclasses, the seven named test rewrites, and
the `docs/reference/API.md`/`docs/ARCHITECTURE.md` updates.

Full suite (`python -m pytest scripts/tests/`): 25241 passed, 54 skipped, 2
failed — both failures pre-existing and unrelated
(`test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`,
caused by unrelated BUG-3522/BUG-3523 issue content; `test_no_parallel_serial_gate.py::
TestKillGroupIfAlive::test_kills_grandchild_in_same_group`, a flaky
process-timing test). `ruff check`/`ruff format --check`/`mypy` clean on
every file this pass touched.

## Status

**In Progress** | Created: 2026-09-22 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-22_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- Very wide blast radius (Change Surface 0/25): ~30 files to modify across 8+ subsystems (session_store, history_reader, issue_history, cli, transport, decisions, tests, docs), with 70+ confirmed callers of `_connect_readonly()` and 50+ callers of `resolve_history_db()` that must keep working unchanged. Classified as Pattern A (code blast radius), not Pattern B, because A2's consumer error-type conversion is a per-site behavioral change, not a uniform mechanical substitution.
- Moderate per-site depth (Complexity 5/25): the `HistoryError` taxonomy conversion changes a shared contract (consumer degradation/catch behavior) across modules rather than being a contained local edit; 7 existing tests explicitly assert on raw `sqlite3.OperationalError`/`sqlite3.Error` for "history failed" and require deliberate rewrites — a missed rewrite breaks behavior silently rather than failing test collection.
- Mitigation already built into the issue: Implementation Steps stage A1 (chokepoint + bypass fixes, no consumer error-type changes) ahead of A2 (consumer error-type conversion, "carries the behavioral risk") as independently landable commits. Recommend landing/soaking A1 first and re-running `/ll:confidence-check` before starting A2; the issue's own Sizing note already flags A2 as a candidate for `/ll:issue-size-review` split.

## Session Log
- `/ll:manage-issue` - 2026-09-22T23:29:04 - `4f3ece7f-4412-4831-a895-fcf5c78a9b60.jsonl`
- `/ll:ready-issue` - 2026-09-22T23:12:21 - `daa84f9b-9db4-4918-b4e3-96cce34e1a59.jsonl`
- `/ll:manage-issue` - 2026-09-22T22:09:47 - `6e23addb-913f-4751-95d4-9caf3143f43d.jsonl`
- `/ll:confidence-check` - 2026-09-22T21:25:58 - `6e23addb-913f-4751-95d4-9caf3143f43d.jsonl`
- `/ll:verify-issues` - 2026-09-22T21:07:24 - `cfaf5a77-1b05-4ab4-a69c-2fd5f977d32f.jsonl`
- `/ll:verify-issues` - 2026-09-22T20:50:47 - `d5913727-aee2-4da4-b9b6-0c7c106cc141.jsonl`
- `/ll:wire-issue` - 2026-09-22T20:46:38 - `5e6fdfe4-a051-499c-b448-1629fbe99667.jsonl`
- `/ll:refine-issue` - 2026-09-22T20:35:26 - `000d50cc-8e65-459d-9c90-7e440ec813a8.jsonl`
