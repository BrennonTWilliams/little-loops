---
id: BUG-3517
type: BUG
title: 'll-session backfill under-captures loop history: non-recursive glob misses
  .history state files'
priority: P2
status: done
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T22:27:37Z'
completed_at: '2026-09-20T00:15:17Z'
labels:
- session-store
- backfill
confidence_score: 95
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3517: ll-session backfill under-captures loop history: non-recursive glob misses .history state files

## Summary

`ll-session backfill` silently under-captures loop history. `_backfill_loops` (session_store/writers.py) reads FSM state with a non-recursive `glob("*.json")`, so it catches the currently-running loops in `.loops/.running/*.state.json` but misses the completed runs stored as `.loops/.history/<run>/state.json` — approximately 92% of state files are omitted from this backfill in the 2026-09-19 local inventory. This is not a measure of total loop-history or analytics loss.

## Current Behavior

`_backfill_loops` iterates `directory.glob("*.json")` over `.loops/.running` and `.loops/.history`:

- `.loops/.running/*.state.json` → caught (112 files on the little-loops repo).
- `.loops/.history/*/state.json` → missed: each completed run is a per-run subdirectory (`<timestamp>-<loop-name>/state.json`), and the non-recursive glob never descends into them.

The plain `INSERT` also duplicates rows and search entries on every re-run. The existing snapshot stores only `(loop_name, current_state, ts)` with `transition="backfill"` and `retries=None`; expanding it to captured outputs or execution sequences is outside this fix.

## Expected Behavior

Ingest state snapshots from `.running/*.json`, flat `.history/<run_id>-<loop_name>/state.json`, and legacy `.history/<loop_name>/<run_id>/state.json`. Repeating the backfill over unchanged snapshots inserts no additional `loop_events` or `search_index` rows and returns `counts["loops"] == 0`.

The contract is **snapshot idempotency**, not one row per run. Preserve raw `current_state` with the existing `state` fallback; do not convert it through `map_final_status()`. A running snapshot with an advancing timestamp or changed state may add a row. Its later archive may also add a row if the stored snapshot differs; an identical stored snapshot is suppressed across layouts.

### Scope Boundaries

- No schema migration, unique index, captured-output persistence, iteration persistence, or full state-sequence reconstruction. A state file contains current state, not an execution sequence.
- Existing duplicate `loop_events` and search entries remain untouched. Coordinated cleanup requires a separate change with validated identity; grouping only by `(loop_name, ts)` can merge different runs, especially with empty timestamps, and the tables have no direct row linkage.
- Historical `loop_runs` backfill and richer execution-history persistence are separate follow-up candidates, not deliverables of BUG-3517.
- Snapshot identity is limited to the fields available in `loop_events`: `(loop_name, ts, state)` scoped to `transition='backfill'` and `retries IS NULL`. Use a NULL-safe state comparison. Distinct runs with identical stored fields cannot be distinguished by this schema; this limitation is accepted here. Do not present the check as stable run identity.

## Acceptance Criteria

1. All three layouts are covered, while the existing `.running/docs-sync.json` fixture remains supported. Malformed JSON, non-object JSON, and empty files are skipped.
2. An unchanged second backfill inserts zero event and search rows; `counts["loops"]` counts newly inserted event rows only. Existing duplicates are neither multiplied nor deleted.
3. Live rows do not suppress backfill snapshots, even with the same loop name, timestamp, and state. Changed timestamps or states can produce new snapshots; unchanged archives match the stored snapshot across layouts.
4. Prefer JSON `loop_name`. Without it, strip `.state.json` from running filenames (use the stem for plain `.json`), parse flat archive folders with `_parse_run_folder`, and use the enclosing loop directory for legacy archives. Running filename fallback is best effort because filenames may contain instance IDs.
5. Raw `current_state` and the existing `state` fallback are retained, including NULL when neither supplies a value. Captured outputs and iteration remain out of scope; docs distinguish these snapshots from live `loop_complete` status buckets.
6. Schema version and manifest remain unchanged. The implementation passes the full local suite (`python -m pytest scripts/tests/`), `ruff check scripts/`, and `python -m mypy scripts/little_loops/`.

## Implementation Steps

