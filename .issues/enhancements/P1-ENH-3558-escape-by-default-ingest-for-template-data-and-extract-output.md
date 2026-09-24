---
id: ENH-3558
type: ENH
title: Escape-by-default ingest for template data and extract output
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
---

# ENH-3558: Escape-by-default ingest for template data and extract output

## Summary

Add idempotent escape_data with a path-based markup allowlist and URL scheme rule, apply it in build_dashboard_html and extract_data, strip the markup annotation from the schema sent to the host, and make the extract prompt request decoded plain text, leaving render_template byte-identical.

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
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
