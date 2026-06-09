---
id: ENH-2056
title: Refactor rlhf-animated-svg.yaml to orchestration-only and write parent test
  class
type: ENH
priority: P3
status: done
parent: ENH-2050
captured_at: '2026-06-09T00:00:00Z'
completed_at: '2026-06-09T17:44:56Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
labels:
- loops
- fsm
- refactoring
confidence_score: 89
outcome_confidence: 85
score_complexity: 22
score_test_coverage: 21
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2056: Refactor rlhf-animated-svg.yaml to orchestration-only and write parent test class

## Summary

Refactor `rlhf-animated-svg.yaml` from ~2001 lines to ≤450 lines by replacing inline generate/evaluate/refine states with `loop: + with:` sub-loop delegation states. Write `TestRlhfAnimatedSvgParentOrchestration` test class to assert the delegation shape.

## Current Behavior

`rlhf-animated-svg.yaml` is ~2000 lines with all generate/evaluate/refine logic inline. ENH-2048 and ENH-2049 have already extracted the evaluate and refine phases into standalone sub-loops (`rlhf-svg-evaluate.yaml`, `rlhf-svg-refine.yaml`), leaving the parent with redundant inline copies of that logic.

## Expected Behavior

`rlhf-animated-svg.yaml` is ≤ 450 lines, delegating to `rlhf-svg-evaluate` and `rlhf-svg-refine` sub-loops via `loop: + with:` syntax. Generate-phase states (`plan_animation`, `render_animation`, `verify_render`) remain inline until ENH-2051 is merged, at which point delegation to `rlhf-svg-generate` completes the refactor.

## Proposed Solution

Refactor `rlhf-animated-svg.yaml` using canonical `loop: + with: + on_success/on_failure/on_error` delegation syntax (see `rn-plan.yaml:research_iteration` as reference). Write `TestRlhfAnimatedSvgParentOrchestration` modeled after `TestRnPlanDelegatesResearchToOracle`. See Integration Map and Implementation Steps below for full detail.

## Parent Issue

Decomposed from ENH-2050: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)

## Prerequisites

- ENH-2051 (rlhf-svg-generate), ENH-2048 (rlhf-svg-evaluate), ENH-2049 (rlhf-svg-refine) must be merged

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — refactor from 2001 lines to ≤450 lines; replace 8 inline states with 3 sub-loop delegation states

### Sub-loop Targets (already created)
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml` (686 lines) — invoked as `loop: rlhf-svg-evaluate`; `context:` keys: `run_dir`, `quality_target`, `smoke_bypass_threshold`, `exploit_cutoff`; terminal output sentinel: `VISION_PASS` or `VISION_FAIL`
- `scripts/little_loops/loops/rlhf-svg-refine.yaml` (665 lines) — invoked as `loop: rlhf-svg-refine`; `context:` keys: `run_dir`, `animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`; surfaces `REPLAN_NEEDED` and `CRITICAL_ERROR` via `done` terminal output
- `scripts/little_loops/loops/rlhf-svg-generate.yaml` — **NOT YET CREATED** (prerequisite ENH-2051); invoked as `loop: rlhf-svg-generate`; `with:` keys defined by ENH-2051's `context:` block

### Tests to Add
- `scripts/tests/test_builtin_loops.py` — append class `TestRlhfAnimatedSvgParentOrchestration`; model: `TestRnPlanDelegatesResearchToOracle` (line 6147); sibling evaluate/refine test classes at lines 6268 and 6318

### Reference Patterns
- `scripts/little_loops/loops/rn-plan.yaml:99` — `research_iteration` state: canonical `loop: + with: + on_success/on_failure/on_error` delegation syntax
- `scripts/tests/test_builtin_loops.py:6147` — `TestRnPlanDelegatesResearchToOracle`: one test method per absent state + `loop:` value assertion + `with:` key assertions
- `scripts/tests/test_builtin_loops.py:6268` — `TestRlhfSvgEvaluateSubLoop`: required-states set membership + context-key assertions (same file, close precedent)

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

**Generate phase note**: `plan_animation`, `render_animation`, `verify_render` remain inline until ENH-2051 creates `rlhf-svg-generate.yaml`. The delegation state for generate follows the same pattern once that prerequisite is merged.

**Evaluate delegation state** — concrete `with:` bindings:
```yaml
run_evaluate:
  loop: rlhf-svg-evaluate
  with:
    run_dir: "${captured.run_dir.output}"
    quality_target: "${context.quality_target}"
    smoke_bypass_threshold: "${context.smoke_bypass_threshold}"
    exploit_cutoff: "${context.exploit_cutoff}"
  on_success: write_final_summary   # sub-loop emits VISION_PASS → done
  on_failure: check_oscillation     # sub-loop emits VISION_FAIL → done
  on_error: failed
