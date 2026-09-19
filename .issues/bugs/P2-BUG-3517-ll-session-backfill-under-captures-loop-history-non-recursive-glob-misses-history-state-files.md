---
id: BUG-3517
type: BUG
title: 'll-session backfill under-captures loop history: non-recursive glob misses
  .history state files'
priority: P2
status: open
decision_needed: false
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T22:27:37Z'
labels:
- session-store
- backfill
---

# BUG-3517: ll-session backfill under-captures loop history: non-recursive glob misses .history state files

## Summary

`ll-session backfill` silently under-captures loop history. `_backfill_loops` (session_store/writers.py) reads FSM state with a non-recursive `glob("*.json")`, so it catches the currently-running loops in `.loops/.running/*.state.json` but misses the completed runs stored as `.loops/.history/<run>/state.json` — roughly 92% of loop history is skipped.

## Current Behavior

`_backfill_loops` iterates `directory.glob("*.json")` over `.loops/.running` and `.loops/.history`:

- `.loops/.running/*.state.json` → caught (112 files on the little-loops repo).
- `.loops/.history/*/state.json` → missed: each completed run is a per-run subdirectory (`<timestamp>-<loop-name>/state.json`), and the non-recursive glob never descends into them.

Two secondary gaps compound it: it stores only `(loop_name, current_state, ts)` with `transition="backfill"` hardcoded, discarding the `captured` dict (per-state `output`/`exit_code`/`duration_ms`); and it uses a plain `INSERT` with no dedup, so re-running duplicates rows.

## Expected Behavior

`_backfill_loops` should capture every loop run — running and completed — and persist the full state sequence plus `captured` outputs (not just `current_state`), deduped on `(loop_name, ts)` so the backfill is idempotent.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

1. Completed runs in both `.history/<run_id>-<loop_name>/state.json` and legacy `.history/<loop_name>/<run_id>/state.json` layouts are ingested, alongside `.running/*.state.json`; verified by a test that builds all three layouts under `tmp_path/.loops` and asserts the row count (existing `test_backfill_loops`, `test_session_store_lifecycle.py:73`, must keep passing).
2. Re-running `backfill()` yields no additional `loop_events` or `search_index` rows; verified alongside `TestBackfillDedup.test_double_backfill_produces_single_row` (line 569) conventions. Decide and document whether `counts["loops"]` stays files-processed or becomes rows-inserted (both conventions exist).
3. Per-state `captured` data and `iteration` are persisted or the issue explicitly scopes them out — `loop_events` has no column for them (`schema.py` `_MIGRATIONS[0]`), so persisting requires a schema change or a different table (`loop_runs` has a UNIQUE `run_id`; see Integration Map).
4. If Option A is chosen: migration dedups before creating the index, `SCHEMA_VERSION`, `schema_manifest.json` and literal-version test assertions move together.
5. Gates: `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_session_store_schema.py scripts/tests/test_session_store_writers.py -v`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority**: P2 - Silent data loss: ~92% of loop history never reaches `loop_events`, skewing any loop analytics built on it
- **Effort**: Small - One function (`_backfill_loops`) plus a dedup index/check
- **Risk**: Low - Backfill-only path; `INSERT OR IGNORE` keeps re-runs idempotent
- **Breaking Change**: No

## Steps to Reproduce

1. On a repo with completed loop history, run `ll-session backfill`.
2. Compare `SELECT COUNT(*) FROM loop_events` against the number of state files under `.loops/.running/*.state.json` plus `.loops/.history/*/state.json`.
3. Observe that only `.running` state is ingested; `.history` subdirectories are skipped.

## Root Cause

