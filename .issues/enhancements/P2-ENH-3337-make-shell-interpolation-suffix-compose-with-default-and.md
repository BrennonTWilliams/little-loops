---
id: ENH-3337
type: ENH
title: Make :shell interpolation suffix compose with :default= and ?
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# ENH-3337: Make :shell interpolation suffix compose with :default= and ?

## Summary

Normalize interpolation.py suffix parsing so :shell composes with :default= and ? in every ordering (fixing the silent misparse and the None-before-quote ordering), with unit tests for all four orderings; this unblocks the class-A/B conversions at the 130 sites that already carry a default/optional suffix.

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
- `/ll:scope-epic` - 2026-08-27T17:51:44 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
