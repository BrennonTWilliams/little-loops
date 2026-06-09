---
id: ENH-2049
title: Create rlhf-svg-refine sub-loop
type: ENH
priority: P3
status: done
parent: ENH-2044
captured_at: '2026-06-09T00:00:00Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
labels:
- loops
- fsm
- refactoring
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2049: Create rlhf-svg-refine sub-loop

## Summary

Extract the refinement phase of `rlhf-animated-svg.yaml` into a standalone child FSM `rlhf-svg-refine.yaml` with states `rank_components → review_critique → apply_refinements → self_diagnose → write_summary`. Register it in tests and the loops README.

## Current Behavior

The refinement states (`rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`) are embedded inside the `rlhf-animated-svg.yaml` monolith (~2000 lines, 24 states). There is no standalone `rlhf-svg-refine.yaml` sub-loop; the refinement phase cannot be run independently or tested in isolation.

## Expected Behavior

A standalone `rlhf-svg-refine.yaml` FSM exists with the five refinement states, accepts context parameters from the parent orchestrator (`animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, etc.), returns `REPLAN_NEEDED` or normal completion, and passes `ll-loop validate`. It is registered in `test_expected_loops_exist` and has a row in `loops/README.md`.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Implementation Steps

### 1. Create `scripts/little_loops/loops/rlhf-svg-refine.yaml`

States: `rank_components → review_critique → apply_refinements → self_diagnose → write_summary`

Context parameters:
- `run_dir` (required)
- `animation_plan` (required): from parent's `${captured.animation_plan}`
- `fix_plan` (optional): from parent's `${captured.fix_plan?}`
- `component_ranking` (optional): from parent's `${captured.component_ranking?}`
- `global_iteration` (required): parent's `state.iteration` value — phase-detection prompts must reference `${context.global_iteration}` (not `${state.iteration}`)
- `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`

Notes:
- `${prev.output}` references work correctly within the sub-loop (always refers to previous child state)
- Returns REPLAN_NEEDED or normal completion; parent captures `fix_plan` and `component_ranking` back via sub-loop output
- `review_critique` state captures `fix_plan`

Parent will invoke via:
```yaml
loop: rlhf-svg-refine
with:
  run_dir: ${captured.run_dir.output}
  animation_plan: ${captured.animation_plan}
  fix_plan: ${captured.fix_plan?}
  component_ranking: ${captured.component_ranking?}
  global_iteration: ${state.iteration}
  explore_cutoff: ${context.explore_cutoff}
  exploit_cutoff: ${context.exploit_cutoff}
  quality_target: ${context.quality_target}
  design_tokens_context: ${context.design_tokens_context}
```

### 2. Update `scripts/tests/test_builtin_loops.py`

- Add `"rlhf-svg-refine"` to the `expected` set in `test_expected_loops_exist` (after `"rlhf-animated-svg"`)
- Write new class `TestRlhfSvgRefineSubLoop`:
  - Assert required states present: `rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`, `done`
  - Assert `context` block declares `run_dir`, `animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`
  - Assert phase-detection prompts reference `${context.global_iteration}` not `${state.iteration}`
  - Assert `review_critique` captures `fix_plan`

Model after `TestRnPlanDelegatesResearchToOracle` (line 6186).

### 3. Update `scripts/little_loops/loops/README.md`

Add one row for `rlhf-svg-refine` to the Animation/Generative Art table following the `rn-remediate`/`rn-decompose` row format.

## Scope Boundaries

- **In scope**: Creating the new YAML file and its associated tests + README entry
- **Out of scope**: Modifying the parent orchestration loop (ENH-2050), changing refinement heuristics

## Acceptance Criteria

- [ ] `rlhf-svg-refine.yaml` passes `ll-loop validate`
- [ ] Sub-loop runs standalone: `ll-loop run rlhf-svg-refine --context run_dir=... animation_plan=...`
- [ ] `TestRlhfSvgRefineSubLoop` passes
- [ ] `test_expected_loops_exist` passes with `"rlhf-svg-refine"` in expected set
- [ ] README.md row added

## Impact

- **Priority**: P3
- **Effort**: Medium-Large — extract and author ~600-line sub-loop YAML (largest of the three)
- **Risk**: Low-Medium — new file; the `global_iteration` threading and REPLAN_NEEDED routing are easy to miss

## Session Log
- `/ll:ready-issue` - 2026-06-09T16:47:05 - `747f8b03-8237-4c86-a670-c30c9164288e.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `45952361-ab4e-44df-98ab-dbae2c7ed4a7.jsonl`
