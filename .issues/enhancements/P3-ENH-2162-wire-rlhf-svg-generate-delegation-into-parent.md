---
id: ENH-2162
title: Wire rlhf-svg-generate delegation into rlhf-animated-svg parent
type: ENH
priority: P3
status: done
parent: ENH-2044
relates_to:
- ENH-2050
- ENH-2051
captured_at: '2026-06-15T05:15:58Z'
completed_at: '2026-06-15T18:39:54Z'
discovered_date: 2026-06-15
discovered_by: capture-issue
labels:
- loops
- fsm
- refactoring
confidence_score: 98
outcome_confidence: 86
score_complexity: 21
score_test_coverage: 21
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2162: Wire rlhf-svg-generate delegation into rlhf-animated-svg parent

## Summary

ENH-2050 explicitly deferred wiring the generate phase into the parent pending ENH-2051 (line 78: "the delegation state for generate follows the same pattern once that prerequisite is merged"). ENH-2051 is now done — `rlhf-svg-generate.yaml` exists — but the parent loop still handles `plan_animation`, `render_animation`, and `verify_render` inline. This duplicates ~200 lines of prompt content between the parent and the sub-loop, creating a maintenance liability when either copy is updated.

## Motivation

This enhancement would:
- Eliminate ~200 lines of duplicated prompt content between `rlhf-animated-svg.yaml` and `rlhf-svg-generate.yaml`, reducing maintenance liability
- Ensure updates to the generate phase propagate consistently to both standalone and parent-coordinated execution paths
- Complete the delegation pattern deferred in ENH-2050, now unblocked by ENH-2051 delivering `rlhf-svg-generate.yaml`

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

## Scope Boundaries

- **In scope**: Replacing `plan_animation`, `render_animation`, `verify_render` inline states in `rlhf-animated-svg.yaml` with a `run_generate` delegation state; updating downstream `${captured.animation_plan}` references; adding `TestRlhfAnimatedSvgDelegatesGenerate` test class; adding an `output:` surfacing block to `rlhf-svg-generate.yaml`'s `done` state (structural addition required to make `animation_plan` available to parent's `run_refine` — not a logic change)
- **Out of scope**: Changes to `rlhf-svg-generate.yaml` generation logic; modifications to existing `run_evaluate` or `run_refine` delegation states; any functional changes to the animation generation algorithm

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — delete inline `plan_animation` (lines 73–249), `render_animation` (lines 252–378), `verify_render` (lines 380–399); insert `run_generate` delegation state immediately before `run_evaluate` (currently line 401). Use `run_evaluate` (lines 401–410) as the exact structural template.
- `scripts/little_loops/loops/rlhf-svg-generate.yaml` — add `output:` block to `done` state (currently bare `terminal: true` at lines 349–350) to surface `animation_plan` back to parent. Without this, `run_refine.with.animation_plan: "${captured.animation_plan}"` (parent line 444) will not resolve after delegation. Minimal structural addition; no logic change.

### Context Keys to Pass (confirmed against rlhf-svg-generate.yaml context block, lines 13–20)

All 7 child context parameters confirmed. `global_iteration` maps to `${state.iteration}` in parent (same as `run_refine.with.global_iteration` at line 447):

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

### Critical: animation_plan Capture Path

