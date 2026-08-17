---
id: ENH-3242
type: ENH
title: Detect history.db structural drift instead of trusting the recorded schema_version
priority: P2
status: open
testable: true
discovered_by: bug-3236-pre-implementation-review
discovered_date: '2026-08-17'
labels:
- history-db
- session-store
- schema-drift
- silent-failure
relates_to:
- BUG-3236
- BUG-3241
confidence_score: 90
outcome_confidence: 49
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
decision_needed: false
---

# ENH-3242: Detect `history.db` structural drift instead of trusting `schema_version`

## Summary

`meta.schema_version` is treated as proof of structure. `_apply_migrations()`
short-circuits on `_current_version(conn) >= len(_MIGRATIONS)`
(`session_store/schema.py:1065`), so a database whose recorded version is current is never
re-examined regardless of what it actually contains. There is no structural verification
anywhere in the codebase and no repair path.

BUG-3236 and BUG-3241 are both instances of this: five databases carrying a drifted
`issue_sessions` view, and roughly two dozen missing indexes their recorded version says
they must have. Each was found by hand, months after the fact, and only because an
unrelated feature happened to depend on the drifted object. This issue is about making the
*next* one loud instead of silent.

## Current Behavior

`_apply_migrations()` treats `meta.schema_version` as authoritative: its fast path
(`_current_version(conn) >= len(_MIGRATIONS)`, `session_store/schema.py:1065`) returns
immediately without re-examining the database's actual structure whenever the recorded
version is current. There is no structural verification anywhere in the codebase — no
test, no startup check, no doctor-style repair command — so a database that
drifted from what its recorded version implies (BUG-3236, BUG-3241) stays drifted
indefinitely, and every affected reader's `except sqlite3.Error: return []` makes the
drift indistinguishable from "no data."

## Expected Behavior

A database whose recorded `schema_version` is current but whose actual structure has
drifted from what that version's migrations produce is detected — at minimum by a test
that fails at authoring time when a migration changes structure without updating a
checked-in manifest, and ideally by a runtime or on-demand check — rather than staying
silently wrong until an unrelated feature happens to depend on the drifted object.

## Motivation

The drift mechanism is structural to how this project is developed, not a one-off. Every
little-loops project on this machine is `local-editable` against the source checkout, so
any `ll-*` invocation during in-progress migration work runs the **working-tree** migration
body against real databases. There is no commit, no artifact, and no signal. The affected
databases then record a version they do not structurally match, permanently, because the
version check never fires again.

Both known instances failed silently: every affected reader catches `sqlite3.Error` and
returns `[]` or `None`, which is indistinguishable from "no data." BUG-3236 sat undetected
long enough that its root cause could only be established by proving a negative
(`git log -S` returning no commits).

## Scope Boundaries

- **In scope**: piece 1 — a structural assertion test comparing a fresh database's
  PRAGMA-derived manifest at the current `SCHEMA_VERSION` against a checked-in snapshot.
  This is the only piece with a hard acceptance criterion below; it is worth doing alone.
- **Out of scope**: fixing the two known drift instances themselves (BUG-3236, BUG-3241 —
  separate issues this one sequences after); mechanically reclassifying all 60+
  `except sqlite3.Error:` sites in `history_reader.py` (piece 3) in this pass — the
  Acceptance Criteria require only a recorded decision on pieces 2 and 3's shipping shape,
  not their full implementation.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- `scripts/little_loops/queue_store.py:154-210` — `_current_version()`, `_apply_migrations()` (fast-path short-circuit at `:172-173`), and `ensure_db()` duplicate the exact `session_store/schema.py` pattern (its own docstring at `:168-171` cross-references `little_loops.session_store._apply_migrations` for the concurrency rationale, but shares no code). Any fix to `schema.py`'s fast-path or a new `_schema_manifest()` needs a parallel decision for `queue_store.py` to be complete — it is not automatically covered.
