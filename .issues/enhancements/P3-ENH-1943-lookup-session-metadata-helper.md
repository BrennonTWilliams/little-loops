---
id: ENH-1943
title: Add lookup_session_metadata() helper for history.db session-quality queries
type: ENH
priority: P3
status: done
completed_at: '2026-06-04'
parent: ENH-1941
relates_to:
- EPIC-1707
- ENH-1710
labels:
- enhancement
- history-db
- sft
- corpus-quality
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1943: Add lookup_session_metadata() helper for history.db session-quality queries

## Summary

Add a `lookup_session_metadata(session_id, *, db=DEFAULT_DB_PATH)` function that queries `history.db` for session-quality signals and returns a JSON-safe metadata dict. This is the data-access layer for ENH-1941's `sft-corpus` quality predicates.

## Current Behavior

Currently, each consumer that needs session-quality signals (issue outcomes, corrections, tool counts, file modifications) must query `history.db` independently. There is no single helper function that bundles these lookups together. Clients that need session metadata either write their own ad-hoc queries or skip quality filtering entirely.

## Expected Behavior

A single `lookup_session_metadata(session_id, *, db=DEFAULT_DB_PATH)` function centralizes all session-quality queries, returning a JSON-safe metadata dict. Consumers call one function instead of writing multiple independent queries. The function degrades gracefully (returns `{}`) when the database is missing, empty, or lacks relevant tables.

## Parent Issue

Decomposed from ENH-1941: Integrate history.db session-quality signals into sft-corpus filtering

## Context

The `sft-corpus` filter state needs structured quality signals per session (issue outcomes, corrections, tool counts, file modifications). Currently no single function bundles these lookups — each predicate would need to query `history.db` independently. A dedicated helper centralizes the queries, encapsulates graceful degradation, and is independently testable.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py` — add `lookup_session_metadata()` function following existing query-function patterns (`issue_effort()` at line 364, `find_user_corrections()` at line 193)
- `scripts/tests/test_history_reader.py` — add `TestLookupSessionMetadata` test class following `TestMissingDatabase` (line 27) and `TestEmptyTables` (line 56) patterns

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history_context.py` — consumer of `history_reader.py` query functions; may eventually use `lookup_session_metadata()`
- `scripts/little_loops/cli/history.py` — CLI for `ll-history`; potential future consumer
- ENH-1944 (`sft-corpus` enrich and quality predicates) — primary planned consumer

### Schema Dependencies (Read-Only)
- `user_corrections` table — `session_id` column present; direct query ✅
- `tool_events` table — `session_id` column present; direct query ✅
- `file_events` table — `session_id` column present; direct query ✅
- `issue_events` table — **no `session_id` column**; must JOIN through `issue_sessions` VIEW (migration v5, `session_store.py:254`)
- `loop_events` table — **no `session_id` column, no `outcome` column**; query infeasible without schema change (column is `state`, not `outcome`; `SQLiteTransport.send()` at `session_store.py:682-691` writes without session ID)

### Similar Patterns
- `issue_effort()` at `history_reader.py:364` — closest existing pattern: returns `dict | None`, queries across tables, handles missing DB with `None`
- `recent_issue_velocity()` at `history_reader.py:399` — composes dict results from multiple query calls
- `_connect_readonly()` at `history_reader.py:164` — standard connection pattern with graceful degradation

### Tests
- `scripts/tests/test_history_reader.py` — existing `TestMissingDatabase` (line 27), `TestEmptyTables` (line 56), `TestFindUserCorrections` (line 151), `TestRecentFileEvents` (line 209)
- Test setup pattern: use `connect(db)` for INSERT, `ensure_db(db)` for schema bootstrap, `tmp_path` fixture

### Configuration
- `DEFAULT_DB_PATH = Path(".ll/history.db")` — defined in `session_store.py:74`, imported in `history_reader.py:44`

### Documentation

_Wiring pass added by `/ll:wire-issue` — advisory only; out of scope per Boundaries but noted for awareness:_

