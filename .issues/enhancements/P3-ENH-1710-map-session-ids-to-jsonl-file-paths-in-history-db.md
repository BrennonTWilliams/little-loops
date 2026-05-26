---
id: ENH-1710
title: Map session IDs to JSONL file paths in history.db
type: ENH
priority: P3
status: open
captured_at: "2026-05-26T01:31:23Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
---

# ENH-1710: Map session IDs to JSONL file paths in history.db

## Summary

Add a `sessions` table (or view) to `.ll/history.db` that maps `session_id` values to their corresponding JSONL file paths on disk, enabling direct navigation from any DB event to its source log.

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

## API / Interface Changes

New `sessions` table in `history.db`. New `ll-session path <session_id>` subcommand.

## Acceptance Criteria

- `ll-session path <session_id>` prints the JSONL path or exits non-zero if unknown.
- After `backfill()`, all session IDs present in `tool_events` or `message_events` have a corresponding row in `sessions` with a non-null `jsonl_path`.

## Status

---

open

## Session Log
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
