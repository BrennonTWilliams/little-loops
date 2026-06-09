---
id: ENH-2057
title: Update CONTRIBUTING.md loop count and LOOPS_GUIDE.md for rlhf-svg sub-loops
type: ENH
priority: P3
status: open
parent: ENH-2050
captured_at: '2026-06-09T00:00:00Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
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
- `docs/guides/LOOPS_GUIDE.md:684` — `rn-remediate` sub-loop section pattern (context variables table, output artifacts, FSM flow, standalone invocation example)
- `docs/guides/LOOPS_GUIDE.md:741` — `rn-decompose` sub-loop section pattern

## Implementation Steps

### 1. Update `CONTRIBUTING.md` (line 122)

Bump loop YAML count from 77 → 81 to reflect the three new YAML files added by ENH-2048, ENH-2049, and ENH-2051. (CONTRIBUTING.md currently reads "77 YAML files"; actual root count is already 80 with evaluate and refine in place — will be 81 after generate is added by ENH-2051.)

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

- [ ] `CONTRIBUTING.md` loop count updated to correct final value (verify with `find`)
- [ ] `LOOPS_GUIDE.md` overview table includes three new sub-loop rows
- [ ] `LOOPS_GUIDE.md` FSM diagram for `rlhf-animated-svg` reflects delegated flow
- [ ] `LOOPS_GUIDE.md` has three new `### rlhf-svg-*` sections following `rn-remediate` pattern
- [ ] `ll-check-links` passes after docs update

## Impact

- **Priority**: P3
- **Effort**: Small — targeted doc edits; no code changes
- **Risk**: Low — documentation only

## Session Log
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `82fc816b-3cca-414b-b8ef-da7662b5c94e.jsonl`
