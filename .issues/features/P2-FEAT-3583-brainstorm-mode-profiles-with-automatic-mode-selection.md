---
id: FEAT-3583
type: FEAT
title: Brainstorm mode profiles with automatic mode selection
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:13Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3583: Brainstorm mode profiles with automatic mode selection

## Summary

Add **mode profiles as data** to the brainstorm engine plus **automatic mode
selection**: profiles `artifact`, `visual`, `functional`, `business`, selected by
`mode: auto` (default) in the first state after `init`.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

- Each profile (a small YAML preset alongside the loop) sets: `reframe` on/off,
  default grid axes, idea schema, `ground` (none|codebase|web), `materialize`
  (none|render), tournament rubric, `premortem` on/off, output shape
  (grid | portfolio | winner + risks).
- `classify_mode` state runs right after `init` when `mode=auto`: LLM emits
  `{mode, confidence, rationale}` to the run dir; confidence below a threshold falls
  back to `artifact`.
- `mode=<x>` skips classification. Individual profile knobs can be overridden via
  context for mixed briefs.
- Downstream states read resolved profile values rather than hardcoded behavior;
  gated states route via `classify`-style routing like the current `route_sink`.

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

1. Define profile schema and the four presets.
2. Add `classify_mode` + `resolve_profile` states.
3. Thread resolved values into reframe/diverge/tournament/output prompts.
4. Tests for resolution precedence (explicit > override > profile > fallback).

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- Four profile files exist and are validated by a schema/test.
- One reference brief per mode is classified to the expected profile (test with a
  stubbed classifier output plus a documented manual reference run).
- Explicit `mode=` bypasses `classify_mode`; per-knob override beats profile default.
- Profile resolution is deterministic (script), and the resolved profile is written
  to `${context.run_dir}/profile.json`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:40 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
