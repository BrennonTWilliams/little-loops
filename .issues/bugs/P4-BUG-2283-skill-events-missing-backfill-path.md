---
id: BUG-2283
type: BUG
priority: P4
status: done
title: "skill_events table has no backfill path \u2014 ll-logs stats undercounts pre-init\
  \ invocations"
discovered_date: 2026-06-25
discovered_by: capture-issue
captured_at: '2026-06-25T01:38:33Z'
completed_at: '2026-06-25T02:00:18Z'
relates_to:
- ENH-1833
labels:
- bug
- session-store
- history
confidence_score: 98
outcome_confidence: 89
score_complexity: 23
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2283: skill_events table has no backfill path — ll-logs stats undercounts pre-init invocations

## Summary

`ll-logs stats` reports skill invocation counts from `history.db`'s `skill_events` table,
which is only populated by the `user_prompt_submit` runtime hook (added in ENH-1833, June 1 2026).
`backfill()` and `backfill_incremental()` in `session_store.py` have no `_backfill_skill_events()`
step, so any JSONL-logged invocations that predate the DB initialization timestamp are permanently
absent from the count.

## Current Behavior

`ll-logs stats` reads skill invocation counts exclusively from `history.db`'s `skill_events` table.
Because `backfill()` and `backfill_incremental()` in `session_store.py` have no
`_backfill_skill_events()` step, JSONL-logged invocations that predate the DB initialization
timestamp are permanently absent.

**Example**: `tradeoff-review-issues` shows 2 invocations in `ll-logs stats`, but 4 invocations
exist in JSONL — 2 occurred before the DB was initialized (June 2–3, before 01:06:22Z) and were
never captured.

Post-DB-init capture rate is ~99–100% (hook working correctly). The entire undercount is pre-init
history.

## Steps to Reproduce

1. Identify a skill that was invoked before `history.db` was initialized (JSONL records exist pre-init)
2. Run `ll-session backfill`
3. Run `ll-logs stats --project .`
4. Observe: pre-init invocations are absent from the count; only post-init sessions appear in the skill stats

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

## Impact

- **Priority**: P4 — Historical accuracy gap only; does not affect real-time capture (hook correct post-init). Low urgency with no user-facing breakage.
- **Effort**: Small — Add `_backfill_skill_events()` following the `_backfill_messages` pattern and wire into two existing call sites (`backfill` and `backfill_incremental`).
- **Risk**: Low — Uses `INSERT OR IGNORE`; idempotent, no existing data modified or at risk.
- **Breaking Change**: No

## Resolution

Added `_backfill_skill_events(conn, jsonl_files)` to `session_store.py` following the `_backfill_messages` pattern. The function scans user JSONL records for `<command-name>/ll:<name></command-name>` signals and inserts into `skill_events`. Wired into both `backfill()` and `backfill_incremental()` (with a per-table watermark in incremental, matching the `assistant_messages` self-healing pattern). Added 5 unit tests in `TestBackfillSkillEvents`.

## Session Log
- `/ll:ready-issue` - 2026-06-25T01:51:54 - `aebd3ceb-67e0-4845-8879-c31cafcdb38c.jsonl`
- `/ll:confidence-check` - 2026-06-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4646b6c-126e-4f42-b27d-67bef4444089.jsonl`
- `/ll:format-issue` - 2026-06-25T01:43:19 - `9f7bef55-c353-41ec-9464-e2f083ac0301.jsonl`
- `/ll:capture-issue` - 2026-06-25T01:38:33Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d627bb2-ced2-4076-9ec1-8bd9033c843a.jsonl`
