---
id: ENH-3338
type: ENH
title: Add static sweep detecting unsafe context/captured interpolation in loop YAMLs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# ENH-3338: Add static sweep detecting unsafe context/captured interpolation in loop YAMLs

## Summary

Write a recursive, both-host-shape-aware sweep (heredoc + python3 -c) that classifies each ${context.*}/${captured.*} interpolation site per the rule in BUG-3331, asserts against a checked-in ratcheting baseline file, and is green on main at every commit.

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
