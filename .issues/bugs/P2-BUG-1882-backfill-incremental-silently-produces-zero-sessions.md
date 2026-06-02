---
id: BUG-1882
type: BUG
priority: P2
status: open
discovered_date: 2026-06-02
captured_at: "2026-06-02T23:39:38Z"
discovered_by: capture-issue
relates_to: [EPIC-1707, ENH-1830, ENH-1710, ENH-1711]
labels:
  - bug
  - history-db
  - sessions
  - captured
---

# BUG-1882: `backfill_incremental` silently produces 0 sessions despite JSONL files present

## Summary

`sessions` table in `.ll/history.db` has 0 rows. The `session_start.py` hook (ENH-1830) spawns a daemon thread calling `backfill_incremental()`, but ~5000 JSONL session files exist under `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`. All exceptions in the thread are suppressed, masking the failure. Without sessions, the `issue_sessions` VIEW (ENH-1711) and `message_events` attribution are inoperable.

## Current Behavior

```python
# session_start.py (simplified)
def _run_backfill() -> None:
    try:
        backfill_incremental(_db_path, jsonl_files=jsonl_files)
    except Exception:
        pass  # all errors suppressed

threading.Thread(target=_run_backfill, daemon=True).start()
```

After every session start, `sessions` table remains at 0 rows. `ll-session recent --kind all` returns no output. The `issue_sessions` VIEW joins `issue_events` to `message_events` via `sessions` — all cross-reference queries return empty.

## Expected Behavior

After a session starts (or after `ll-session backfill` is run manually), JSONL files from the current project directory are indexed into the `sessions` table with `session_id`, `jsonl_path`, `started_at`, and `project_path`. `message_events` backfilled from those JSONL files are attributed to their sessions. `ll-session recent --kind all` returns recent sessions.

## Motivation

ENH-1830 was marked done, but the `sessions` table being empty means:
- ENH-1710 (session-to-JSONL mapping) — no data
- ENH-1711 (issue-to-session cross-references) — no data
- `history_reader.py` `search()` and `related_issue_events()` can't correlate sessions
- EPIC-1707's stated goal of "prior user_corrections, recently touched files, related issue events inform skill outputs" is blocked for the session dimension

## Proposed Solution

1. **Diagnose** why `backfill_incremental` silently returns without inserting rows — run it directly with exceptions un-suppressed:
   ```python
   from little_loops.session_store import backfill_incremental
   backfill_incremental('.ll/history.db')
   ```
2. **Fix** the root cause (likely one of: JSONL discovery path resolution, schema version mismatch, INSERT conflict on `session_id` unique constraint, or `jsonl_files` arg receiving wrong paths from the hook).
3. **Add a diagnostic log line** (not suppressed) so future failures surface in hook stderr rather than silently no-op.
4. **Add a test** in `scripts/tests/` that runs `backfill_incremental` against a fixture JSONL file and asserts at least one `sessions` row is inserted.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/session_start.py` — improve error visibility in `_run_backfill`
- `scripts/little_loops/session_store.py` — fix root cause in `backfill_incremental`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session backfill` subcommand
- `scripts/little_loops/history_reader.py` — reads `sessions` table

### Similar Patterns
- N/A — suppressed-exception pattern in `_run_backfill` is unique; other hooks in `scripts/little_loops/hooks/` do not use daemon threads

### Tests
- `scripts/tests/test_session_store.py` — add backfill fixture test

### Documentation
- `docs/reference/API.md` — `session_store` module documentation may need updating if `backfill_incremental` signature or behavior changes

### Configuration
- N/A

## Implementation Steps

1. Run `backfill_incremental` manually with debug logging enabled to capture the actual exception
2. Fix root cause in `session_store.py::backfill_incremental`
3. In `session_start.py::_run_backfill`, replace bare `except Exception: pass` with logging at WARNING level (keep suppressing so hook doesn't fail, but make it visible)
4. Add unit test: create a minimal JSONL fixture → call `backfill_incremental` → assert `sessions` row count > 0
5. Verify manually: restart a session, check `SELECT COUNT(*) FROM sessions` in `.ll/history.db`

## Impact

- **Priority**: P2 — blocks the entire session/message cross-reference layer; ENH-1710/1711 are dead without it
- **Effort**: Small-Medium — diagnosis may reveal a trivial fix or a schema issue
- **Risk**: Low — backfill is read-only on JSONL files; worst case is no-op
- **Breaking Change**: No

## Steps to Reproduce

1. Start any session in this project
2. Run:
   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM sessions').fetchone())"
   ```
3. Observe: `(0,)` despite `ls ~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/*.jsonl | wc -l` showing ~5000 files

## Root Cause

- **File**: `scripts/little_loops/hooks/session_start.py`
- **Anchor**: `_run_backfill()` inner function
- **Cause**: Unknown — all exceptions suppressed. Most likely candidates: JSONL file path passed to the thread is wrong (relative vs absolute), `session_id` INSERT conflicts on unique constraint without `OR IGNORE`, or `backfill_incremental` receives an empty `jsonl_files` list because the glob pattern doesn't match.

## Related Key Documentation

- `docs/reference/API.md` — `little_loops.session_store` module reference
- `docs/reference/API.md` — `little_loops.hooks.session_start` hook documentation

## Labels

`bug`, `history-db`, `sessions`, `captured`

## Status

**Open** | Created: 2026-06-02 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-02T23:43:17 - `5a6438e8-ff2f-4342-b911-43dcd9985f55.jsonl`

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
