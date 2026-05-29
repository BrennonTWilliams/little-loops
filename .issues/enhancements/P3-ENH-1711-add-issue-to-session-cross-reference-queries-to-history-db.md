---
id: ENH-1711
title: Add issue-to-session cross-reference queries to history.db
type: ENH
priority: P3
status: open
captured_at: "2026-05-26T01:31:23Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
relates_to: [ENH-1710]
parent: EPIC-1707
blocked_by: [ENH-1752]
---

# ENH-1711: Add issue-to-session cross-reference queries to history.db

## Summary

Enable querying which sessions touched a given issue (and vice versa) by joining `issue_events` lifecycle timestamps with co-occurring `message_events` and `tool_events` session IDs in `history.db`.

## Motivation

`history.db` contains both `issue_events` (with `issue_id` and timestamps) and `message_events` / `tool_events` (with `session_id` and timestamps). The link between them is implicit: a session "worked on" an issue if its messages overlap the issue's active period. Making this join explicit and queryable closes the second gap in the issue → session → log drill-down chain.

Practically: `ll-history show ENH-1710` should be able to list the sessions that worked on that issue, and `ll-session recent --issue ENH-1710` should filter to those sessions.

## Implementation Steps

1. **Depends on ENH-1710** for the `sessions` table (session_id → JSONL path mapping).
2. Add a `CREATE VIEW issue_sessions AS ...` that joins `issue_events` to `message_events` via overlapping timestamps within the same `session_id`. A session "touches" an issue if any of its messages fall between `captured_at` and `completed_at` (or now, if open).
3. Alternatively, add a `session_id` column to `issue_events` populated when an `issue.*` event is emitted during a live session (the `SQLiteTransport` already has session context available via the event payload).
4. Add `ll-session recent --issue <ID>` filter flag.
5. Add `ll-history sessions <ID>` subcommand that lists sessions by issue ID with their JSONL paths.

## API / Interface Changes

- New `issue_sessions` view (or `session_id` column on `issue_events`).
- `ll-session recent --issue <ID>` flag.
- `ll-history sessions <ID>` subcommand.

## Acceptance Criteria

- `ll-history sessions ENH-1710` returns at least one session row after that issue has been worked on in a session where backfill was run.
- `ll-session recent --issue <ID>` filters output to matching sessions.

## Status

---

open

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
