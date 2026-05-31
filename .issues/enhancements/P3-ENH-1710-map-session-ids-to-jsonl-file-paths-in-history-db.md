---
id: ENH-1710
title: Map session IDs to JSONL file paths in history.db
type: ENH
priority: P3
status: open
captured_at: "2026-05-26T01:31:23Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
parent: EPIC-1707
---

# ENH-1710: Map session IDs to JSONL file paths in history.db

## Summary

Add a `sessions` table (or view) to `.ll/history.db` that maps `session_id` values to their corresponding JSONL file paths on disk, enabling direct navigation from any DB event to its source log.

## Current Behavior

`history.db` event tables (`tool_events`, `message_events`, `file_events`, `user_corrections`) carry a `session_id` column with no corresponding mapping table. The session-ID-to-JSONL-path mapping is built at query time by `ll-logs discover` scanning `~/.claude/projects/`, but the result is not persisted, leaving no way to navigate from a DB event back to its source log file.

## Expected Behavior

- A `sessions` table in `history.db` maps each `session_id` to its JSONL file path and metadata.
- `ll-session path <session_id>` resolves and prints the JSONL path directly from the DB, exiting non-zero if unknown.
- After `ll-session backfill`, all session IDs present in `tool_events` or `message_events` have a corresponding `sessions` row with a non-null `jsonl_path`.
- `ll-session recent` output includes the JSONL path alongside session metadata.

## Motivation

Every event table in `history.db` (`tool_events`, `message_events`, `file_events`, `user_corrections`) carries a `session_id` column, but the DB has no way to resolve that ID back to the JSONL file it came from. `ll-logs discover` builds this mapping at query time by scanning `~/.claude/projects/`, but the result is not persisted. This creates a broken link in what should be a navigable chain: issue → session → log.

Closing this gap is the cheapest step toward drill-down from a high-level issue to full session detail, and is a prerequisite for the issue-to-session cross-reference (ENH-1711) and any future LCM-style history navigation.

## Implementation Steps

1. Add a `sessions` table in a new schema migration:
   ```sql
   CREATE TABLE sessions (
       session_id TEXT PRIMARY KEY,
       jsonl_path TEXT NOT NULL,
       started_at TEXT,
       project_path TEXT
   );
   ```
2. Populate it during `backfill()` by correlating session IDs found in JSONL files with their file paths (already parsed in `_backfill_tool_events` and `_backfill_messages`).
3. Populate it live in `SQLiteTransport.send()` on the first event of each `session_id` by resolving the path from `ll-logs discover` output or a direct glob of the logs dir.
4. Add `ll-session path <session_id>` subcommand that prints the resolved JSONL path.
5. Update `ll-session recent` output to include the JSONL path alongside session metadata.

## API/Interface

New `sessions` table in `history.db`. New `ll-session path <session_id>` subcommand.

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    jsonl_path TEXT NOT NULL,
    started_at TEXT,
    project_path TEXT
);
```

## Scope Boundaries

- **In scope**: `sessions` table schema and migration; `backfill()` population from existing JSONL files; live population in `SQLiteTransport.send()` on first event per session; `ll-session path <session_id>` subcommand; `ll-session recent` JSONL path display.
- **Out of scope**: Issue-to-session cross-reference (ENH-1711); LCM-style history navigation; querying or indexing session content; changes to existing event tables or their schemas.

## Acceptance Criteria

- `ll-session path <session_id>` prints the JSONL path or exits non-zero if unknown.
- After `backfill()`, all session IDs present in `tool_events` or `message_events` have a corresponding row in `sessions` with a non-null `jsonl_path`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` - Add `sessions` table schema and schema migration
- `scripts/little_loops/transport.py` - Populate `sessions` on first event of each `session_id` in `SQLiteTransport.send()`
- `scripts/little_loops/cli/session.py` - Add `path` subcommand; update `recent` output to include JSONL path

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` `backfill()` function - Correlate session IDs from JSONL files during backfill

### Similar Patterns
- `ll-logs discover` in `scripts/little_loops/cli/` - Existing session-ID-to-path mapping logic to reuse/adapt

### Tests
- `scripts/tests/test_session_store.py` - Add tests for `sessions` table creation, migration, and `backfill()` population
- `scripts/tests/test_ll_session.py` - Add tests for `path` subcommand (found path, unknown session_id)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 - Foundational plumbing that unblocks ENH-1711 and session drill-down features; not urgent standalone.
- **Effort**: Small - Additive schema migration + backfill update + one new CLI subcommand; reuses existing `ll-logs discover` mapping logic.
- **Risk**: Low - Purely additive change; no existing tables, APIs, or CLI contracts are modified.
- **Breaking Change**: No

## Labels

`enhancement`, `database`, `session-management`, `captured`

## Status

**Open** | Created: 2026-05-26 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:format-issue` - 2026-05-26T20:18:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f238e1de-2a0d-4c63-94af-3f5bc586be30.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