- Importers of `session_store/schema.py` (confirmed via code graph): `session_store/queries.py:18`, `session_store/lifecycle.py:33`, `session_store/writers.py:33`, `session_store/__init__.py:96`.
- `scripts/little_loops/cli/doctor.py` — an existing check-registration framework (`@register_check`, `_CHECKS: list[Callable[[], list[CheckResult]]]`, `doctor.py:81-87`) already exists, with `CheckResult(status: full|partial|unsupported, severity: error|informational)` (`doctor.py:54-73`). A `_history_db_data()` check (`doctor.py:353-395`) already exists for `.ll/history.db` but is presence/readability-only (`SELECT 1` on a read-only connection) — it does not touch schema structure. Piece 2's "ll-history doctor" option has a ready home in this registry rather than needing a new command.
- Two competing repair-command shapes exist as precedent for piece 2's decision: (a) diagnose-only `ll-doctor` registry above, with no `--fix`/repair path anywhere in `doctor.py`; (b) per-command `--fix` flag that both diagnoses and repairs in one surface — `ll-verify-docs --fix` (`cli/docs.py:66-70`) and `epic-consistency --fix` (`cli/issues/epic_consistency.py:279-283,295-299`, which documents itself as detecting/reconciling "drift" with the same report-only-by-default / `--fix`-to-repair shape this issue would need).
- `scripts/little_loops/history_reader.py` — confirmed **62** (not "60+") `except sqlite3.Error:` sites via exact grep count. Representative sites: `:436-438` (`_connect_readonly` ensure-schema failure), `:443-445` (read-only open failure), `:487-489` (`find_user_corrections` query failure). All 62 currently log at `logger.warning` uniformly — there is no existing warning/error split to preserve or break.
- A second, separate "missing vs present" distinction already exists outside the `except sqlite3.Error:` handlers: `lookup_session_metadata` (`history_reader.py:2217`) and `conversation_turns` (`:2302`) each do `if not db_path.exists(): return {}/[]` *before* calling `_connect_readonly()`, and log nothing in that branch — a second undocumented "missing" convention alongside the uniform-`warning` one for "present but broken."
- No existing `_schema_manifest()`-shaped helper exists anywhere in the codebase. All `PRAGMA table_info`/`sqlite_master` structural introspection is done inline, per call site, only inside `scripts/tests/test_session_store_schema.py` (~40+ sites, e.g. `:74,94,243,321,377,476,622`) — none aggregates a full-database manifest across all tables/views/indexes.
- Two snapshot/fixture conventions coexist for "generate from live code, diff against committed file" tests, and they disagree on tooling: (a) `syrupy`-based, `scripts/tests/__snapshots__/*.ambr`, regenerated via `pytest --snapshot-update`, tests marked `@pytest.mark.usefixtures("stable_snapshot_env")` (`conftest.py:131`) — see `scripts/tests/test_snapshot_output_primitives.py`; (b) hand-maintained JSON/YAML "golden corpus" fixtures under `scripts/tests/fixtures/<subsystem>/`, compared with plain `==`, no auto-update tooling — see `scripts/tests/test_adapt_golden_corpus.py:34-38,64` and `scripts/tests/fixtures/policy_builder/`. Neither is tied to "structural" data specifically; the manifest-snapshot test this issue proposes would need to pick one.
- `scripts/tests/test_session_store_schema.py::TestEnsureDb.test_all_tables_created` (`:70-88`) is the closest existing analog to the proposed manifest test, but only asserts a fixed 10-table allowlist is a *subset* of the actual set (no columns, no indexes, no views, no checked-in snapshot file) — it would not be duplicated by the new test.

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- Correction to the earlier "Codebase Research Findings" bullet on `history_reader.py`'s log levels: it states "all 62 currently log at `logger.warning` uniformly — there is no existing warning/error split to preserve or break." That is stale/incorrect — the "Files to Modify" section below it already has the accurate count (2 `logger.error`, 60 `logger.warning`), confirmed again this pass: `sessions_for_issue()` (`history_reader.py:2117-2120`) and `issue_effort()` (`:2149-2152`) use `logger.error` with a `"(possible schema drift)"` annotation; the remaining 60 sites use `logger.warning`. Both error sites query the `issue_sessions` VIEW specifically — the object BUG-3236 found drifted — and this is a one-off point-fix annotation, not a documented or repeated convention. No structural/exception-type difference distinguishes the 2 sites from the 60; a mechanical classifier (e.g. "does this except-block touch `issue_sessions`") could only reclassify that one already-fixed object, not generalize to the other 60, none of which have a known drift history to key off of.
- `ensure_db()` is confirmed on essentially every `ll-*` invocation's hot path via two independent chains: `cli_event_context()` (`session_store/writers.py:483-561`, calls `_pkg.connect()` at `:521`) is imported/called from ~52 files under `scripts/little_loops/cli/`; and `hooks/session_start.py:132-135` calls `ensure_db()` directly on every session start (wrapped in `contextlib.suppress(Exception)`, independent of the CLI path). This confirms the AC's "startup-cost measurement, not an estimate" requirement is measuring a real, structural cost center, not a speculative one.
- A directly reusable timing-measurement pattern already exists for piece 2's required startup-cost measurement: `scripts/tests/bench_opencode_adapter.py` (a standalone script, not pytest-collected) measures cold-start latency across N sequential invocations via `time.perf_counter()` (`:55,69`), reports min/median/p95/max via `statistics`, and states explicit numeric decision thresholds in-file (`_DECISION_TARGET_MS`/`_DECISION_THRESHOLD_MS`, `:34-35`, docstring `:7-10`: "Target: p95 ≤ 200ms; if p95 ≥ 400ms: a persistent sidecar must be proposed"). Piece 2's measurement can reuse this shape instead of inventing new benchmarking tooling.
- Adding a new check to `cli/doctor.py`'s registry is structurally trivial by existing precedent: write a `_data()`-returning helper matching the `{"status", "severity", "note"}` dict shape `_history_db_data()` uses (`doctor.py:353-374`), wrap it with an `@register_check`-decorated function returning `[CheckResult(...)]` (pattern at `_history_db_check()`, `doctor.py:387-395`). `main_doctor()`'s `for check in _CHECKS:` loop (`:119`) picks it up automatically — no argument-parsing or dispatch plumbing needed. The only real decision is registry-check vs. a new `ll-history doctor` subcommand in `cli/history.py`.

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store/schema.py` — `_MIGRATIONS` (`:111`), `SCHEMA_VERSION`
  (`:21`), `_current_version()` (`:1064-1078`), `_apply_migrations()` (`:1081-1117`,
  fast-path short-circuit at `:1096-1097`), `ensure_db()` (`:1120-1158`) — all three pieces
  land here.
- `scripts/little_loops/history_reader.py` — 62 `except sqlite3.Error:` sites (piece 3);
  note the file is already non-uniform: `sessions_for_issue()` (`:2117-2120`) and
  `issue_effort()` (`:2148-2149`) already use `logger.error` from BUG-3236's point fix,
  while the remaining 60 sites use `logger.warning` — piece 3's convention must reconcile
  this, not treat the file as a blank slate.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/queue_store.py` (`:100,154-210`) — an **identical, independently
  maintained** duplicate of `_current_version()`/`_apply_migrations()`/`ensure_db()`. Piece
  2's fast-path decision needs an explicit call on whether it also applies here, or the two
  schema systems diverge on drift-detection coverage.
