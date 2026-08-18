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
- BUG-3255
confidence_score: 98
outcome_confidence: 81
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 14
score_change_surface: 24
decision_needed: false
reconcile_attempted: true
---

# ENH-3242: Detect `history.db` structural drift instead of trusting `schema_version`

## Summary

`meta.schema_version` is treated as proof of structure. `_apply_migrations()`
short-circuits on `_current_version(conn) >= len(_MIGRATIONS)`
(`session_store/schema.py:1229`), so a database whose recorded version is current is never
re-examined regardless of what it actually contains. There is no structural verification
anywhere in the codebase and no repair path.

BUG-3236 and BUG-3241 are both instances of this: five databases carrying a drifted
`issue_sessions` view, and roughly two dozen missing indexes their recorded version says
they must have. Each was found by hand, months after the fact, and only because an
unrelated feature happened to depend on the drifted object. This issue is about making the
*next* one loud instead of silent.

## Current Behavior

`_apply_migrations()` treats `meta.schema_version` as authoritative: its fast path
(`_current_version(conn) >= len(_MIGRATIONS)`, `session_store/schema.py:1229`) returns
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

_Revised 2026-08-17 (pre-implementation review) to reconcile with the Option A decision
below — the earlier wording ("pieces 2 and 3 need only a recorded decision") contradicted
Acceptance Criteria bullet 4, which requires a working detector. Piece 2 ships._

- **In scope, piece 1**: a `_schema_manifest(conn)` helper plus a structural assertion test
  comparing a fresh database's PRAGMA-derived manifest at the current `SCHEMA_VERSION`
  against a checked-in manifest file.
- **In scope, piece 2**: the report-only `ll-doctor` structural check (Option A, decided
  below). This *ships*, not merely a recorded decision — it is what satisfies AC bullet 4,
  which piece 1's fresh-database test structurally cannot (a fresh DB is never the drifted
  one). It reuses piece 1's `_schema_manifest()` — the one *generator* must not fork — but
  builds its comparison reference by replaying `_MIGRATIONS[:recorded]` rather than loading the
  checked-in manifest (revised 2026-08-18; see Program Design > Call Path). The two pieces
  answer different questions: piece 1 asks "did a migration edit change structure without the
  manifest being regenerated", piece 2 asks "does this real database match what its own
  recorded version's migrations produce". Replay cannot answer the first (it derives from the
  same edited source) and a fixed-version manifest cannot answer the second (no real database
  is at the manifest's version).
- **Out of scope**: any *repair* path (`--fix`, self-healing, a migration that rewrites
  drifted objects) — detection only, repair deferred to a follow-up issue; any change to
  `_apply_migrations()`'s fast-path short-circuit (Option A deliberately avoids the
  `ensure_db()` hot path entirely); fixing the two known drift instances themselves
  (BUG-3236, BUG-3241 — separate issues this one sequences after); the parallel
  `queue_store.py` manifest (explicitly deferred — see Dependent Files); piece 3's
  reclassification of the 62 `except sqlite3.Error:` sites in `history_reader.py`, which
  remains decision-only in this pass.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- `scripts/little_loops/queue_store.py:154-210` — `_current_version()`, `_apply_migrations()` (fast-path short-circuit at `:172-173`), and `ensure_db()` duplicate the exact `session_store/schema.py` pattern (its own docstring at `:168-171` cross-references `little_loops.session_store._apply_migrations` for the concurrency rationale, but shares no code). Any fix to `schema.py`'s fast-path or a new `_schema_manifest()` needs a parallel decision for `queue_store.py` to be complete — it is not automatically covered.
- Importers of `session_store/schema.py` (confirmed via code graph): `session_store/queries.py:18`, `session_store/lifecycle.py:33`, `session_store/writers.py:33`, `session_store/__init__.py:96`.
- `scripts/little_loops/cli/doctor.py` — an existing check-registration framework (`@register_check`, `_CHECKS: list[Callable[[], list[CheckResult]]]`, `doctor.py:81-87`) already exists, with `CheckResult(status: full|partial|unsupported, severity: error|informational)` (`doctor.py:54-73`). A `_history_db_data()` check (`doctor.py:353-395`) already exists for `.ll/history.db` but is presence/readability-only (`SELECT 1` on a read-only connection) — it does not touch schema structure. Piece 2's proposed `ll-history` `doctor` option has a ready home in this registry rather than needing a new command.
- Two competing repair-command shapes exist as precedent for piece 2's decision: (a) diagnose-only `ll-doctor` registry above, with no `--fix`/repair path anywhere in `doctor.py`; (b) per-command `--fix` flag that both diagnoses and repairs in one surface — `ll-verify-docs --fix` (`cli/docs.py:66-70`) and `epic-consistency --fix` (`cli/issues/epic_consistency.py:279-283,295-299`, which documents itself as detecting/reconciling "drift" with the same report-only-by-default / `--fix`-to-repair shape this issue would need).
- `scripts/little_loops/history_reader.py` — confirmed **62** (not "60+") `except sqlite3.Error:` sites via exact grep count. Representative sites: `:436-438` (`_connect_readonly` ensure-schema failure), `:443-445` (read-only open failure), `:487-489` (`find_user_corrections` query failure). ~~All 62 currently log at `logger.warning` uniformly — there is no existing warning/error split to preserve or break.~~ **STRICKEN 2026-08-17 (review pass): false.** 2 sites use `logger.error` (`:2117`, `:2149`), 60 use `logger.warning` — see the correcting bullet below and Files to Modify.
- A second, separate "missing vs present" distinction already exists outside the `except sqlite3.Error:` handlers: `lookup_session_metadata` (`history_reader.py:2217`) and `conversation_turns` (`:2302`) each do `if not db_path.exists(): return {}/[]` *before* calling `_connect_readonly()`, and log nothing in that branch — a second undocumented "missing" convention alongside the uniform-`warning` one for "present but broken."
- No existing `_schema_manifest()`-shaped helper exists anywhere in the codebase. All `PRAGMA table_info`/`sqlite_master` structural introspection is done inline, per call site, only inside `scripts/tests/test_session_store_schema.py` (~40+ sites, e.g. `:74,94,243,321,377,476,622`) — none aggregates a full-database manifest across all tables/views/indexes.
- Two snapshot/fixture conventions coexist for "generate from live code, diff against committed file" tests, and they disagree on tooling: (a) `syrupy`-based, `scripts/tests/__snapshots__/*.ambr`, regenerated via `pytest --snapshot-update`, tests marked `@pytest.mark.usefixtures("stable_snapshot_env")` (`conftest.py:131`) — see `scripts/tests/test_snapshot_output_primitives.py`; (b) hand-maintained JSON/YAML "golden corpus" fixtures under `scripts/tests/fixtures/<subsystem>/`, compared with plain `==`, no auto-update tooling — see `scripts/tests/test_adapt_golden_corpus.py:34-38,64` and `scripts/tests/fixtures/policy_builder/`. Neither is tied to "structural" data specifically; the manifest-snapshot test this issue proposes would need to pick one.
- `scripts/tests/test_session_store_schema.py::TestEnsureDb.test_all_tables_created` (`:70-88`) is the closest existing analog to the proposed manifest test, but only asserts a fixed 10-table allowlist is a *subset* of the actual set (no columns, no indexes, no views, no checked-in snapshot file) — it would not be duplicated by the new test.

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- Correction to the earlier "Codebase Research Findings" bullet on `history_reader.py`'s log levels: it states "all 62 currently log at `logger.warning` uniformly — there is no existing warning/error split to preserve or break." That is stale/incorrect — the "Files to Modify" section below it already has the accurate count (2 `logger.error`, 60 `logger.warning`), confirmed again this pass: `sessions_for_issue()` (`history_reader.py:2117-2120`) and `issue_effort()` (`:2149-2152`) use `logger.error` with a `"(possible schema drift)"` annotation; the remaining 60 sites use `logger.warning`. Both error sites query the `issue_sessions` VIEW specifically — the object BUG-3236 found drifted — and this is a one-off point-fix annotation, not a documented or repeated convention. No structural/exception-type difference distinguishes the 2 sites from the 60; a mechanical classifier (e.g. "does this except-block touch `issue_sessions`") could only reclassify that one already-fixed object, not generalize to the other 60, none of which have a known drift history to key off of.
- `ensure_db()` is confirmed on essentially every `ll-*` invocation's hot path via two independent chains: `cli_event_context()` (`session_store/writers.py:483-561`, calls `_pkg.connect()` at `:521`) is imported/called from ~52 files under `scripts/little_loops/cli/`; and `hooks/session_start.py:132-135` calls `ensure_db()` directly on every session start (wrapped in `contextlib.suppress(Exception)`, independent of the CLI path). This confirms the AC's "startup-cost measurement, not an estimate" requirement is measuring a real, structural cost center, not a speculative one.
- A directly reusable timing-measurement pattern already exists for piece 2's required startup-cost measurement: `scripts/tests/bench_opencode_adapter.py` (a standalone script, not pytest-collected) measures cold-start latency across N sequential invocations via `time.perf_counter()` (`:55,69`), reports min/median/p95/max via `statistics`, and states explicit numeric decision thresholds in-file (`_DECISION_TARGET_MS`/`_DECISION_THRESHOLD_MS`, `:34-35`, docstring `:7-10`: "Target: p95 ≤ 200ms; if p95 ≥ 400ms: a persistent sidecar must be proposed"). Piece 2's measurement can reuse this shape instead of inventing new benchmarking tooling.
- Adding a new check to `cli/doctor.py`'s registry is structurally trivial by existing precedent: write a `_data()`-returning helper matching the `{"status", "severity", "note"}` dict shape `_history_db_data()` uses (`doctor.py:353-374`), wrap it with an `@register_check`-decorated function returning `[CheckResult(...)]` (pattern at `_history_db_check()`, `doctor.py:387-395`). `main_doctor()`'s `for check in _CHECKS:` loop (`:119`) picks it up automatically — no argument-parsing or dispatch plumbing needed. The only real decision is registry-check vs. a new `ll-history` `doctor` subcommand in `cli/history.py`.

