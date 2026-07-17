---
id: ENH-2465
title: Periodic epic-progress snapshots into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: '2026-07-02T00:00:00Z'
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
refined_at: '2026-07-07T00:00:00Z'
refined_by: refine-issue
labels:
- enhancement
- history-db
- epics
- captured
confidence_score: 98
outcome_confidence: 71
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# ENH-2465: Periodic epic-progress snapshots into history.db

> **✅ Architecture alignment (ENH-2581 `raw_events`).**
> [[ENH-2581]] made `raw_events` the single ingestion point for **session-transcript
> JSONL**, with stream-derived tables materialized by `_backfill_*()` parsers via
> `rebuild()` (the pattern [[ENH-2461]] became). **`epic_progress_snapshots` is NOT
> such a table, and correctly so.** A snapshot is a *rollup computed from live issue
> files* on the `.issues/` filesystem (a by-status aggregation of `issue_events`),
> written at child-issue transition time and on each `ll-issues epic-progress`
> invocation — nothing about it is present in, or recovered from, transcript JSONL.
> It is therefore a **live/direct-write sibling** (same category as `commit_events`/
> [[ENH-2458]] and `test_run_events`/[[ENH-2459]]) and joins the "outside
> `raw_events`'s scope" exclusion set (NOT in `_REBUILD_TABLES` /
> `_REBUILD_SEARCH_KINDS`). No `raw_events`-sourced parser is needed. (Read the live
> `SCHEMA_VERSION`/`VALID_KINDS` — now `20` / exported tuple `VALID_KINDS` — at
> implementation time; the v15–v19 references in the body predate [[ENH-2581]].)

## Summary

`ll-issues epic-progress <EPIC>` recomputes from live issue state every time — there's no historical snapshot. Once an EPIC closes (or a child moves from `open` → `in_progress` → `done`), the previous state of "what was open last Tuesday at 14:00?" is no longer recoverable from the DB. Add an `epic_progress_snapshots` table populated at child-issue transition time (and on `ll-issues epic-progress` invocation) carrying `(ts, epic_id, by_status_json, total_children, open_count, in_progress_count, done_count, deferred_count, blocked_count, cancelled_count, completion_fraction)`. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #8: *"periodically (e.g. on `epic-progress` invocation, or on child issue transitions) snapshot `by_status` counts so epic velocity is queryable historically, not just as a point-in-time computation."*

## Motivation

Epic velocity is one of the project-management signals most users ask for ("how fast does this EPIC close?"), but it cannot be reconstructed after the fact:

- **No "was BUG-3 open two weeks ago?" answer** — once an issue transitions to `done`, its status history is captured in `issue_events` (per ENH-1686), but a rollup-by-status view is missing.
- **No progress-over-time line chart** — `ll-history` cannot render an EPIC's burndown without the snapshot.
- **No trend anomaly detection** — "this EPIC went 30 days with no closes" requires historical data.
- **Sibling cache/calc** — `ll-sprint` consumes epic progress; if that consumer crashes mid-computation, the snapshot is the fallback.

The `issue_events` schema (ENH-1686) gives raw transition events; a rollup table aggregates them.

## Current Behavior

- `ll-issues epic-progress <EPIC>` reads current issue state from `.issues/<type>/*.md` files; computes `by_status` counts; returns a rollup. No persistence.
- `ll-issues show <EPIC>` lists children and their current statuses.
- `ll-session search --fts "<epic title>"` finds the EPIC file but no historical view.
- No "epic was 25% done last week" data.

## Expected Behavior

- `epic_progress_snapshots` table exists in the next schema version (v19+ as of 2026-07-06; the issue predates v15–v18 landing) with columns: `id`, `ts`, `epic_id`, `total_children`, `open_count`, `in_progress_count`, `done_count`, `deferred_count`, `blocked_count`, `cancelled_count`, `completion_fraction REAL`.
- A snapshot is written on each child issue transition (via the `issue.*` live-write path) keyed by parent epic; idempotent on `(epic_id, ts)` for within-second transitions.
- A snapshot is written on every `ll-issues epic-progress <EPIC>` invocation, regardless of outcome.
- `history_reader.epic_progress_history(epic_id, since=None)` returns a time-series of snapshots for an EPIC.
- `ll-sprint` and `ll-history` consumers can read the snapshot stream without recomputing on each call.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS epic_progress_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    epic_id TEXT NOT NULL,
    total_children INTEGER NOT NULL,
    open_count INTEGER,
    in_progress_count INTEGER,
    done_count INTEGER,
    deferred_count INTEGER,
    blocked_count INTEGER,
    cancelled_count INTEGER,
    completion_fraction REAL
);
CREATE INDEX IF NOT EXISTS idx_epic_snapshots_epic_id ON epic_progress_snapshots(epic_id);
CREATE INDEX IF NOT EXISTS idx_epic_snapshots_ts ON epic_progress_snapshots(ts);
```

Bump `SCHEMA_VERSION`. Add `"epic_progress"` to `_VALID_KINDS` and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE`.

### Producer wiring

- In `SQLiteTransport.send()` `issue.*` branch (per ENH-1686 / ENH-1690 / ENH-2462 — sibling work on this exact emit site), after the `issue_events` insert, walk the issue's `parent`/`relates_to` chain, find any ancestor EPIC, and compute the EPIC's current rollup. Insert a row into `epic_progress_snapshots`.
- In `scripts/little_loops/cli/issues/epic_progress.py` (the `cmd_epic_progress()` handler), on every invocation, after computing the rollup, write a snapshot row.
- Both writers use `contextlib.suppress(Exception)`. Walks degrade gracefully if `.issues/` files are missing or the parent chain is broken.

### Computation source

- Walk current `.issues/<type>/<epic-id>-*.md` files for `relates_to:` matches against the epic.
- Each child file's `status:` frontmatter drives the by_status count.
- For performance: cache the rollup calc in `scripts/little_loops/issue_progress.py` and re-use; existing `ll-issues epic-progress` already does this.

### Read API

Add to `history_reader.py`:
- `epic_progress_history(epic_id, since=None, limit=200)` — time-series for an EPIC.
- `epic_progress_latest(epic_id)` — most-recent snapshot.
- `epic_velocity(epic_id, window_days=14)` — derived rate (commits per day or done-count delta per day).

### CLI surface

