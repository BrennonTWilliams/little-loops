---
id: ENH-2051
title: Create rlhf-svg-generate sub-loop
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

# ENH-2051: Create rlhf-svg-generate sub-loop

## Summary

Extract the generation phase of `rlhf-animated-svg.yaml` into a standalone child FSM `rlhf-svg-generate.yaml` with states `plan_animation → render_animation → verify_render`. Register it in tests and the loops README.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Implementation Steps

### 1. Create `scripts/little_loops/loops/rlhf-svg-generate.yaml`

States: `plan_animation → render_animation → verify_render`

Context parameters:
- `input` (required): animation description
- `run_dir` (required): output directory
- `design_tokens_context` (optional, default `""`)
- `quality_target` (optional, default `8`)
- `explore_cutoff` / `exploit_cutoff` (for phase detection)
- `global_iteration` (required): parent's `state.iteration` value — phase-detection prompts must reference `${context.global_iteration}` (not `${state.iteration}`)

Terminal states: `done` (output.html written), `plan_failed`

Extract states from `rlhf-animated-svg.yaml` using the existing logic. All `${state.iteration}` references inside phase-detection prompts become `${context.global_iteration}`.

### 2. Update `scripts/tests/test_builtin_loops.py`

- Add `"rlhf-svg-generate"` to the `expected` set in `test_expected_loops_exist` (after `"rlhf-animated-svg"`)
- Write new class `TestRlhfSvgGenerateSubLoop`:
  - Assert required states present: `plan_animation`, `render_animation`, `verify_render`, `done`, `plan_failed`
  - Assert `context` block declares `input`, `run_dir`, `quality_target`, `global_iteration`, `design_tokens_context`, `explore_cutoff`, `exploit_cutoff`
  - Assert phase-detection prompts reference `${context.global_iteration}` not `${state.iteration}`

Model after `TestRnPlanDelegatesResearchToOracle` (line 6185).

### 3. Update `scripts/little_loops/loops/README.md`

Add one row for `rlhf-svg-generate` to the Animation/Generative Art table following the `rn-remediate`/`rn-decompose` row format.

## Scope Boundaries

- **In scope**: Creating the new YAML file and its associated tests + README entry
- **Out of scope**: Modifying the parent orchestration loop (ENH-2050), changing SVG generation quality or behavior

## Acceptance Criteria

- [ ] `rlhf-svg-generate.yaml` passes `ll-loop validate`
- [ ] Sub-loop runs standalone: `ll-loop run rlhf-svg-generate --context input="test" run_dir=/tmp/test`
- [ ] `TestRlhfSvgGenerateSubLoop` passes
- [ ] `test_expected_loops_exist` passes with `"rlhf-svg-generate"` in expected set
- [ ] README.md row added

## Impact

- **Priority**: P3
- **Effort**: Medium — extract and author ~500-line sub-loop YAML
- **Risk**: Low — new file, no existing callers

## Session Log
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
