---
id: ENH-1832
type: ENH
priority: P4
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - EPIC-1707
  - FEAT-1112
labels:
  - enhancement
  - captured
---

# ENH-1832: Populate `file_events` table via post_tool_use hook

## Summary

The `file_events` table in `history.db` has a complete schema (`path`, `op`,
`issue_id`, `git_sha`, `session_id`) but no active write path. The `post_tool_use`
hook already fires on every tool call and writes `tool_events`; extending it to
also write a row to `file_events` when the tool is Read/Write/Edit/Glob/Grep/Bash
(with a file argument) would enable `history_reader.recent_file_events()` queries.

## Motivation

`recent_file_events()` exists as a typed read API in `history_reader.py` but always
returns `[]` because the table is empty. File-operation history would let skills like
`refine-issue` and `confidence-check` surface recently touched files related to an
issue, giving them richer context about where work is actually happening.

## Acceptance Criteria

- `post_tool_use` intent handler writes one `file_events` row per tool call where
  `tool_name` is in `{Read, Write, Edit, Glob, Grep}` or is `Bash` with a detectable
  file path argument
- `path` is stored relative to the project root (no leading `./`)
- `op` is the tool name (e.g., `"Write"`, `"Edit"`, `"Bash"`)
- `issue_id` is `NULL` unless a `.issues/` path is detected in the tool args
- `git_sha` is `NULL` (populated only if a git context is available — out of scope here)
- `history_reader.recent_file_events(path)` returns results for files that have been
  accessed
- The FTS5 `search_index` is updated with `kind='file'` rows
- Write is gated on `analytics.enabled` in config (same gate as `tool_events`)

## Implementation Steps

1. In `hooks/post_tool_use.py` `handle()`, after writing `tool_events`, add a
   `write_file_event()` branch that extracts file paths from `tool_input` based on
   `tool_name`
2. Add `write_file_event(db_path, session_id, path, op, issue_id=None)` to
   `session_store.py`
3. Update FTS5 insert to include `kind='file'` rows alongside `file_events` inserts
4. Add tests for the extraction logic (per-tool path key mapping) and the round-trip
   DB write/read

## Files to Modify

- `scripts/little_loops/hooks/post_tool_use.py` — extend handle() with file_events write
- `scripts/little_loops/session_store.py` — `write_file_event()` method
- `scripts/tests/test_session_store.py` — file_events write tests

## Session Log
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
