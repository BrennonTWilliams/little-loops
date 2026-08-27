---
id: BUG-3341
type: BUG
title: Convert class-B LLM-output interpolations to heredoc-to-file (67 sites)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
parent: EPIC-3336
---

# BUG-3341: Convert class-B LLM-output interpolations to heredoc-to-file (67 sites)

## Summary

Convert the 67 class-B LLM-output interpolation sites to Option B (per-site quoted heredoc writing captured output to a run-dir file, then opened from the Python heredoc), using the LL_RAW_9F3C1A7E_EOF sentinel and <state>-<capture>.txt naming, hoisting the heredoc above any enclosing if/for.

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