1. Add deterministic discovery for `.running/*.json` and both archive layouts; implement the layout-specific loop-name fallbacks.
2. Add the Option B snapshot pre-existence check before inserting either event or search rows, retaining raw state and returning newly inserted event counts.
3. Extend lifecycle tests for layouts, naming, malformed input, unchanged re-runs, changed running snapshots, cross-layout archives, live-row non-collision, NULL/empty timestamps, and preservation of existing duplicates.
4. Check `cli/session.py` count wording against rows-inserted semantics; change wording only if needed. Update the documentation and stale observability docstring listed below.
5. Run the focused lifecycle/schema/writer tests during development, then the full local suite and lint/type gates before implementation completion.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Derive `loop_name` in `_backfill_loops` (`writers.py:3371`) using the JSON field first, then the layout-specific fallbacks in Acceptance Criteria; the current generic stem fallback misnames both archives and running files
- Keep `.running` matching `*.json` (not `*.state.json`) so the existing `test_backfill_loops` fixture (`docs-sync.json`) still passes
- Gate the `_index` call (`writers.py:3379`) on the pre-existence check so re-runs add no `search_index` rows
- Update `tests/test_session_store_lifecycle.py` — extend `TestBackfill.test_backfill_loops`; add `TestBackfillLoopsLayouts` (three layouts, double-run idempotency, live-row non-collision, malformed file)
- Check `cli/session.py:main_session` headline and loop count wording against the selected rows-inserted semantics; adjust only if needed
- Update `docs/reference/EVENT-SCHEMA.md`, `docs/reference/CLI.md` (`ll-session backfill` loop-history wording) and fix the stale `_backfill_loop_events` docstring in `observability/schema.py:755`
- Add CHANGELOG entry in a concrete version section during release prep

## Impact

- **Priority**: P2 - Archived snapshots are absent from loop-event search/recent results. On 2026-09-19, this repo used `events.transports: ["socket"]` and had no live `loop_events` rows. Separately, `loop_runs` already contained 1,289 summaries beginning 2026-07-17; run analytics read that table (`history_reader/runs.py`). Older runs lack that summary coverage, but repairing `loop_runs` is separate from this fix.
- **Effort**: Small - One backfill function plus a discovery helper, tests, and documentation
- **Risk**: Low - Backfill-only scoped pre-existence check; no schema change or deletion. Stored snapshot identity has the documented collision limits
- **Breaking Change**: No

## Steps to Reproduce

1. On a repo with completed loop history, run `ll-session backfill`.
2. Inspect backfilled snapshots and their search anchors against state files in `.running` and both archive layouts. Raw event counts alone are misleading because existing duplicates and live events can inflate them.
3. Observe that only `.running` state is ingested; `.history` subdirectories are skipped.

## Root Cause

`directory.glob("*.json")` is non-recursive, but completed runs live one or two directories deeper in the flat and legacy-nested archive layouts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Confirmed at `session_store/writers.py:_backfill_loops` (line 3357): `sorted(directory.glob("*.json"))` over `(".running", ".history")`. `.running/<stem>.state.json` matches; completed runs are archived by `StatePersistence.archive_run` (`fsm/persistence.py`) into `.history/<run_id>-<loop_name>/state.json` — one directory deeper — so the glob never sees them. Older archives use a legacy nested layout `.history/<loop_name>/<run_id>/state.json` (`list_run_history`, `persistence.py:1571`), also missed. Verified local inventory on 2026-09-19: 1,294 archived `state.json` files (1,258 flat and 36 legacy-nested) versus 112 `.running/*.state.json` files; approximately 92% of these state files are omitted by the glob.
- No flat `.loops/.history/*.json` files exist and nothing writes that shape, so `.history` iteration in the current code is dead.
- Secondary defects confirmed: the insert is a plain `INSERT INTO loop_events(ts, loop_name, state, transition, retries)` with `transition="backfill"`, `retries=None`; `loop_events` (`schema.py`, `_MIGRATIONS[0]`) has no UNIQUE key or index, so every `backfill()` re-inserts every file and re-adds a `search_index` row via `_index`. `captured`, `iteration`, `status` are never read. The current count increments once per successfully parsed object and unconditional insert; after dedup it must increment only for newly inserted rows. Local database inspection on 2026-09-19 found 240 backfill event rows with 118 distinct `(loop_name, ts)` pairs, plus 240 loop search entries with 118 distinct `(content, kind, ref, anchor, ts)` tuples. These observations do not establish a safe deletion key for arbitrary databases.

## Proposed Solution

**Selected: Option B — schema-preserving, backfill-scoped snapshot pre-existence check.**