- `scripts/little_loops/session_store/lifecycle.py` (`:33` import, `:857` call) — calls
  `_pkg.ensure_db()` during backfill; a second exerciser of piece 2's fast-path cost.
- `scripts/little_loops/session_store/writers.py` (`:33` import, `:2277` call,
  `cli_event_context()` at `:483`) — wraps every CLI invocation; the primary hot path piece
  2's cost must be measured against.
- `scripts/little_loops/session_store/queries.py` (`:18` import) and
  `scripts/little_loops/session_store/__init__.py` (`:96` re-export) — transitive importers
  of the changed symbols; no behavior change expected, listed for completeness.
- `scripts/little_loops/hooks/session_start.py` (`:132-135`) — calls `ensure_db()` directly
  (wrapped in `contextlib.suppress(Exception)`, not via `cli_event_context`) on every session
  start — the other independent hot-path call site alongside `writers.py`.
- `scripts/little_loops/cli/doctor.py` — existing `register_check()`/`_CHECKS` registry
  (`:81-87`) with `_history_db_data()`/`_history_db_check()` (`:353-395`), currently
  presence/readability-only. This is a smaller, in-registry extension point for piece 2's
  manifest check than standing up a new `ll-history doctor` subcommand, and the AC's
  "explicit `ll-history doctor` command" fallback should weigh this existing home before
  picking a name.
- `scripts/little_loops/cli/history.py` (`main_history()` at `:16`, subparsers `:66-248`) —
  alternate registration point if the `ll-history doctor` subcommand name is chosen instead
  of extending `ll-doctor`.
- `scripts/little_loops/cli/__init__.py` (`:64` import of `main_doctor`, `:40` module
  docstring documenting `ll-doctor`) — a second wire-issue pass (post-decision, 2026-08-17)
  found this is a third independent one-line `ll-doctor` description surface (alongside
  `commands/help.md`, `.claude/CLAUDE.md`) that FEAT-2796's precedent flagged as prone to
  drifting stale independently — check whether the new check's wording belongs here too.
