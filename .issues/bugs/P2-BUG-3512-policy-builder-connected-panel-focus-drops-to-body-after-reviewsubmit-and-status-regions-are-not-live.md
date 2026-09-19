---
id: BUG-3512
type: BUG
title: 'Policy builder connected panel: focus drops to BODY after Review/Submit and
  status regions are not live'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# BUG-3512: Policy builder connected panel: focus drops to BODY after Review/Submit and status regions are not live

## Summary

Found by ENH-3500 audit (keyboard traces kb-happy-path, kb-outcome-unknown, kb-rejected). After Enter on Review and Enter on Submit, document.activeElement becomes BODY (control disabled/re-rendered), so keyboard users lose place. #conn-status, #conn-notices and #conn-review-info have no role=status/aria-live, so accepted/rejected/outcome-unknown transitions and review results are not announced (DOM announcement support only; no manual screen-reader check performed). Expected: focus stays on or moves to a sensible control/status; outcome text announced. Evidence: kb-*-keyboard.json.


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