_Added by pre-implementation review — 2026-08-17 — verified against the working tree:_

- **All `schema.py` line anchors in earlier passes are ~130 lines stale**, having been
  written before v43 (BUG-3241) landed in this working tree. Verified current anchors:
  `SCHEMA_VERSION = 43` (`:21`), `_MIGRATIONS` (`:111`), v43 migration body (`:1029+`),
  `_current_version()` (`:1197`), `_apply_migrations()` (`:1214`, fast-path short-circuit
  at `:1229`), `ensure_db()` (`:1253`), `connect()` (`:1294`). Ignore the `:1064`/`:1081`/
  `:1096-1097`/`:1120`/`:1161` figures quoted elsewhere in this issue.
- **`SCHEMA_VERSION` is 43, not 42.** Every "v42" reference in this issue (Impact
  sequencing, Documentation) predates BUG-3241's repair migration.
- **The manifest must be package data, not a test fixture.** Option A (decided below) puts
  the check in `cli/doctor.py`, so the manifest is read at *runtime* by installed users —
  a file under `scripts/tests/fixtures/` or `scripts/tests/__snapshots__/` is not present
  in the wheel (`scripts/pyproject.toml:186` ships `little_loops/**` only). The manifest
  therefore lives under `scripts/little_loops/session_store/`, and the test loads the same
  file the check does. This supersedes the Wiring Phase bullet that framed the choice as
  syrupy `.ambr` vs. `scripts/tests/fixtures/schema/` — neither is viable.
- **Adding it requires a `PACKAGE_DATA_ASSETS` entry.** `scripts/little_loops/package_data.py:28-48`
  is a declarative manifest of every runtime-read package asset; its own comment (`:24-27`)
  warns that omitting an entry gives a false-green completeness result. `ll-verify-package-data`
  (`cli/verify_package_data.py:235`) and `test_package_data_manifest.py` gate it.
- **`cli/doctor.py` has two registries, not one.** Alongside `_CHECKS`/`register_check`
  (`:81-87`, run on every `ll-doctor`) there is `_FULL_CHECKS`/`register_full_check`
  (`:484-490`, `--full`-gated only, `_run_full_checks()` at `:493`) — added for FEAT-2795's
  `ll-verify-*` family. Every prior pass in this issue was blind to it. A PRAGMA-introspecting
  check is a plausible `_FULL_CHECKS` member; the choice must be made explicitly.
- **The new check must inherit `_history_db_data()`'s never-create constraint.** Its
  docstring (`doctor.py:353-358`) is explicit: `connect()`/`ensure_db()` both create on
  demand, so the DB is probed via `Path.exists()` first and opened read-only
  (`file:{db}?mode=ro`, `:365`). A structural check that reaches for `ensure_db()` would
  make `ll-doctor` create `history.db` as a side effect — and would also *migrate* it,
  destroying the very drift it is meant to report.