Discover the three supported layouts, normalize the existing snapshot fields, and check for a row matching `(loop_name, ts, state)` with `transition='backfill'` and `retries IS NULL`. Compare state with SQLite `IS ?` so NULL snapshots match. Insert the event and call `_index` only when the snapshot is absent; keep them in the caller's transaction and increment the returned count only on insertion.

### Decision Rationale

Option A (a DB-level unique index and `INSERT OR IGNORE`) remains rejected: the current schema has no stable per-run key, and a broad unique index can collide with legitimate live events. Option B needs no migration, schema-version bump, or manifest regeneration. Including state in the scoped comparison avoids suppressing a changed state merely because its timestamp is unchanged; it does not solve indistinguishable runs.

Do not use `search_index.anchor` alone as the dedup key. Although `_index` already stores the state-file path there, `anchor` and `kind` are FTS5 `UNINDEXED` columns; equality lookup scans rather than providing the claimed indexed performance improvement. A `.running/<loop_name>.state.json` path can also be reused by later runs (`StatePersistence` uses `instance_id or loop_name`). Anchor-only dedup would suppress later runs and changed snapshots. Archive moves are not stable per-run identity either.

The scoped event lookup is also unindexed and can scan existing rows per file. This bounded implementation accepts that cost; do not claim an indexing improvement. Stable run identity, concurrent-writer uniqueness, and coordinated historical duplicate repair require separate design. Do not delete historical rows or their search entries in this fix.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Files to modify: `scripts/little_loops/session_store/writers.py` (`_backfill_loops` and discovery helper); `scripts/tests/test_session_store_lifecycle.py` (`TestBackfill.test_backfill_loops`, line 73, covers only a single flat state file under `.running`).
- Sole caller: `session_store/lifecycle.py:1102` (`counts["loops"] = _backfill_loops(conn, loops_dir)`, guarded by `loops_dir.is_dir()`); `cli/session.py` (~line 794) prints `counts['loops']`. `backfill_incremental` deliberately does not backfill loops. No `_iter_loop_state_files` helper exists yet.
- Other `loop_events` writer: `SQLiteTransport.send` (`writers.py:~2940`) — many rows per run, `transition` = event type, plain INSERT. `loop_events` has no `run_id` column. Readers: `queries.py` (`_EXPORT_TABLE_MAP["loop_event"]`), `recent(kind="loop")`, `search_index` kind `loop`; `history_reader/sessions.py` does not read it. `loop_events` is excluded from `_REBUILD_TABLES` (`lifecycle.py:937`).
- Conventions in force:
  - Every sibling backfill dedupes with `INSERT OR IGNORE` backed by a UNIQUE column/index, and gates the `_index` FTS row on `cursor.rowcount` — evidence: `_backfill_commit_events` (`writers.py:972`), `record_loop_run_summary` (`writers.py:1834`), `_backfill_subagent_runs`, `_backfill_issues_and_snapshots`. `_backfill_loops` is the lone exception.
  - Historical context only; not part of selected Option B: schema change = new string appended to `_MIGRATIONS` with a `# vNN (ISSUE-ID)` comment, `SCHEMA_VERSION` bumped in step (`test_schema_version_matches_migrations_length`), `schema_manifest.json` regenerated (`test_schema_manifest_matches_checked_in_file`), and literal `assert SCHEMA_VERSION == 52` occurrences in tests (`test_session_store_writers.py`, `test_assistant_messages.py`, ~20 in `test_session_store_schema.py`) updated.
  - Historical context only; not a cleanup instruction for this fix: a unique index over a table that may already hold duplicates must dedupe first (v43, BUG-3241, `schema.py` ~1047-1116: `DELETE ... WHERE rowid NOT IN (SELECT MIN(rowid) ... GROUP BY ...)` then `CREATE UNIQUE INDEX`); a bare create raises `IntegrityError` and makes `ensure_db()` fail at startup. NULLs are distinct in a UNIQUE index but equal in `GROUP BY`, so nullable key columns need `IS NOT NULL` guards. Migration tests: `TestSchemaV43IndexRepair` (`test_session_store_schema.py:2494`).
  - Run-folder naming is parsed by `_parse_run_folder` / `_RUN_FOLDER` (`persistence.py:127-131`); a duplicate regex `_HISTORY_RUN_RE` lives in `cli/logs.py:53`. Existing walkers (`list_run_history`, `next_loop._scan_history`, `logs._collect_loop_runs`) each handle flat and legacy-nested layouts; none yields all loops' state files.
  - Idempotency tests call `backfill()` twice and assert both returned counts and `recent(db, kind=...)` row count (`TestBackfillDedup.test_double_backfill_produces_single_row`, line 569). Two count conventions coexist: rows-inserted (commits) vs files-processed (learning tests).
