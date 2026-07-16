---
id: ENH-2465
title: Periodic epic-progress snapshots into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
refined_at: "2026-07-07T00:00:00Z"
refined_by: refine-issue
labels:
  - enhancement
  - history-db
  - epics
  - captured
---

# ENH-2465: Periodic epic-progress snapshots into history.db

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
- `scripts/little_loops/session_store.py` — bump `SCHEMA_VERSION = 18` → `19` (line 102); append `"epic_progress"` to `_VALID_KINDS` (lines 104–118) and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE` (lines 119–130); append v19 migration string (after line 545); add `record_epic_progress_snapshot()`, `_backfill_epic_progress_snapshots()`, and `backfill_epic_progress_snapshots()` helpers mirroring the `record_issue_snapshot` / `_backfill_snapshots` / `backfill_snapshots` triple at lines 816–866, 1538–1583, 2418–2438; wire into `SQLiteTransport.send()` `issue.*` branch (lines 1377–1417) immediately after the `_index(...)` call at line 1408 and before the content-snapshot block at 1409.
- `scripts/little_loops/history_reader.py` — add `EpicProgressSnapshot` dataclass to the dataclass block (alongside `CommitEvent` at lines 125–137); add `epic_progress_history(epic_id, since=None, *, limit=200, db=DEFAULT_DB_PATH)`, `epic_progress_latest(epic_id, *, db=DEFAULT_DB_PATH)`, and `epic_velocity(epic_id, window_days=14, *, db=DEFAULT_DB_PATH)` reading-side functions following the `related_issue_events` shape at lines 370–404 (id-filterable, since-bounded, limit-bounded, read-only via `_connect_readonly`, graceful degrade to `[]`).
- `scripts/little_loops/cli/issues/epic_progress.py` — call `record_epic_progress_snapshot(db, prog, ts=...)` at the end of `cmd_epic_progress()` (after line 58) inside a `try/except` so a DB write failure cannot break the CLI; add an `--history` flag to `add_epic_progress_parser()` (lines 16–35) that re-uses the new `epic_progress_history()` reader.
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

_Freshness re-verification (2026-07-16, `/ll:refine-issue --auto`) — architecture confirmed intact; all cited symbols still exist but **line-number anchors throughout the Integration Map / Implementation Steps have drifted forward substantially — locate by symbol name, not by line**:_

- **Kind-constant renamed**: the issue references `_VALID_KINDS`, but the current constant is the *public* `VALID_KINDS` (`session_store.py:209`, tuple form) — add `"epic_progress"` there, not to a private `_VALID_KINDS`. `_KIND_TABLE` is unchanged (now `session_store.py:223`).
- **Schema slot**: `SCHEMA_VERSION = 20` (`session_store.py:207`), confirming the Scope Boundary note. Read the live constant at implementation time; the next-open slot is v21+ unless another sibling lands first.
- **Drifted anchors (current → was)**: `record_issue_snapshot` 1001 (was 816), `record_commit_event` 1222 (was 1041), `_backfill_snapshots` 1728 (was 1538), `related_issue_events` 395 (was 370), `_EXPORT_TABLE_MAP` 3304 (was 2791), `_EXPORT_DEFAULT_TABLES` 3318 (was 2804). In `issue_progress.py`: `compute_epic_progress` 120 (was 83), `_issue_descends_to` 104 (was 67), `EpicProgress.to_dict` 30 (unchanged). `CommitEvent` (`history_reader.py:125`) and `cmd_epic_progress` / `add_epic_progress_parser` (`cli/issues/epic_progress.py:38` / `16`) are unchanged.

### Second-pass verification (2026-07-16, `/ll:refine-issue --auto` run 2)

_Added by `/ll:refine-issue` — corrections and refinements on top of the first 2026-07-16 pass above:_

- **Migration slot is `v21`, not `v19`** — Implementation Step #1 still says "bump 18→19"; the live `SCHEMA_VERSION = 20` is confirmed (`session_store.py:207`) and v21 is the next open slot. Same correction flows to stale "18→19" callouts in Implementation Steps #2 and #9 and the Acceptance Criteria "schema migration lands" line. Always read `SCHEMA_VERSION` at implementation time; never trust the v19 literal in this file. Sibling EPIC-2457 migrations confirmed landed: v17=`commit_events`/ENH-2458 (lines 626-645), v18=`test_run_events`/ENH-2459 (lines 646-669), v19=`raw_events`/ENH-2581 (lines 670-708), v20=`usage_events`/ENH-2461 (lines 709-733).
- **`record_commit_event` is the better writer template than `record_issue_snapshot`** (despite the original Implementation Step #3 saying "clone `record_issue_snapshot` verbatim"). The latter returns `None` and *unconditionally* calls `_index(...)`; the former returns `bool` indicating `cursor.rowcount > 0` and only FTS-indexes when the row actually inserted (lines 1222-1272). The dedup-index + `if inserted: _index(...)` shape is exactly what AC#6 mandates — it avoids FTS-row duplication on within-second transitions. Adopt `record_commit_event` as the shape and have `record_epic_progress_snapshot()` return `bool` so the transport caller can decide whether to FTS-index.
- **`__all__` export list to update** at `session_store.py:61-93` — already exports `backfill_snapshots`, `record_issue_snapshot`, `record_commit_event`, `record_test_run_event`. New public helpers `record_epic_progress_snapshot` and `backfill_epic_progress_snapshots` must be appended or they will be importable but undiscoverable via `from little_loops.session_store import *`.
- **DES audit gate correction**: the prior freshness-re-verification note claiming `ll-verify-des-audit` would fail is **incorrect**. `observability/audit.py:audit_tree` only walks `_emit(...)` / `event_bus.emit(...)` / `bus.emit(...)` call sites (lines 55-67 regex + lines 75-111 AST) and matches their `event=` literal against `DES_VARIANT_TYPES`. ENH-2465 writes directly to `epic_progress_snapshots` from `SQLiteTransport.send()` via a helper call — no event-bus emit. The audit does NOT enforce Channel A variant registration; Channel A variants like `IssueSnapshotVariant`, `CommitEventVariant`, `TestRunEventVariant` are registered defensively for parity with `DES_VARIANTS` tuple, but a missing entry does not fail the gate. Two valid implementations: (a) skip DES registration entirely (simplest, gate-clean), or (b) register an `EpicProgressSnapshotVariant(DESVariant)` with `type: Literal["epic_progress_snapshot"] = "epic_progress_snapshot"` in `observability/schema.py`'s Channel A block (lines 619-633, after `IssueSnapshotVariant`) for consistency with the existing precedent. Either is gate-clean.
- **`_EXPORT_TABLE_MAP` key correction**: Implementation Step #2 says `"epic_snapshot": ("epic_progress_snapshots", "ts")` — the existing convention is `issue_snapshot` → `issue_snapshots` (mirror it as `epic_progress_snapshot` → `epic_progress_snapshots`). Use the full `epic_progress_snapshot` key, not the abbreviated `epic_snapshot`, which would semantically collide with the existing `snapshot` key in `_KIND_TABLE`. `_EXPORT_TABLE_MAP` is at lines 3304-3316; `_EXPORT_DEFAULT_TABLES` at 3318-3329 (both the previous Implementation Step #2 line refs of 2791-2802 and 2804-2814 are stale).
- **Test class to clone is `TestNewEventReaders`, not `TestCommitEventsBlock`** — the latter does not exist. The former (`scripts/tests/test_history_reader.py:1395-1546`) bundles commit/test-run/skill/usage reader tests and is the correct mirror for `TestEpicProgressHistoryRead`. Its `test_recent_commit_events_filters` method is the closest analog for `epic_progress_history(epic_id, since=..., limit=...)`.
- **`_isolate_history_db` autouse fixture is at `scripts/tests/conftest.py:546-561`**, not the previously-cited 519-534. The fixture sets `LL_HISTORY_DB=tmp_path/.ll/history.db` and `monkeypatch` cleans up after the test. Use it for every test that touches `record_epic_progress_snapshot` or `epic_progress_history`.
- **`compute_epic_progress()` returns `EpicProgress | None`** — None when the EPIC ID is unknown / has no children. The snapshot writer must guard for `None` (skip the row, `logger.warning(...)`) so a misspelled EPIC ID in `event.get("issue_id")` does not crash the live-write transport. Mirrors the existing `cmd_epic_progress()` behavior at `cli/issues/epic_progress.py:54` (where `prog is None` short-circuits the output branches).
- **`_TERMINAL_STATUSES = {"done", "cancelled"}`** is defined in `issue_progress.py` (referenced inside `compute_epic_progress`) — reuse for `completion_fraction` derivation if the snapshot writer chooses to compute it locally rather than read `EpicProgress.percent_done / 100`. Both shapes are acceptable; the latter (read from `EpicProgress`) is consistent with the "do not reimplement the walk" principle.
- **`_issue_descends_to` lives at `issue_progress.py:104-117`** (was 67-80 in the prior Implementation Step #4 reference; verify at implementation time). `find_nearest_epic_ancestor` at lines 80-101 is a sibling helper that returns the *closest* EPIC ancestor — useful inside `SQLiteTransport.send()` `issue.*` branch where the direct `parent` may not itself be an EPIC; the snapshot writer should walk transitively up the parent chain until it finds an EPIC, then emit one row per ancestor EPIC.
- **`recent_usage_events()` (history_reader.py:549-593) and `aggregate_usage()` (lines 596-648) are the closest precedent** for `epic_progress_history()` and a future `epic_progress_velocity()` reader. They share the `since` + `limit` + `_connect_readonly` (lines 256-270) + `_row_to_dataclass` (lines 273-277) + `try/except sqlite3.Error → []` shape. Clone `recent_usage_events` in preference to `recent_commit_events` because it covers the same multi-clause WHERE + ORDER BY DESC + limit shape and adds the `since` parameter the epic reader needs.
- **`cli/issues/__init__.py:813`** registers `add_epic_progress_parser`; **lines 877-878** dispatch `cmd_epic_progress` (the prior Implementation Step said line 857; the file has shifted). The new `--history` flag requires NO dispatch change — `cmd_epic_progress` already handles all flags via argparse; adding a mutually-exclusive short-circuit at the top of the function is sufficient.
- **`hooks/post_commit.py`** imports `record_commit_event` as a direct-write hook reference (analogous role); ENH-2465 does NOT need a new hook because the snapshot writes flow through the existing `SQLiteTransport.send()` `issue.*` branch (`session_store.py:1567-1607`), not via a hook callback. The transport's existing side-effect pattern (`conn.commit() + record_issue_snapshot(self._path, str(issue_id), transition, str(file_path))` for the `(done | open | cancelled)` subset) is the exact model to clone.
- **Confirmed no `epic_progress` symbols exist anywhere** — `record_epic_progress_snapshot`, `_backfill_epic_progress_snapshots`, `backfill_epic_progress_snapshots`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`, `EpicProgressSnapshot`, `epic_progress_snapshots` table are all absent. ENH-2465 is greenfield for this surface area.

