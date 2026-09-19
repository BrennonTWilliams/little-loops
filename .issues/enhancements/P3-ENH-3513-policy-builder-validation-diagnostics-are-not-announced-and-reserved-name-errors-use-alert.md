---
id: ENH-3513
type: ENH
title: 'Policy builder: validation diagnostics are not announced and reserved-name
  errors use alert()'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# ENH-3513: Policy builder: validation diagnostics are not announced and reserved-name errors use alert()

## Summary

Found by ENH-3500 audit. #messages (Result diagnostics) is not a live region; after an edit or Open project produces msg-error diagnostics, copy/download are disabled but only #live-status ('Project opened.') is announced. #import-diagnostics is polite even for errors. add-outcome/add-dim reserved or duplicate names use blocking alert() instead of inline messages. Repro: open a project with a bogus dimension type; try adding outcome 'done' in decision_table. Expected: errors announced (assertive or status) and inline. Evidence: auth-invalid-model-*, live-import-error-offline.


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