- Constraint: `test_backfill_missing_sources_is_noop` (lifecycle tests line 112) asserts the exact `counts` dict with `==`; adding a count key breaks it.
- Constraint: `(loop_name, ts)` alone is not a safe unique key — live `loop_events` rows for one loop can share a `ts` across different `transition`/`state` values, and `ts` may be `""` when a state file lacks `updated_at`/`started_at`. State files carry `status` (`running`/`interrupted`/completed…), so a `.running` file and its later `.history` archive describe the same run at different times and produce different `ts`.
- Documentation: `docs/reference/CLI.md` (`ll-session backfill`, lines ~4077, 4149-4163, 4241-4244), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md` mention `loop_events`.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py` — line 44 imports `_backfill_loops`; only call is `backfill()` (line 1102). `session_store/__init__.py` does not re-export it, and no test imports it by name (reached only via `backfill()`) [Agent 1]
- `scripts/little_loops/cli/session.py:main_session` — `total = sum(counts.values())` (~791) feeds the headline "Backfilled {total} rows"; changing `counts["loops"]` from files-processed to rows-inserted (or ingesting ~1294 more files) changes that total. Keep `_backfill_loops -> int` [Agent 2]
- `scripts/little_loops/session_store/writers.py:SQLiteTransport.send` (~2940-2955) — live writer into the same `loop_events`/`search_index` kind `loop`; source of the live rows the scoped `transition='backfill'` check must not collide with [Agent 1, 2]
- `scripts/little_loops/session_store/queries.py` (`recent`, ~76-80; `_EXPORT_TABLE_MAP["loop_event"]`, ~94) — reads `loop_events` with no `transition` filter and orders `recent` by `id`, so backfilled historical rows interleave by insertion order and `ll-session recent --kind loop` / export volume grows; no code change needed [Agent 2]
- `scripts/little_loops/fsm/persistence.py:_parse_run_folder` (line 131) / `_RUN_FOLDER` and `list_run_history` (line 1571) — reuse for the `<run_id>-<loop_name>` folder split rather than a third regex (the duplicate `_HISTORY_RUN_RE` in `cli/logs.py:53` exists already); `cli/loop/next_loop.py:50` also imports `_parse_run_folder` [Agent 1]
- No `.loops/` YAML, hook, skill or command consumes `ll-session backfill` output or `counts["loops"]` (grep of the CLI string found only prose and run-log artifacts) [Agent 2]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_lifecycle.py::TestBackfill.test_backfill_loops` (line 73) — fixture writes `.running/docs-sync.json` (NOT `*.state.json`); the fix must keep matching `*.json` under `.running` or this test's `counts["loops"] == 1` (line 81) drops to 0 [Agent 3]
- `scripts/tests/test_session_store_lifecycle.py` — add `TestBackfillLoopsLayouts` beside `TestBackfillDedup`: running layout, flat `.history/<run_id>-<loop>/state.json`, legacy `.history/<loop>/<run_id>/state.json`, double `backfill()` → single `loop_events` row and single `search_index` row (`search(..., kind="loop")` twice), pre-seeded live `SQLiteTransport` row with the same `(loop_name, ts)` but `transition != 'backfill'` is not suppressed, malformed/empty `state.json` skipped, `_iter_loop_state_files` unit tests. Idempotency pattern to copy: `TestBackfillDedup.test_double_backfill_produces_single_row`, `TestBackfillMessages.test_backfill_corrections_idempotent` (line 422) [Agent 3]
- Fixture builders to reuse: real `StatePersistence("test-loop", tmp_loops_dir)` with `initialize()` / `save_state()` / `archive_run()` (`scripts/tests/test_fsm_persistence.py:532`, `_make_state()`) for the flat layout; legacy layout is hand-built in `scripts/tests/test_ll_logs.py::test_collect_loop_runs_legacy_nested_layout` (line 5582) but writes `events.jsonl`, so add a `state.json` [Agent 3]
- `scripts/tests/test_session_store_lifecycle.py::TestBackfillUsageEvents` (`test_run_id_backfilled_from_unambiguous_loop_run_window`, `..._stays_null_*`, `test_run_id_backfill_idempotent_on_rerun`) and `TestRebuild.test_rebuild_does_not_touch_out_of_scope_tables` (~line 1713) — touch `loop_events`; re-run to confirm the added `transition='backfill'` rows don't perturb them [Agent 3]
- `scripts/tests/test_ll_session.py` (lines 318, 336, 364, 742, 766, 820, 1157) — mock `backfill()` and hard-code `"loops": 0`; insulated unless `cli/session.py` output format changes. Optional: one unmocked CLI test against a tmp `.loops` tree (none exists today) [Agent 3]
- Under Option B no `SCHEMA_VERSION` / `test_session_store_schema.py` literal-version edits are needed [Agent 2]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:~2069` — document raw `current_state` (existing `state` fallback) for `transition="backfill"`; distinguish this from the `map_final_status()` bucket used by live `loop_complete` events (BUG-3066). Do not normalize backfill state to a status bucket.
- `docs/reference/API.md` (~lines 9043, 10179) — long lines mentioning `loop_events`/backfill; verify by hand [Agent 2]
- `scripts/little_loops/observability/schema.py:755` — docstring cites nonexistent `_backfill_loop_events`; update to `_backfill_loops` [Agent 2]
- `CHANGELOG.md` — new entry goes in a concrete `## [X.Y.Z]` section, not `[Unreleased]` [Agent 2]

