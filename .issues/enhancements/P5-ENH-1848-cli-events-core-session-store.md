---
id: ENH-1848
type: ENH
priority: P5
status: done
completed_at: 2026-06-01 12:30:23+00:00
parent: ENH-1834
relates_to:
- EPIC-1707
- ENH-1833
labels:
- enhancement
size: Medium
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1848: Core `cli_events` infrastructure in session_store.py

## Summary

Decomposed from ENH-1834: Record `ll-` CLI command invocations in history.db.

Implement the `cli_events` table schema migration, `_VALID_KINDS`/`_KIND_TABLE` routing, and `cli_event_context()` context manager in `session_store.py`, along with all direct unit tests. This is the foundational child — ENH-1849 (CLI wiring) depends on this shipping first.

## Parent Issue

Decomposed from ENH-1834: Record `ll-` CLI command invocations in history.db

## Acceptance Criteria

- `cli_events` table created at schema v8 with columns: `id`, `ts`, `binary`, `args`, `exit_code`, `duration_ms`
- `"cli"` added to `_VALID_KINDS` frozenset and `"cli": "cli_events"` to `_KIND_TABLE` dict in `session_store.py`
- `cli_event_context()` context manager: inserts row on enter (exit_code=NULL), updates exit_code + duration_ms on exit via `finally`; passes exit_code=1 on exception
- All four test cases in `TestCliEventContext` pass
- Existing schema and table tests updated to reflect v8

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — add imports, append v8 migration to `_MIGRATIONS`, bump `SCHEMA_VERSION`, extend `_VALID_KINDS`/`_KIND_TABLE`, implement `cli_event_context()`, add `__all__`
- `scripts/tests/test_session_store.py` — add `TestCliEventContext`, `TestSchemaV8`, update `TestSchemaV6.test_schema_version_is_seven`, update `TestEnsureDb.test_all_tables_created`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py:82` — imports and uses `record_skill_event()` (sibling pattern; `cli_event_context()` will be wired by ENH-1849)
- `scripts/little_loops/hooks/session_start.py` — imports `ensure_db()` and `backfill_incremental()` (the new `cli_events` table gets created automatically by `ensure_db()` at startup)
- `scripts/little_loops/hooks/post_tool_use.py` — imports `connect()`, `_hash_args()`, `_now()` (imports module-level helpers; not affected by this change)
- `scripts/little_loops/__init__.py:43` — exports `SQLiteTransport` from session_store (will need `cli_event_context` added if `__all__` is declared)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py` — `_build_parser()` hardcodes `--kind choices` as a static string list (not derived from `_VALID_KINDS`); adding `"cli"` to `_VALID_KINDS` in ENH-1848 does NOT automatically enable `ll-session recent --kind cli` — argparse will reject it until ENH-1849 manually adds `"cli"` to both `search_parser` and `recent_parser` choices lists at lines 68 and 80 [Agent 1/2 finding]

### Similar Patterns
- `scripts/little_loops/session_store.py:382` — `record_skill_event()` (INSERT shape to follow)
- `scripts/little_loops/issue_manager.py:72` — `timed_phase()` (`@contextmanager` + `time.time()` + `finally` shape to follow)
- `scripts/little_loops/file_utils.py:60` — `acquire_lock()` (`yield` inside `try/finally` pattern)
- `scripts/little_loops/cli/ctx_stats.py` — `DEFAULT_DB_RELPATH` CWD-resolution pattern