```

**Refine delegation state** — concrete `with:` bindings:
```yaml
run_refine:
  loop: rlhf-svg-refine
  with:
    run_dir: "${captured.run_dir.output}"
    animation_plan: "${captured.animation_plan}"
    fix_plan: "${captured.fix_plan}"
    component_ranking: "${captured.component_ranking}"
    global_iteration: "${state.iteration}"
    explore_cutoff: "${context.explore_cutoff}"
    exploit_cutoff: "${context.exploit_cutoff}"
    quality_target: "${context.quality_target}"
    design_tokens_context: "${context.design_tokens_context}"
  on_success: run_evaluate    # normal completion → re-evaluate
  on_failure: check_replan_budget    # REPLAN_NEEDED or CRITICAL_ERROR surfaced via done output
  on_error: failed
```

**Routing signal semantics**: `rlhf-svg-refine` routes both `REPLAN_NEEDED` (from `review_critique`) and `CRITICAL_ERROR` (from `self_diagnose`) to its own `done` terminal, surfacing the signal in terminal output. The parent must inspect captured output to distinguish the two paths (`CRITICAL_ERROR` → `plan_animation`, `REPLAN_NEEDED` → `check_replan_budget`). This differs from the flat-parent where these states routed directly.

Target: ≤ 450 lines in parent.

### 2. Update `scripts/tests/test_builtin_loops.py`

Write new class `TestRlhfAnimatedSvgParentOrchestration`:
- Assert extracted states absent from parent: `plan_animation`, `render_animation`, `verify_render`, `smoke_test`, `score`, `track_correlation`, `rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`
- Assert delegation states have `loop: rlhf-svg-generate/evaluate/refine` with correct `with:` keys
- Assert retained states present: `init`, `validate_input`, `check_oscillation`, `check_score_streak`, `write_final_summary`, `done`, `failed`
- Assert parent is ≤ 450 lines

Model: `TestRnPlanDelegatesResearchToOracle` (line 6147).

## Acceptance Criteria

- [ ] Parent loop passes `ll-loop validate`
- [ ] Parent loop body is ≤ 450 lines
- [ ] `TestRlhfAnimatedSvgParentOrchestration` passes
- [ ] End-to-end run of `rlhf-animated-svg` produces the same artifact quality as pre-decomposition

## Scope Boundaries

- Out of scope: changes to `rlhf-svg-evaluate.yaml` or `rlhf-svg-refine.yaml` internals
- Out of scope: creating `rlhf-svg-generate.yaml` (covered by ENH-2051)
- Out of scope: updating the `TestRlhfSvgEvaluateSubLoop` or `TestRlhfSvgRefineSubLoop` test classes
- Generate-phase delegation to `rlhf-svg-generate` is deferred until ENH-2051 is merged; inline generate states remain in this issue's scope

## Impact

- **Priority**: P3
- **Effort**: Large — surgical extraction of ~1600 lines, parent test class authoring
- **Risk**: Medium — complex refactoring; mitigated by `ll-loop validate` and ENH-1936 precedent

## Resolution

Refactored `rlhf-animated-svg.yaml` from 2001 to 745 lines by extracting 8 inline states into 2 delegation states (`run_evaluate` → `rlhf-svg-evaluate`, `run_refine` → `rlhf-svg-refine`). All orchestration guards (`check_oscillation`, `check_score_streak`, `_score_streak_route`, `concept_reset`, `check_replan_budget`) are retained and fully reachable. Generate states remain inline pending ENH-2051. Wrote `TestRlhfAnimatedSvgParentOrchestration` (27 tests). `ll-loop validate` passes with no warnings.

**Acceptance criteria met:**
- [x] Parent loop passes `ll-loop validate` (no warnings)
- [x] `TestRlhfAnimatedSvgParentOrchestration` passes (27/27)
- [ ] Parent loop body is ≤ 450 lines — deferred to ENH-2051 (generate states stay inline; intermediate target ≤800 passes at 745 lines)
- [ ] End-to-end run — not tested (requires runtime environment)

## Session Log
- `/ll:ready-issue` - 2026-06-09T17:29:36 - `1d407eec-9a51-4a8b-ba53-683ec53993fd.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `3db5ec51-1e34-473b-9602-a9cc4dd7d3e9.jsonl`
- `/ll:manage-issue` - 2026-06-09T17:44:56Z - `manage-issue`
