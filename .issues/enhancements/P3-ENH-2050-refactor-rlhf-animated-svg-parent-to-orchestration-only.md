---
id: ENH-2050
title: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)
type: ENH
priority: P3
status: open
parent: ENH-2044
captured_at: '2026-06-09T00:00:00Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
labels:
- loops
- fsm
- refactoring
---

# ENH-2050: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)

## Summary

With the three sub-loops (ENH-2048, ENH-2049, ENH-2051) created, refactor `rlhf-animated-svg.yaml` to delegate each phase via `loop: + with:`, reducing it to ~400 lines of orchestration. Add the parent test class and update docs/CONTRIBUTING.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Prerequisites

- ENH-2051 (rlhf-svg-generate), ENH-2048 (rlhf-svg-evaluate), ENH-2049 (rlhf-svg-refine) must be merged

## Implementation Steps

### 1. Refactor `scripts/little_loops/loops/rlhf-animated-svg.yaml`

Retained states: `init`, `validate_input`, `input_missing`, `check_oscillation`, `check_score_streak`, `_score_streak_route`, `concept_reset`, `check_replan_budget`, `write_final_summary`, `restore_best`, `done`, `plan_failed`, `failed`

Flow becomes:
```
init → validate_input → [sub: rlhf-svg-generate] → [sub: rlhf-svg-evaluate]
  → VISION_PASS → write_final_summary → restore_best → done
  → VISION_FAIL → check_oscillation/check_score_streak guards
    → [sub: rlhf-svg-refine] → [sub: rlhf-svg-evaluate] → ...
```

Replace generate/evaluate/refine inline states with sub-loop delegation using `loop: + with:` syntax. Pass `global_iteration: ${state.iteration}` to generate and refine sub-loops.

Target: ≤ 450 lines in parent.

### 2. Update `scripts/tests/test_builtin_loops.py`

Write new class `TestRlhfAnimatedSvgParentOrchestration`:
- Assert extracted states absent from parent: `plan_animation`, `render_animation`, `verify_render`, `smoke_test`, `score`, `track_correlation`, `rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`
- Assert delegation states have `loop: rlhf-svg-generate/evaluate/refine` with correct `with:` keys
- Assert retained states present: `init`, `validate_input`, `check_oscillation`, `check_score_streak`, `write_final_summary`, `done`, `failed`
- Assert parent is ≤ 450 lines

Model: `TestRnPlanDelegatesResearchToOracle` (line 6185).

### 3. Update `CONTRIBUTING.md` (line 122)

Bump loop YAML count from 78 → 81 to reflect the three new YAML files.

### 4. Update `docs/guides/LOOPS_GUIDE.md`

- Lines 2215–2223: Update parent `rlhf-animated-svg` FSM flow diagram to show sub-loop delegation rather than the flat 24-state graph
- After line 2244: Add three new `### \`rlhf-svg-*\`` sections following the `rn-remediate`/`rn-decompose` pattern (lines 684/741): each with context variables table, output artifacts, FSM flow, and standalone invocation example
- Line 1460 overview table: add note that phases are delegated to sub-loops; add three sub-loop rows following `rn-remediate`/`rn-decompose` precedent

## Scope Boundaries

- **In scope**: Refactoring the parent YAML to orchestration-only, parent test class, CONTRIBUTING count, LOOPS_GUIDE docs
- **Out of scope**: Creating the sub-loop YAMLs themselves (ENH-2048, ENH-2049, ENH-2051), changing external context parameters of `rlhf-animated-svg`

## Acceptance Criteria

- [ ] Parent loop passes `ll-loop validate`
- [ ] Parent loop body is ≤ 450 lines
- [ ] `TestRlhfAnimatedSvgParentOrchestration` passes
- [ ] End-to-end run of `rlhf-animated-svg` produces the same artifact quality as pre-decomposition
- [ ] `CONTRIBUTING.md` loop count updated to 81
- [ ] `LOOPS_GUIDE.md` updated with sub-loop delegation flow and three new sub-sections

## Impact

- **Priority**: P3
- **Effort**: Large — surgical extraction of ~1600 lines, parent test class authoring, docs updates
- **Risk**: Medium — complex refactoring; mitigated by `ll-loop validate` and ENH-1936 precedent

## Session Log
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