- `scripts/pyproject.toml` (`:89`, `ll-doctor = "little_loops.cli:main_doctor"`) — the
  console-script entry point completing the call chain from shell invocation to the `_CHECKS`
  registry; no change needed, listed for completeness of the wiring trace.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md` (~`:8883-8889`, ~`:9800-9808`) — quotes `SCHEMA_VERSION` as `38`
  and describes `ensure_db()`; already stale against the real value (42 after BUG-3236) —
  correct in the same pass regardless of which piece lands.
- `docs/ARCHITECTURE.md` — Write Path mermaid diagram (`:706`,
  `ensure_db() — bootstrap schema (v1–v34)`) and Components table (`:731`) both hardcode
  "v1–v34", already stale; `:808` documents `queue_store.py` as "matching every other sqlite
  consumer" — inaccurate if piece 2 lands only in `schema.py` and not `queue_store.py`.
- `docs/reference/CLI.md` — `### ll-history` (`:2790`, subcommand list + usage examples
  `:2905-2931`) or `### ll-doctor` (`:285`), whichever the piece 2 decision lands on, needs a
  new subsection documenting the check/subcommand.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_session_store_schema.py` — already modified in this working tree;
  existing `TestEnsureDb.test_all_tables_created()` (`:70-88`) is the closest existing
  partial-manifest analog (fixed 10-table allowlist, subset only); `_bootstrap_schema_at()`
  helper (`:1134-1154`) replays `_MIGRATIONS[:version]` for drifted-DB fixtures and is the
  helper piece 1's new manifest test should reuse, not reimplement (a byte-identical copy
  already exists at `test_session_store_writers.py:1045-1065` — flagged by BUG-3241 as
  unshared; don't add a third copy).
- `scripts/tests/test_codequery_codegraph.py` (`TestSchemaGuard`, `:28-48, 224-234`) — the
  closest existing "manifest vs. PRAGMA" pattern in the repo (`_SCHEMA_COLUMNS` dict compared
  via `PRAGMA table_info` in a loop), for a different database — the shape to model piece 1's
  new manifest test after, minus the checked-in-file requirement (this test inlines its
  manifest instead of loading a snapshot).
- `scripts/tests/fixtures/tier0_traces/manifest.json`,
  `scripts/tests/fixtures/heuristic_traces/manifest.json`,
  `scripts/tests/fixtures/fragment_store_traces/manifest.json` — existing checked-in JSON
  manifest fixture convention to follow for piece 1's schema manifest file, if a
  file-snapshot (vs. inline-dict) approach is chosen over the `TestSchemaGuard` style.
- `scripts/tests/test_queue_store.py` (`:55-405`) — covers `queue_store.py`'s duplicate
  migration system; needs the same piece-2 decision applied or explicitly deferred.
- `scripts/tests/test_history_reader.py` — no existing test asserts on log level/records for
  any `except sqlite3.Error:` site (confirmed: no `caplog` usage in this file today), so
  piece 3 needs new tests, not fixes to existing ones. `test_ll_logs.py:259-294`
  (`test_stale_worktree_path_emits_no_warning`, using
  `caplog.at_level(logging.WARNING, logger="...")`) is the only existing
  `caplog.at_level(..., logger=...)` pattern in the suite and the template to follow.
- `scripts/tests/test_session_store_db.py`, `test_session_store_lifecycle.py`,
  `test_session_store_queries.py`, `test_issue_history_cli.py`, `test_cli_ctx_stats.py`,
  `test_correction_retirement.py`, `test_issue_manager.py` — all call `ensure_db()` directly
  or transitively; relevant if piece 2's fast-path measurement needs broader startup-cost
  coverage than the primary schema tests provide.
- `scripts/tests/test_cli_doctor_install_checks.py` — `TestHistoryDb` (`:158-200`) is the
  exact template for the new check's `_*_data()` function: three-tier scenario coverage
  (absent/healthy/drifted), `monkeypatch.chdir(tmp_path)`, asserts the returned dict's
  `status`/`severity`/`note`. Add a new dedicated test class here (e.g. `TestSchemaDrift`) —
  do not extend `TestHistoryDb` itself, since its `test_absent_is_informational_and_does_not_create`
  asserts exact dict equality that a shared/extended return shape would break.
- `scripts/tests/test_cli_doctor.py` — `TestCheckRegistry` (`:656-755`), specifically
  `test_register_check_appends_and_runs` (`:682-697`)'s save/clear/restore idiom for
  isolating `_CHECKS` mutation in tests. Confirmed no existing test enumerates the full
  `_CHECKS` list or count, so registering a new check needs no update here — additive-safe.
- `scripts/tests/test_wiring_guides_and_meta.py` (`:40` pattern) and
  `scripts/tests/test_wiring_reference_docs.py` (`:51` pattern) — FEAT-2796 precedent: each
  new default `_CHECKS` entry gets a paired `(doc_path, check_name_or_json_key, ISSUE_ID)`
  string-presence wiring-test tuple once its doc prose lands, so a future edit can't silently
  drop the new check's documentation. The Documentation section above already flags
  API.md/ARCHITECTURE.md/CLI.md prose updates but not these paired test rows — add them when
  that prose lands.
- New comment-drift regression test (no existing precedent in the suite) — a
  `TestSchemaManifest` case that appends a SQL comment to a table's DDL post-creation (via
  a raw `sqlite3.connect` + `executescript`, following the `_bootstrap_schema_at` helper
  shape at `test_session_store_schema.py:1134-1154`) and asserts `_schema_manifest()` output
  is unchanged — the concrete proof for AC bullet 2 ("comment-only edit does not fail it").

## Program Design

### Types

- `SchemaManifest: dict[str, list[str]]` — table/view name -> sorted column names, plus a
  parallel `list[str]` of index names; the PRAGMA-derived structure a fresh database is
  compared against.

### Signatures

- `_schema_manifest(conn: sqlite3.Connection) -> SchemaManifest` (new, `session_store/schema.py`)
- `test_schema_manifest_matches_snapshot() -> None` (new pytest test, `scripts/tests/`)

### Call Path

`test_schema_manifest_matches_snapshot()` -> `ensure_db()` (fresh temp database) ->
`_schema_manifest(conn)` -> compared against a checked-in manifest snapshot file;
fails when a migration changes structure without updating the snapshot.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- `_apply_migrations()` fast-path short-circuit (`session_store/schema.py:1096-1097`) is `if _current_version(conn) >= len(_MIGRATIONS): return` — an unconditional early return with zero structural inspection. Its docstring (`:1092-1094`) frames this explicitly as a WAL-mode lock-avoidance optimization ("return without taking the write lock at all") — confirming the short-circuit is deliberate and load-bearing for concurrency, not an oversight to simply remove.
- `_current_version(conn)` (`schema.py:1064-1078`) returns `0` only when the `meta` table itself is missing (`OperationalError` matching `"no such table"`); any other `sqlite3.Error` re-raises. `TestConcurrencyHardening` (`test_session_store_schema.py:145-223`) already covers the "locked vs genuinely-missing" distinction in this exact function — worth checking before adding new logic here so a new structural check doesn't reintroduce a race this suite already guards against.
- `ensure_db()` (`schema.py:1120-1158`) delegates entirely to `_apply_migrations()` for verification; `connect()` (`:1161-1170`) calls `ensure_db()` first, so any structural drift is invisible through every `connect()` caller, not just direct `ensure_db()` callers.
- `queue_store.py:154-210` duplicates this exact fast-path shape independently (see Integration Map) — a piece-2 fix scoped only to `session_store/schema.py` leaves the identical gap open in the queue database.

## Proposed Solution

Three pieces, roughly in order of cost and value. The first is worth doing alone.

**1. A structural assertion in the test suite.** For the current `SCHEMA_VERSION`, assert
that a freshly built database's PRAGMA-derived column sets and index names match an
expected manifest. This is what would have caught both known instances at authoring time,
costs nothing at runtime, and needs no decision about self-healing. Generating the manifest
from `ensure_db()` on a fresh temp database and comparing it against a checked-in snapshot
keeps it maintainable — the snapshot diff becomes a required, reviewable part of any
migration PR.

**2. A cheap structural check in `ensure_db()`'s fast path.** The version-current path
already returns without taking the write lock. A single `PRAGMA table_info` on one sentinel
view (`issue_sessions`) would make view drift self-healing rather than permanent. Weigh
against startup cost — `ensure_db()` is on every `ll-*` invocation's critical path. If the
per-call cost is unacceptable, an opt-in *ll-history doctor* command (proposed name, not
yet implemented) carrying the full
manifest check is the fallback, and is more useful for the index drift in BUG-3241 anyway.

**3. A log-level convention for reader query failures.** BUG-3236 raises
`history_reader.py:2107` and `:2136` to `logger.error` as a point fix. There are 60+
`except sqlite3.Error:` sites in `history_reader.py` with no distinction anywhere between
"database missing" (expected, `warning`) and "query failed against a present, readable
database" (a defect, `error`). Establishing that distinction file-wide is the durable
version of BUG-3236's item 2. `sessions_for_issue`'s own docstring
(`history_reader.py:2092-2093`) already concedes that its empty-list return conflates three
distinct causes.

### Implementation trap, inherited from BUG-3236

**Do not compare `sqlite_master.sql` text.** SQLite stores the *original* `CREATE`
statement verbatim and never rewrites it, so a comment added to a `CREATE TABLE` body after
the table was created reads as drift forever. A naive text diff of this checkout's database
against a fresh one flags `raw_events` as drifted; the only difference is a block comment
added long after the table existed, and the structure is identical. Any structural check
must compare **PRAGMA-derived column sets and index names**, never SQL strings.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Piece 1 (manifest snapshot test) — dominant convention confirmed**: for "assert generated structure against a fixed expectation" against a live SQLite schema, this codebase's established shape is an inline Python dict/set literal compared against `PRAGMA table_info` results inside the test body — see `scripts/tests/test_codequery_codegraph.py:224` (`TestSchemaGuard.test_pinned_columns_present_in_fixture`, module docstring calls this exact shape a "schema-drift guard"), and the same idiom repeated ad hoc across `scripts/tests/test_session_store_schema.py` (e.g. lines 94, 243, 303, 820, 883, 989, 1165, 1220). The checked-in-JSON-manifest convention (`scripts/tests/fixtures/*/manifest.json`) and the syrupy `.ambr` snapshot convention (`conftest.py:130-144` `stable_snapshot_env`) both exist but are scoped to different domains (fixture-set cataloging; CLI text-output regression) — neither has any precedent of being applied to schema/PRAGMA assertions. No shared PRAGMA-introspection helper exists anywhere in `scripts/little_loops/` (confirmed via grep for `def.*table_info`/`def.*introspect_schema`) — every PRAGMA/`sqlite_master` use across the codebase is written inline per call site, as the issue already claims.
- **Piece 2 (fast-path check vs. `ll-history doctor`) — no existing precedent combines a PRAGMA-based structural check with either shape**. Two established-but-disagreeing shapes exist for "diagnose vs. repair" surfaces: (a) `cli/doctor.py`'s shared `_CHECKS`/`register_check` registry (`:81-87`), consumed by one diagnose-only command — no `--fix`/repair path exists anywhere in that file; (b) independent per-command `--fix` flags that diagnose-and-optionally-repair within a single command, e.g. `cli/docs.py:67` (`"--fix"`, "Auto-fix mismatches") and `cli/issues/epic_consistency.py` (self-describes its subject as "drift" throughout — `has_drift`, `compute_drift`, `any_drift`; its `--fix` is scoped to only one drift category, remaining report-only for the rest; exit code is `0` under `--fix`, `1` on unresolved drift in report-only mode). Neither shape has been combined with a `PRAGMA table_info`-based structural check before — this is a genuinely undecided choice, not resolvable by precedent alone.
- **Piece 3 (log-level convention) — no mechanical rule exists to generalize from today, and none is derivable structurally**. The near-universal pattern across `history_reader.py`'s ~45 `except sqlite3.Error:`/`OperationalError:` sites and ~20 more in `session_store/writers.py`, `queries.py`, `lifecycle.py`, `schema.py` is `logger.warning(...)` with a `"<fn>: <thing> failed"` message; the sole exception is the matched `sessions_for_issue()`/`issue_effort()` pair (`history_reader.py:2117-2120`, `:2149-2152`) already covered above. Every site is exception-handler-identical in shape (`except sqlite3.Error:` → log → return empty/None) — the `.warning` vs `.error` choice does not correlate with table-vs-view, connect-vs-query, or any other structural condition visible at the call site, so a mechanical classifier cannot generalize the 2-site fix to the other 60 without new logic (e.g. checking `db_path.exists()` first, which `lookup_session_metadata`/`conversation_turns` already do as a third, undocumented convention — silently returning empty with no log at all when the db file itself is absent).

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **BUG-3241 work in this working tree is unrelated to ENH-3242.** `session_store/schema.py`'s new v43 migration (SCHEMA_VERSION 43) is a one-time *repair* migration for two already-known drift instances (dedups `assistant_messages`/`summary_nodes`, re-asserts non-UNIQUE indexes) — it does not add any drift-*detection* mechanism and does not touch `_apply_migrations()`'s fast-path short-circuit. No code toward ENH-3242's three pieces exists yet anywhere in the working tree.
- **Piece 2 decision is confirmed genuinely unresolved, not resolvable by precedent** (independently reconfirmed by codebase-pattern-finder this pass): `cli/doctor.py`'s `_CHECKS` registry (`:81-87`) is diagnose-only — zero `--fix`/repair vocabulary anywhere in that file — while `cli/docs.py` (`--fix`, `:66-70`) and `cli/issues/epic_consistency.py` (self-describes its subject as "drift": `EpicDrift`, `compute_drift()`, `has_drift`, `:44-96,141-224`; `--fix` diagnoses, repairs, then re-diagnoses to report post-fix state, `:279-283,332-343`) both bundle diagnose+repair behind a per-command `--fix` flag. These two shapes coexist today and have never been combined with a PRAGMA-based structural check before.

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

> **Selected:** Option A — matches `doctor.py`'s existing read-only convention exactly, adds zero cost to the `ensure_db()` hot path, and stays inside the issue's own Scope Boundary of "a recorded decision, not full implementation."

**Option A**: Extend `cli/doctor.py`'s `_CHECKS` registry with a manifest-based structural check (report-only). Write a `_data()`-shaped helper returning `{"status","severity","note"}`, wrap it with `@register_check`, and `main_doctor()`'s `for check in _CHECKS:` loop picks it up automatically — no new subcommand plumbing. Matches the file's existing convention (every check in `doctor.py` is read-only; there is no `--fix`/repair vocabulary anywhere in it). Diagnose-only: an operator still has to act on the finding manually.

**Option B**: Add a per-command `--fix` flag on a new/extended `ll-history doctor` subcommand (`cli/history.py`) that both diagnoses and repairs the structural drift in one surface, following `cli/docs.py --fix` and `cli/issues/epic_consistency.py --fix` precedent (self-describes its subject as "drift" throughout; `--fix` diagnoses, repairs, then re-diagnoses to report post-fix state). Self-healing, but a larger surface — new argument parsing, a repair code path, and re-diagnose-after-fix logic that Option A's registry does not need.

Both options can detect drift; only Option B repairs it in the same invocation. Neither has prior precedent combining a PRAGMA-based structural check with its shape — this is a genuinely open choice, not a coin-flip: it hinges on whether piece 2 should stop at detection (matching the issue's Scope Boundaries, which asks only for "a recorded decision... not full implementation") or extend to self-healing (which Acceptance Criteria bullet 4 arguably already requires — see the Confidence Check Notes' flagged inconsistency).

### Decision Rationale

**Selected**: Option A — extend `cli/doctor.py`'s `_CHECKS` registry with a report-only manifest check.

**Reasoning**: Option A matches the registry's own established convention exactly (every existing check in `doctor.py` is read-only; there is no `--fix`/repair vocabulary anywhere in the file), needs no new subcommand plumbing, and adds zero cost to `ensure_db()`'s hot path — sidestepping the startup-cost measurement the issue's Acceptance Criteria otherwise require for a fast-path check. It also stays inside the issue's own Scope Boundary ("a recorded decision... not their full implementation"). Option B's self-healing appeal presumes Acceptance Criteria bullet 4 requires a working repair path now — exactly the internal inconsistency the Confidence Check Notes flagged as unresolved between Scope Boundaries and AC bullet 4. Deferring repair to a follow-up issue is cheaper than building it against a contested requirement.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — doctor.py registry (report-only) | 3 | 3 | 3 | 3 | 12/12 |
| B — `--fix` flag on `ll-history doctor` | 2 | 1 | 2 | 1 | 6/12 |

**Key evidence**:
- `cli/doctor.py`'s `_CHECKS`/`register_check()` registry (`:81-87`) has zero `--fix`/repair vocabulary anywhere in the file; `_history_db_data()`/`_history_db_check()` (`:353-395`) is the direct precedent this check extends.
- `ensure_db()` sits on nearly every `ll-*` invocation's hot path (`cli_event_context()` in `session_store/writers.py`, plus `hooks/session_start.py` independently) — Option A avoids that surface entirely rather than adding to it.
- Option B's precedent (`cli/docs.py --fix`, `cli/issues/epic_consistency.py --fix`) is real but belongs to a different diagnose-and-repair convention that has never before been combined with a PRAGMA-based structural check.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Pick a `CheckResult.name` for the new check that does not collide with `"history_db"` —
  `_run_registered_checks()` (`doctor.py:116-121`) has no uniqueness guard across `_CHECKS`.
- If the new check's data should surface in `ll-doctor --json` (not just text output), add an
  explicit `data[...]` line in `_print_report()` (`doctor.py:951-971`) and a matching
  `_print_<x>_section()` call in `main_doctor()`'s ordered list (`doctor.py:1072-1079`) —
  neither is automatic from `@register_check` alone; every existing install-surface check
  (`_decisions_store_check`, `_history_db_check`, `_loop_validity_check`) required this as a
  separate step.
- Decide the checked-in manifest snapshot's storage convention before writing
  `test_schema_manifest_matches_snapshot()`: syrupy `.ambr` under
  `scripts/tests/__snapshots__/` (regenerated via `pytest --snapshot-update`) vs. a plain JSON
  fixture under a new `scripts/tests/fixtures/schema/` dir (following the existing
  `fixtures/*/manifest.json` convention) — both are live, disagreeing conventions in this
  repo (see Codebase Research Findings above); pick one rather than inventing a third shape.

## Impact

- **Priority**: P2 — no user-visible defect today once BUG-3236 and BUG-3241 land; this
  prevents the class. Piece 1 is small and high-leverage; pieces 2 and 3 are larger.
- **Effort**: Piece 1 small, piece 2 medium (needs a startup-cost measurement), piece 3
  medium-large (touches 60+ call sites, mechanically).
- **Sequencing**: after BUG-3236, so the manifest snapshot is taken against a correct v42
  schema rather than baking in the drift. Independent of BUG-3241.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] A test asserts the full PRAGMA-derived structure (table and view column sets, index
      names) of a fresh database at the current `SCHEMA_VERSION` against a checked-in
      manifest, and fails when a migration changes structure without updating it.
- [ ] The test compares PRAGMA output, never `sqlite_master.sql` text; a comment-only edit
      to a `CREATE TABLE` body does not fail it.
- [ ] A decision is recorded — with a startup-cost measurement, not an estimate — on
      whether the `ensure_db()` fast-path check ships or is replaced by an explicit
      *ll-history doctor* command (proposed name, not yet implemented).
- [ ] Whichever ships detects a database stamped current but structurally drifted, on both
      known shapes: a missing view column (BUG-3236) and a missing index (BUG-3241).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Split out of BUG-3236 during its pre-implementation review, where items 3 and 4 of the Fix
section were correctly scoped out of the point fix but had no issue to land in.

## Status

- [ ] open

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 49/100 → LOW

### Outcome Risk Factors
- Piece 2's chosen shape (fast-path check in `ensure_db()` vs. a new `ll-history doctor` command) is genuinely undecided by the issue's own research findings — no existing precedent combines a PRAGMA-based structural check with either the `doctor.py` registry or a `--fix`-flag shape. Whichever is chosen, `ensure_db()` sits on nearly every `ll-*` invocation's hot path (~52 files via `cli_event_context()`, plus `hooks/session_start.py` independently) — a fast-path change is an 11+-caller blast radius, not an isolated one.
- Scope Boundaries states pieces 2 and 3 need only "a recorded decision... not their full implementation," but Acceptance Criteria bullet 4 ("Whichever ships detects a database stamped current but structurally drifted, on both known shapes") reads as requiring piece 2 to actually ship a working detector, not just a documented decision. Resolve this internal inconsistency before implementation to avoid over- or under-building piece 2.


## Session Log
- `/ll:decide-issue` - 2026-08-17T19:50:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:48:59 - `210ffe2f-782a-4152-bb68-4c236339a110.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:36:36 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:decide-issue` - 2026-08-17T19:30:44 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:28:34 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:08:26 - `ef11a41c-065c-4fa1-bb32-c968298e27a9.jsonl`
- `/ll:wire-issue` - 2026-08-17T18:58:48 - `a29924e0-c6de-4707-a414-f7282d13c3c9.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:46:12 - `f45aab6b-bb54-4fbd-9613-662d061dc865.jsonl`
- `/ll:format-issue` - 2026-08-17T18:39:06 - `73e92a5b-b52b-41fd-896b-d930c6b15dc8.jsonl`
