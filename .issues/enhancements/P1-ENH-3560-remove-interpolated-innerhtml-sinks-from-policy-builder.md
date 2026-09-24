---
id: ENH-3560
type: ENH
title: Remove interpolated innerHTML sinks from policy builder
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
---

# ENH-3560: Remove interpolated innerHTML sinks from policy builder

## Summary

Replace the three model-state-interpolating innerHTML assignments in policy-router-builder.html.tmpl with createElement/textContent and add a Node hostile-project test plus a static check that fails on any innerHTML/insertAdjacentHTML template literal containing ${.

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
- `/ll:scope-epic` - 2026-09-24T18:30:40 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