- `docs/reference/API.md` (line 5971+) — `## little_loops.history_reader` section does not yet document `lookup_session_metadata()`; will need a new subsection when this function graduates to public API documentation scope [Agent 2 finding]
- `docs/ARCHITECTURE.md` (line 640) — states "10 query functions"; will drift to 11 after addition (pre-existing stale count; not created by this change) [Agent 2 finding]
- `CONTRIBUTING.md` (line 247) — states "8 query functions"; pre-existing drift widened further (not in scope for this issue) [Agent 2 finding]

## Implementation Steps

1. **Add `lookup_session_metadata()` to `history_reader.py`** — function signature:
   ```python
   def lookup_session_metadata(session_id: str, *, db: str = DEFAULT_DB_PATH) -> dict:
       """Return session-quality metadata dict for a session ID.
       
       Returns:
           dict with keys: has_corrections (bool), issue_outcome (str|None),
           tool_count (int), files_modified (int), loop_outcome (str|None)
           
           loop_outcome is always None until loop_events gains a session_id
           column (schema change out of scope per Boundaries).

       Returns empty dict {} when DB is missing, empty, or lacks relevant tables.
       """
   ```

2. **Graceful degradation** — replicate the `_connect_readonly()` pattern from `history_reader.py:164`:
   - Attempt `sqlite3.connect(db, uri=True)` with `mode=ro`
   - If file missing → return `{}`
   - Catch `sqlite3.Error` → return `{}`
   - Close in `finally`

3. **Query each predicate table** (queries revised based on actual schema analysis):
   - `has_corrections`: `SELECT COUNT(*) > 0 FROM user_corrections WHERE session_id = ?` — direct query; `user_corrections` has `session_id` column ✅
   - `issue_outcome`: JOIN through `issue_sessions` VIEW (migration v5, `session_store.py:254`) since `issue_events` has **no `session_id` column**:
     ```sql
     SELECT ie.issue_id, ie.transition
     FROM issue_sessions is2
     JOIN issue_events ie ON is2.issue_id = ie.issue_id
     WHERE is2.session_id = ? AND ie.transition = 'done'
     ORDER BY ie.ts DESC LIMIT 1
     ```
   - `tool_count`: `SELECT COUNT(*) FROM tool_events WHERE session_id = ?` — direct query; `tool_events` has `session_id` column ✅
   - `files_modified`: `SELECT COUNT(*) FROM file_events WHERE session_id = ? AND op IN ('write', 'create', 'Write')` — direct query; note: `op` values from hooks use capitalized forms (e.g., `'Write'` per `test_history_reader.py:410`); include both cases
   - `loop_outcome`: ⚠ **`loop_events` has no `session_id` column** — `SQLiteTransport.send()` at `session_store.py:682-691` writes loop events without session ID. Return `None` for this key with graceful degradation (schema change out of scope per Boundaries)

4. **Add tests** in `scripts/tests/test_history_reader.py`:
   - Follow existing `TestMissingDatabase` (line 27) and `TestEmptyTables` (line 56) patterns
   - Add `TestLookupSessionMetadata` class with:
     - `test_degrades_when_db_missing` — returns `{}`
     - `test_degrades_when_tables_empty` — returns dict with falsy values
     - `test_has_corrections_true` — mock `user_corrections` table
     - `test_has_corrections_false` — clean session
     - `test_issue_outcome_done` — mock `issue_events` + `message_events` + `sessions` to populate `issue_sessions` VIEW
     - `test_issue_outcome_null` — no issue events for session
     - `test_tool_count` — mock `tool_events`
     - `test_files_modified` — mock `file_events`
     - `test_loop_outcome_null` — `loop_events` lacks `session_id`; always returns `None`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Closest existing pattern**: `issue_effort()` at `history_reader.py:364` returns `dict | None` with mixed types (`int`, `float | None`), follows the `_connect_readonly()` → query → `finally: conn.close()` pattern, and degrades to `None` on missing DB. `lookup_session_metadata()` differs only in returning `{}` instead of `None` for the empty case.
