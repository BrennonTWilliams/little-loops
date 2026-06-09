---
id: ENH-2051
title: Create rlhf-svg-generate sub-loop
type: ENH
priority: P3
status: done
parent: ENH-2044
captured_at: '2026-06-09T00:00:00Z'
completed_at: 2026-06-09 18:20:25+00:00
discovered_date: 2026-06-09
discovered_by: issue-size-review
labels:
- loops
- fsm
- refactoring
confidence_score: 96
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
---

# ENH-2051: Create rlhf-svg-generate sub-loop

## Summary

Extract the generation phase of `rlhf-animated-svg.yaml` into a standalone child FSM `rlhf-svg-generate.yaml` with states `plan_animation → render_animation → verify_render`. Register it in tests and the loops README.

## Current Behavior

The generation phase (`plan_animation`, `render_animation`, `verify_render`) is embedded inline in `rlhf-animated-svg.yaml`. No standalone `rlhf-svg-generate` sub-loop exists, so the generation phase cannot be tested or invoked independently of the full orchestration loop.

## Expected Behavior

A standalone `rlhf-svg-generate.yaml` sub-loop exists with states `plan_animation → render_animation → verify_render`, passes `ll-loop validate`, runs independently via `ll-loop run rlhf-svg-generate`, and is covered by `TestRlhfSvgGenerateSubLoop` in `test_builtin_loops.py`.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Motivation

This enhancement would:
- Complete the decomposition of `rlhf-animated-svg.yaml` into reusable sub-loops (parent: ENH-2044), enabling each phase to be tested and invoked independently
- Allow the generation phase to be reused by other orchestration loops without pulling in evaluation/refinement logic
- Isolate generation failures from evaluation/refinement failures, reducing debugging surface area

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

Model after `TestRnPlanDelegatesResearchToOracle` (line 6147).

### 3. Update `scripts/little_loops/loops/README.md`

Add one row for `rlhf-svg-generate` to the Animation/Generative Art table following the `rn-remediate`/`rn-decompose` row format.

## API/Interface

Loop context parameters (public contract for callers):

```yaml
context:
  input: str                   # animation description (required)
  run_dir: str                 # output directory for output.html (required)
  global_iteration: int        # parent's state.iteration for phase-detection prompts (required)
  design_tokens_context: str   # design token context string (optional, default "")
  quality_target: int          # target quality score (optional, default 8)
  explore_cutoff: int          # iteration threshold for explore phase
  exploit_cutoff: int          # iteration threshold for exploit phase
```

Terminal states:
- `done` — `output.html` written to `run_dir`
- `plan_failed` — generation could not be planned

## Scope Boundaries

- **In scope**: Creating the new YAML file and its associated tests + README entry
- **Out of scope**: Modifying the parent orchestration loop (ENH-2050), changing SVG generation quality or behavior

## Acceptance Criteria

- [x] `rlhf-svg-generate.yaml` passes `ll-loop validate`
- [x] Sub-loop runs standalone: `ll-loop run rlhf-svg-generate --context input="test" run_dir=/tmp/test`
- [x] `TestRlhfSvgGenerateSubLoop` passes
- [x] `test_expected_loops_exist` passes with `"rlhf-svg-generate"` in expected set
- [x] README.md row added

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rlhf-svg-generate.yaml` (new — create)
- `scripts/tests/test_builtin_loops.py` (add `TestRlhfSvgGenerateSubLoop`, update `test_expected_loops_exist`)
- `scripts/little_loops/loops/README.md` (add row to Animation/Generative Art table)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — will delegate generation phase to this sub-loop (ENH-2050)

### Similar Patterns
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml` — sibling sub-loop for evaluation phase
- `scripts/little_loops/loops/rlhf-svg-refine.yaml` — sibling sub-loop for refinement phase
- `scripts/tests/test_builtin_loops.py:TestRnPlanDelegatesResearchToOracle` (line 6147) — test class to model after

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestRlhfSvgGenerateSubLoop`

### Documentation
- `scripts/little_loops/loops/README.md` — Animation/Generative Art table

### Configuration
- N/A

## Impact

- **Priority**: P3
- **Effort**: Medium — extract and author ~500-line sub-loop YAML
- **Risk**: Low — new file, no existing callers

## Status

**Open** | Created: 2026-06-09 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-09T18:13:15 - `dfe72044-44ec-4859-b5b5-d3659c64add5.jsonl`
- `/ll:format-issue` - 2026-06-09T18:01:15 - `2d482232-6523-4263-ba00-0d17c049d9ee.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `83eb0379-081b-4b33-8ad2-9b0c1c2ddba4.jsonl`
