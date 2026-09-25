---
id: FEAT-3585
type: FEAT
title: 'Brainstorm materialize state: rendered mockups judged visually'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3585: Brainstorm materialize state: rendered mockups judged visually

## Summary

Add a gated `materialize` state for **visual** brainstorming: finalists are rendered
as standalone HTML/SVG mockups, screenshotted with Playwright, and the tournament
judges **image pairs** instead of text descriptions.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

- Visual profile grid axes are visual dimensions (e.g. density × palette/typography
  temperament).
- For each shortlisted idea: LLM writes a self-contained HTML/SVG mockup under
  `${context.run_dir}/mockups/`; a Playwright probe (existing on-demand loop +
  probe pattern under `.loops/`, resolving Playwright from the global npm install)
  captures a PNG.
- Tournament pairs are judged from the two screenshots side by side (position
  swapped).
- Output includes a gallery section linking mockups + screenshots.
- Degrades gracefully when Playwright is unavailable: judges HTML source and notes
  the degradation in the report.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- Mockups and screenshots land only under the run dir.
- A render failure for one idea drops that idea, not the run.
- No pytest gate depends on Playwright (browser probes stay on-demand).
- Reference visual-mode run produces ≥ N rendered finalists and a ranked gallery.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:48 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
