---
id: BUG-3439
type: BUG
title: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above
  128 KiB
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3439: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above 128 KiB

## Summary

DefaultActionRunner spawns every shell action as ["bash", "-c", action] (fsm/runners.py:348), so any :shell-interpolated capture exceeding Linux MAX_ARG_STRLEN (131072 B) raises OSError Errno 7 in every loop, not just loop-router. Reproduced by test_write_sub_loop_output_survives_oversized_stream (rendered 264085 B). Fix at the runner: feed the script on stdin (bash -s) or via a temp file, mirror in the executor _run_subprocess shell path, keep the loop-router test as the regression pin and make its docstring platform-honest (A4 / BUG-3334 AC14).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]


## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
