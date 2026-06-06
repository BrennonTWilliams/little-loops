---
id: BUG-1882
type: BUG
priority: P2
status: open
discovered_date: 2026-06-02
captured_at: '2026-06-02T23:39:38Z'
completed_at: '2026-06-03T00:49:03Z'
discovered_by: capture-issue
relates_to:
- EPIC-1707
- ENH-1830
- ENH-1710
- ENH-1711
decision_needed: false
labels:
- bug
- history-db
- sessions
- captured
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1882: `backfill_incremental` silently produces 0 sessions despite JSONL files present

## Summary

`sessions` table in `.ll/history.db` has 0 rows. The `session_start.py` hook (ENH-1830) spawns a daemon thread calling `backfill_incremental()`, but ~5000 JSONL session files exist under `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`. All exceptions in the thread are suppressed, masking the failure. Without sessions, the `issue_sessions` VIEW (ENH-1711) and `message_events` attribution are inoperable.

## Current Behavior

```python
# session_start.py (simplified)
def _run_backfill() -> None:
    with contextlib.suppress(Exception):  # all errors silently swallowed
        backfill_incremental(_db_path, jsonl_files=jsonl_files)

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

## Root Cause

- **File**: `scripts/little_loops/hooks/session_start.py`
- **Anchor**: `_run_backfill()` inner function; `scripts/little_loops/session_store.py::backfill_incremental()`
- **Cause**: Three compounding failures (any one is sufficient to produce 0 sessions):

  1. **Daemon thread killed before completion** (primary suspect): The hook process is short-lived. A `daemon=True` thread processing ~5000 JSONL files is terminated the moment the hook process exits — before the thread can complete. The `daemon=True` in `threading.Thread(target=_run_backfill, daemon=True).start()` means no joining occurs; the OS reclaims the thread when the parent process exits.

  2. **Ordering + single commit in `backfill_incremental`**: `session_store.py::backfill_incremental()` calls `_backfill_tool_events(conn, filtered)` and `_backfill_messages(conn, filtered)` — both using plain `INSERT` (no dedup) — **before** calling `_backfill_sessions(conn, filtered)`. All three share a single `conn.commit()` at the end. If either preceding function raises, `_backfill_sessions` never runs and the transaction rolls back silently (caught by `contextlib.suppress`).

  3. **`last_backfill_ts` one-way ratchet**: Once `backfill_incremental` commits successfully (even with 0 sessions inserted), it writes the current UTC timestamp to `meta` as `last_backfill_ts`. Subsequent runs in `_run_backfill` filter files by `_mtime(f) >= since_ts`, excluding all JSONL files that predate that timestamp. This closes the backfill window for historical files permanently.

## Proposed Solution

1. **Diagnose** the actual exception by temporarily exposing it. Run `backfill_incremental` directly with exceptions un-suppressed:
   ```python
   from pathlib import Path
   from little_loops.session_store import backfill_incremental
   from little_loops.user_messages import get_project_folder
   project_folder = get_project_folder()
   jsonl_files = list(project_folder.glob("*.jsonl"))
   result = backfill_incremental('.ll/history.db', jsonl_files=jsonl_files)
   print(result)
   ```

2. **Fix call ordering** in `session_store.py::backfill_incremental()`: move `_backfill_sessions(conn, filtered)` to run **first**, before `_backfill_tool_events` and `_backfill_messages`. Sessions are the highest-priority output and should not be gated on the success of tool/message backfill. Alternatively, use separate `conn.commit()` calls after each sub-function so a failure in one doesn't roll back the others.

3. **Add a diagnostic log line** in `session_start.py::_run_backfill()`: replace `contextlib.suppress(Exception)` with a `try/except Exception` that calls `logger.warning("session_start: backfill failed", exc_info=True)`. Follow the `SQLiteTransport.send()` pattern in `session_store.py` which uses `logger = logging.getLogger(__name__)` + `logger.warning(..., exc_info=True)`. Keep the exception suppressed so the hook never aborts the host session.

4. **Add a test** in `scripts/tests/test_session_store.py` following the `TestBackfillIncremental._make_tool_jsonl()` fixture pattern: write a minimal JSONL file with a `sessionId` field, call `backfill_incremental`, and assert `sessions` row count > 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/session_start.py` — replace `with contextlib.suppress(Exception):` in `_run_backfill()` with `try/except Exception: logger.warning(..., exc_info=True)`; add `import logging` and `logger = logging.getLogger(__name__)`
- `scripts/little_loops/session_store.py` — fix `backfill_incremental()`: reorder calls to run `_backfill_sessions` before `_backfill_tool_events` / `_backfill_messages`; or add per-sub-function `commit()` calls; consider adding `INSERT OR IGNORE` to `_backfill_tool_events` and `_backfill_messages` for consistency with `_backfill_sessions` and `_backfill_issues`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session backfill` subcommand (line 247); the `--since` path correctly mirrors the hook's discovery pattern; plain `backfill()` (no `--since`) never passes `jsonl_files` and will always show 0 sessions
- `scripts/little_loops/history_reader.py` — reads `sessions` table; all `search()` and `related_issue_events()` queries return empty without rows
- `scripts/little_loops/user_messages.py` — `get_project_folder()` (used in both `_run_backfill()` and the CLI `--since` path); same `path_str.replace("/", "-")` encoding; both resolve `~/.claude/projects/<encoded-cwd>`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/workflow_sequence/io.py` — queries `message_events` and `issue_sessions` VIEW; blocked on sessions data [Agent 1 finding]
- `scripts/little_loops/workflow_sequence/analysis.py` — queries `message_events` and `issue_sessions` VIEW; blocked on sessions data [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/session_store.py::SQLiteTransport.__init__()` and `.send()` — canonical `logger.warning(..., exc_info=True)` pattern for diagnosable background DB failures; this is the model to follow in `_run_backfill`
- `scripts/little_loops/session_store.py::_backfill_issues()` — uses `INSERT OR IGNORE` for dedup (contrast: `_backfill_tool_events` and `_backfill_messages` use plain `INSERT`; inconsistency is worth fixing)
- `scripts/little_loops/hooks/post_tool_use.py::handle()` — `contextlib.suppress(Exception)` wrapping a DB write; shows the existing pattern (no logging) — same anti-pattern to fix in `_run_backfill`

### Tests
- `scripts/tests/test_session_store.py` — `TestBackfillIncremental` class; `_make_tool_jsonl()` and `_make_msg_jsonl()` fixture helpers for minimal JSONL with `sessionId` field (model for new `_make_session_jsonl()` helper)
- `scripts/tests/test_hook_session_start.py` — `TestSessionStartBackfillThread`; `in_tmp` fixture (`os.chdir` pattern); `monkeypatch.setattr("...threading.Thread", _MockThread)` pattern for inline thread execution tests
- Add: `TestBackfillSessions.test_sessions_inserted_from_jsonl` in `scripts/tests/test_session_store.py` — write JSONL with `{type: "assistant", sessionId: "sess-1", ...}` → call `backfill_incremental(db, jsonl_files=[jsonl])` → `assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — `TestBackfillSinceFlag` class; exercises `ll-session backfill --since DATE`; all calls mock `backfill_incremental` so these pass today but confirm CLI wiring after fix [Agent 1 finding]
- Update: `test_backfill_error_does_not_propagate` in `test_hook_session_start.py` — docstring currently says "wrapped in contextlib.suppress"; update to reflect `try/except Exception: logger.warning(...)` mechanism after fix [Agent 3 finding]
- Add: `TestSessionStartBackfillThread.test_backfill_warning_logged` in `test_hook_session_start.py` — use `_inline_thread`, patch `backfill_incremental` to raise, use `caplog.at_level(logging.WARNING, logger="little_loops.hooks.session_start")` and assert `any("backfill" in r.message for r in caplog.records)` — follow pattern from `test_transport.py::TestSQLiteTransport` [Agent 3 finding]
- Note: `test_messages_and_sessions_backfilled` in `TestBackfillIncremental` asserts `counts["messages"] >= 1` but NOT `counts["sessions"]` despite its name; consider adding sessions assertion as part of this fix [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `session_store` module documentation may need updating if `backfill_incremental` call order or behavior changes

### Configuration
- N/A

## Implementation Steps

1. **Expose the exception**: temporarily change `session_start.py::_run_backfill()`'s `with contextlib.suppress(Exception):` to a bare `try/except Exception as exc: raise` and trigger a session start. Capture the actual exception type from stderr. Alternatively, call `backfill_incremental` directly in a REPL (see Proposed Solution step 1).

2. **Fix call order in `session_store.py::backfill_incremental()`**: move `counts["sessions"] = _backfill_sessions(conn, filtered)` to execute before `counts["tools"] = _backfill_tool_events(conn, filtered)` and `counts["messages"] = _backfill_messages(conn, filtered)`. This ensures `sessions` is populated even if tool/message backfill fails.

3. **Replace `contextlib.suppress` in `session_start.py::_run_backfill()`**: add `import logging` and `logger = logging.getLogger(__name__)` at module level, then replace the `with contextlib.suppress(Exception):` block with:
   ```python
   try:
       ...backfill_incremental(...)
   except Exception:
       logger.warning("session_start: backfill_incremental failed", exc_info=True)
   ```
   Follow the `SQLiteTransport.send()` model in `session_store.py`.

4. **Add unit test** in `scripts/tests/test_session_store.py` following `TestBackfillIncremental._make_tool_jsonl()` pattern:
   - Write a JSONL file with `{"type": "assistant", "sessionId": "sess-1", "timestamp": "...", "message": {...}}`
   - Call `backfill_incremental(db, jsonl_files=[jsonl])`
   - Assert `conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1`

5. **Verify end-to-end**: restart a session, wait ~5 seconds (to let the daemon thread run), then check:
   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM sessions').fetchone())"
   ll-session recent --kind all
   ```
   Also run `ll-session backfill --since 1970-01-01` to force a full re-backfill of all historical JSONL files (resets the mtime filter to `0.0`). Note: `--since 0` will fail with a date parse error; use `1970-01-01` as the epoch reset.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update docstring in `scripts/tests/test_hook_session_start.py::TestSessionStartBackfillThread::test_backfill_error_does_not_propagate` — change `"wrapped in contextlib.suppress"` to reflect `try/except Exception: logger.warning(...)` after step 3
7. Add `TestSessionStartBackfillThread.test_backfill_warning_logged` to `scripts/tests/test_hook_session_start.py` — caplog-based assertion that `logger.warning` fires when `backfill_incremental` raises (use `caplog.at_level(logging.WARNING, logger="little_loops.hooks.session_start")`)
8. Verify `scripts/little_loops/workflow_sequence/io.py` and `workflow_sequence/analysis.py` return populated data after the fix (these query `message_events` and `issue_sessions` VIEW and are currently blocked on empty sessions table)

## Impact

- **Priority**: P2 — blocks the entire session/message cross-reference layer; ENH-1710/1711 are dead without it
- **Effort**: Small-Medium — diagnosis may reveal a trivial fix (call ordering) or a schema issue
- **Risk**: Low — backfill is read-only on JSONL files; worst case is no-op
- **Breaking Change**: No

## Steps to Reproduce

1. Start any session in this project
2. Run:
   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM sessions').fetchone())"
   ```
3. Observe: `(0,)` despite `ls ~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/*.jsonl | wc -l` showing ~5000 files

## Related Key Documentation

- `docs/reference/API.md` — `little_loops.session_store` module reference
- `docs/reference/API.md` — `little_loops.hooks.session_start` hook documentation

## Labels

`bug`, `history-db`, `sessions`, `captured`

## Reopened — 2026-06-06

**Root cause confirmed**. The June 3 "fix" (reordering `_backfill_sessions` before `_backfill_tool_events`) addressed the symptom but not the cause. Investigation on 2026-06-06 confirmed the daemon thread is still being killed before `conn.commit()`:

- `last_backfill_ts` is stuck at `2026-06-03T19:47:48Z` — never updated since the last manual `ll-session backfill` run.
- 1,729 JSONL files are newer than `last_backfill_ts` but haven't been committed.
- `assistant_messages` table (added in v11 / ENH-1942, merged June 4) has **0 rows** — direct proof the daemon thread never commits: `_backfill_assistant_messages` works correctly when called manually (tested: inserted 37 rows from 5 files in isolation).
- The `sessions` table has rows only because the manual June 3 backfill pre-dated the daemon thread being the sole mechanism.

The timing: `session-start.sh` spawns a short-lived Python subprocess. After `handle()` starts the daemon thread and returns, `main_hooks()` writes to stdout and exits. Total process lifetime is ~0.1–0.5s. Processing 1,729 files takes ~4.5s+ — the thread is always killed before `conn.commit()` runs.

**Second root cause**: even after fixing thread lifetime, historical files (pre-`last_backfill_ts`) won't be reprocessed for `assistant_messages` because `backfill_incremental` only processes files newer than `last_backfill_ts`. No per-table watermark exists to detect that a new schema migration added a table needing a targeted historical re-backfill.

**Required fix**:
1. Replace `threading.Thread(daemon=True)` with a detached subprocess (`subprocess.Popen([sys.executable, '-m', 'little_loops.hooks.backfill_worker', str(_db_path)], start_new_session=True, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)`) that outlives the hook process.
2. Add per-table backfill watermarks to `meta` (e.g., `last_backfill_ts_assistant_messages`) so `backfill_incremental` can detect and re-process historical files for newly-added tables.

## Status

**Open** | Created: 2026-06-02 | Reopened: 2026-06-06 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-06-03T00:39:07 - `17557f51-d1e7-48ab-8c75-d04f0cc19f24.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `cd5941ce-4a67-45ab-bbe8-a3a963fd0340.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:35:47 - `74dfcd78-1fad-4c70-aa72-73eab649f386.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:29:59 - `288ea8fe-1443-4178-9435-e6f8b106cc59.jsonl`
- `/ll:format-issue` - 2026-06-02T23:43:17 - `5a6438e8-ff2f-4342-b911-43dcd9985f55.jsonl`

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
