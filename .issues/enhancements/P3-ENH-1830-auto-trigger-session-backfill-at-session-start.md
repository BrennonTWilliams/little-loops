---
id: ENH-1830
type: ENH
priority: P3
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - FEAT-1262
  - EPIC-1707
labels:
  - enhancement
  - captured
---

# ENH-1830: Auto-trigger `session_store.backfill()` at session start

## Summary

The `session_start` hook currently only bootstraps the DB schema (`ensure_db()`).
It never calls `backfill()`, so interactive session content — user messages and tool
calls from JSONL — only reaches `history.db` if the user manually runs
`ll-session backfill`. Wire an automatic backfill call into the session start hook
so historical data is populated without manual intervention.

## Current Behavior

`session_start` hook (`hooks/session_start.py`) calls only `ensure_db()` to bootstrap the SQLite schema. It never invokes `backfill()`, so `message_events` and `tool_events` tables remain empty for interactive sessions unless the user manually runs `ll-session backfill`. As a result, `ll-session search`, `ll-history`, and the `history_reader` API return partial or no results for most projects.

## Motivation

`history.db` is designed to be a queryable record of project activity, but the
data it contains is largely incomplete for interactive sessions. The `message_events`
and `tool_events` tables depend on JSONL-backed backfill, which is never triggered
automatically. This means `ll-session search`, `ll-history`, and the `history_reader`
read API return partial or empty results for most projects unless someone remembers
to run `ll-session backfill` manually. FEAT-1262 (session-event-capture-hook) was
the original vehicle for continuous capture but was deferred/superseded by the
hook-intent abstraction (FEAT-1116) with no replacement created.

## Expected Behavior

- `session_start` hook (or its Python intent handler) calls `session_store.backfill()`
  after `ensure_db()` succeeds
- Backfill is incremental: only JSONL files modified since the last backfill timestamp
  are processed (avoid re-scanning all files on every session start)
- Backfill runs in a background thread or subprocess so it does not add latency to
  session startup (the hook's response must be fast)
- Errors in backfill are silently swallowed (same `contextlib.suppress` pattern as
  `ensure_db()`) so a backfill failure never blocks a session
- A `last_backfill_ts` timestamp is written to the `meta` table after each successful
  incremental run

## Scope Boundaries

- **Out of scope**: Real-time/continuous event capture during a session (deferred FEAT-1262 scope)
- **Out of scope**: Backfill of non-JSONL sources
- **Out of scope**: Changes to query interfaces (`ll-session search`, `ll-history`, `history_reader`)
- **Out of scope**: Surfacing backfill progress to the user (runs silently in background)

## Implementation Steps

1. Add `last_backfill_ts` key to the `meta` table (new migration, v4)
2. Add `backfill_incremental(db_path, since_ts)` variant in `session_store.py` that
   filters JSONL files by mtime >= `since_ts`
3. Update `hooks/session_start.py` `handle()` to spawn a background thread calling
   `backfill_incremental` after `ensure_db()`, wrapped in `contextlib.suppress`
4. Update `ll-session backfill` CLI to accept `--since` flag using the same logic
5. Add unit tests covering: incremental filter, meta timestamp write, failure isolation

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `backfill_incremental()`, v4 migration
- `scripts/little_loops/hooks/session_start.py` — call backfill in background
- `scripts/little_loops/cli/session.py` — `--since` flag for `backfill` subcommand
- `scripts/tests/test_session_store.py` — incremental backfill tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/session_start.py` — imports `session_store`
- No existing callers read `last_backfill_ts` from the `meta` table (new key)

### Similar Patterns
- `hooks/session_start.py` already uses `contextlib.suppress` for `ensure_db()` — apply the same pattern for the backfill call
- `ll-session backfill` CLI provides the existing full-scan baseline to extend with `--since`

### Tests
- `scripts/tests/test_session_store.py` — incremental filter, meta timestamp write, failure isolation

### Documentation
- N/A

### Configuration
- N/A (backfill runs automatically; no new config toggles)

## API/Interface

```python
# New function in session_store.py
def backfill_incremental(db_path: Path, since_ts: float) -> None:
    """Backfill only JSONL files with mtime >= since_ts."""

# Updated CLI flag
# ll-session backfill --since <iso8601-or-unix-ts>

# New meta table key: "last_backfill_ts" → ISO 8601 timestamp string
```

## Impact

- **Priority**: P3 — Improves history completeness for `ll-session`/`ll-history` without blocking other work
- **Effort**: Small — Adds one new function variant, hooks into existing `session_start.py` pattern, extends one CLI flag
- **Risk**: Low — Errors suppressed via `contextlib.suppress`; runs in a background thread so session startup latency is unaffected
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-01T01:16:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b36ecc52-50ca-45d3-a937-1a07c2c7a5ee.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