- Verified current: `hooks/session_start.py:133-135` (`ensure_db()` call),
  `history_reader.py` `sessions_for_issue()` (`:2085`, `logger.error` at `:2117`) and
  `issue_effort()` (`:2127`, `logger.error` at `:2149`), `doctor.py` `_run_registered_checks()`
  (`:116`), `_print_report()` (`:936`), `main_doctor()` (`:988`).

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Staleness flag resolved**: research-triage flagged `scripts/little_loops/cli/history.py` as changed after the last refine pass. Re-read in full (579 lines, current subcommand set: `summary`, `analyze`, `export`, `rework`, `sessions`, `audit-issue-collisions`, `root`) — it carries no `doctor` subcommand, no `--fix` flag, and no structural-check plumbing of any kind. The recent change is unrelated to this issue; it does not affect the Option A vs Option B tradeoff already decided in favor of Option A.
- **All previously-cited line anchors re-confirmed exact against the current working tree**: `session_store/schema.py` (`SCHEMA_VERSION` `:21`, `_MIGRATIONS` `:111`, `_current_version()` `:1197`, `_apply_migrations()` `:1214`/fast-path `:1229`, `ensure_db()` `:1253`, `connect()` `:1294`); `cli/doctor.py` (`CheckResult` `:54-73`, `_CHECKS`/`register_check` `:81-87`, `_run_registered_checks()` `:116`, `_history_db_data()`/`_history_db_check()` `:353-395`, `_FULL_CHECKS`/`register_full_check` `:484-490`, `_print_report()` `:936`, `main_doctor()` `:988`, ordered print calls `:1072-1079`); `history_reader.py` (62 `except sqlite3.Error:` sites confirmed by exact grep count, `logger.error` sites at `:2117`/`:2149` confirmed); `package_data.py` (`PACKAGE_DATA_ASSETS` `:28-48`, 19 current entries, `check_asset_accessible()` `:61-69`, `list_missing_assets()` `:72-75`); `queue_store.py` (`_current_version()` `:154-162`, fast-path `:172-173`, `ensure_db()` `:196-210`). Nothing has shifted since the 2026-08-17T19:48:59Z refine pass.
- **`_connect_readonly()` (`history_reader.py:422-446`) calls `ensure_db(db_path)` first** (`:435`, inside its own `try/except sqlite3.Error`) before opening the read-only connection — confirming a new schema-drift check must NOT reuse this helper (it would migrate away the drift it's inspecting) and must instead follow `_history_db_data()`'s `Path.exists()` + raw `sqlite3.connect(f"file:{db}?mode=ro", uri=True)` pattern, which never calls `ensure_db()`/`connect()`.

_Added by pre-implementation review — 2026-08-18 — measured empirically, not inferred:_

- **The version guard as specified leaves the detector near-inert.** Surveyed every
  `.ll/history.db` under `~/AIProjects` (13 databases): recorded versions are
  `13, 14, 14, 14, 37, 37, 37, 38, 38, 39, 39, 40, 45`. **Zero are at 43.** Under the
  four-branch guard below, twelve take the "behind → informational, do not compare" branch and
  one takes "ahead → informational" — the structural comparison runs on *none* of them. The
  guard is correct that comparing a behind-database against the v43 manifest is a false-positive
  generator; it is wrong that "behind" is a rare transient. It is the steady state. Resolved
  below: the runtime check builds its reference by **replaying `_MIGRATIONS[:recorded]`**
  instead of loading a fixed-version manifest, so it compares at every version.
- **Replay cost measured**: replaying all 43 migrations into `sqlite3.connect(":memory:")`
  takes **5.0 ms** (this machine, SQLite 3.49.2) — the same class as the `SELECT 1` that
  `_history_db_data()` already runs from `_CHECKS`, and well inside `ll-doctor`'s budget.
  This is a measurement, not an estimate; it removes the last cost objection to `_CHECKS`
  registration.
- **This repo's own `history.db` records `schema_version = 45` against `SCHEMA_VERSION = 43`
  (`len(_MIGRATIONS) = 43`).** `git log -S'SCHEMA_VERSION = 45'` returns no commits, so it was
  stamped by an uncommitted working-tree state run against the live database — precisely the
  mechanism this issue's Motivation describes, producing a *version-ahead* database rather than
  a structurally-drifted one. Consequence: `_apply_migrations()`'s fast path short-circuits on
  `45 >= 44`, so **migrations 44 and 45 will never apply to this database** when they land,
  silently and permanently. See BUG-3255 (filed 2026-08-18) for the repair; the guard branch
  below is re-rated from `informational` to a real finding as a result.
- **Structure on that v45 database is currently clean**: its full PRAGMA-derived manifest was
  diffed against a fresh `ensure_db()` build at v43 — zero object, column, or index differences
  in either direction. So the v45 stamp is a version-accounting defect, not live structural drift.
- **FTS5 shadow tables are in scope under the enumeration rule as written, and should not be.**
  `search_index` is `CREATE VIRTUAL TABLE ... USING fts5` (`schema.py:155`), so a fresh database
  carries five shadow tables that `sqlite_master` reports as `type='table'`:
  `search_index_config`, `search_index_content`, `search_index_data`, `search_index_docsize`,
  `search_index_idx`. The stated exclusions (`sqlite_autoindex_*`, `sqlite_stat*`) do not match
  them, so they and their internals land in the manifest — `search_index_content` is
  `id, c0, c1, c2, c3, c4`, an FTS5 implementation detail that can change between SQLite builds.
  A manifest generated on 3.49.2 could then false-positive against a user on a different build.
- **`sqlite_sequence` also slips through**: auto-created by `AUTOINCREMENT`, present on a fresh
  database, and matching neither named exclusion prefix.
- **View column *types* are inferred, not declared.** `PRAGMA table_info(issue_sessions)` returns
  `issue_id` as `BLOB` and `first_message_ts`/`last_message_ts` with an *empty* type string —
  SQLite derives these from the view's expressions, and that inference has changed across
  versions. AC bullet 1's "table **and view** column entries (name/type/notnull/pk)" therefore
  over-specifies views: the BUG-3236 object is a view, making the detector that matters most the
  one most exposed to cross-build noise.
- **No fresh-vs-migrated divergence exists** (checked, since it would have invalidated piece 1
  outright): `_MIGRATIONS` is a replayed ordered list and `ensure_db()` on a fresh database runs
  the identical sequence an old database completes incrementally, so there is no
  bootstrap-vs-migration column-order skew of the kind an `ALTER TABLE ADD COLUMN` bootstrap
  shortcut would create.

### Files to Modify

_Wiring pass added by `/ll:wire-issue`; line anchors corrected by the 2026-08-17 review pass:_

⚠ Superseded — the pre-v43 line anchors quoted by the earlier passes (`:1064`, `:1081`,
`:1096-1097`, `:1120`, `:1161`) and every "v42" reference in this issue are stale and must not
be used; the corrected anchors are the ones listed below and in the Integration Map review
block. The `history_reader.py` "all 62 log at `logger.warning` uniformly" finding is likewise
struck (2 sites use `logger.error`).

- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION` (`:21`), `_MIGRATIONS`
  (`:111`), `_current_version()` (`:1197`), `_apply_migrations()` (`:1214`, fast-path
  short-circuit at `:1229`), `ensure_db()` (`:1253`). Piece 1's `_schema_manifest()` and piece
  2's `_reference_manifest_at()` both land here; **no change to the fast path** (Option A
  avoids it — the `>=` defect at `:1229` is BUG-3255's, not this issue's).
- `scripts/little_loops/session_store/schema_manifest.json` (new) — the checked-in
  PRAGMA-derived manifest, as package data so both the test and the `ll-doctor` check read
  the same file.
- `scripts/little_loops/package_data.py` (`:28-48`) — add
  `("session_store", "schema_manifest.json")` to `PACKAGE_DATA_ASSETS`, or the completeness
  gate is false-green and the asset can silently escape the wheel.
- `scripts/little_loops/cli/doctor.py` — new `_schema_drift_data()` / `@register_check`
  (or `@register_full_check`) pair, modeled on `_history_db_data()`/`_history_db_check()`
  (`:353-395`); read-only, never creates or migrates the DB.
- `scripts/little_loops/history_reader.py` — 62 `except sqlite3.Error:` sites (piece 3,
  decision-only this pass); the file is already non-uniform: `sessions_for_issue()`
  (`logger.error` at `:2117`) and `issue_effort()` (`logger.error` at `:2149`) carry
  BUG-3236's point fix, while the remaining 60 sites use `logger.warning` — piece 3's
  convention must reconcile this, not treat the file as a blank slate.

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
  manifest check than standing up a new `ll-history` `doctor` subcommand, and the AC's
  "explicit `ll-history` `doctor` command" fallback should weigh this existing home before
  picking a name.
- `scripts/little_loops/cli/history.py` (`main_history()` at `:16`, subparsers `:66-248`) —
  alternate registration point if the `ll-history` `doctor` subcommand name is chosen instead
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
  and describes `ensure_db()`; already stale against the real value (**43**, after
  BUG-3241's v43 repair migration) — correct in the same pass regardless of which piece
  lands. Also document `_schema_manifest()` here.
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
- ~~`scripts/tests/fixtures/*/manifest.json` — existing checked-in JSON manifest fixture
  convention to follow for piece 1's schema manifest file.~~ **STRICKEN 2026-08-17 (review
  pass):** these are the right *JSON shape* precedent but the wrong *location* — the manifest
  is read at runtime by `ll-doctor` and must be package data. See the review-pass block under
  Integration Map.
- `scripts/tests/test_package_data_manifest.py` — the completeness gate over
  `PACKAGE_DATA_ASSETS`; adding the manifest without registering it there is a false-green.
- `scripts/tests/test_queue_store.py` (`:55-405`) — covers `queue_store.py`'s duplicate
  migration system; **explicitly deferred** this pass (see Scope Boundaries), so no change
  expected here — listed so the deferral is visible rather than looking like an oversight.
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
  is unchanged — the concrete proof for the "comment-only edit does not fail it" AC.
- New drift-detection tests, one per AC-named shape, built by mutating a healthy temp DB and
  then stamping `meta.schema_version` back to current so it looks clean to `_current_version()`:
  (a) `DROP`/recreate `issue_sessions` missing a column (BUG-3236 shape); (b) `DROP INDEX
  idx_assistant_messages_dedup` (BUG-3241 missing-index shape); (c) drop and recreate that
  same index **without** `UNIQUE` — the degraded-attribute case a name-only manifest passes,
  and the reason the manifest type was revised.
- New version-branch tests (added 2026-08-18, matching the revised version guard): (d) a v41
  database built via `_bootstrap_schema_at(41)`, unmutated → reported behind, **no drift
  claim**; (e) the same v41 database with an object dropped → **drift claim at v41**, proving
  the check is not confined to the current version (the whole point of the replay reference —
  0 of 13 real databases surveyed are at 43); (f) a database stamped `meta.schema_version = 45`
  → version-ahead finding naming both numbers, not `informational` (BUG-3255 shape).
- New exclusion test (added 2026-08-18): assert `_schema_manifest()` on a fresh database
  contains no `sqlite_%` name and none of the five `search_index_*` FTS5 shadow tables, while
  `search_index` itself *is* present with its five declared columns. Without this the manifest
  silently carries SQLite-build-dependent internals and the first cross-build comparison
  false-positives.

## Program Design

_Revised by the 2026-08-17 review pass: the previous `dict[str, list[str]]` shape (name ->
columns, plus a flat list of index names) **cannot satisfy AC bullet 4.** BUG-3241's drift
is about `idx_assistant_messages_dedup` (UNIQUE) and `idx_summary_nodes_retention_dedup`
(UNIQUE **and partial**, `WHERE kind = 'retention'` — `schema.py:1029+`). Comparing index
*names* alone passes an index that exists but has lost its UNIQUE-ness or its partial
predicate — i.e. it would not have caught the bug this AC names._

### Types

- `SchemaManifest: dict[str, Any]` — a JSON-serializable, deterministically ordered mapping
  with three top-level keys:
  - `"schema_version": int` — the `SCHEMA_VERSION` the manifest was generated at. The test
    asserts this equals the live `SCHEMA_VERSION`, so a manifest left un-regenerated after
    a migration fails loudly instead of silently comparing a stale structure.
  - `"objects": dict[str, dict]` — one entry per table and view (`sqlite_master` filtered to
    `type IN ('table','view')`), keyed by name, each holding its `PRAGMA table_info` columns
    as an ordered list of `{name, type, notnull, pk}` (a column losing NOT NULL or PK is
    drift worth catching; `dflt_value` is included only if it proves stable across SQLite
    builds — decide during implementation and record the call in a code comment).
    **Views record `name` and ordinal position only** (revised 2026-08-18): a view's
    `type`/`notnull`/`pk` are *inferred* by SQLite from the underlying expressions, not
    declared — `issue_sessions` reports `issue_id` as `BLOB` and both timestamp columns with
    an empty type string, and that inference has changed across SQLite versions. Recording
    them would make the BUG-3236 object the one most prone to cross-build false positives.
    Column presence and order is the part that actually encodes the BUG-3236 drift.
  - `"indexes": dict[str, dict]` — one entry per index, keyed by name, each holding
    `{unique, partial, origin, columns}` from `PRAGMA index_list` + `PRAGMA index_info`.

### Signatures

- `_schema_manifest(conn: sqlite3.Connection) -> SchemaManifest` (new, `session_store/schema.py`)
  — takes only a connection; no session-store coupling, so `queue_store.py` can reuse it
  verbatim in the deferred follow-up.
- `_load_schema_manifest() -> SchemaManifest` (new) — reads
  `session_store/schema_manifest.json` via `importlib.resources`, matching
  `package_data.check_asset_accessible()`'s access pattern. **Used by piece 1's test only**
  (revised 2026-08-18 — see `_reference_manifest_at()` below); the manifest stays package data
  regardless, so a future repair path and the deferred `queue_store.py` reuse do not have to
  relocate it, and so the settled "not a test fixture" decision is not reopened.
- `_reference_manifest_at(version: int) -> SchemaManifest` (new, `session_store/schema.py`) —
  replays `_MIGRATIONS[:version]` into `sqlite3.connect(":memory:")` and returns
  `_schema_manifest()` of the result: the structure a database at *that* recorded version is
  supposed to have. This is what piece 2 compares against, so the check works at every version
  rather than only at `SCHEMA_VERSION`. Measured at 5.0 ms for the full 43-migration replay.
  It shares the `_MIGRATIONS[:version]` replay idea with the tests' `_bootstrap_schema_at()`
  (`test_session_store_schema.py:1134-1154`) but is not the same function — that helper writes
  a real file for fixture use; this one is in-memory and returns a manifest. Prefer making the
  test helper delegate to this over adding a third replay copy (BUG-3241 already flagged the
  two existing copies as unshared).
- `test_schema_manifest_matches_checked_in_file() -> None` (new pytest test)
- `_schema_drift_data() -> dict` / `_schema_drift_check() -> list[CheckResult]` (new,
  `cli/doctor.py`)

### Enumeration and filtering rules

- Enumerate objects from `sqlite_master`, not from a hardcoded name list, or the manifest
  cannot detect an object that was *added* out of band.
- Exclude **every `sqlite_%` name**, not the two named prefixes (revised 2026-08-18). The
  original rule named only `sqlite_autoindex_*` and `sqlite_stat*` and therefore admitted
  `sqlite_sequence`, which `AUTOINCREMENT` auto-creates and which is present on a fresh
  database. The auto-index rationale still holds: their names are positional, so they churn on
  unrelated DDL edits, and the UNIQUE constraints they represent are already captured via the
  owning table's column entries.
- **Exclude FTS5 shadow tables** (added 2026-08-18). `search_index` is
  `CREATE VIRTUAL TABLE ... USING fts5` (`schema.py:155`), and SQLite materialises five backing
  tables that `sqlite_master` reports as ordinary `type='table'` rows:
  `search_index_config`, `search_index_content`, `search_index_data`, `search_index_docsize`,
  `search_index_idx`. Their internals are FTS5 version detail — `search_index_content` is
  `id, c0, c1, c2, c3, c4` — so including them makes the manifest a hostage to the generating
  machine's SQLite build. Record the `search_index` virtual table's own declared columns and
  drop the shadows. Derive the exclusion from the virtual tables actually present
  (`sqlite_master.sql LIKE 'CREATE VIRTUAL TABLE%'` → skip `<name>_%`), not a hardcoded list of
  five suffixes, so a second FTS table added later is handled without editing this rule.
- Sort every collection by name before serializing; the manifest is diffed by humans in
  review, so ordering must be stable across runs and SQLite builds.
- `PRAGMA index_list`'s `partial` column is a 0/1 flag — the predicate *text* exists only in
  `sqlite_master.sql`. See the Implementation trap below for how to handle this without
  reintroducing the text-comparison bug.

### Call Path

Piece 1 (test): `test_schema_manifest_matches_checked_in_file()` -> `ensure_db()` on a fresh
temp database -> `_schema_manifest(conn)` -> compared against `_load_schema_manifest()`;
fails when a migration changes structure without regenerating the file.

Piece 2 (runtime): `ll-doctor` -> `_run_registered_checks()` (`doctor.py:116`) ->
`_schema_drift_check()` -> `_schema_drift_data()` -> `Path.exists()` guard -> read-only
`sqlite3.connect(f"file:{db}?mode=ro", uri=True)` -> read recorded `meta.schema_version` ->
**version guard (below)** -> `_schema_manifest(conn)` compared against
`_reference_manifest_at(recorded)` -> `CheckResult` naming the differing objects. Never calls
`ensure_db()`/`connect()` — those would create and migrate the DB, erasing the drift.

_Revised 2026-08-18: the reference is built by replaying `_MIGRATIONS[:recorded]`, **not** by
loading the checked-in manifest. Comparing against a fixed v43 manifest would have restricted
the check to databases at exactly v43, of which there are currently **none** on this machine
(13 surveyed: versions 13–40 and one 45) — see the empirical block under Integration Map. The
checked-in manifest remains piece 1's authoring-time guard, which replay structurally cannot
replace: replay derives from the same `_MIGRATIONS` source an edit would have changed, so it is
self-consistent and blind to "someone edited migration 12's `CREATE TABLE` body". The two
mechanisms are complementary, and both are needed._

#### Version guard — required before any structural comparison

_Added by the 2026-08-17 pre-implementation review; the Call Path above and AC bullet 5
previously went straight from "open read-only" to "compare", which produces a false positive
on the first real database that is merely behind._

Because the check deliberately never migrates, it will encounter databases whose recorded
`schema_version` is **below** the current one. Such a database is not drifted — it is behind,
and `_apply_migrations()` will bring it to v43 correctly on the next `connect()`. Comparing
its structure against the *v43* reference reports every object added since its version as drift.

_Revised 2026-08-18: the original guard resolved this by refusing to compare anything but a v43
database. Measured against reality that silences the check almost entirely — 12 of the 13
databases on this machine are behind and the 13th is ahead, so the comparison branch would never
execute. Replaying `_MIGRATIONS[:recorded]` (`_reference_manifest_at()`) instead lets the behind
case be **compared, not skipped**: a v37 database is checked against what v37's own migrations
produce, which is exactly the "stamped a version it does not structurally match" question this
issue exists to answer, and answering it at v37 is as valuable as at v43._

The check therefore reads `meta.schema_version` (same query shape as `_current_version()`,
`schema.py:1197`, but on the read-only connection) and branches:

- **`0 < recorded <= len(_MIGRATIONS)`** — compare structure against
  `_reference_manifest_at(recorded)`. Covers both the current-version case (the BUG-3236 /
  BUG-3241 condition: stamped current, structurally not) and every behind-but-honest database.
  When `recorded < len(_MIGRATIONS)`, the `note` also states the database is behind and will
  migrate on next use — informational context alongside the structural verdict, not instead
  of it.
- **`recorded > len(_MIGRATIONS)`** — **a finding, not `informational`** (re-rated 2026-08-18).
  The original wording assumed this meant "the installed little-loops is older than the
  database (a downgrade or a mixed install)", which is benign. This repo's own `history.db` is
  in exactly this state — `schema_version = 45` against `len(_MIGRATIONS) = 43`, stamped by an
  uncommitted working tree, with no commit ever setting 45 — and it is not benign: the fast
  path short-circuits on `45 >= 44`, so migrations 44 and 45 will never apply to it. The note
  must say so, naming both numbers, because the database is permanently unreachable by future
  migrations until repaired. Do not compare structure (no reference exists for a version the
  installed code does not have). See BUG-3255.
- **`meta` table missing entirely** — `_current_version()` treats this as version 0; report
  `informational` (uninitialized), not drift.

The manifest's `"schema_version"` key stays load-bearing in piece 1's test (a manifest left
un-regenerated after a migration must fail loudly); at runtime, `len(_MIGRATIONS)` is the
authority, since that is what `_apply_migrations()` itself compares against.

**Comparison direction, when the versions match**: an object or index present in the manifest
but missing from the database is drift (BUG-3236 / BUG-3241's shape); an object present in the
database but absent from the manifest is *also* drift — the manifest enumerates from
`sqlite_master` (see Enumeration rules) precisely so an out-of-band addition is visible. The
`note` must distinguish the two directions rather than reporting an undifferentiated count.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

_Line anchors below were written pre-v43 and are ~130 lines stale; corrected figures are in
the review-pass block under Integration Map. Retained for their reasoning, not their numbers._

- `_apply_migrations()` fast-path short-circuit (now `session_store/schema.py:1229`) is `if _current_version(conn) >= len(_MIGRATIONS): return` — an unconditional early return with zero structural inspection. Its docstring frames this explicitly as a WAL-mode lock-avoidance optimization ("return without taking the write lock at all") — confirming the short-circuit is deliberate and load-bearing for concurrency, not an oversight to simply remove. **Option A leaves it untouched.**
- `_current_version(conn)` (now `schema.py:1197`) returns `0` only when the `meta` table itself is missing (`OperationalError` matching `"no such table"`); any other `sqlite3.Error` re-raises. `TestConcurrencyHardening` (`test_session_store_schema.py:145-223`) already covers the "locked vs genuinely-missing" distinction in this exact function — worth checking before adding new logic here so a new structural check doesn't reintroduce a race this suite already guards against.
- `ensure_db()` (now `schema.py:1253`) delegates entirely to `_apply_migrations()` for verification; `connect()` (now `:1294`) calls `ensure_db()` first, so any structural drift is invisible through every `connect()` caller, not just direct `ensure_db()` callers. **This is also why the `ll-doctor` check must open the DB read-only itself rather than going through either function** — both would migrate the drifted database out from under the check.
- `queue_store.py:154-210` duplicates this exact fast-path shape independently (see Integration Map) — the same gap exists in the queue database. **Explicitly deferred**: `_schema_manifest(conn)` takes only a connection precisely so a follow-up can point it at `queue.db` with no refactor.

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **A concrete precedent exists for the AC's "distinguish objects/indexes missing from the database from those present but absent from the manifest" requirement**: `cli/doctor.py:653-676` `_full_package_data_data()` is the only check in the file that distinguishes more than one finding category in a single note — it builds `parts: list[str]` conditionally per category (each a count + noun), then joins with `"; "`. Every other check in the file (`_history_db_data()` `:353`, `_decisions_store_data()` `:280`, `_loop_validity_data()` `:398` — the latter's `f"{len(invalid)}/{len(paths)} invalid: {', '.join(invalid)}"` shape is a count plus a name list, but only one category) produces a single-category note. The new `_schema_drift_data()`'s two-directional note (missing-from-db vs missing-from-manifest) should follow the `_full_package_data_data()` two-`parts`-entries shape, not the single-category shape the file otherwise uses uniformly.
- **No shared deterministic-JSON-writer utility exists anywhere in the codebase**; every serialization site is an inline `json.dumps(..., sort_keys=True, ...)` call at the write site (e.g. `session_store/writers.py:387,2401,2545,2669`, `prompts/fragment_store.py:31`). The one existing precedent for a *checked-in* JSON artifact writer, `verify_private_refs.py:473`, deliberately deviates: it pre-sorts the dict itself (`dict(sorted(counts_by_file(findings).items()))`, `:471`) and dumps with `sort_keys=False, indent=2` to preserve that pre-sorted insertion order rather than re-sorting at dump time. The manifest serializer this issue adds should pick one of these two shapes explicitly rather than assume `sort_keys=True` alone is "the" convention.
- **`PRAGMA index_list`/`PRAGMA index_info` produce zero matches anywhere in `scripts/`** — confirmed via search. Unlike the table-column manifest (which has `TestSchemaGuard`'s `PRAGMA table_info` shape as a loose ad hoc precedent, `test_codequery_codegraph.py:224-234`, a subset check only, not exact-match), the index half of `_schema_manifest()` has no existing code in the repository to model after at all — it is genuinely new introspection, not an adaptation of an existing pattern.

## Proposed Solution

Three pieces, roughly in order of cost and value. The first is worth doing alone.

**1. A structural assertion in the test suite.** For the current `SCHEMA_VERSION`, assert
that a freshly built database's PRAGMA-derived structure (see Program Design > Types for the
exact shape — columns *and* index unique/partial/column attributes, not just names) matches
a checked-in manifest. This is what would have caught both known instances at authoring
time, costs nothing at runtime, and needs no decision about self-healing. Generating the
manifest from `ensure_db()` on a fresh temp database and comparing it against the checked-in
file keeps it maintainable — the manifest diff becomes a required, reviewable part of any
migration PR.

**2. A report-only structural check in `ll-doctor`** (Option A, decided below). Compares the
*live* `.ll/history.db`'s manifest, read-only, against the structure its own recorded version's
migrations produce (`_reference_manifest_at(recorded)`, a 5.0 ms in-memory replay — revised
2026-08-18 from "the same checked-in file piece 1 asserts against", which would have confined
the check to v43 databases, of which none currently exist), and reports differing objects.
This is the piece that satisfies AC bullet 4:
piece 1's fresh-database test can only catch drift introduced by a migration edit, never
drift already present in a real database — which is exactly what BUG-3236 and BUG-3241 were.

_Superseded approach, retained for rationale:_ an earlier draft proposed a cheap sentinel
`PRAGMA table_info` inside `_apply_migrations()`'s fast path, making view drift self-healing.
Rejected — `ensure_db()` is on every `ll-*` invocation's critical path, the short-circuit is
load-bearing for WAL concurrency, and self-healing is out of scope. The `ll-doctor` check
carries the full manifest and is strictly more useful for BUG-3241's index drift anyway.

**3. A log-level convention for reader query failures.** BUG-3236 raises
`history_reader.py:2117` and `:2149` to `logger.error` as a point fix. There are 60+
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
must compare **PRAGMA-derived structure**, never SQL strings.

**The one place this rule is under pressure: partial-index predicates.** `PRAGMA index_list`
exposes `partial` as a 0/1 flag only; the `WHERE kind = 'retention'` predicate text on
`idx_summary_nodes_retention_dedup` lives solely in `sqlite_master.sql`. A predicate that
changed while the flag stayed `1` is therefore invisible to a pure-PRAGMA manifest. Two
acceptable resolutions — pick one and record it in a code comment:

- **Accept the flag only** (recommended, and the default if undecided): the manifest records
  `partial: 1`. A silently rewritten predicate goes undetected, but that requires editing an
  existing migration's body, which piece 1's test catches for a *fresh* database anyway.
- **Extract the predicate narrowly**: parse only the `WHERE ...` tail of the index's
  `sqlite_master.sql` and normalize whitespace. This stays clear of the comment-drift trap
  (the trap is about `CREATE TABLE` bodies; an index's WHERE tail carries no comments in this
  schema) but is fragile to harmless reformatting. Do **not** generalize this to tables.

Either way, never store or diff a whole `sqlite_master.sql` string.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Piece 1 (manifest snapshot test) — dominant convention confirmed**: for "assert generated structure against a fixed expectation" against a live SQLite schema, this codebase's established shape is an inline Python dict/set literal compared against `PRAGMA table_info` results inside the test body — see `scripts/tests/test_codequery_codegraph.py:224` (`TestSchemaGuard.test_pinned_columns_present_in_fixture`, module docstring calls this exact shape a "schema-drift guard"), and the same idiom repeated ad hoc across `scripts/tests/test_session_store_schema.py` (e.g. lines 94, 243, 303, 820, 883, 989, 1165, 1220). The checked-in-JSON-manifest convention (`scripts/tests/fixtures/*/manifest.json`) and the syrupy `.ambr` snapshot convention (`conftest.py:130-144` `stable_snapshot_env`) both exist but are scoped to different domains (fixture-set cataloging; CLI text-output regression) — neither has any precedent of being applied to schema/PRAGMA assertions. No shared PRAGMA-introspection helper exists anywhere in `scripts/little_loops/` (confirmed via grep for `def.*table_info`/`def.*introspect_schema`) — every PRAGMA/`sqlite_master` use across the codebase is written inline per call site, as the issue already claims.
- **Piece 2 (fast-path check vs. `ll-history` `doctor`) — no existing precedent combines a PRAGMA-based structural check with either shape**. Two established-but-disagreeing shapes exist for "diagnose vs. repair" surfaces: (a) `cli/doctor.py`'s shared `_CHECKS`/`register_check` registry (`:81-87`), consumed by one diagnose-only command — no `--fix`/repair path exists anywhere in that file; (b) independent per-command `--fix` flags that diagnose-and-optionally-repair within a single command, e.g. `cli/docs.py:67` (`"--fix"`, "Auto-fix mismatches") and `cli/issues/epic_consistency.py` (self-describes its subject as "drift" throughout — `has_drift`, `compute_drift`, `any_drift`; its `--fix` is scoped to only one drift category, remaining report-only for the rest; exit code is `0` under `--fix`, `1` on unresolved drift in report-only mode). Neither shape has been combined with a `PRAGMA table_info`-based structural check before — this is a genuinely undecided choice, not resolvable by precedent alone.
- **Piece 3 (log-level convention) — no mechanical rule exists to generalize from today, and none is derivable structurally**. The near-universal pattern across `history_reader.py`'s ~45 `except sqlite3.Error:`/`OperationalError:` sites and ~20 more in `session_store/writers.py`, `queries.py`, `lifecycle.py`, `schema.py` is `logger.warning(...)` with a `"<fn>: <thing> failed"` message; the sole exception is the matched `sessions_for_issue()`/`issue_effort()` pair (`history_reader.py:2117-2120`, `:2149-2152`) already covered above. Every site is exception-handler-identical in shape (`except sqlite3.Error:` → log → return empty/None) — the `.warning` vs `.error` choice does not correlate with table-vs-view, connect-vs-query, or any other structural condition visible at the call site, so a mechanical classifier cannot generalize the 2-site fix to the other 60 without new logic (e.g. checking `db_path.exists()` first, which `lookup_session_metadata`/`conversation_turns` already do as a third, undocumented convention — silently returning empty with no log at all when the db file itself is absent).

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **BUG-3241 work in this working tree is unrelated to ENH-3242.** `session_store/schema.py`'s new v43 migration (SCHEMA_VERSION 43) is a one-time *repair* migration for two already-known drift instances (dedups `assistant_messages`/`summary_nodes`, re-asserts non-UNIQUE indexes) — it does not add any drift-*detection* mechanism and does not touch `_apply_migrations()`'s fast-path short-circuit. No code toward ENH-3242's three pieces exists yet anywhere in the working tree.
- **Piece 2 decision is confirmed genuinely unresolved, not resolvable by precedent** (independently reconfirmed by codebase-pattern-finder this pass): `cli/doctor.py`'s `_CHECKS` registry (`:81-87`) is diagnose-only — zero `--fix`/repair vocabulary anywhere in that file — while `cli/docs.py` (`--fix`, `:66-70`) and `cli/issues/epic_consistency.py` (self-describes its subject as "drift": `EpicDrift`, `compute_drift()`, `has_drift`, `:44-96,141-224`; `--fix` diagnoses, repairs, then re-diagnoses to report post-fix state, `:279-283,332-343`) both bundle diagnose+repair behind a per-command `--fix` flag. These two shapes coexist today and have never been combined with a PRAGMA-based structural check before.

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

> **Selected:** Option A — matches `doctor.py`'s existing read-only convention exactly, adds zero cost to the `ensure_db()` hot path, ~~and stays inside the issue's own Scope Boundary of "a recorded decision, not full implementation."~~ **STRICKEN 2026-08-17 (pre-implementation review):** that clause predates the Scope Boundaries revision, which now states piece 2 *ships* as a working report-only detector. Option A is selected on convention and hot-path grounds alone — it is not a licence to record a decision and build nothing.

**Option A**: Extend `cli/doctor.py`'s `_CHECKS` registry with a manifest-based structural check (report-only). Write a `_data()`-shaped helper returning `{"status","severity","note"}`, wrap it with `@register_check`, and `main_doctor()`'s `for check in _CHECKS:` loop picks it up automatically — no new subcommand plumbing. Matches the file's existing convention (every check in `doctor.py` is read-only; there is no `--fix`/repair vocabulary anywhere in it). Diagnose-only: an operator still has to act on the finding manually.

**Option B**: Add a per-command `--fix` flag on a new/extended `ll-history` `doctor` subcommand (`cli/history.py`) that both diagnoses and repairs the structural drift in one surface, following `cli/docs.py --fix` and `cli/issues/epic_consistency.py --fix` precedent (self-describes its subject as "drift" throughout; `--fix` diagnoses, repairs, then re-diagnoses to report post-fix state). Self-healing, but a larger surface — new argument parsing, a repair code path, and re-diagnose-after-fix logic that Option A's registry does not need.

Both options can detect drift; only Option B repairs it in the same invocation. Neither has prior precedent combining a PRAGMA-based structural check with its shape — this is a genuinely open choice, not a coin-flip: it hinges on whether piece 2 should stop at detection (matching the issue's Scope Boundaries, which asks only for "a recorded decision... not full implementation") or extend to self-healing (which Acceptance Criteria bullet 4 arguably already requires — see the Confidence Check Notes' flagged inconsistency).

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **`importlib.resources` API shape, confirmed consistent across every existing caller**: `importlib.resources.files("little_loops")`, then `.joinpath(...)` per path segment (never a single multi-segment string), then either `.read_text(encoding="utf-8")` or `.is_file()`. Concrete model for the Program Design's `_load_schema_manifest()`: `scripts/little_loops/init/core.py:27-36` `_load_schema()` — single `.joinpath("config-schema.json")` then `.read_text(encoding="utf-8")` fed to `json.loads()`, wrapped in `@lru_cache(maxsize=1)`. `package_data.py:61-69`'s `check_asset_accessible()` uses the same `.joinpath()`-per-segment shape but does not cache (called once per asset in a sweep, not a hot path) — `_load_schema_manifest()` should decide caching on its own call frequency, not copy either precedent blindly.
- **A concrete precedent exists for the Wiring Phase's open "regeneration path" item**, resolving it from "no precedent" to "one clear model": `scripts/little_loops/generate_schemas.py:639-644` is the only `if __name__ == "__main__":` block in `scripts/little_loops/` shaped as "regenerate a checked-in artifact" — `python -m little_loops.generate_schemas [--output OUTPUT_DIR]`, also wired as a real console-script (`scripts/pyproject.toml:103`: `ll-generate-schemas = "little_loops.cli:main_generate_schemas"`, with an inline comment `# internal: dev tooling`). The other 12 `__main__` blocks in the package are ordinary CLI/debug entry points, not artifact-regeneration hooks.
- **The "regenerate with: ..." failure-message convention exists in two disagreeing shapes**, neither of which is a standalone `--dump-manifest`-style flag: (a) the instruction lives only in the test assertion string, e.g. `scripts/tests/test_wiring_skills_and_commands.py:395-398` (`f"{mirror_rel} is stale ... Regenerate with: ll-adapt --host gemini --apply && ..."`); (b) the instruction is embedded as a `_comment` field inside the checked-in JSON artifact itself, e.g. `scripts/little_loops/cli/verify_private_refs.py:461-474` `write_baseline()` writes `.ll/private-refs-baseline.json` with `"_comment": "Regenerate with ll-verify-private-refs --all --update-baseline. ..."`, and its regeneration is a flag (`--update-baseline`) on the same verifier CLI, not a separate dump command.

### Decision Rationale

**Selected**: Option A — extend `cli/doctor.py`'s `_CHECKS` registry with a report-only manifest check.

**Reasoning**: Option A matches the registry's own established convention exactly (every existing check in `doctor.py` is read-only; there is no `--fix`/repair vocabulary anywhere in the file), needs no new subcommand plumbing, and adds zero cost to `ensure_db()`'s hot path — sidestepping the startup-cost measurement the issue's Acceptance Criteria otherwise require for a fast-path check. ~~It also stays inside the issue's own Scope Boundary ("a recorded decision... not their full implementation").~~ **STRICKEN 2026-08-17 (pre-implementation review):** stale against the revised Scope Boundaries — piece 2 ships a working detector under Option A; only *repair* is deferred. Option B's self-healing appeal presumes Acceptance Criteria bullet 4 requires a working repair path now — exactly the internal inconsistency the Confidence Check Notes flagged as unresolved between Scope Boundaries and AC bullet 4. Deferring repair to a follow-up issue is cheaper than building it against a contested requirement.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — doctor.py registry (report-only) | 3 | 3 | 3 | 3 | 12/12 |
| B — `--fix` flag on `ll-history` `doctor` | 2 | 1 | 2 | 1 | 6/12 |

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
- ~~Decide the checked-in manifest snapshot's storage convention: syrupy `.ambr` vs. a JSON
  fixture under `scripts/tests/fixtures/schema/`.~~ **RESOLVED 2026-08-17 (review pass):
  neither.** Both are test-only locations, and Option A's `ll-doctor` check reads the
  manifest at runtime in installed environments where `scripts/tests/` does not exist. The
  manifest is package data at `scripts/little_loops/session_store/schema_manifest.json`,
  registered in `package_data.py:PACKAGE_DATA_ASSETS`, loaded via `importlib.resources` by
  both the test and the check. Letting the two read different files would recreate this
  issue's own failure class inside the fix.
- ~~Decide `_CHECKS` vs. `_FULL_CHECKS` (`doctor.py:81-87` vs. `:484-490`) for the new check.
  Weigh the cost of a full PRAGMA sweep of `history.db` against how often drift needs
  surfacing.~~ **RESOLVED 2026-08-17 (pre-implementation review): `_CHECKS`** — the default
  registry, running on every `ll-doctor`. The cost premise behind the open question does not
  hold: `PRAGMA table_info` / `index_list` / `index_info` read `sqlite_master` metadata only,
  so the sweep is proportional to the ~10-table schema and **independent of the store's data
  size** (5.8 GB on this repo). It is sub-millisecond, in the same class as the `SELECT 1` the
  existing `_history_db_data()` (`doctor.py:353-395`) already performs from `_CHECKS`.
  Against that, drift that only surfaces under `--full` will not be seen by the operator who
  needs it — both known instances (BUG-3236, BUG-3241) went undetected for months precisely
  because nothing surfaced them by default. Registering beside the existing `history.db`
  check also keeps the two `.ll/history.db` findings adjacent in the report.
- Provide a regeneration path for the manifest and document it in the test's failure message
  (e.g. a `python -m little_loops.session_store.schema --dump-manifest`-style hook, or an
  explicit "regenerate with: ..." line). Neither of the rejected conventions' tooling
  (`pytest --snapshot-update`) applies now, so without this a failing test tells a
  contributor nothing about how to fix it.

## Impact

- **Priority**: P2 — no user-visible defect today once BUG-3236 and BUG-3241 land; this
  prevents the class. Piece 1 is small and high-leverage; pieces 2 and 3 are larger.
- **Effort**: Piece 1 small; piece 2 small-medium under Option A (a read-only `doctor.py`
  check reusing piece 1's helper — no hot-path change, so no startup-cost measurement
  needed); piece 3 medium-large (touches 60+ call sites, mechanically) and is decision-only
  in this pass.
- **Sequencing**: after **both** BUG-3236 and BUG-3241 — the manifest must be generated at
  v43 or later, or it bakes in exactly the index drift BUG-3241's v43 migration repairs. The
  earlier "taken against a correct v42 schema / independent of BUG-3241" note predates v43
  and is wrong. **Satisfied as of 2026-08-17**: both BUG-3236 and BUG-3241 are `done`
  (verified via `ll-issues show`), and `SCHEMA_VERSION = 43` is live in the working tree, so
  nothing blocks this issue — generate the manifest against the current schema.
- **Breaking Change**: No.

## Acceptance Criteria

_Revised by the 2026-08-17 review pass: bullet 3 demanded a startup-cost measurement for a
fast-path check that the Option A decision means nobody is building, and bullet 4's "whichever
ships" was ambiguous about whether anything ships at all. Both are now concrete._

_Revised again 2026-08-18 (pre-implementation review, empirically verified): the runtime check
compares against a replayed per-version reference rather than the fixed-version manifest; view
columns drop inferred type/notnull/pk; the exclusion rule widens to all `sqlite_%` plus FTS5
shadow tables; the version-ahead branch is re-rated from informational to a finding._

- [ ] A test asserts the full PRAGMA-derived structure of a fresh database at the current
      `SCHEMA_VERSION` against a checked-in manifest, and fails when a migration changes
      structure without regenerating it. The manifest covers: **table** column entries
      (name/type/notnull/pk), **view** column names and ordinal position only (their
      type/notnull/pk are SQLite-inferred and vary across builds — see Program Design > Types),
      and per-index `unique`, `partial`, `origin`, and ordered column list — **not index names
      alone**.
- [ ] The manifest excludes every `sqlite_%` object (not just `sqlite_autoindex_*` /
      `sqlite_stat*` — `sqlite_sequence` exists on a fresh database and would otherwise be
      included) and excludes the FTS5 shadow tables backing `search_index`
      (`search_index_config`/`_content`/`_data`/`_docsize`/`_idx`), whose internals are
      SQLite-build-dependent. The shadow exclusion is derived from the virtual tables present,
      not a hardcoded suffix list. A test asserts none of these names appear in the manifest.
- [ ] The manifest records the `SCHEMA_VERSION` it was generated at, and the test fails if
      that value differs from the live `SCHEMA_VERSION`.
- [ ] The manifest ships as package data at
      `scripts/little_loops/session_store/schema_manifest.json`, is registered in
      `PACKAGE_DATA_ASSETS` (`package_data.py`), and `ll-verify-package-data` exits 0. There
      is exactly one manifest file in the repository. (Revised 2026-08-18: the `ll-doctor`
      check no longer *reads* it — it replays `_MIGRATIONS[:recorded]` instead — but the
      manifest stays package data so a future repair path and the deferred `queue_store.py`
      reuse need not relocate it, and so the settled "not a test fixture" decision is not
      reopened.)
- [ ] The test compares PRAGMA output, never whole `sqlite_master.sql` text; a comment-only
      edit to a `CREATE TABLE` body does not fail it. (Any narrow partial-index predicate
      extraction, if chosen, is scoped to index `WHERE` tails and documented in a comment.)
- [ ] A report-only `ll-doctor` check ships that detects a database stamped current but
      structurally drifted, on both known shapes: a missing view column (BUG-3236) and a
      missing/degraded index (BUG-3241), with tests covering absent / healthy / drifted.
      "Degraded" includes an index present by name but no longer UNIQUE or no longer
      partial — the BUG-3241 shape a name-only manifest would miss.
- [ ] The check never creates or migrates `.ll/history.db`: it guards on `Path.exists()` and
      opens read-only, per `_history_db_data()`'s existing constraint. A test asserts running
      it in a directory with no `.ll/history.db` leaves none behind.
- [ ] The check compares each database against the structure **its own recorded version**
      produces (`_reference_manifest_at(recorded)`), for any `0 < recorded <= len(_MIGRATIONS)`.
      A behind-but-structurally-correct database is reported as behind-and-will-migrate and
      **not** as drift; a behind *and* drifted database is still reported as drifted. Tests
      cover a v41 database in both conditions (clean → no drift claim; mutated → drift claim),
      alongside the current-version healthy and drifted cases. (Revised 2026-08-18: comparing
      only at `SCHEMA_VERSION` would have made the check inert — 0 of the 13 databases surveyed
      on this machine are at 43.)
- [ ] A database whose recorded version **exceeds** `len(_MIGRATIONS)` is reported as a finding
      — not `informational` — with a note naming both numbers and stating that pending
      migrations will never apply to it, because `_apply_migrations()`'s fast path
      short-circuits. A test covers this branch. (This repo's own `history.db` is at 45 against
      `len(_MIGRATIONS) = 43`; see BUG-3255.) A missing `meta` table remains `informational`.
- [ ] The drift `note` distinguishes objects/indexes missing from the database from those
      present but absent from the manifest, rather than reporting an undifferentiated count.
- [ ] The check is registered in `_CHECKS` (runs on every `ll-doctor`), not `_FULL_CHECKS` —
      decided 2026-08-17, see Wiring Phase. A decision is recorded on whether it also surfaces
      in `ll-doctor --json` (`_print_report()`, `doctor.py:951-971`).
- [ ] Explicitly deferred, recorded in this issue rather than silently dropped: any repair
      path, the `queue_store.py` parallel manifest, and piece 3's log-level reclassification.
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
- Piece 2's chosen shape (fast-path check in `ensure_db()` vs. a new `ll-history` `doctor` command) is genuinely undecided by the issue's own research findings — no existing precedent combines a PRAGMA-based structural check with either the `doctor.py` registry or a `--fix`-flag shape. Whichever is chosen, `ensure_db()` sits on nearly every `ll-*` invocation's hot path (~52 files via `cli_event_context()`, plus `hooks/session_start.py` independently) — a fast-path change is an 11+-caller blast radius, not an isolated one.
- Scope Boundaries states pieces 2 and 3 need only "a recorded decision... not their full implementation," but Acceptance Criteria bullet 4 ("Whichever ships detects a database stamped current but structurally drifted, on both known shapes") reads as requiring piece 2 to actually ship a working detector, not just a documented decision. Resolve this internal inconsistency before implementation to avoid over- or under-building piece 2.

### Review-Pass Resolutions — 2026-08-17

- **Risk factor 1 (piece 2's shape / hot-path blast radius): resolved.** Option A ships the
  check in `cli/doctor.py`, read-only, and touches neither `_apply_migrations()`'s fast path
  nor `ensure_db()`. The ~52-caller blast radius is not entered at all, and the
  startup-cost measurement the old AC demanded is moot.
- **Risk factor 2 (Scope Boundaries vs. AC bullet 4): resolved.** Scope Boundaries now
  states piece 2 *ships* as report-only detection, with repair, `queue_store.py`, and piece 3
  explicitly out of scope. AC bullet 4 was the correct requirement; the Scope Boundaries
  wording was the defect, because piece 1's fresh-database test can never satisfy it.
- **New finding this pass, not previously flagged:** the `SchemaManifest` type as specified
  (index *names* only) could not have detected BUG-3241, which is an AC-named shape. Type
  revised to carry `unique`/`partial`/`origin`/columns per index. Outcome confidence should
  be re-scored against the revised Program Design.

### Second Review Pass — 2026-08-17 (verified against the working tree)

Three changes, all recorded in place above rather than as a separate plan:

1. **The check had no `schema_version` guard — a false-positive generator.** The Call Path
   went from "open read-only" straight to "compare against the v43 manifest", but the check
   deliberately never migrates, so it will meet databases legitimately sitting below v43.
   Those are behind, not drifted, and would have been reported as drift in every object added
   since their version — meaning the check's first output on any un-upgraded project is
   wrong. Resolved: a four-branch version guard is now specified under Program Design > Call
   Path, with a matching AC bullet and a v41 test case. This is the finding most likely to
   have shipped as a defect.
2. **`_CHECKS` vs `_FULL_CHECKS` decided: `_CHECKS`.** The open question weighed a "full
   PRAGMA sweep" cost that does not exist — PRAGMA introspection reads `sqlite_master`
   metadata and is independent of the 5.8 GB data size, putting it in the same class as the
   `SELECT 1` `_history_db_data()` already runs by default. A `--full`-gated check would not
   have surfaced either known instance. Reasoning recorded at the Wiring Phase bullet; AC
   bullet updated from "record a decision" to the decision itself.
3. **Two stale Option-A justifications struck.** Both the `> **Selected:**` blockquote and the
   Decision Rationale still justified Option A partly as "stays inside the issue's own Scope
   Boundary ('a recorded decision, not full implementation')" — written before Scope
   Boundaries was revised to state piece 2 *ships*. Left as strikethrough rather than deleted,
   per this issue's existing correction convention. An implementer reading only the Decision
   Rationale would otherwise have shipped a decision record and no detector.

Also confirmed: BUG-3236 and BUG-3241 are both `done`, so the Impact > Sequencing constraint
is satisfied and nothing blocks implementation.

### Third Review Pass — 2026-08-18 (assumptions verified empirically, not by reading)

Five changes. The design was sound on every question it had already asked; what it had not done
was run its own premises against real databases.

1. **The version guard, correct in isolation, made the detector nearly inert.** Surveying all 13
   `.ll/history.db` files under `~/AIProjects` found versions 13–40 and one 45 — **none at 43**.
   The "compare only at `SCHEMA_VERSION`" rule would therefore have executed its comparison
   branch on zero real databases while passing all its own tests. Resolved by replaying
   `_MIGRATIONS[:recorded]` as the reference (`_reference_manifest_at()`, measured at 5.0 ms for
   the full 43-migration replay), which compares at every version. The checked-in manifest stays
   as piece 1's authoring-time guard, which replay structurally cannot replace. This is the
   finding most likely to have shipped as a no-op feature.
2. **The version-ahead branch is a live defect, not a benign edge case.** This repo's own
   database is at 45 against `len(_MIGRATIONS) = 43`, stamped by an uncommitted working tree
   (`git log -S` finds no commit), and will silently skip migrations 44 and 45. Filed as
   BUG-3255; the guard branch is re-rated from `informational` to a finding.
3. **FTS5 shadow tables and `sqlite_sequence` were in scope under the exclusion rule as
   written.** `search_index` is an fts5 virtual table, so five shadow tables report as ordinary
   tables in `sqlite_master`; their internals (`search_index_content` = `id, c0..c4`) are
   SQLite-version detail. Exclusion widened to all `sqlite_%` plus virtual-table shadows.
4. **View column types are inferred, not declared** — `issue_sessions` reports `issue_id` as
   `BLOB` and its timestamp columns with empty type strings. AC bullet 1 over-specified views,
   making the BUG-3236 object the one most exposed to cross-build false positives. Views now
   record names and ordinal position only.
5. **Checked and found sound** (recorded so a later pass does not re-litigate): there is no
   fresh-vs-migrated structural divergence — `ensure_db()` replays the same `_MIGRATIONS`
   sequence an old database completes incrementally, so piece 1's fresh-database premise holds;
   `_connect_readonly()` does call `ensure_db()` at `history_reader.py:435` as claimed, confirming
   it must not be reused; and the 62 `except sqlite3.Error:` / 2 `logger.error` counts are
   accurate.


## Session Log
- `/ll:confidence-check` - 2026-08-18T20:26:47 - `d31a43c6-df20-4b44-8f4b-1800e5b2fd9f.jsonl`
- `/ll:confidence-check` - 2026-08-18T20:00:14 - `a6a80ad6-5605-4f34-ad7e-747b40989e95.jsonl`
- `/ll:reconcile-issue` - 2026-08-18T19:49:34 - `06995e01-0c99-42f0-82c2-6ada1ee575ad.jsonl`
- `/ll:refine-issue` - 2026-08-18T19:14:07 - `83fc2c85-7489-49a3-809c-acf74625afa6.jsonl`
- `/ll:format-issue` - 2026-08-17T21:42:04 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:20:09 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:confidence-check` - 2026-08-17T20:06:56 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:wire-issue` - 2026-08-17T20:02:00 - `39c0d6a6-4890-4cb9-b9a6-2422918637ba.jsonl`
- `/ll:decide-issue` - 2026-08-17T19:50:12 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:48:59 - `210ffe2f-782a-4152-bb68-4c236339a110.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:36:36 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:decide-issue` - 2026-08-17T19:30:44 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:refine-issue` - 2026-08-17T19:28:34 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:08:26 - `ef11a41c-065c-4fa1-bb32-c968298e27a9.jsonl`
- `/ll:wire-issue` - 2026-08-17T18:58:48 - `a29924e0-c6de-4707-a414-f7282d13c3c9.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:46:12 - `f45aab6b-bb54-4fbd-9613-662d061dc865.jsonl`
- `/ll:format-issue` - 2026-08-17T18:39:06 - `73e92a5b-b52b-41fd-896b-d930c6b15dc8.jsonl`
