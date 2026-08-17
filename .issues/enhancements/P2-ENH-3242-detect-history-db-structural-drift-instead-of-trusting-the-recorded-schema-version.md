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
confidence_score: 96
outcome_confidence: 76
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 14
score_change_surface: 20
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


## Session Log
- `/ll:confidence-check` - 2026-08-17T19:08:26 - `ef11a41c-065c-4fa1-bb32-c968298e27a9.jsonl`
- `/ll:wire-issue` - 2026-08-17T18:58:48 - `a29924e0-c6de-4707-a414-f7282d13c3c9.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:46:12 - `f45aab6b-bb54-4fbd-9613-662d061dc865.jsonl`
- `/ll:format-issue` - 2026-08-17T18:39:06 - `73e92a5b-b52b-41fd-896b-d930c6b15dc8.jsonl`