Research confirmed that `rlhf-svg-generate.yaml`'s `done` state (lines 349–350) is currently:
```yaml
done:
  terminal: true
```
No `output:` block. The child's `plan_animation` state does set `capture: animation_plan` (child line 197), but the `done` state does not surface it to the parent. Fix: add `output: {animation_plan: "${captured.animation_plan}"}` to the child's `done` state. Also check whether `candidate` (set by child's `render_animation` via `capture: candidate`) is needed by any parent state.

### Downstream Impact: States Referencing ${captured.animation_plan}

Research found exactly two references in the parent:
- `render_animation` (line 260) — **deleted** as part of this enhancement; no update needed
- `run_refine.with.animation_plan` (line 444) — **must remain resolvable**; resolved by the child `output:` block addition above

Verify before removing inline states: `grep -n 'animation_plan' scripts/little_loops/loops/rlhf-animated-svg.yaml` to confirm no additional references (e.g., `check_score_streak`).

### Routing References to Update

Five states outside the deleted block route to `plan_animation`, `render_animation`, or `verify_render`. These must be updated to `run_generate` before deletion (or the FSM will have dangling state references caught by `ll-loop validate`):

| Line | State | Current target | Updated target |
|------|-------|---------------|----------------|
| 65 | `validate_input` | `on_yes: plan_animation` | `on_yes: run_generate` |
| 436 | `check_oscillation` | `on_yes: plan_animation` | `on_yes: run_generate` |
| 503 | `_streak_route` | `on_yes: plan_animation` | `on_yes: run_generate` |
| 549 | `concept_reset` | `next: render_animation` | `next: run_generate` |
| 585 | `check_replan_budget` | `on_no: plan_animation` | `on_no: run_generate` |

Run `grep -n 'on_yes: plan_animation\|on_no: plan_animation\|next: render_animation\|on_yes: render_animation' scripts/little_loops/loops/rlhf-animated-svg.yaml` after deletion to confirm all routing references are resolved.

### Reference Patterns (confirmed line numbers)

- `rlhf-animated-svg.yaml` lines 401–410 — `run_evaluate` delegation state: direct structural template for `run_generate`
- `rlhf-animated-svg.yaml` lines 440–454 — `run_refine` delegation state: shows `animation_plan` and `global_iteration` pass-through pattern

### Tests to Add/Update

- `scripts/tests/test_builtin_loops.py` — add `TestRlhfAnimatedSvgDelegatesGenerate` after `TestRlhfAnimatedSvgParentOrchestration` (lines 6669–6829). Follow the sibling class's assertion structure (not `TestRnPlanDelegatesResearchToOracle` at line 6339 — the sibling class covers the same parent loop and uses the same accessor pattern):
  - Negative: `plan_animation`, `render_animation`, `verify_render` absent from `data["states"]`
  - Positive: `run_generate` present; `.loop == "rlhf-svg-generate"`; all 7 `with:` keys present (`input`, `run_dir`, `global_iteration`, `design_tokens_context`, `quality_target`, `explore_cutoff`, `exploit_cutoff`); `on_success == "run_evaluate"`; `on_failure == "plan_failed"`

## Implementation Steps

1. **Add output surfacing to rlhf-svg-generate.yaml**: In `done` state (lines 349–350), add `output: {animation_plan: "${captured.animation_plan}"}`. Verify child `plan_animation` uses `capture: animation_plan` (child line 197 — confirmed). Also check whether `candidate` output is needed by parent.

2. **Audit all animation_plan references in parent**: `grep -n 'animation_plan' scripts/little_loops/loops/rlhf-animated-svg.yaml`. Expected hits: line 260 (in `render_animation`, deleting) and line 444 (in `run_refine.with`, must stay valid). Confirm no others (e.g., `check_score_streak`).

3. **Update routing references**: Before deleting states, update all 5 routing references that target `plan_animation`/`render_animation` to point to `run_generate` instead (see Integration Map § Routing References to Update): `validate_input` line 65, `check_oscillation` line 436, `_streak_route` line 503, `concept_reset` line 549, `check_replan_budget` line 585.

4. **Delete inline states from parent**: Remove `plan_animation` (lines 73–249), `render_animation` (lines 252–378), `verify_render` (lines 380–399) from `rlhf-animated-svg.yaml`.

5. **Insert run_generate delegation state**: Add before `run_evaluate` (currently line 401, shifts after deletion) using the YAML from the Expected Behavior section. Structural template: `run_evaluate` at lines 401–410.

6. **Run ll-loop validate**: `ll-loop validate rlhf-animated-svg` — confirm no MR-rule violations. Also `ll-loop validate rlhf-svg-generate` after the `output:` block addition.

7. **Add TestRlhfAnimatedSvgDelegatesGenerate test class**: In `scripts/tests/test_builtin_loops.py` after `TestRlhfAnimatedSvgParentOrchestration` (lines 6669–6831). Test methods:
   - `test_no_inline_plan_animation`, `test_no_inline_render_animation`, `test_no_inline_verify_render`
   - `test_run_generate_state_exists`, `test_run_generate_delegates_to_rlhf_svg_generate`
   - `test_run_generate_passes_input`, `test_run_generate_passes_run_dir`, `test_run_generate_passes_global_iteration`, `test_run_generate_passes_design_tokens_context`, `test_run_generate_passes_quality_target`, `test_run_generate_passes_explore_cutoff`, `test_run_generate_passes_exploit_cutoff`
   - `test_run_generate_on_success_is_run_evaluate`, `test_run_generate_on_failure_is_plan_failed`

8. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py -k "TestRlhfAnimatedSvg" -v`

## Impact

- **Priority**: P3 - Deferred wiring now unblocked by ENH-2051 completion; reduces ~200-line duplication maintenance liability
- **Effort**: Small - Delegation pattern well-established (`run_evaluate` at line 401 serves as direct template); structural edit only
- **Risk**: Low - No functional change; delegates to existing tested sub-loop; test coverage added
- **Breaking Change**: No - Internal refactor; all external behavior preserved

## Status

**Open** | Created: 2026-06-15 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-15T18:02:21 - `265659c2-6055-4b48-98e1-11e9f318dc86.jsonl`
- `/ll:ready-issue` - 2026-06-15T17:54:38 - `9fe01794-d135-49ba-824a-1d15ee055b09.jsonl`
- `/ll:confidence-check` - 2026-06-15T18:00:00Z - `f6401789-d391-4477-a63c-a4a61ebbb1f1.jsonl`
- `/ll:refine-issue` - 2026-06-15T17:45:04 - `7fe5f59a-ddb8-4cee-8e84-907618f69c14.jsonl`
- `/ll:format-issue` - 2026-06-15T05:19:04 - `1f4581dd-da15-407d-9ef1-ad44bc9999d6.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `706fe6dd-4d96-4068-8ab4-6c70801cc3e1.jsonl`