### Tests
- `scripts/tests/test_session_store.py` — primary test file; `TestRecordSkillEvent` (line 1218) is the model to follow; `TestSchemaV6` (line 1017) is the model for `TestSchemaV8`; `TestEnsureDb.test_all_tables_created` (line 52) needs `"cli_events"` added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — tests `ll-session` CLI including `--kind` argument parsing; `TestArgumentParsing` covers choices validation; no test currently exercises `--kind cli`; ENH-1849 must add `"cli"` to `choices=` in `cli/session.py` before a `test_recent_subcommand_cli_accepted` test would pass [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — documents producer→consumer flow for history.db (may need `cli_events` mention)
- `docs/reference/API.md` — module reference documentation for session_store (add `cli_event_context` to Public API section)

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` line 241 — directory tree comment for `session_store.py` reads `v1–v7 migrations`; update to `v1–v8 migrations` when this ships [Agent 2 finding]

## Implementation Steps

0. **Add missing imports** to `scripts/little_loops/session_store.py` (lines 32–42 import block). The module currently imports `hashlib, json, logging, re, sqlite3, threading`, `datetime`, `pathlib.Path`, `typing.Any` — but has no `time`, `contextlib`, or `Generator`. Add:

   ```python
   import time
   from collections.abc import Generator
   from contextlib import contextmanager
   ```

1. **Migrate schema** in `scripts/little_loops/session_store.py`: append a new SQL string to `_MIGRATIONS` at line 95. The list currently has **7 entries** (indices 0–6); the new entry becomes **index 7**, which bumps `SCHEMA_VERSION = 7` → `8`. Use `CREATE TABLE IF NOT EXISTS`:

   ```python
   # v8 (ENH-1848): cli_events table records ll- CLI invocations via cli_event_context()
   """
   CREATE TABLE IF NOT EXISTS cli_events (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       ts TEXT NOT NULL,
       binary TEXT NOT NULL,
       args TEXT NOT NULL,
       exit_code INTEGER,
       duration_ms INTEGER
   );
   """,
   ```

   Also update `SCHEMA_VERSION = 7` → `SCHEMA_VERSION = 8` at line 47.

2. **Extend kind routing** in `session_store.py:49–58`: add `"cli"` to `_VALID_KINDS` frozenset and `"cli": "cli_events"` to `_KIND_TABLE` dict so `recent(db, kind="cli")` resolves correctly

3. **Implement `cli_event_context()`** in `session_store.py`, after `record_skill_event()` (which ends at line ~405, before the `# Query API` section at line ~408):

   ```python
   @contextmanager
   def cli_event_context(
       db_path: Path,
       binary: str,
       args: list[str],
       config: dict | None = None,  # reserved for ENH-1835 gating; ignored
   ) -> Generator[None, None, None]:
       """Insert cli_events row on enter; update exit_code and duration_ms on exit."""
   ```

   - Follow the `record_skill_event()` open-insert-commit-close shape (line 382): `conn = connect(db_path)` then `try/finally: conn.close()`
   - Capture `start = time.time()` and `ts = _now()` before the INSERT
   - `cursor = conn.execute("INSERT INTO cli_events(ts, binary, args) VALUES(?, ?, ?)", (ts, binary, json.dumps(args[:50])))`
   - `row_id = cursor.lastrowid`; `conn.commit()`; then `yield`
   - Default `exit_code = 0`; catch `BaseException` in the body to set `exit_code = 1` before re-raising
   - In the `finally` block: `duration_ms = int((time.time() - start) * 1000)` (mirror `timed_phase()` at `issue_manager.py:73`), then `conn.execute("UPDATE cli_events SET exit_code=?, duration_ms=? WHERE id=?", (exit_code, duration_ms, row_id))`; `conn.commit()`

4. **Insert-then-update mechanics**: `cursor = conn.execute("INSERT INTO cli_events...")` → `row_id = cursor.lastrowid` → `conn.commit()` → `yield` → UPDATE in `finally`. The `exit_code` defaults to `NULL` in the inserted row (crash-abort visibility); the UPDATE runs unconditionally in `finally`.

5. **Add `__all__`**: `session_store.py` has no `__all__` declaration — the public API is documented only in the module docstring (lines 16–30). Add an `__all__` list after the import block, including `cli_event_context` alongside the existing public names (`DEFAULT_DB_PATH`, `SCHEMA_VERSION`, `ensure_db`, `connect`, `SQLiteTransport`, `backfill`, `backfill_incremental`, `search`, `recent`, `is_correction`, `record_correction`, `record_skill_event`).

6. **DB path resolution**: `connect()` (line 288) takes `path: Path | str = DEFAULT_DB_PATH` and passes it verbatim to `ensure_db()` with no CWD joining — it resolves relative to wherever the process runs. `cli_event_context()` should accept `db_path: Path` and default to `DEFAULT_DB_PATH` in its signature (same convention as `record_skill_event()`). Callers (ENH-1849) will pass the CWD-resolved path explicitly, mirroring `ctx_stats.py`'s `cwd / DEFAULT_DB_RELPATH` pattern.

7. **Tests** in `scripts/tests/test_session_store.py`: add a `TestCliEventContext` class following `TestRecordSkillEvent` (class definition at line 1218) with:
   - `test_cli_event_roundtrip`: insert via context manager, assert row in `recent(db, kind="cli")`
   - `test_cli_event_exception_exit`: enter context, raise inside body, assert `exit_code=1` in DB
   - `test_cli_event_duration_accuracy`: assert `duration_ms >= 0` and is integer
   - `test_schema_v8_cli_events_table_exists`: mirror `TestSchemaV6` (line 1017) — bootstrap fresh DB via `ensure_db()`, assert `SCHEMA_VERSION == 8` and `cli_events` in tables

8. Update `scripts/tests/test_session_store.py` → `TestSchemaV6.test_schema_version_is_seven`: change `assert SCHEMA_VERSION == 7` to `assert SCHEMA_VERSION == 8` (the `assert int(row[0]) == SCHEMA_VERSION` line on the same test already covers the contract dynamically)

9. Update `scripts/tests/test_session_store.py` → `TestEnsureDb.test_all_tables_created` (line 52): add `"cli_events"` to the `for table in (...)` tuple alongside `"skill_events"` and the other event tables

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `session_store.py` module docstring (lines 16–30 Public API list) to add `cli_event_context` — step 5 covers `__all__`, but the module docstring is a separate artifact listing the same public names
11. Update `recent()` function docstring to enumerate all valid kinds including `"cli"` — currently stale (lists only `tool, file, issue, loop, correction`; missing `message`, `skill`, and the new `cli`)
12. Update `CONTRIBUTING.md` line 241: change `v1–v7 migrations` to `v1–v8 migrations` in the session_store.py directory tree comment

## Similar Patterns

- `scripts/little_loops/session_store.py:382` — `record_skill_event()` (ENH-1833 predecessor) follows the open-insert-commit-close shape; `cli_event_context()` extends this with a `yield` + UPDATE in `finally`
- `scripts/little_loops/issue_manager.py:72` — `timed_phase()` decorator at line 72, function def at line 73; closest `@contextmanager` using `start = time.time()` before yield and `finally` to compute elapsed — mirrors the `duration_ms` pattern exactly
- `scripts/little_loops/file_utils.py:60` — `acquire_lock()` decorator at line 60, def at line 61; shows `yield` inside `try/finally` for unconditional cleanup

## Impact

- **Priority**: P5
- **Effort**: Small — schema migration + one context manager + 4 tests
- **Risk**: Low — additive only; no existing behavior changes
- **Breaking Change**: No

## Resolution

Implemented `cli_events` table (schema v8), `cli_event_context()` context manager, and `__all__` in `session_store.py`. Added 4 unit tests in `TestCliEventContext`. Updated `TestSchemaV6`, `TestEnsureDb`, CONTRIBUTING.md, and ARCHITECTURE.md to reflect v8. All 89 tests pass; ruff clean.

## Session Log
- `/ll:ready-issue` - 2026-06-01T12:24:31 - `6ffe721c-3812-4f8b-a94d-d393292df9eb.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `2a69032c-74c5-4bf9-8d15-e15183d27209.jsonl`
- `/ll:wire-issue` - 2026-06-01T12:20:12 - `585411f0-eeee-43e3-8cc9-8f74e225aab3.jsonl`
- `/ll:manage-issue` - 2026-06-01T12:30:23 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-06-01T12:12:54 - `aadfdde5-7d5b-4950-9b58-a8ebcd82f760.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00 - `0686c0da-b3e0-4215-b978-6a0771cae829.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P5
