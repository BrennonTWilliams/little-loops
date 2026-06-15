---
id: ENH-2162
title: Wire rlhf-svg-generate delegation into rlhf-animated-svg parent
type: ENH
priority: P3
status: open
parent: ENH-2044
relates_to: [ENH-2050, ENH-2051]
captured_at: '2026-06-15T05:15:58Z'
discovered_date: 2026-06-15
discovered_by: capture-issue
labels:
- loops
- fsm
- refactoring
---

# ENH-2162: Wire rlhf-svg-generate delegation into rlhf-animated-svg parent

## Summary

ENH-2050 explicitly deferred wiring the generate phase into the parent pending ENH-2051 (line 78: "the delegation state for generate follows the same pattern once that prerequisite is merged"). ENH-2051 is now done — `rlhf-svg-generate.yaml` exists — but the parent loop still handles `plan_animation`, `render_animation`, and `verify_render` inline. This duplicates ~200 lines of prompt content between the parent and the sub-loop, creating a maintenance liability when either copy is updated.

## Current Behavior

`rlhf-animated-svg.yaml` contains inline `plan_animation`, `render_animation`, and `verify_render` states (~200 lines of prompt content) that duplicate the same states in `rlhf-svg-generate.yaml`. The parent delegates to `rlhf-svg-evaluate` and `rlhf-svg-refine` but not to `rlhf-svg-generate`.

## Expected Behavior

The parent replaces its inline generate states with a `run_generate` delegation state:

```yaml
run_generate:
  loop: rlhf-svg-generate
  with:
    input: "${context.input}"
    run_dir: "${captured.run_dir.output}"
    global_iteration: "${state.iteration}"
    design_tokens_context: "${context.design_tokens_context}"
    quality_target: "${context.quality_target}"
    explore_cutoff: "${context.explore_cutoff}"
    exploit_cutoff: "${context.exploit_cutoff}"
  on_success: run_evaluate
  on_failure: plan_failed
  on_error: failed
```

The inline `plan_animation`, `render_animation`, and `verify_render` states are removed from the parent.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — replace 3 inline generate states with `run_generate` delegation; captured.animation_plan references in downstream states need to pull from sub-loop output or be passed through

### Context Keys to Pass

From ENH-2051's `context:` block: `input`, `run_dir`, `global_iteration`, `design_tokens_context`, `quality_target`, `explore_cutoff`, `exploit_cutoff`

### Downstream Impact

States that currently reference `${captured.animation_plan}` (e.g., `run_refine`) will need the sub-loop's output captured correctly. Check how `rlhf-svg-generate` surfaces `animation_plan` at done — may need a capture alias or context pass-through.

### Tests to Add/Update

- `scripts/tests/test_builtin_loops.py` — add `TestRlhfAnimatedSvgDelegatesGenerate` asserting absence of `plan_animation`, `render_animation`, `verify_render` in parent states and presence of `run_generate` with correct `loop:` and `with:` keys. Pattern: `TestRnPlanDelegatesResearchToOracle` (line 6187).

### Reference Patterns

- `scripts/little_loops/loops/rlhf-animated-svg.yaml:401` — existing `run_evaluate` delegation state: use as the `run_generate` template
- ENH-2050 lines 80–92 — concrete `with:` binding pattern for evaluate; apply same structure to generate

## Implementation Steps

1. Confirm `rlhf-svg-generate.yaml` captures `animation_plan` in a way the parent can reference after delegation
2. Replace inline `plan_animation`, `render_animation`, `verify_render` in `rlhf-animated-svg.yaml` with `run_generate` delegation
3. Update any downstream `${captured.animation_plan}` references in `run_refine` / `check_score_streak` to use the correct capture path
4. Run `ll-loop validate rlhf-animated-svg` to confirm no MR-rule violations
5. Add `TestRlhfAnimatedSvgDelegatesGenerate` test class
