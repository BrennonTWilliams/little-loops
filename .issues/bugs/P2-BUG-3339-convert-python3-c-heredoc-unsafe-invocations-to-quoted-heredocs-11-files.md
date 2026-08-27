---
id: BUG-3339
type: BUG
title: Convert python3 -c heredoc-unsafe invocations to quoted heredocs (11 files)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# BUG-3339: Convert python3 -c heredoc-unsafe invocations to quoted heredocs (11 files)

## Summary

Convert the 53 python3 -c "..." interpolation sites (11 files under the narrow scope) to quoted python3 << PYEOF heredocs so they stop being shell-injectable, validating each converted file with ll-loop validate.

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
- `/ll:scope-epic` - 2026-08-27T17:51:45 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
