---
id: ENH-1834
type: ENH
priority: P5
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - EPIC-1707
  - ENH-1833
labels:
  - enhancement
  - captured
---

# ENH-1834: Record `ll-` CLI command invocations in history.db

## Summary

When a user runs `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint`, or any other
`ll-` CLI tool, the invocation itself (binary name, args, start timestamp, exit code,
duration) is not persisted to `history.db`. Downstream events (loop state transitions,
issue lifecycle changes) are recorded, but the top-level CLI call that caused them is
not. This makes it impossible to correlate "how many times was `ll-loop run` invoked
this month" or "what was the exit code of the last `ll-sprint` run" from the DB.

## Motivation

CLI invocation history enables usage analytics and debugging. Combined with
`loop_events` and `issue_events`, it provides a complete audit trail: what was
invoked, what states it transitioned through, and what issues it affected.

## Acceptance Criteria

- A new `cli_events` table records: `ts`, `binary`, `args` (JSON array, truncated),
  `exit_code`, `duration_ms`
- Each `ll-` CLI entry point writes a row at startup (with `exit_code=NULL`) and
  updates it on exit with the actual exit code and duration
- `ll-session recent --kind cli` returns the captured rows
- The write path is a thin wrapper around the existing CLI entry points — no
  changes to core logic required

## Implementation Steps

1. New migration adding `cli_events` table to `session_store.py`
2. Add `kind='cli'` to `_VALID_KINDS` and `_KIND_TABLE`
3. Add a `cli_event_context(db_path, binary, args)` context manager to
   `session_store.py` that inserts on enter and updates exit_code/duration on exit
4. Wrap `main()` in each CLI entry point with the context manager (or add to a
   shared `cli_main()` wrapper)
5. Tests for the context manager (normal exit, exception exit, duration accuracy)

## Files to Modify

- `scripts/little_loops/session_store.py` — `cli_events` table, context manager
- `scripts/little_loops/cli/*.py` — wrap `main()` entry points
- `scripts/tests/test_session_store.py` — CLI event tests

## Session Log
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
