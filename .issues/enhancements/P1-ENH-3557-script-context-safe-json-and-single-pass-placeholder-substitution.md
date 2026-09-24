---
id: ENH-3557
type: ENH
title: Script-context-safe JSON and single-pass placeholder substitution
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
---

# ENH-3557: Script-context-safe JSON and single-pass placeholder substitution

## Summary

Add script_json helper (escape <, >, &, U+2028, U+2029 as JSON unicode escapes) for every json.dumps spliced into HTML in policy_builder.py and dashboard.py, and replace the chained html.replace placeholder splices in render_policy_builder_html() with one re.sub pass, pinned by hostile </script> and placeholder-token tests.

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