- `ll-issues epic-progress --history <EPIC>` — print snapshot time-series.
- `ll-history epic-velocity --since 30d` — roll-up across all epics.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — bump `SCHEMA_VERSION` from its live value (confirmed `23` as of 2026-07-17; next open slot `24` — see Verification Log) at line 211; append `"epic_progress"` to `VALID_KINDS` (lines 213–227) and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE` (lines 229–243); append the new migration string to `_MIGRATIONS` (list spans lines 341–806); add `record_epic_progress_snapshot()`, `_backfill_epic_progress_snapshots()`, and `backfill_epic_progress_snapshots()` helpers mirroring the `record_issue_snapshot()` / `_backfill_snapshots()` / `backfill_snapshots()` triple at lines 1073, 1986, and the `__all__`-exported wrapper respectively; wire into `SQLiteTransport.send()` `issue.*` branch (starts line 1825) immediately after the `_index(...)` call at line 1849 — **but see the Verification Log below: an early `return` at line 1864 (inside the `done`/`open`/`cancelled` file-snapshot block) means the epic-snapshot call must be placed BEFORE that `return`, not merely "after `_index()`", or it never runs for exactly the terminal transitions epic-progress cares about.**
- `scripts/little_loops/history_reader.py` — add `EpicProgressSnapshot` dataclass to the dataclass block (alongside `CommitEvent` at line 133); add `epic_progress_history(epic_id, since=None, *, limit=200, db=DEFAULT_DB_PATH)`, `epic_progress_latest(epic_id, *, db=DEFAULT_DB_PATH)`, and `epic_velocity(epic_id, window_days=14, *, db=DEFAULT_DB_PATH)` reading-side functions. Clone `recent_usage_events()` (line 683) rather than `related_issue_events()` (line 439) — the former already has the `since` + `limit` + `_connect_readonly()` (line 300) shape the epic reader needs.
- `scripts/little_loops/cli/issues/epic_progress.py` — call `record_epic_progress_snapshot(db, prog, ts=...)` at the end of `cmd_epic_progress()` (after the `compute_epic_progress()` call at line 53) inside a `try/except` so a DB write failure cannot break the CLI; add an `--history` flag to `add_epic_progress_parser()` (starts line 16) that re-uses the new `epic_progress_history()` reader.
- `scripts/little_loops/cli/history.py` — add an `epic-velocity` subcommand for `ll-history epic-velocity --since 30d`. (`cli/history_context.py` is the separate `ll-history-context` CLI — not the right home.) Insert the new subparser immediately after the `root_parser` block at lines 205–221 (the most recent subcommand added) and before `add_config_arg(parser)` at line 223; mirror the dispatch-by-`args.command` pattern that already routes `summary`/`analyze`/`export`/`sessions`/`root` later in the function.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/observability/schema.py` (lines 487–505, 563–634) — OPTIONAL: register `EpicProgressSnapshotVariant(DESVariant)` with `type: Literal["epic_progress_snapshot"] = "epic_progress_snapshot"` to follow the `IssueSnapshotVariant` / `CommitEventVariant` / `TestRunEventVariant` Channel A precedent. The DES audit (`observability/audit.py:55-67, 75-111`) only flags `event_bus.emit(...)` / `_emit(...)` call sites, so the direct-writer approach is gate-clean either way. Skip if minimizing channel footprint; include if matching the `IssueSnapshotVariant` precedent for symmetry. [Agent 1 / Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_progress.py` — `compute_epic_progress()` (lines 83–147) and `EpicProgress` (lines 17–48) are the canonical rollup source; the snapshot writer should call `compute_epic_progress()` and shape `EpicProgress.to_dict()` into the snapshot row rather than reimplementing the walk.
- `scripts/little_loops/issue_lifecycle.py` — six `event_bus.emit(...)` call sites (lines 577, 674, 748, 841, 937, 993) all flow into the `SQLiteTransport.send()` `issue.*` branch; no producer-side change needed (snapshot writes happen in the transport, not at the producer).
- `scripts/little_loops/cli/issues/list_cmd.py` — imports `compute_epic_progress` (lines 63, 234) and uses it for the `--parent` filter; unchanged by this issue but consumes the same rollup function.
- `scripts/little_loops/cli/issues/__init__.py` — registers `add_epic_progress_parser` at line 795 and dispatches `cmd_epic_progress` at line 857; needs no edits unless the parser signature grows.
- `scripts/little_loops/transport.py` — registers the SQLite transport on the EventBus (lines 652–655); unchanged.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` (line 44) — re-exports `SQLiteTransport`, `record_issue_snapshot`, etc. from `session_store`; append `record_epic_progress_snapshot` and `backfill_epic_progress_snapshots` for parity (otherwise the helpers are importable but undiscoverable via `from little_loops import *`). [Agent 1 finding]
- `scripts/little_loops/cli/session.py` (lines 45, 103, 115) — argparse `choices=list(VALID_KINDS)` drives the `--kind`/`--exclude` filter surfaces; once `"epic_progress"` is added to `VALID_KINDS` these auto-extend. No code edit required at this file, but verify the `recent` and `search` subcommands accept the new kind in a smoke test. [Agent 1 finding]
- `scripts/little_loops/cli/issues/set_status.py:75` — imports `record_issue_snapshot`, `resolve_history_db`; sibling writer pattern that the new snapshot writer mirrors. No code edit required, but flag as the closest set_status-side precedent for transactional safety (the `set_status` cascade writes a snapshot before/after every status flip). [Agent 1 finding]
- `scripts/little_loops/hooks/post_commit.py:50,73` — imports `record_commit_event` as a direct-write hook reference. ENH-2465 does NOT need a new hook (snapshot writes flow through `SQLiteTransport.send()` `issue.*` branch), but the `post_commit` writer shape is the closest sibling for "best-effort own-connection insert with FTS-index on success". [Agent 1 finding]
- `scripts/little_loops/pytest_history_plugin.py:126-129` — imports `record_test_run_event`, `resolve_history_db`. Same best-effort direct-writer pattern; flag as the third sibling in the writer family (`record_issue_snapshot` / `record_commit_event` / `record_test_run_event` → `record_epic_progress_snapshot`). [Agent 1 finding]
- `scripts/little_loops/issue_manager.py:1161` — `self.event_bus.add_transport(SQLiteTransport(db_path or DEFAULT_DB_PATH))` (AutoManager path). Confirms the only place a fresh `SQLiteTransport` is constructed outside `transport.py`. No edit, but flag if the schema-version gate in `ensure_db()` is called inside the transport's `__init__` — verify a v20→v21 auto-upgrade path runs before the first `record_epic_progress_snapshot` call. [Agent 1 finding]
- `scripts/little_loops/cli/verify_kinds.py:30-47` — `_all_migration_tables()` and `_run()` form the `ll-verify-kinds` gate (the kindless/kind centralization check). The new `epic_progress_snapshots` table MUST be registered in either `_KIND_TABLE` or `_KINDLESS_TABLES` at `session_store.py:223-255` to keep this gate green. Recommended path: register in `_KIND_TABLE` (drives the `--kind epic_progress` filter) and rely on the `set(VALID_KINDS) == set(_KIND_TABLE.keys())` invariant enforced by `TestValidKindsCentralization` (see Tests). [Agent 1 / Agent 2 finding]
- `scripts/little_loops/parallel/orchestrator.py:1234,1261,1281` — uses `compute_epic_progress` for the all-done gate. Read-only consumer of the same rollup function; could be a follow-up candidate for switching to `epic_progress_latest(epic_id)` to avoid recomputation. Out of scope for ACs but worth a follow-up issue. [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/session_store.py:record_issue_snapshot()` (lines 816–866) — closest architectural analog: best-effort "compute-then-insert" writer called as a side-effect after the main `issue_events` insert.
- `scripts/little_loops/session_store.py:record_commit_event()` (lines 1041–1091) — closest analog for the writer signature: `db_path` first, payload fields next, returns `bool` indicating inserted-or-not via `cursor.rowcount`; idempotent via `INSERT OR IGNORE` on the `commit_sha UNIQUE` column.
- `scripts/little_loops/session_store.py:_MIGRATIONS` v3 (lines 277–282) and v14 (lines 437–450) — pattern for an additive migration that adds a new `CREATE TABLE` plus a `CREATE UNIQUE INDEX` dedup index. The v19 migration should follow this shape: `CREATE TABLE IF NOT EXISTS epic_progress_snapshots (...)` + `CREATE UNIQUE INDEX IF NOT EXISTS idx_epic_snapshots_dedup ON epic_progress_snapshots(epic_id, ts)`.
- `scripts/little_loops/history_reader.py:related_issue_events()` (lines 370–404) and `recent_commit_events()` (lines 524–559) — read-side shape to clone for `epic_progress_history()`: `db_path` → `_connect_readonly` → build SQL with optional `since` → execute → wrap in `try/except sqlite3.Error → return []`.
- `scripts/little_loops/text_utils.py:parse_duration()` (lines 173–188) — for the `--since 30d` flag on the new `epic-velocity` subcommand. Pair with the argparse + consumption pattern at `scripts/little_loops/cli/loop/info.py:cmd_history` (lines 648–659).
- `scripts/little_loops/cli/issues/set_status.py` (lines 81–98) — transitive-cascade walker over `parent:` edges (cycle-guarded with `seen: set`); mirrors the `_issue_descends_to` walker in `issue_progress.py:67–80` and is the right precedent for "transitive parent rollup" semantics.

### Tests
- `scripts/tests/test_session_store.py:TestRecordIssueSnapshot` (lines 2942–3013) — four-test pattern (round-trip / idempotent / missing-file noop / FTS) to clone as `TestRecordEpicSnapshot`.
- `scripts/tests/test_session_store.py:TestSchemaV14` (lines 2872–2987) — three-test pattern (schema version, table exists, dedup index exists, plus `_bootstrap_schema_at` upgrade path) to clone as `TestSchemaV19EpicProgressSnapshots`. Use the shared `_bootstrap_schema_at(db, version)` helper at `tests/test_session_store.py:3075–3095` to test v18→v19 upgrade without re-bootstrapping.
- `scripts/tests/test_session_store.py:TestSchemaV16IssueSessionId.test_transport_writes_session_id_from_payload` (lines 3266–3285) — `SQLiteTransport(db).send({...})` end-to-end test pattern; clone to verify `issue.completed → epic_progress_snapshots` row appears.
- `scripts/tests/test_history_reader.py` — precedent for read-side tests for new kind readers; mirror `TestCommitEventsBlock` shape with a `TestEpicProgressHistoryRead` class.
- `scripts/tests/test_set_status_cli.py:TestIssuesCLISetStatus.test_set_status_writes_new_status` (lines 17–50) — for verifying that `ll-issues epic-progress EPIC-X` actually writes a DB row. Use the autouse `_isolate_history_db` fixture (`conftest.py:519–534`) which redirects DB opens to `tmp_path/.ll/history.db`.
- `scripts/tests/test_issue_progress.py` — already covers transitive chain behavior in `compute_epic_progress` (no changes needed); reuse to seed test fixtures.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py:TestSchemaV20UsageEvents` (lines 3221–3244) — **closest precedent** for the new `TestSchemaV21EpicProgressSnapshots` class; the v20 test asserts `PRAGMA table_info(usage_events)` column-set equals the expected set. Clone for `epic_progress_snapshots`. [Agent 3 finding]
- `scripts/tests/test_session_store.py:_bootstrap_schema_at` helper (lines 3891–3911) — apply the v17/v18 historical-schema bootstrap helper for the v20→v21 upgrade test. Pattern at lines 3927–3956 (`_bootstrap_schema_at(db, 14)` → insert → `ensure_db()` → assert version + preservation + NULL columns). [Agent 3 finding]
- `scripts/tests/test_session_store.py:TestValidKindsCentralization` (lines 3409–3418) — `set(VALID_KINDS) == set(_KIND_TABLE.keys())` invariant; the v21 migration MUST add `"epic_progress"` to BOTH (or to NEITHER and rely on `_KINDLESS_TABLES`) or this test will fail. [Agent 1 finding]
- `scripts/tests/test_session_store.py` — seven `assert SCHEMA_VERSION == 20` literals (lines 1372, 1817, 1932, 1984, 2080, 3658, 3699) — every literal MUST bump to the live `SCHEMA_VERSION` value (`21`) at the v21 implementation time. Grep for `assert SCHEMA_VERSION == 20` across `scripts/tests/` and update each site. [Agent 1 finding]
- `scripts/tests/test_assistant_messages.py:88` — one `assert SCHEMA_VERSION == 20` literal; bump to `21`. [Agent 1 finding]
- `scripts/tests/test_verify_kinds.py:11-52` — `test_clean_state_returns_zero` (line 19-23) and the `epic_progress_snapshots` registration in `_KIND_TABLE`/`_KINDLESS_TABLES` together determine whether this gate passes. Confirm the table is registered in exactly one of the two lists at implementation time. [Agent 1 / Agent 2 finding]
- `scripts/tests/test_des_audit.py` (lines 27–68, especially `test_real_tree_passes` at 52–68) — the real-tree audit walks `_emit`/`event_bus.emit`/`bus.emit` sites (not direct DB writes); since `record_epic_progress_snapshot` is invoked directly from `SQLiteTransport.send()` without going through `event_bus.emit`, this gate is NOT triggered. Confirmed gate-clean path. No test changes needed unless the optional `EpicProgressSnapshotVariant` is registered, in which case the parametrized `TestVariantShape` tests (lines 74–121) automatically pick it up. [Agent 1 / Agent 3 finding]
- `scripts/tests/test_history_reader.py:TestNewEventReaders` (lines 1438–1473) — bundles `recent_commit_events`/`recent_test_runs`/etc.; clone a `TestEpicProgressHistoryRead` class here. The closest `epic_progress_history(epic_id, since=..., limit=...)` analog is `test_recent_commit_events_filters`. [Agent 3 finding]
- `scripts/tests/test_issue_history_cli.py` (lines 14–209) — `ll-history` parser/integration precedent (summary, --json, top-level flag pass-through); clone a `TestEpicVelocity` class to cover the new subcommand's parser + integration. [Agent 3 finding]
- `scripts/tests/test_issues_cli.py:5786–6012` — `TestEpicProgress*` block already covers the existing CLI; add sibling `test_epic_progress_history_*` tests for the `--history` flag. The fixture `issues_dir_with_epic_progress` (lines 5791–5809) and `issues_dir_with_epic` (lines 5786) are shared with `test_list_group_by_epic_badge` (line 6014) — confirm both fixtures survive the `--history` short-circuit at the top of `cmd_epic_progress`. [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py:68` — `("docs/reference/API.md", "SQLiteTransport", "ENH-1734")` wiring entry; add a new `("docs/reference/API.md", "record_epic_progress_snapshot", "ENH-2465")` (and a similar one for `epic_progress_history` / `epic_progress_latest` / `epic_velocity` / `EpicProgressSnapshot`) so the wiring reference doc test asserts the new symbols are documented. [Agent 1 finding]
- `scripts/tests/test_review_epic_skill.py:56-60` — `test_epic_progress_command_referenced` asserts the literal `"ll-issues epic-progress"` in the review-epic skill body. Verify whether the skill body should also reference `--history`; if so, extend the skill text and the assertion. [Agent 3 finding]
- `scripts/tests/test_issue_parser.py:1459-1460` — `("epic_progress:53", {"status_filter": _ALL_STATUSES})` call-pattern test fixture; line `53` is the call site in `cmd_epic_progress`. The new `--history` short-circuit lives at the TOP of `cmd_epic_progress` (per Implementation Step #5), so the anchor may shift downward; verify and update the line literal at the time of implementation. [Agent 3 finding]
- `scripts/tests/test_ll_loop_parsing.py:464-516` — `TestParseDuration` already covers `30d` (line 479-483) and multi-digit parsing; no new edge cases indicated for the `epic-velocity` `--since` flag. The CLI test must still cover the invalid-duration error path. [Agent 3 finding]
- `scripts/tests/test_session_store.py:test_best_effort_on_unopenable_db` (line ~4025-4029) — graceful-degradation precedent for "DB path that cannot be opened does not break the body"; clone for `record_epic_progress_snapshot` and `cmd_epic_progress` so AC#6's graceful-degrade contract is test-enforced. [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — add v19 row to the schema-versions table (lines 612–635).
- `docs/reference/API.md` — add exports for `record_epic_progress_snapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`, and `EpicProgressSnapshot`; update `SCHEMA_VERSION` from 18 to 19 (currently at line 6970 for `little_loops.session_store`, line 6527 for `little_loops.history_reader`).
- `docs/reference/CLI.md` — document `ll-issues epic-progress --history <EPIC>` (line 1515 area) and the new `ll-history epic-velocity [--since DURATION]` subcommand.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — add a section showing how to query epic velocity from `.ll/history.db` end-to-end.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (line 6837, `little_loops.history_reader` import block; lines 7278–7294, `little_loops.session_store` import block; line 7279, `SCHEMA_VERSION=19` reference; line 7346, `### record_commit_event` precedent) — extend the import blocks to surface the four new `history_reader` symbols (`EpicProgressSnapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`) and two new `session_store` symbols (`record_epic_progress_snapshot`, `backfill_epic_progress_snapshots`); bump `SCHEMA_VERSION` literal from `19` to the live value at implementation time (currently `20`, next open slot is `21`); mirror the `### record_commit_event` section as `### record_epic_progress_snapshot`. [Agent 2 finding]
- `docs/reference/CLI.md` (lines 1417, 1645, 1670–1676, 2435) — the existing `epic-progress` reference at line 1417 (currently documents `--format`), the ll-issues block at 1645 and 1670–1676 (must mention `--history <EPIC>`), and the `--kind` enumeration at line 2435 (auto-derived from `VALID_KINDS`, but the doc renders the full list — needs a new `epic_progress` row). [Agent 2 finding]
- `commands/help.md` (line 286, `ll-verify-des-audit` help text; the surrounding block already covers `ll-history` subcommands) — verify that `ll-history epic-velocity` appears in the generated help listing after the new subparser is registered. [Agent 2 finding]

### Configuration
- `.ll/ll-config.json` — `analytics.capture.*` gates already apply (snapshot writes inherit the existing `analytics.capture.issues` gate; no new config knob needed).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:815` (`SQLiteTransport` config block) — confirm the existing `analytics.capture.issues` gate is the one that flips the snapshot writer off. No new gate required, but if a future finer-grained gate is wanted (`analytics.capture.epic_progress`), this is the file to extend (mirroring `_ANALYTICS_CAPTURE_KEYS` in `scripts/little_loops/init/core.py:140`). [Agent 1 finding]

## Acceptance Criteria

- Schema migration lands; `epic_progress_snapshots` table exists.
- A child transition (`open` → `in_progress` → `done`) writes a new snapshot row for the parent EPIC each time.
- `ll-issues epic-progress <EPIC>` writes a snapshot row on every invocation.
- `history_reader.epic_progress_history(EPIC-1707)` returns the time-series.
- `ll-sprint` and `ll-history` consumers can switch from "compute on every call" to "read latest snapshot" with no observable behavior change.
- Idempotent on `(epic_id, ts)` for within-second transitions (use `INSERT OR IGNORE` with appropriate uniqueness constraint or de-dupe at write).
- Tests cover: schema migration, transition-triggered write, explicit-invocation write, read API, idempotency, graceful degradation when files missing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against `session_store.py`, `history_reader.py`, `issue_progress.py`, and `cli/issues/epic_progress.py`:_

- The 6 upstream issue producers all flow through `SQLiteTransport.send()` lines 1377–1417 (`issue_lifecycle.py` emits at lines 577, 674, 748, 841, 937, 993). AC#2 is therefore satisfied by a single transport-side write hook — no producer-side edits required.
- `EpicProgress.to_dict()` at `issue_progress.py:30–48` already carries every column the schema needs (`total = len(prog.children)`, `by_status` JSON, `percent_done` as `completion_fraction / 100`). The snapshot writer can shape `to_dict()` into the row directly without re-walking children.
- Idempotency mechanism is the v3 `idx_issue_events_dedup` pattern (lines 277–282): `(epic_id, ts)` `CREATE UNIQUE INDEX` + `INSERT OR IGNORE`. Within-second collisions discard naturally and the FTS index only fires when `cursor.rowcount` is truthy.
- Existing graceful-degradation contract is established by `record_issue_snapshot` (best-effort own-connection insert at lines 816–866) and `record_commit_event` (lines 1041–1091) — both wrap the body in `try/except sqlite3.Error` and log on failure. AC#7 inherits this contract; no new error-handling infrastructure needed.
- `compute_epic_progress()` already walks the `parent:` chain transitively (`_issue_descends_to` at lines 67–80, cycle-guarded with `seen: set`), so the snapshotter resolves grandparent→EPIC chains without extra plumbing. NOTE: `relates_to:` is intentionally excluded by `_issue_descends_to` — snapshot rollup is hierarchical only, mirroring `set_status.py:81–98` (BUG-2265 lesson).
- `_backfill_epic_progress_snapshots` is **not a verbatim clone** of `_backfill_snapshots` (`session_store.py:1538–1583`): issue_snapshots stores `body` + `frontmatter` JSON, but `epic_progress_snapshots` stores aggregated `by_status` counts only — no per-child walk inside the writer. Instead, reuse the existing `(conn, issues_dir)` parameter shape but body becomes a single `compute_epic_progress(epic_id, _load_issues(issues_dir))` call per EPIC rather than a per-file read. Backfill is invoked from the existing `ensure_db()` / `backfill_history_db()` chain — locate the precise caller at the v19 implementation site rather than reusing the snapshot backfill signature literally.
- `TestRecordEpicSnapshot` cannot clone `TestRecordIssueSnapshot` (`scripts/tests/test_session_store.py:2942–3013`) byte-for-byte: the issue_snapshot assertions cover `body` and `frontmatter` columns, but the epic snapshot has neither. Carry forward only the round-trip / idempotent / missing-file-noop assertions; replace the FTS test with an invariant that confirms `kind="epic_progress"` lands in `search_index` when `cursor.rowcount` is truthy (mirroring `record_commit_event` lines 1078–1087's `if inserted: _index(...)` shape).
- The `--history` flag on `add_epic_progress_parser` (`scripts/little_loops/cli/issues/epic_progress.py:16–35`) is in addition to the existing `--format/-f` flag and `epic_id` positional — argparse handles the mutual exclusion naturally if `--history` short-circuits before the `compute_epic_progress` call. No `--format` change is needed for `--history` output (default `text` rendering works for the time-series table).
- `scripts/little_loops/observability/schema.py` and `scripts/little_loops/observability/audit.py` consume the event-bus's `_VALID_KINDS` / `_KIND_TABLE` / `SCHEMA_VERSION` directly via the DES (Dynamic Event Schema) layer (FEAT-2274 / ENH-2475). Adding `"epic_progress"` to those constants in `session_store.py` will fail `ll-verify-des-audit` until a corresponding `epic_snapshot` (or `epic_progress`) event-emit variant is registered in `observability/schema.py`. Either (a) register the DES variant up-front (preferred — keeps the kind and the emit site in lockstep), or (b) register a passive variant that documents the kind but defers the emit-site wiring to the loop-half of EPIC-2457 (matches `commit_event`/`test_run_event` precedent).
- `scripts/little_loops/cli/issues/sequence.py` (`ll-issues sequence`) is a downstream consumer candidate not yet listed under "ll-sprint and ll-history consumers" in the Expected Behavior — it walks cross-issue dependencies and may benefit from a "since last sequence" snapshot diff for trend reporting. Out of scope for ACs but worth a follow-up issue note in the Sources section.

### Verification Log

_Consolidated by `/ll:refine-issue --auto --full-rewrite` on 2026-07-17, replacing four prior same-day verification passes (freshness re-verification, second/third/fourth-pass) that had accumulated into largely-repeated "nothing changed" confirmations. Line-number anchors have drifted repeatedly across those passes — the Integration Map and Implementation Steps above have now been rewritten in place with the current anchors rather than patched via appended corrections; this log keeps only the durable facts and the newest finding._

- **Fifth-pass finding (new): the `SQLiteTransport.send()` wiring has an early `return` the prior four passes missed.** Inside the `issue.*` branch (`session_store.py:1825`), the `if file_path and issue_id and transition in ("done", "open", "cancelled")` block (line 1858) calls `record_issue_snapshot(...)` and then `return`s at line 1864, skipping any code placed after it for exactly those three transitions. Since `done`/`cancelled` are the transitions epic velocity cares about most, the epic-snapshot call must be placed **before** that `return` (see Implementation Step 4), not simply "after `_index(...)`" as originally scoped. This is now the single highest-risk wiring detail in the issue.
- **Schema slot, as of 2026-07-17**: live `SCHEMA_VERSION = 23` (`session_store.py:211`); next open slot is `24` unless another EPIC-2457 sibling lands first. Full lineage: v17=`commit_events`/ENH-2458, v18=`test_run_events`/ENH-2459, v19=`raw_events`/ENH-2581, v20=`usage_events`/ENH-2461, v21=FEAT-2478 (OTel addenda, no new table), v22=`orchestration_runs`/ENH-2492, v23=`loop_runs`/ENH-2463 (commit `842059a6`). This slot has moved on every prior pass (v19→v20→v23→now unchanged) — always read the live constant at implementation time rather than trusting any numeric literal in this file.
- **10 `assert SCHEMA_VERSION == 23` sentinel sites confirmed** (re-grepped this pass, unchanged from the fourth pass): `test_assistant_messages.py:88`; `test_session_store.py:1372, 1817, 1932, 1984, 2080, 3661, 3702, 4450, 4596`. Bump each to the new version at implementation time; re-grep rather than trusting this count.
- **`record_commit_event` (`session_store.py:1294`) is the writer-shape template, not `record_issue_snapshot` (`session_store.py:1073`)** — the former returns `bool` from `cursor.rowcount > 0` and only FTS-indexes on real insert, matching the AC#6 idempotency contract; the latter returns `None` and unconditionally indexes.
- **`loop_runs`/ENH-2463 and `orchestration_runs`/ENH-2492 both register in `_KIND_TABLE`** (`session_store.py:229–243`), not `_KINDLESS_TABLES` (`session_store.py:252–262`, reserved for structural tables like `raw_events`/`meta`/`search_index`) — confirms `"epic_progress": "epic_progress_snapshots"` belongs in `_KIND_TABLE`.
- **DES audit is gate-clean regardless of registration.** `observability/audit.py:audit_tree` only walks `_emit(...)`/`event_bus.emit(...)`/`bus.emit(...)` call sites, not direct DB writes; `record_epic_progress_snapshot` is called directly from `SQLiteTransport.send()`, so `ll-verify-des-audit` does not require a Channel A variant. Registering `EpicProgressSnapshotVariant` in `observability/schema.py` (after `IssueSnapshotVariant`) is optional, for parity only.
- **`compute_epic_progress()` returns `EpicProgress | None`** (None for an unknown/childless EPIC ID) — the snapshot writer and `cmd_epic_progress()` must both guard for `None` rather than crash (`cmd_epic_progress()` already does this at line 55).
- **Test class to clone for the reader tests is `TestNewEventReaders`** (`tests/test_history_reader.py:1395–1546`) — a `TestCommitEventsBlock` class does not exist.
- **`_isolate_history_db` autouse fixture is at `scripts/tests/conftest.py:546–561`.**
- **Confirmed greenfield, re-verified this pass**: no matches anywhere in `scripts/little_loops/` or `scripts/tests/` for `record_epic_progress_snapshot`, `_backfill_epic_progress_snapshots`, `backfill_epic_progress_snapshots`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`, `EpicProgressSnapshot`, or table `epic_progress_snapshots`. ENH-2465 remains entirely unimplemented.

## Implementation Steps

1. Schema migration for `epic_progress_snapshots`; read the live `SCHEMA_VERSION` at `scripts/little_loops/session_store.py:211` (confirmed `23` as of 2026-07-17 — bump to the next open slot, `24` unless another EPIC-2457 sibling lands first) and append the new migration string to `_MIGRATIONS` (list spans lines 341–806), modeled on the `loop_runs`/ENH-2463 migration (the table just before the list's closing bracket at line 806): `CREATE TABLE IF NOT EXISTS epic_progress_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, epic_id TEXT NOT NULL, total_children INTEGER NOT NULL, open_count INTEGER, in_progress_count INTEGER, done_count INTEGER, deferred_count INTEGER, blocked_count INTEGER, cancelled_count INTEGER, completion_fraction REAL)` + `CREATE UNIQUE INDEX IF NOT EXISTS idx_epic_snapshots_dedup ON epic_progress_snapshots(epic_id, ts)` + two read-side indexes (`idx_epic_snapshots_epic_id`, `idx_epic_snapshots_ts`).
2. Add `"epic_progress"` to `VALID_KINDS` (lines 213–227) and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE` (lines 229–243). Also add an `"epic_progress_snapshot": ("epic_progress_snapshots", "ts")` entry to `_EXPORT_TABLE_MAP` (line 3562) and `"epic_progress_snapshot"` to `_EXPORT_DEFAULT_TABLES` (line 3578) so `ll-session export` exposes the new table — use the full `epic_progress_snapshot` key, not an abbreviated `epic_snapshot`, to avoid colliding semantically with the existing `snapshot` key in `_KIND_TABLE`.
3. Implement `record_epic_progress_snapshot(db_path, prog, ts=None) -> bool` and `_backfill_epic_progress_snapshots(conn, issues_dir)` in `session_store.py`. Use `record_commit_event()` (`session_store.py:1294`) as the writer-shape template, not `record_issue_snapshot()` (`session_store.py:1073`) — the former returns `bool` from `cursor.rowcount > 0` and only FTS-indexes on a real insert, which is exactly the idempotency contract AC#6 needs; the latter returns `None` and unconditionally indexes. Wrap the body in `try/except sqlite3.Error → logger.warning(...)` so a DB failure degrades gracefully. Use `INSERT OR IGNORE` against the `idx_epic_snapshots_dedup` index for idempotency on `(epic_id, ts)`.
4. Wire `SQLiteTransport.send()` `issue.*` branch (`session_store.py:1825`) to call the snapshotter after the existing `_index(...)` call at line 1849 — **and before the early `return` at line 1864** (inside the `if file_path and issue_id and transition in ("done", "open", "cancelled")` block, which currently returns right after calling `record_issue_snapshot(...)`). Placing the epic-snapshot call after that `return` means it silently never fires for exactly the terminal transitions (`done`/`cancelled`) epic velocity most needs — this is the single highest-risk wiring detail in this issue. Use the existing 6 `event_bus.emit(...)` sites in `issue_lifecycle.py` (lines 577, 674, 748, 841, 937, 993) as the upstream trigger — no producer-side edits needed. Inside the snapshotter, walk the parent chain via `find_nearest_epic_ancestor()` (`issue_progress.py:80`) then `compute_epic_progress(epic_id, all_issues)` (`issue_progress.py:120`), and write one row per ancestor EPIC. Wrap the call in `contextlib.suppress(Exception)`.
5. Wire `cmd_epic_progress()` at `scripts/little_loops/cli/issues/epic_progress.py:38` to call `record_epic_progress_snapshot(db, prog, ts=...)` immediately after the existing `compute_epic_progress(epic_id, all_issues)` call at line 53, inside `try/except` so a DB failure cannot break the existing CLI behavior (AC#3: "writes a snapshot row on every invocation, regardless of outcome"). Guard for `prog is None` (unknown EPIC ID) the same way the existing code does at line 55 — skip the snapshot write, do not raise.
6. Extend `history_reader.py`:
   - Add `EpicProgressSnapshot` dataclass alongside `CommitEvent` (`history_reader.py:133`), fields: `id`, `ts`, `epic_id`, `total_children`, `open_count`, `in_progress_count`, `done_count`, `deferred_count`, `blocked_count`, `cancelled_count`, `completion_fraction`.
   - `epic_progress_history(epic_id, since=None, *, limit=200, db=DEFAULT_DB_PATH) -> list[EpicProgressSnapshot]` — clone `recent_usage_events()` (`history_reader.py:683`), which already has the `since` + `limit` + `_connect_readonly()` (`history_reader.py:300`) shape this reader needs.
   - `epic_progress_latest(epic_id, *, db=DEFAULT_DB_PATH) -> EpicProgressSnapshot | None` — `ORDER BY id DESC LIMIT 1`.
   - `epic_velocity(epic_id, *, window_days=14, db=DEFAULT_DB_PATH) -> dict` — derive done-count delta per day over the window.
7. CLI surface:
   - `ll-issues epic-progress --history <EPIC>` — add `--history` flag at `add_epic_progress_parser` lines 16–35; on `--history`, call `epic_progress_history()` and print the time-series in `--format {text,json,markdown}`.
   - `ll-history epic-velocity --since 30d` — new subcommand. Reuse `parse_duration()` at `scripts/little_loops/text_utils.py:173–188`. Argparse registration follows the `--since` precedent at `scripts/little_loops/cli/loop/__init__.py:532–539`; consumption follows `cmd_history` at `scripts/little_loops/cli/loop/info.py:648–659`.
8. Update `ll-sprint` (when found) to prefer `epic_progress_latest()` over recomputing on every call. Fallback: existing on-the-fly compute via `compute_epic_progress()`.
9. Tests — mirror existing patterns:
   - `TestRecordEpicSnapshot` — clone the round-trip / idempotent / missing-file-noop assertions from `TestRecordIssueSnapshot` (`tests/test_session_store.py:2942–3013`), but replace its FTS assertion with `record_commit_event`'s `if inserted: _index(...)` shape (`session_store.py:1294`) since the epic snapshot has no `body`/`frontmatter` columns to assert on.
   - A `TestSchemaV<N>EpicProgressSnapshots` class — clone `TestSchemaV14`'s shape (schema-version assert, table-exists, dedup-index-exists, `_bootstrap_schema_at` upgrade path).
   - `TestEpicProgressHistoryRead` — clone `TestNewEventReaders` (`tests/test_history_reader.py:1395–1546`), not `TestCommitEventsBlock` (does not exist); its `test_recent_commit_events_filters` method is the closest analog.
   - Clone the "`SQLiteTransport.send()` → DB row" integration-test pattern used elsewhere in `test_session_store.py` for `TestSchemaV16IssueSessionId` to verify `issue.completed → epic_progress_snapshots` row appears **and specifically that it appears despite the early `return` noted in Implementation Step 4** — this is the one test most likely to catch a wiring regression.
   - Use the autouse `_isolate_history_db` fixture (`scripts/tests/conftest.py:546–561`) so test DB writes go to `tmp_path/.ll/history.db` and never the live `.ll/history.db`.
   - Bump every `assert SCHEMA_VERSION == 23` sentinel site to the new value — 10 sites confirmed as of 2026-07-17 (`test_assistant_messages.py:88`; `test_session_store.py:1372, 1817, 1932, 1984, 2080, 3661, 3702, 4450, 4596`); re-count at implementation time since more EPIC-2457 siblings may land first.
10. Docs — update:
    - `docs/ARCHITECTURE.md` schema-versions table (lines 612–635) — add v19 row.
    - `docs/reference/API.md` — exports for `record_epic_progress_snapshot`, `EpicProgressSnapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`. Update `SCHEMA_VERSION` reference (line 6970 for `session_store`, line 6527 for `history_reader`).
    - `docs/reference/CLI.md` — `ll-issues epic-progress --history <EPIC>` flag (around line 1515) and the new `ll-history epic-velocity` subcommand.
    - `docs/guides/HISTORY_SESSION_GUIDE.md` — section on querying epic velocity from `.ll/history.db`.
    - `CHANGELOG.md` — note the v19 schema bump (do NOT add to `[Unreleased]` — promote to a concrete `## [X.Y.Z] - DATE` section during release prep, per project feedback rule).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation; they are not surfaced by the Implementation Steps above._

11. **Update `scripts/little_loops/session_store.py:__all__` (lines 64–96)** — append `"record_epic_progress_snapshot"` and `"backfill_epic_progress_snapshots"` so `from little_loops.session_store import *` exports the new helpers (currently the issue's Implementation Steps only adds the helpers but does not register them in `__all__`).
12. **Update `scripts/little_loops/session_store.py` module docstring (lines 16–38)** — append entries for the two new public helpers (`record_epic_progress_snapshot`, `backfill_epic_progress_snapshots`) so the docstring-rendered public API surface stays in sync with `__all__`.
13. **Update `scripts/little_loops/history_reader.py` module docstring (lines 1–42)** — append `EpicProgressSnapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity` to the public API listing (no `__all__` enforcement here, but the docstring is the source of truth for "what's exported from this module").
14. **Bump `assert SCHEMA_VERSION == <N>` literals across the test suite** — as of 2026-07-17, 10 sites assert `== 23`: `scripts/tests/test_session_store.py:1372, 1817, 1932, 1984, 2080, 3661, 3702, 4450, 4596` (9 sites) and `scripts/tests/test_assistant_messages.py:88` (1 site). Bump each to the live value at implementation time; re-grep rather than trusting this count, since other EPIC-2457 siblings may land first.
15. **Register the new `epic_progress_snapshots` table in `_KIND_TABLE` OR `_KINDLESS_TABLES`** (Agent 1 / Agent 2 finding) — `scripts/little_loops/session_store.py:223-255`. Required to keep `ll-verify-kinds` (`scripts/little_loops/cli/verify_kinds.py:30-47`) and `TestValidKindsCentralization` (`scripts/tests/test_session_store.py:3409-3418`) green. Recommended: register in `_KIND_TABLE` so the `--kind epic_progress` filter is available in `ll-session search`/`recent`.
16. **Update `scripts/little_loops/cli/session.py` smoke-test** — once `"epic_progress"` is in `VALID_KINDS`, the argparse `choices=list(VALID_KINDS)` at lines 103 and 115 automatically extends the `--kind`/`--exclude` filter surfaces; no code edit required, but add a CLI smoke test that exercises both filter branches with the new kind.
17. **Extend `scripts/little_loops/__init__.py:__all__`** (Agent 1 finding, line 44) — add `record_epic_progress_snapshot` and `backfill_epic_progress_snapshots` for parity with `record_issue_snapshot` (already exported). Without this, the helpers are importable via `from little_loops.session_store import ...` but undiscoverable via `from little_loops import *`.
18. **(Optional) Register `EpicProgressSnapshotVariant` in `scripts/little_loops/observability/schema.py`** (Agent 1 / Agent 2 finding, lines 487–505 precedent; append to `DES_VARIANTS` at lines 563–634) — only for consistency with the `IssueSnapshotVariant` Channel A precedent. Gate-clean either way (the DES audit walker at `observability/audit.py:55-67, 75-111` only inspects `event_bus.emit(...)` / `_emit(...)` call sites, and the new transport-side `record_epic_progress_snapshot(self._path, prog, ts=...)` call is not an event-bus emit).
19. **Add `scripts/tests/test_wiring_reference_docs.py:68` wiring entry** for each new exported symbol (`record_epic_progress_snapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`, `EpicProgressSnapshot`) so the wiring reference-doc test catches accidental removal of the documentation.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 7 ("Epic progress over time"), §3 ranked recommendation #8
- `scripts/little_loops/issue_progress.py` — existing `ll-issues epic-progress` computation; reference for rollup logic
- `scripts/little_loops/cli/issues/epic_progress.py` — invocation site
- `scripts/little_loops/session_store.py:SQLiteTransport.send()` — shared `issue.*` emit site (sibling of ENH-2462)

## Impact

- **Priority**: P3 — historical epic-velocity data is valuable for reporting and trend analysis but does not block any other EPIC-2457 sibling or day-to-day operation; `ll-issues epic-progress` already works without it.
- **Effort**: Medium — one additive schema migration, a snapshot writer + backfill helper mirroring `record_commit_event`, two call sites (`SQLiteTransport.send()` and `cmd_epic_progress()`), three new `history_reader.py` read functions, one new CLI subcommand, plus test and doc coverage across roughly a dozen files (see Integration Map).
- **Risk**: Low — additive-only migration (new table + indexes, no changes to existing tables); the writer is best-effort (`contextlib.suppress`/`try-except`) so a DB failure cannot break `ll-issues epic-progress` or the live `issue.*` write path (AC#6). The one real risk is the shared schema-version slot: read `SCHEMA_VERSION` live at implementation time rather than trusting this issue's stale "v19" literal, since roughly ten other EPIC-2457 siblings independently claim the same "next" slot (see Scope Boundary).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` extensions |
| `docs/reference/CLI.md` | New flags |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2492, ENH-2493, ENH-2494, ENH-2495, ENH-2496,
ENH-2497, ENH-2498, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **23**
as of 2026-07-17 (v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459
done, v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done,
v21=FEAT-2478 done, v22=`orchestration_runs`/ENH-2492 done,
v23=`loop_runs`/ENH-2463 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-17; re-verified same day after a third refine-issue pass_

**Readiness Score**: 98/100 → READY TO IMPLEMENT
**Outcome Confidence**: 71/100 → moderate

### Outcome Risk Factors
- The claimed schema-version slot has kept drifting across four refine passes (v19 → v20 → v23-confirmed → now); implementation must read `SCHEMA_VERSION` live rather than trust any numeric literal already in this file, and re-verify the count of `assert SCHEMA_VERSION == 20` sentinel-test sites (10 confirmed as of the third-pass verification, all already bumped to `== 23` — re-check the live count again at implementation time since more EPIC-2457 siblings may land first).
- Line-number anchors throughout the Integration Map and Implementation Steps have drifted repeatedly and will drift again before implementation; every cited location must be re-found by symbol name, not by line number.
- The change touches roughly a dozen files across schema, writer, transport wiring, CLI, reader API, and docs — a moderately broad footprint that raises the odds of missing one wiring site despite the exhaustive Integration Map.

## Session Log
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `563ce54a-7e42-4ef2-a24a-cf41f49df8b6.jsonl` (re-run, --auto; no material state change — SCHEMA_VERSION still 23, greenfield confirmed, no corrections found, scores unchanged)
- `/ll:refine-issue` - 2026-07-17T22:35:40 - `759b7693-5571-43e2-a1fc-e43c04c1acd8.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `6e4381b0-87b6-48bc-9798-c6bc7acb6f07.jsonl` (re-run, --auto; no material state change since fourth-pass verification — SCHEMA_VERSION still 23, greenfield confirmed, scores unchanged)
- `/ll:refine-issue` - 2026-07-17T22:27:26 - `8772a523-963c-42ff-914e-ba7e76e66ae9.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `06ae8f78-6ab7-4555-9053-48494f8a06c0.jsonl`
- `/ll:refine-issue` - 2026-07-17T22:23:15 - `1f08699e-b349-4765-9892-7b5966b4ab34.jsonl`
- `/ll:confidence-check` - 2026-07-17T00:00:00Z - `e21f230e-d50b-4910-97e1-e04c1dec7cb7.jsonl`
- `/ll:format-issue` - 2026-07-17T22:17:55 - `3e35f670-b4c4-4e57-970e-9ddd156140fa.jsonl`
- `/ll:wire-issue` - 2026-07-16T21:18:38 - `4efa27c8-3195-440e-9c27-a5fc0d9a60a1.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:48:28 - `a2829a96-dd89-45b5-a3b2-6f21828d058e.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:14:06 - `bdbb2eb5-2bad-4d5c-8b9b-7682c9ce3a55.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:47 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T07:23:03 - `7ac73f41-a98d-4b31-aab9-5d2f0701c0a0.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:25:57 - `b67f0e2c-461a-43e1-8ce2-322030b708c5.jsonl`
- audit - 2026-07-06 - Updated stale schema-version reference ("v15+" → v19+; v15–v18 were consumed by ENH-2460/2462/2458/2459). Verified `issue_progress.py` and `cli/issues/epic_progress.py` exist.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