## Implementation Steps

1. Schema migration for `epic_progress_snapshots`; bump `SCHEMA_VERSION` from `18` to `19` at `scripts/little_loops/session_store.py:102`. Append the v19 migration string to `_MIGRATIONS` (list at lines 208–545), modeled on v14 (lines 437–450): `CREATE TABLE IF NOT EXISTS epic_progress_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, epic_id TEXT NOT NULL, total_children INTEGER NOT NULL, open_count INTEGER, in_progress_count INTEGER, done_count INTEGER, deferred_count INTEGER, blocked_count INTEGER, cancelled_count INTEGER, completion_fraction REAL)` + `CREATE UNIQUE INDEX IF NOT EXISTS idx_epic_snapshots_dedup ON epic_progress_snapshots(epic_id, ts)` + two read-side indexes (`idx_epic_snapshots_epic_id`, `idx_epic_snapshots_ts`).
2. Add `"epic_progress"` to `_VALID_KINDS` (line 104) and `"epic_progress": "epic_progress_snapshots"` to `_KIND_TABLE` (line 119). Also add an `"epic_snapshot": ("epic_progress_snapshots", "ts")` entry to `_EXPORT_TABLE_MAP` (lines 2791–2802) and `epic_snapshot` to `_EXPORT_DEFAULT_TABLES` (lines 2804–2814) so `ll-session export` exposes the new table.
3. Implement `record_epic_progress_snapshot(db_path, prog, ts=None)` and `_backfill_epic_progress_snapshots(conn, issues_dir)` in `session_store.py`, cloning `record_issue_snapshot` (lines 816–866) and `_backfill_snapshots` (lines 1538–1583) verbatim. Wrap the body in `try/except sqlite3.Error → logger.warning(...)` so a DB failure degrades gracefully per the AC#6 graceful-degradation contract. Use `INSERT OR IGNORE` against the `idx_epic_snapshots_dedup` index for idempotency on `(epic_id, ts)`. Optionally FTS-index only when `cursor.rowcount` is truthy (mirroring `record_commit_event` at lines 1078–1087).
4. Wire `SQLiteTransport.send()` `issue.*` branch (lines 1377–1417) to call the snapshotter after the existing `_index(...)` call at line 1408. Use the existing 6 `event_bus.emit(...)` sites in `issue_lifecycle.py` (lines 577, 674, 748, 841, 937, 993) as the upstream trigger — no producer-side edits needed. Inside the snapshotter, read the `.issues/` issue files, walk the parent chain via `compute_epic_progress(epic_id, all_issues)` at `issue_progress.py:83–147`, and write one row per ancestor EPIC. Wrap the call in `contextlib.suppress(Exception)`.
5. Wire `cmd_epic_progress()` at `scripts/little_loops/cli/issues/epic_progress.py:38–131` to call `record_epic_progress_snapshot(db, prog, ts=...)` immediately after the existing `compute_epic_progress(epic_id, all_issues)` call at line 54, inside `try/except` so a DB failure cannot break the existing CLI behavior (AC#3: "writes a snapshot row on every invocation, regardless of outcome").
6. Extend `history_reader.py` (lines 1–42 docstring lists the public API):
   - Add `EpicProgressSnapshot` dataclass to the dataclass block, fields: `id`, `ts`, `epic_id`, `total_children`, `open_count`, `in_progress_count`, `done_count`, `deferred_count`, `blocked_count`, `cancelled_count`, `completion_fraction`.
   - `epic_progress_history(epic_id, since=None, *, limit=200, db=DEFAULT_DB_PATH) -> list[EpicProgressSnapshot]` — clone `related_issue_events` at lines 370–404.
   - `epic_progress_latest(epic_id, *, db=DEFAULT_DB_PATH) -> EpicProgressSnapshot | None` — `ORDER BY id DESC LIMIT 1`.
   - `epic_velocity(epic_id, *, window_days=14, db=DEFAULT_DB_PATH) -> dict` — derive done-count delta per day over the window.
7. CLI surface:
   - `ll-issues epic-progress --history <EPIC>` — add `--history` flag at `add_epic_progress_parser` lines 16–35; on `--history`, call `epic_progress_history()` and print the time-series in `--format {text,json,markdown}`.
   - `ll-history epic-velocity --since 30d` — new subcommand. Reuse `parse_duration()` at `scripts/little_loops/text_utils.py:173–188`. Argparse registration follows the `--since` precedent at `scripts/little_loops/cli/loop/__init__.py:532–539`; consumption follows `cmd_history` at `scripts/little_loops/cli/loop/info.py:648–659`.
8. Update `ll-sprint` (when found) to prefer `epic_progress_latest()` over recomputing on every call. Fallback: existing on-the-fly compute via `compute_epic_progress()`.
9. Tests — mirror existing patterns:
   - `TestRecordEpicSnapshot` — clone `TestRecordIssueSnapshot` at `tests/test_session_store.py:2942–3013` (round-trip / idempotent / graceful-degrade / FTS).
   - `TestSchemaV19EpicProgressSnapshots` — clone `TestSchemaV14` at lines 2872–2987. Use `_bootstrap_schema_at(db, 18)` at lines 3075–3095 to test v18→v19 upgrade.
   - `TestEpicProgressHistoryRead` — clone `TestCommitEventsBlock` at `tests/test_history_reader.py:1379–1504`.
   - `TestSchemaV16IssueSessionId.test_transport_writes_session_id_from_payload` (lines 3266–3285) is the closest "SQLiteTransport.send() → DB row" integration test pattern.
   - Use the autouse `_isolate_history_db` fixture (`scripts/tests/conftest.py:519–534`) so test DB writes go to `tmp_path/.ll/history.db` and never the live `.ll/history.db`.
10. Docs — update:
    - `docs/ARCHITECTURE.md` schema-versions table (lines 612–635) — add v19 row.
    - `docs/reference/API.md` — exports for `record_epic_progress_snapshot`, `EpicProgressSnapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity`. Update `SCHEMA_VERSION` reference (line 6970 for `session_store`, line 6527 for `history_reader`).
    - `docs/reference/CLI.md` — `ll-issues epic-progress --history <EPIC>` flag (around line 1515) and the new `ll-history epic-velocity` subcommand.
    - `docs/guides/HISTORY_SESSION_GUIDE.md` — section on querying epic velocity from `.ll/history.db`.
    - `CHANGELOG.md` — note the v19 schema bump (do NOT add to `[Unreleased]` — promote to a concrete `## [X.Y.Z] - DATE` section during release prep, per project feedback rule).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation; they are not surfaced by the Implementation Steps above._

11. **Update `scripts/little_loops/session_store.py:__all__` (lines 61–93)** — append `"record_epic_progress_snapshot"` and `"backfill_epic_progress_snapshots"` so `from little_loops.session_store import *` exports the new helpers (currently the issue's Implementation Steps only adds the helpers but does not register them in `__all__`).
12. **Update `scripts/little_loops/session_store.py` module docstring (lines 16–38)** — append entries for the two new public helpers (`record_epic_progress_snapshot`, `backfill_epic_progress_snapshots`) so the docstring-rendered public API surface stays in sync with `__all__`.
13. **Update `scripts/little_loops/history_reader.py` module docstring (lines 1–42)** — append `EpicProgressSnapshot`, `epic_progress_history`, `epic_progress_latest`, `epic_velocity` to the public API listing (no `__all__` enforcement here, but the docstring is the source of truth for "what's exported from this module").
14. **Bump `assert SCHEMA_VERSION == 20` literals across the test suite** (Agent 1 finding — 8 sites total):
    - `scripts/tests/test_session_store.py:1372, 1817, 1932, 1984, 2080, 3658, 3699` (7 sites)
    - `scripts/tests/test_assistant_messages.py:88` (1 site)
    These are sentinel tests that assert the current schema version is `20`; bump each to the live value at implementation time (currently the next open slot is `21`).
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
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Session Log
- `/ll:wire-issue` - 2026-07-16T21:18:38 - `4efa27c8-3195-440e-9c27-a5fc0d9a60a1.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:48:28 - `a2829a96-dd89-45b5-a3b2-6f21828d058e.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:14:06 - `bdbb2eb5-2bad-4d5c-8b9b-7682c9ce3a55.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:47 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T07:23:03 - `7ac73f41-a98d-4b31-aab9-5d2f0701c0a0.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:25:57 - `b67f0e2c-461a-43e1-8ce2-322030b708c5.jsonl`
- audit - 2026-07-06 - Updated stale schema-version reference ("v15+" → v19+; v15–v18 were consumed by ENH-2460/2462/2458/2459). Verified `issue_progress.py` and `cli/issues/epic_progress.py` exist.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
