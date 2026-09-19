---
id: ENH-3514
type: ENH
title: 'Policy builder: unify status/message class vocabularies and heading/legend
  conventions'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# ENH-3514: Policy builder: unify status/message class vocabularies and heading/legend conventions

## Summary

Found by ENH-3500 audit. Two class vocabularies coexist: is-error/is-warning/is-success (connected status) vs msg-error/msg-warn/msg-ok plus msg-info (Result diagnostics, scenarios, lifecycle). 'Try it' is the legend of two fieldsets; the h2s ('Result', 'Submit to host') use inline font-size:1rem while left column uses legends; dark theme 'Otherwise ->' fallback row renders as a saturated green block with italic label unlike other rows. Expected: one status vocabulary and consistent heading treatment. Evidence: auth-populated-decision_table-dark-w1280-offline.png, conn-accepted-warnings-*.


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
