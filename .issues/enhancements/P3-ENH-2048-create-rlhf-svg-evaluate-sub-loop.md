---
id: ENH-2048
title: Create rlhf-svg-evaluate sub-loop
type: ENH
priority: P3
status: done
parent: ENH-2044
captured_at: '2026-06-09T00:00:00Z'
completed_at: '2026-06-09T16:36:44Z'
discovered_date: 2026-06-09
discovered_by: issue-size-review
labels:
- loops
- fsm
- refactoring
confidence_score: 98
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 25
---

# ENH-2048: Create rlhf-svg-evaluate sub-loop

## Summary

Extract the evaluation phase of `rlhf-animated-svg.yaml` into a standalone child FSM `rlhf-svg-evaluate.yaml` with states `smoke_test → score → track_correlation`. Register it in tests and the loops README.

## Current Behavior

The evaluation phase (`smoke_test → score → track_correlation`) is embedded inline within `rlhf-animated-svg.yaml`. There is no standalone, reusable sub-loop for SVG evaluation.

## Expected Behavior

A standalone `rlhf-svg-evaluate.yaml` sub-loop handles the evaluation pipeline (`smoke_test → score → track_correlation`) as a child FSM. The parent loop invokes it via `loop: rlhf-svg-evaluate` with context parameters, and the sub-loop returns a `VISION_PASS` or `VISION_FAIL` sentinel for parent routing.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Implementation Steps

### 1. Create `scripts/little_loops/loops/rlhf-svg-evaluate.yaml`

States: `smoke_test → score → track_correlation`

Context parameters:
- `run_dir` (required): directory containing output.html
- `quality_target` (pass-through from parent context)
- `smoke_bypass_threshold` (pass-through from parent context)
- `exploit_cutoff` (pass-through from parent context)

Key change: `${captured.run_dir.output}` throughout these states becomes `${context.run_dir}`. The sub-loop returns a VISION_PASS or VISION_FAIL sentinel in output for parent routing.

Parent will invoke via:
```yaml
loop: rlhf-svg-evaluate
with:
  run_dir: ${captured.run_dir.output}
  quality_target: ${context.quality_target}
  smoke_bypass_threshold: ${context.smoke_bypass_threshold}
  exploit_cutoff: ${context.exploit_cutoff}
```

### 2. Update `scripts/tests/test_builtin_loops.py`

- Add `"rlhf-svg-evaluate"` to the `expected` set in `test_expected_loops_exist` (after `"rlhf-animated-svg"`)
- Write new class `TestRlhfSvgEvaluateSubLoop`:
  - Assert required states present: `smoke_test`, `score`, `track_correlation`, `done`
  - Assert `context` block declares `run_dir`, `quality_target`, `smoke_bypass_threshold`, `exploit_cutoff`
  - Assert shell states reference `${context.run_dir}` (not `${captured.run_dir.output}`)

Model after `TestRnPlanDelegatesResearchToOracle` (line 6185).

### 3. Update `scripts/little_loops/loops/README.md`

Add one row for `rlhf-svg-evaluate` to the Animation/Generative Art table following the `rn-remediate`/`rn-decompose` row format.

## Scope Boundaries

- **In scope**: Creating the new YAML file and its associated tests + README entry
- **Out of scope**: Modifying the parent orchestration loop (ENH-2050), changing evaluation scoring logic

## Acceptance Criteria

- [ ] `rlhf-svg-evaluate.yaml` passes `ll-loop validate`
- [ ] Sub-loop runs standalone: `ll-loop run rlhf-svg-evaluate --context run_dir=/path/to/existing/artifact`
- [ ] `TestRlhfSvgEvaluateSubLoop` passes
- [ ] `test_expected_loops_exist` passes with `"rlhf-svg-evaluate"` in expected set
- [ ] README.md row added

## Impact

- **Priority**: P3
- **Effort**: Medium — extract and author ~400-line sub-loop YAML
- **Risk**: Low — new file, no existing callers

## Resolution

Extracted `smoke_test → score → track_correlation` from `rlhf-animated-svg.yaml` into the standalone `rlhf-svg-evaluate.yaml` sub-loop. Key changes:
- All `${captured.run_dir.output}` references replaced with `${context.run_dir}`
- `${captured.fix_plan?}` removed (not captured in this sub-loop; correlation categories will be empty on standalone use)
- Added `smoke_fail_exit` normalisation state: smoke failures emit `VISION_FAIL` for uniform parent routing
- Both `done` paths (pass and fail) go through `done` terminal; sentinel is in the preceding state's output
- Passes `ll-loop validate` (no MR-1/MR-3/MR-4 errors)

## Session Log
- `/ll:ready-issue` - 2026-06-09T16:20:58 - `f7300707-ab77-4eac-b544-b72e50514ab2.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `86a8c572-a875-468b-92b9-e78558327f0a.jsonl`
- `/ll:manage-issue` - 2026-06-09T16:36:44Z - `6349ae72-561a-4584-8463-07014ec518fb`
