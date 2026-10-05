---
id: BUG-3741
type: BUG
title: FSM action_complete session_jsonl attributes the wrong transcript when sessions
  run concurrently
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:09:46Z'
labels:
- loops
- fsm
---

# BUG-3741: FSM action_complete session_jsonl attributes the wrong transcript when sessions run concurrently

## Summary

The FSM executor's `action_complete.session_jsonl` (shown as `session=` in `ll-loop` output and history) was resolved by `get_current_session_jsonl()`, which returns the most-recently-modified `.jsonl` in the project's session folder. When another host session writes in the same project concurrently, the wrong transcript is recorded. Observed: `refine_followup` in run `refine-to-ready-issue-20261005T130338` was logged against a concurrent `/ll:manage-issue FEAT-3681` session (`250ddee1...`) instead of its own (`2e17f620...`).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`executor.py` ignored `ActionResult.session_id` (FEAT-2711, the host-reported `system/init` session ID) and used the mtime heuristic.

## Resolution

`get_current_session_jsonl()` gained an optional `session_id` that resolves `<session_id>.jsonl` directly (path-like IDs rejected, unknown IDs fall back to the mtime heuristic). The executor passes `result.session_id`. Tests added in `test_session_log.py` and `test_fsm_executor.py`.

## Status

**Open** | Created: 2026-10-05 | Priority: P3
