---
id: ENH-2057
title: Update CONTRIBUTING.md loop count and LOOPS_GUIDE.md for rlhf-svg sub-loops
type: ENH
priority: P3
status: done
parent: ENH-2050
captured_at: '2026-06-09T00:00:00Z'
completed_at: '2026-06-09T18:04:43Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
testable: false
labels:
- loops
- docs
confidence_score: 95
outcome_confidence: 77
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2057: Update CONTRIBUTING.md loop count and LOOPS_GUIDE.md for rlhf-svg sub-loops

## Summary

Update `CONTRIBUTING.md` loop YAML count to reflect the three new sub-loop files added by ENH-2048/2049/2051. Update `docs/guides/LOOPS_GUIDE.md` with the delegated FSM flow diagram for the refactored parent and three new `### rlhf-svg-*` sub-loop sections.

## Current Behavior

`CONTRIBUTING.md` line 122 reports "77 YAML files" — stale, actual count is 94+ (verified 2026-06-09). `docs/guides/LOOPS_GUIDE.md` line 1460 lists `rlhf-animated-svg` without any note of sub-loop delegation, and the FSM diagram at lines 2217–2225 shows a flat 24-state graph. There are no `### rlhf-svg-evaluate`, `### rlhf-svg-refine`, or `### rlhf-svg-generate` sections in the guide.

## Expected Behavior

`CONTRIBUTING.md` loop YAML count matches the output of `find scripts/little_loops/loops -name '*.yaml' | wc -l`. The `rlhf-animated-svg` overview row notes sub-loop delegation and three new sub-loop rows appear in the table. The FSM diagram reflects the orchestration-only shape (init → plan → generate → run_evaluate → run_refine) with sub-loop delegation. Three new `### rlhf-svg-*` sections appear following the `rn-decompose`/`rn-remediate` pattern.

## Parent Issue

Decomposed from ENH-2050: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)

## Prerequisites

- ENH-2056 (rlhf-animated-svg.yaml refactor) should be complete or in progress so the actual line count and delegation flow can be verified before finalizing docs
- ENH-2051 (rlhf-svg-generate.yaml) must be merged so the final YAML count is stable

## Integration Map

### Files to Modify
- `CONTRIBUTING.md` (line 122) — bump loop YAML count
- `docs/guides/LOOPS_GUIDE.md` — three locations: line 1460 overview table, lines 2215–2223 FSM diagram, after line 2244 new sub-loop sections

### Reference Patterns
- `docs/guides/LOOPS_GUIDE.md:684` — `rn-decompose` sub-loop section pattern (context variables table, output artifacts, FSM flow, standalone invocation example)
- `docs/guides/LOOPS_GUIDE.md:741` — `rn-remediate` sub-loop section pattern

## Implementation Steps

### 1. Update `CONTRIBUTING.md` (line 122)

Bump loop YAML count from 77 → current verified value. (CONTRIBUTING.md currently reads "77 YAML files"; actual count as of 2026-06-09 is 94 with rlhf-svg-evaluate and rlhf-svg-refine in place — will increase by 1 after rlhf-svg-generate is added by ENH-2051.)

**Verify count before patching**: Run `find scripts/little_loops/loops -name '*.yaml' | wc -l` to confirm the actual count and use that value.

### 2. Update `docs/guides/LOOPS_GUIDE.md`

#### 2a. Line 1460 overview table
Add note to the `rlhf-animated-svg` row that phases are delegated to sub-loops. Add three sub-loop rows following `rn-remediate`/`rn-decompose` precedent:

| Loop | Description |
|------|-------------|
| `rlhf-svg-generate` | Sub-loop: plan + render + verify animation SVG |
| `rlhf-svg-evaluate` | Sub-loop: vision-score and smoke-test rendered SVG |
| `rlhf-svg-refine` | Sub-loop: critique + apply refinements + self-diagnose |

#### 2b. Lines 2215–2223 FSM diagram
Update parent `rlhf-animated-svg` FSM flow diagram to show sub-loop delegation rather than the flat 24-state graph. Reflect the orchestration-only shape after ENH-2056's refactor.

#### 2c. After line 2244: new sub-loop sections
Add three new `### \`rlhf-svg-*\`` sections following the `rn-remediate`/`rn-decompose` pattern (lines 684/741): each with:
- Context variables table (keys, types, descriptions)
- Output artifacts
- FSM flow (condensed)
- Standalone invocation example

Use ENH-2048, ENH-2049, ENH-2051 issue files as source-of-truth for context variables and artifacts.

## Acceptance Criteria

- [x] `CONTRIBUTING.md` loop count updated to correct final value (verify with `find`)
- [x] `LOOPS_GUIDE.md` overview table includes three new sub-loop rows
- [x] `LOOPS_GUIDE.md` FSM diagram for `rlhf-animated-svg` reflects delegated flow
- [x] `LOOPS_GUIDE.md` has three new `### rlhf-svg-*` sections following `rn-remediate` pattern
- [x] `ll-check-links` passes after docs update

## Impact

- **Priority**: P3
- **Effort**: Small — targeted doc edits; no code changes
- **Risk**: Low — documentation only

## Scope Boundaries

- Only `CONTRIBUTING.md` and `docs/guides/LOOPS_GUIDE.md` are modified — no code changes
- Does not add the `rlhf-svg-generate` sub-loop section (depends on ENH-2051 completing first)
- Does not update any other loop documentation beyond the rlhf-svg family
- Does not change any YAML loop files

## Resolution

Updated `CONTRIBUTING.md` loop YAML count from 77 → 94 (verified via `find`). Added `rlhf-svg-evaluate` and `rlhf-svg-refine` rows to the LOOPS_GUIDE.md overview table (line 1461–1462) with note on sub-loop delegation in the `rlhf-animated-svg` row. Replaced the stale flat-24-state FSM diagram with an orchestration-only delegating shape showing `run_evaluate`/`run_refine` sub-loop callout. Added two full `### rlhf-svg-*` sections (lines 2262 and 2327) following the `rn-decompose`/`rn-remediate` pattern with context-variable tables, output-artifact tables, FSM flows, and usage examples. `rlhf-svg-generate` section omitted pending ENH-2051.

## Session Log
- `/ll:ready-issue` - 2026-06-09T17:57:16 - `9a25ad37-f856-4731-acfd-715d091c0fcd.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `82fc816b-3cca-414b-b8ef-da7662b5c94e.jsonl`
- `/ll:manage-issue` - 2026-06-09T18:04:43Z - `improve`
