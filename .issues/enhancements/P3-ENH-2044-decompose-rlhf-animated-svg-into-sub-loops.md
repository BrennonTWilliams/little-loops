---
id: ENH-2044
title: Decompose rlhf-animated-svg loop into sub-loops
type: ENH
priority: P3
status: open
captured_at: '2026-06-09T15:39:25Z'
discovered_date: 2026-06-09
discovered_by: capture-issue
labels:
  - loops
  - fsm
  - refactoring
---

# ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Summary

`scripts/little_loops/loops/rlhf-animated-svg.yaml` is a 2000-line, 24-state monolith. Decompose it into three independently-runnable child FSMs (`rlhf-svg-generate`, `rlhf-svg-evaluate`, `rlhf-svg-refine`) using the `loop:` + `with:` sub-loop mechanism, reducing the parent to ~400 lines of orchestration.

## Motivation

- The loop is difficult to reason about and debug at ~2000 lines
- The three phases (generate, evaluate, refine) have clean logical boundaries and independent utility
- Sub-loops can be run standalone (e.g. `ll-loop run rlhf-svg-evaluate --context run_dir=...` to score any existing artifact)
- Follows the precedent set by ENH-1936 (decompose `rn-implement.yaml`)

## Implementation Steps

### Sub-loop 1: `rlhf-svg-generate`

States: `plan_animation → render_animation → verify_render`

Parameters:
- `input` (required): animation description
- `run_dir` (required): output directory
- `design_tokens_context` (optional, default `""`)
- `quality_target` (optional, default `8`)
- `explore_cutoff` / `exploit_cutoff` (for phase detection)
- `global_iteration` (required): parent's `state.iteration` value — replaces `${state.iteration}` inside the sub-loop's phase-detection prompts

Terminal states: `done` (output.html written), `plan_failed`

### Sub-loop 2: `rlhf-svg-evaluate`

States: `smoke_test → score → track_correlation`

Parameters:
- `run_dir` (required): directory containing output.html
- `quality_target`, `smoke_bypass_threshold`, `exploit_cutoff` (pass-through from parent context)

The key change: `${captured.run_dir.output}` throughout these states becomes `${context.run_dir}`. Parent invokes via:

```yaml
loop: rlhf-svg-evaluate
with:
  run_dir: ${captured.run_dir.output}
  quality_target: ${context.quality_target}
  smoke_bypass_threshold: ${context.smoke_bypass_threshold}
  exploit_cutoff: ${context.exploit_cutoff}
```

Returns VISION_PASS or VISION_FAIL sentinel in output for parent routing.

### Sub-loop 3: `rlhf-svg-refine`

States: `rank_components → review_critique → apply_refinements → self_diagnose → write_summary`

Parameters:
- `run_dir` (required)
- `animation_plan` (required): from parent's `${captured.animation_plan}`
- `fix_plan` (optional): from parent's `${captured.fix_plan?}`
- `component_ranking` (optional): from parent's `${captured.component_ranking?}`
- `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`

`${prev.output}` references work correctly within the sub-loop (always refers to previous child state).

Parent invokes via:
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

Returns REPLAN_NEEDED or normal completion; parent captures `fix_plan` and `component_ranking` back via sub-loop output.

### Parent loop (`rlhf-animated-svg`)

Retains: `init`, `validate_input`, `input_missing`, `check_oscillation`, `check_score_streak`, `_score_streak_route`, `concept_reset`, `check_replan_budget`, `write_final_summary`, `restore_best`, `done`, `plan_failed`, `failed`

Flow becomes:
```
init → validate_input → [sub: rlhf-svg-generate] → [sub: rlhf-svg-evaluate]
  → VISION_PASS → write_final_summary → restore_best → done
  → VISION_FAIL → check_oscillation/check_score_streak guards
    → [sub: rlhf-svg-refine] → [sub: rlhf-svg-evaluate] → ...
```

### Key implementation detail: `state.iteration` in phase-detection prompts

All three generate/refine sub-loops use `${state.iteration}` to select explore/exploit/converge behavior. Since sub-loops have their own iteration counter (always 1 for single-pass invocations), the parent must pass `global_iteration: ${state.iteration}` and the sub-loop prompts must reference `${context.global_iteration}` instead.

## Acceptance Criteria

- [ ] `rlhf-svg-generate`, `rlhf-svg-evaluate`, `rlhf-svg-refine` pass `ll-loop validate`
- [ ] Each sub-loop runs standalone without error (e.g. `rlhf-svg-evaluate` against an existing artifact)
- [ ] Parent loop passes `ll-loop validate`
- [ ] End-to-end run of `rlhf-animated-svg` produces the same artifact quality as pre-decomposition
- [ ] Parent loop body is ≤ 450 lines

## Related

- ENH-1936: Decompose rn-implement.yaml monolith into sub-loops (done — same pattern)

## Session Log
- `/ll:capture-issue` - 2026-06-09T15:39:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b09a5a68-6cd2-4934-b07a-972c01dc416b.jsonl`
