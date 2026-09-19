---
id: ENH-3511
type: ENH
title: 'Policy builder: explain disabled controls (aria-describedby / visible reason)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# ENH-3511: Policy builder: explain disabled controls (aria-describedby / visible reason)

## Summary

Found by ENH-3500 audit. ~13 bare .disabled sites and zero aria-disabled/aria-describedby; only #conn-unavailable gives a reason. Disabled Submit before review, delete-outcome-in-use, rule up/down at ends, and Copy/Download on invalid models give no reason (title only on some). Repro: any mode with invalid model -> Copy/Download disabled with no explanation next to them; connected panel before review -> Submit disabled. Expected: visible/associated reason. Native disabled semantics may stay. Evidence: auth-invalid-model-*, conn-issue-selected-*, conn-review-none-*.


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