## Program Design

### Types

- `state_file: Path` — `.running/*.json`, flat `.history/*/state.json`, or legacy `.history/*/*/state.json`.
- Snapshot fields: `loop_name: str`, `ts: str` (existing `updated_at` / `started_at` / empty-string fallback), `state: str | None` (existing raw-state extraction).
- `transition="backfill"`, `retries=None`; captured data and iteration are not persisted.

### Signatures

- `_backfill_loops(conn: sqlite3.Connection, loops_dir: Path) -> int` — performs the scoped, NULL-safe snapshot pre-existence check, inserts missing event/search pairs, and returns newly inserted event rows.
- `_iter_loop_state_files(loops_dir: Path) -> Iterator[Path]` — deterministically yields `.running/*.json`, flat `.history/*/state.json`, and legacy `.history/*/*/state.json`.

### Call Path

`backfill` (session_store/lifecycle.py) -> `_backfill_loops` -> `_iter_loop_state_files` -> scoped snapshot check -> event insert and `_index` only if absent.

## Review Resolution

Applied the reviewed scope and consistency corrections on 2026-09-19. Retained Option B with snapshot idempotency, rows-inserted counts, raw state semantics, and all three layouts. Rejected anchor-only dedup and automatic `(loop_name, ts)` historical deletion. Existing duplicates are accepted for this fix; duplicate repair, stable run identity, captured execution history, and historical `loop_runs` coverage remain separate follow-up candidates.

## Resolution

**Fixed** — `_backfill_loops` now walks `.running/*.json`, flat and legacy `.history` archives via `_iter_loop_state_files`, with a scoped `(loop_name, ts, state)` pre-existence check gating event + search inserts. Tests added in `test_session_store_lifecycle.py`; docs and stale docstring updated.

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-20T00:15:17 - `f12de13a-18ba-4e37-a58e-f21eed3889cd.jsonl`
- `/ll:ready-issue` - 2026-09-20T00:08:57 - `1886396e-cdcc-47ce-bf10-8a53d85acd40.jsonl`
- `/ll:confidence-check` - 2026-09-20T00:02:59 - `be1263b0-2beb-4bf2-91f0-aafba59ad1a2.jsonl`
- `/ll:verify-issues` - 2026-09-19T23:58:33 - `dfdc64ea-f3c8-41c0-9f24-89d5c090ffb6.jsonl`
- `/ll:wire-issue` - 2026-09-19T23:27:50 - `4f20c1d3-a8db-42b4-9c73-8f8aaa3aa2fe.jsonl`
- `/ll:decide-issue` - 2026-09-19T23:22:42 - `d4660828-e0d9-40c0-89b8-9bbf5b5e050f.jsonl`
- `/ll:refine-issue` - 2026-09-19T23:17:05 - `4f31a004-1b37-455a-97b4-0a7a1b1424a6.jsonl`
- `/ll:format-issue` - 2026-09-19T23:02:59 - `f7716757-cc12-4f9f-9358-3ee432f01464.jsonl`