- **Schema gap — `loop_events`**: The `loop_events` table (`session_store.py:193-200`) has columns `(id, ts, loop_name, state, transition, retries)` — no `session_id`, no `outcome`. The `SQLiteTransport.send()` at line 682-691 writes without session context. The `state` column serves as the outcome for `loop_complete` events (line 679-680), but there is no mechanism to link loop runs to sessions. Per scope boundaries, schema changes are out of scope; return `None` for `loop_outcome`.
- **Schema gap — `issue_events`**: `issue_events` has no `session_id` column. The `issue_sessions` VIEW (migration v5, `session_store.py:254-268`) bridges this by joining `issue_events` to `message_events` on timestamp overlap. Query must JOIN through this VIEW, not query `issue_events` directly.
- **Test setup conventions**: Tests use `connect(db)` (not `_connect_readonly`) for INSERT-based setup, `ensure_db(db)` for schema bootstrap, and `tmp_path` fixture for temp directories. No custom pytest fixtures exist for database setup. See `_insert_old_correction()` at `test_history_reader.py:93` and `_insert_file_event()` at line 404 for patterns.
- **`files_modified` op values**: Hook-written `op` values use capitalized forms (`'Write'` per `test_history_reader.py:410`). The query should match `op IN ('write', 'create', 'Write')` to cover both lower and title case.
- **All existing query functions degrade gracefully** — none raise exceptions to callers. The standard pattern: `except sqlite3.Error` → `logger.warning(...)` → return empty/falsy value. `search()` at line 291 also catches `sqlite3.OperationalError` specifically for FTS5 syntax errors.

## Scope Boundaries

- **In scope**: `lookup_session_metadata()` function; graceful degradation; tests
- **Out of scope**: Changes to `history.db` schema or write paths (owned by EPIC-1707); calling this function from the `sft-corpus` loop (that's ENH-1944)

## Impact

- **Priority**: P3 — inherited from parent ENH-1941
- **Effort**: Small — Single function + tests; all table schemas and degradation pattern already exist
- **Risk**: Low — Additive only; degrades gracefully; no callers until ENH-1944
- **Breaking Change**: No

## Resolution

Added `lookup_session_metadata()` to `history_reader.py` (following `issue_effort()` patterns) and 9 tests in a new `TestLookupSessionMetadata` class.

### Changes
- `scripts/little_loops/history_reader.py` — Added `lookup_session_metadata(session_id, *, db)` function (~60 lines). Pre-checks file existence to distinguish missing DB (`{}`) from empty tables (dict with falsy values). Queries `user_corrections`, `issue_sessions` VIEW, `tool_events`, and `file_events`. Returns `None` for `loop_outcome` (schema gap — `loop_events` has no `session_id` column).
- `scripts/tests/test_history_reader.py` — Added `TestLookupSessionMetadata` class with 9 tests covering missing DB, empty tables, correction detection, issue outcome via VIEW JOIN, tool counts, file modification counts, and loop outcome graceful degradation.

### Verification
- `python -m pytest scripts/tests/test_history_reader.py::TestLookupSessionMetadata` — **9/9 passed**
- `python -m pytest scripts/tests/test_history_reader.py` — **71/71 passed** (no regressions)
- `ruff check` — **clean**

## Session Log
- `/ll:ready-issue` - 2026-06-04T17:24:36 - `7d2afac2-78f1-4d4b-8763-8f4967ab976a.jsonl`
- `/ll:wire-issue` - 2026-06-04T17:19:30 - `ee85b092-39e2-45cb-9f46-3d4c81808bfa.jsonl`
- `/ll:refine-issue` - 2026-06-04T17:13:38 - `93ec1288-b079-4c05-92c9-6b19926f5cbc.jsonl`
- `/ll:issue-size-review` - 2026-06-04T18:45:00Z - `ca366434-0e71-4ffe-883b-0f265ec672e1.jsonl`
- `/ll:confidence-check` - 2026-06-04T19:20:00Z - `d788e31f-b49f-4295-9fad-32f2821cb49d.jsonl`
