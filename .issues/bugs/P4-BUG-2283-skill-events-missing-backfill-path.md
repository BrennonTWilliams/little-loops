---
id: BUG-2283
type: BUG
priority: P4
status: open
title: skill_events table has no backfill path — ll-logs stats undercounts pre-init invocations
discovered_date: 2026-06-25
discovered_by: capture-issue
captured_at: '2026-06-25T01:38:33Z'
relates_to:
- ENH-1833
---

# BUG-2283: skill_events table has no backfill path — ll-logs stats undercounts pre-init invocations

## Summary

`ll-logs stats` reports skill invocation counts from `history.db`'s `skill_events` table,
which is only populated by the `user_prompt_submit` runtime hook (added in ENH-1833, June 1 2026).
`backfill()` and `backfill_incremental()` in `session_store.py` have no `_backfill_skill_events()`
step, so any JSONL-logged invocations that predate the DB initialization timestamp are permanently
absent from the count.

**Observed**: `tradeoff-review-issues` shows 2 invocations in `ll-logs stats`.  
**Actual**: 4 invocations exist in JSONL — 2 occurred before the DB was initialized (June 2 and June 3 before 01:06:22Z) and were never captured.

Post-DB-init capture rate is ~99-100% for all skills (hook is working correctly).
The entire undercount is pre-init history.

## Root Cause

`session_store.py::backfill()` (line 1922) calls:
- `_backfill_issues`
- `_backfill_snapshots`
- `_backfill_loops`
- `_backfill_tool_events`
- `_backfill_messages`
- `_backfill_assistant_messages`
- `_backfill_sessions`

There is no `_backfill_skill_events(conn, jsonl_files)` call. The `skill_events` table was added
in schema v7 (ENH-1833) but the backfill routine was never extended to populate it.

`backfill_incremental()` (line 1970) has the same gap.

## Expected Behavior

Running `ll-session backfill` (or any incremental backfill) should scan JSONL user records for
the `<command-name>/ll:<name>` signal pattern (same logic as `_COMMAND_NAME_SKILL_RE` in
`cli/logs.py:209`) and populate `skill_events` for any sessions not yet covered.

`ll-logs stats` should then reflect the true invocation count across all JSONL history, not just
post-init sessions.

## Implementation Steps

1. Add `_backfill_skill_events(conn, jsonl_files)` to `session_store.py`:
   - Iterate JSONL files; for each `type == "user"` record, check for `<command-name>/ll:` pattern
   - Extract `skill_name` (strip `</command-name>` suffix if present, as `_detect_ll_signal` does)
   - Extract `args` from `<command-args>...</command-args>` tag (if present)
   - Use `INSERT OR IGNORE` into `skill_events(ts, session_id, skill_name, args)` — idempotent
   - Return count of new rows inserted

2. Call `_backfill_skill_events(conn, jsonl_files)` from `backfill()` at line ~1961
   and from `backfill_incremental()` at line ~2013

3. Add unit test in `scripts/tests/` verifying that a JSONL file with a `<command-name>/ll:` user
   record populates `skill_events` after `backfill()` is called

## Anchor References

- `session_store.py::backfill` — missing call site (line ~1922)
- `session_store.py::backfill_incremental` — missing call site (line ~1970)
- `session_store.py::_backfill_messages` — pattern to follow (line 1218)
- `cli/logs.py::_COMMAND_NAME_SKILL_RE` — regex to reuse: `r"<command-name>/ll:(\S+)"` (line 209)
- `cli/logs.py::_detect_ll_signal` — full signal detection logic to reference (line 297)
- `session_store.py::record_skill_event` — write function to call or replicate (line 672)

## Verification

After fix: run `ll-session backfill` on this project then `ll-logs stats --project .` and
verify `tradeoff-review-issues` shows ≥ 4 (not 2).

## Session Log
- `/ll:capture-issue` - 2026-06-25T01:38:33Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d627bb2-ced2-4076-9ec1-8bd9033c843a.jsonl`
