---
id: ENH-3510
type: ENH
title: 'Policy builder: add empty-state text to dimension, rule, outcome lists and
  issue selector'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:56Z'
relates_to:
- ENH-3500
---

# ENH-3510: Policy builder: add empty-state text to dimension, rule, outcome lists and issue selector

## Summary

Found by ENH-3500 audit. Dimensions, rules and outcomes lists render nothing when empty (children=0, no text) in decision_table/lifecycle; the connected issue selector shows no note when the issue list is empty (conn-issue-note is blank). Only scenarios has 'No scenarios yet.'. Zero-dimension rubric/decision_table also reports 'No issues detected.' with export enabled. Repro: open offline builder, Open project with dimensions=[] (or Start blank in rubric); serve with ./issues returning {issues:[]}. Expected: a consistent empty-state hint per list. Evidence (run .loops/runs/enh-3500-audit-final/evidence): auth-empty-dimensions-*, auth-empty-rules-*, auth-empty-outcomes-*, conn-issues-empty-*.


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