`directory.glob("*.json")` is non-recursive, but completed runs live one directory deeper under `.loops/.history/<run>/state.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Confirmed at `session_store/writers.py:_backfill_loops` (line 3357): `sorted(directory.glob("*.json"))` over `(".running", ".history")`. `.running/<stem>.state.json` matches; completed runs are archived by `StatePersistence.archive_run` (`fsm/persistence.py`) into `.history/<run_id>-<loop_name>/state.json` — one directory deeper — so the glob never sees them. Older archives use a legacy nested layout `.history/<loop_name>/<run_id>/state.json` (`list_run_history`, `persistence.py:1571`), also missed. On-disk counts at research time: 1294 `state.json` under `.history/` vs 112 `.running/*.state.json` (≈92% skipped, matching the issue).
- No flat `.loops/.history/*.json` files exist and nothing writes that shape, so `.history` iteration in the current code is dead.
- Secondary defects confirmed: the insert is a plain `INSERT INTO loop_events(ts, loop_name, state, transition, retries)` with `transition="backfill"`, `retries=None`; `loop_events` (`schema.py`, `_MIGRATIONS[0]`) has no UNIQUE key or index, so every `backfill()` re-inserts every file and re-adds a `search_index` row via `_index`. `captured`, `iteration`, `status` are never read. The returned `count` is files-processed, not rows-inserted.

## Proposed Solution

1. Replace the flat `glob("*.json")` with a recursive walk — e.g. `loops_dir.rglob("state.json")`, or iterate `.history/*/state.json` explicitly alongside `.running/*.state.json`.
2. Extract the full state: `current_state`, the `captured` dict, and `iteration`.
3. Dedupe on `(loop_name, ts)` (or the state-file path) — e.g. a UNIQUE index + `INSERT OR IGNORE`, or a pre-existence check.
4. Re-run `ll-session backfill` to ingest the completed runs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

**Option A**: Add a DB-level dedup key — new migration (v53) with dedup-before-index and a UNIQUE index over the chosen key columns, then `INSERT OR IGNORE` and gate `_index` on `cursor.rowcount` (matches sibling backfills).

**Option B**: Keep the schema unchanged; do a pre-existence check in `_backfill_loops` (e.g. `SELECT 1 FROM loop_events WHERE loop_name=? AND ts=? AND transition='backfill'`) before insert, skipping `_index` when a row exists — no migration, `SCHEMA_VERSION` and manifest untouched.

> **Selected:** Option B — scoped pre-existence check; no v53 migration, and no unique key that could collide with live `loop_events` rows.

**Recommended**: Option B — the only rows needing dedup are `transition="backfill"` rows, which the live writer never produces; a scoped check avoids a v53 migration, ~25 literal-version test edits, and a unique key that could collide with live rows sharing `(loop_name, ts)`. Choose A only if a stable per-run key is added to `loop_events`.

### Decision Rationale

**Selected**: Option B — scoped pre-existence check in `_backfill_loops`.

**Reasoning**: Option A has strong precedent (v43 dedup-before-index, `INSERT OR IGNORE` + rowcount gating in sibling backfills), but no safe unique key exists over `loop_events`: live rows share `(loop_name, ts)` across transitions, `retries`/`state` are nullable (NULLs are distinct in a UNIQUE index), and backfill `ts` is a mutable `updated_at`. A would add a v53 migration plus ~25 literal-version test edits for a backfill-only path. B is contained to one function and needs no schema change.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — DB-level UNIQUE + INSERT OR IGNORE | 2 | 1 | 2 | 1 | 6/12 |
| B — pre-existence check | 1 | 3 | 3 | 2 | 9/12 |

**Key evidence**: B departs from the sibling-backfill convention (reuse 1/3 vs 2/3) and, as an unindexed SELECT, is O(n) per file. Implementation must key the check on `transition='backfill'` and treat empty `ts` and `.running` files with advancing `updated_at` as known limits (candidate follow-up: key on run id/state-file path).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Files to modify: `scripts/little_loops/session_store/writers.py` (`_backfill_loops`); `scripts/little_loops/session_store/schema.py` (`_MIGRATIONS`, `SCHEMA_VERSION`=52) if a DB-level dedup key is chosen; `scripts/little_loops/session_store/schema_manifest.json` (regenerated); `scripts/tests/test_session_store_lifecycle.py` (`TestBackfill.test_backfill_loops`, line 73, covers only a single flat state file under `.running`).
- Sole caller: `session_store/lifecycle.py:1102` (`counts["loops"] = _backfill_loops(conn, loops_dir)`, guarded by `loops_dir.is_dir()`); `cli/session.py` (~line 794) prints `counts['loops']`. `backfill_incremental` deliberately does not backfill loops. No `_iter_loop_state_files` helper exists yet.
- Other `loop_events` writer: `SQLiteTransport.send` (`writers.py:~2940`) — many rows per run, `transition` = event type, plain INSERT. `loop_events` has no `run_id` column. Readers: `queries.py` (`_EXPORT_TABLE_MAP["loop_event"]`), `recent(kind="loop")`, `search_index` kind `loop`; `history_reader/sessions.py` does not read it. `loop_events` is excluded from `_REBUILD_TABLES` (`lifecycle.py:937`).
- Conventions in force:
  - Every sibling backfill dedupes with `INSERT OR IGNORE` backed by a UNIQUE column/index, and gates the `_index` FTS row on `cursor.rowcount` — evidence: `_backfill_commit_events` (`writers.py:972`), `record_loop_run_summary` (`writers.py:1834`), `_backfill_subagent_runs`, `_backfill_issues_and_snapshots`. `_backfill_loops` is the lone exception.
  - Schema change = new string appended to `_MIGRATIONS` with a `# vNN (ISSUE-ID)` comment, `SCHEMA_VERSION` bumped in step (`test_schema_version_matches_migrations_length`), `schema_manifest.json` regenerated (`test_schema_manifest_matches_checked_in_file`), and literal `assert SCHEMA_VERSION == 52` occurrences in tests (`test_session_store_writers.py`, `test_assistant_messages.py`, ~20 in `test_session_store_schema.py`) updated.
  - A unique index over a table that may already hold duplicates must dedupe first (v43, BUG-3241, `schema.py` ~1047-1116: `DELETE ... WHERE rowid NOT IN (SELECT MIN(rowid) ... GROUP BY ...)` then `CREATE UNIQUE INDEX`); a bare create raises `IntegrityError` and makes `ensure_db()` fail at startup. NULLs are distinct in a UNIQUE index but equal in `GROUP BY`, so nullable key columns need `IS NOT NULL` guards. Migration tests: `TestSchemaV43IndexRepair` (`test_session_store_schema.py:2494`).
  - Run-folder naming is parsed by `_parse_run_folder` / `_RUN_FOLDER` (`persistence.py:127-131`); a duplicate regex `_HISTORY_RUN_RE` lives in `cli/logs.py:53`. Existing walkers (`list_run_history`, `next_loop._scan_history`, `logs._collect_loop_runs`) each handle flat and legacy-nested layouts; none yields all loops' state files.
  - Idempotency tests call `backfill()` twice and assert both returned counts and `recent(db, kind=...)` row count (`TestBackfillDedup.test_double_backfill_produces_single_row`, line 569). Two count conventions coexist: rows-inserted (commits) vs files-processed (learning tests).
- Constraint: `test_backfill_missing_sources_is_noop` (lifecycle tests line 112) asserts the exact `counts` dict with `==`; adding a count key breaks it.
- Constraint: `(loop_name, ts)` alone is not a safe unique key — live `loop_events` rows for one loop can share a `ts` across different `transition`/`state` values, and `ts` may be `""` when a state file lacks `updated_at`/`started_at`. State files carry `status` (`running`/`interrupted`/completed…), so a `.running` file and its later `.history` archive describe the same run at different times and produce different `ts`.
- Documentation: `docs/reference/CLI.md` (`ll-session backfill`, lines ~4077, 4149-4163, 4241-4244), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md` mention `loop_events`.

## Program Design

### Types

- `state_file: Path` — a `.running/*.state.json` or `.history/<run>/state.json` file
- `data["captured"]: dict[str, dict]` — per-state `output`/`exit_code`/`duration_ms`

### Signatures

- `_backfill_loops(conn: sqlite3.Connection, loops_dir: Path) -> int` — walks both dirs, `INSERT OR IGNORE`, returns rows inserted
- `_iter_loop_state_files(loops_dir: Path) -> Iterator[Path]` — yields `.running/*.state.json` then `.history/*/state.json`

### Call Path

`backfill` (session_store/lifecycle.py) -> `_backfill_loops` -> `_iter_loop_state_files` -> `_index`

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Session Log
- `/ll:decide-issue` - 2026-09-19T23:22:42 - `d4660828-e0d9-40c0-89b8-9bbf5b5e050f.jsonl`
- `/ll:refine-issue` - 2026-09-19T23:17:05 - `4f31a004-1b37-455a-97b4-0a7a1b1424a6.jsonl`
- `/ll:format-issue` - 2026-09-19T23:02:59 - `f7716757-cc12-4f9f-9358-3ee432f01464.jsonl`
