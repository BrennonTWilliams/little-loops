---
id: ENH-2044
title: Decompose rlhf-animated-svg loop into sub-loops
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T15:39:25Z'
discovered_date: 2026-06-09
discovered_by: capture-issue
labels:
- loops
- fsm
- refactoring
confidence_score: 98
outcome_confidence: 72
score_complexity: 17
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
implementation_order_risk: true
size: Very Large
completed_at: '2026-06-09T16:15:11Z'
---

# ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Summary

`scripts/little_loops/loops/rlhf-animated-svg.yaml` is a 2000-line, 24-state monolith. Decompose it into three independently-runnable child FSMs (`rlhf-svg-generate`, `rlhf-svg-evaluate`, `rlhf-svg-refine`) using the `loop:` + `with:` sub-loop mechanism, reducing the parent to ~400 lines of orchestration.

## Current Behavior

`scripts/little_loops/loops/rlhf-animated-svg.yaml` is a ~2000-line, 24-state monolith. All generate, evaluate, and refine logic lives in a single file, making the loop difficult to debug, test independently, or reuse individual phases in isolation.

## Expected Behavior

The loop is decomposed into three independently-runnable child FSMs (`rlhf-svg-generate`, `rlhf-svg-evaluate`, `rlhf-svg-refine`) that communicate via the `loop: + with:` sub-loop mechanism. The parent `rlhf-animated-svg` is reduced to ~400 lines of orchestration, delegating each phase to the appropriate child loop. Each sub-loop can be run standalone (e.g. `ll-loop run rlhf-svg-evaluate --context run_dir=...` against any existing artifact).

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/tests/test_builtin_loops.py` — add `"rlhf-svg-generate"`, `"rlhf-svg-evaluate"`, `"rlhf-svg-refine"` to `test_expected_loops_exist` expected set (after line 153)
2. Write 4 new test classes in `scripts/tests/test_builtin_loops.py` alongside each loop delivery: `TestRlhfAnimatedSvgParentOrchestration`, `TestRlhfSvgGenerateSubLoop`, `TestRlhfSvgEvaluateSubLoop`, `TestRlhfSvgRefineSubLoop`
3. Update `scripts/little_loops/loops/README.md` — add one row per sub-loop to the Animation/Generative Art table following `rn-remediate`/`rn-decompose` row format
4. Update `CONTRIBUTING.md` line 122 — bump loop YAML count from 77 → 80
5. Update `docs/guides/LOOPS_GUIDE.md` — revise `rlhf-animated-svg` section FSM flow (lines 2215–2223) and add three new `### \`rlhf-svg-*\`` sub-sections after line 2244

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

## Scope Boundaries

- **In scope**: Creating three new sub-loop YAML files, refactoring the parent orchestration loop to ~400 lines, ensuring all four loops pass `ll-loop validate`
- **Out of scope**: Changing SVG generation quality or behavior, modifying the public context interface of `rlhf-animated-svg`, performance optimization of the animation pipeline

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — refactor to orchestration-only (~400 lines), delegate phases to sub-loops
- `scripts/little_loops/loops/README.md` — add one row per sub-loop to the Animation/Generative Art table, following `rn-remediate`/`rn-decompose` pattern [Agent 1 finding]
- `CONTRIBUTING.md` (line 122) — update loop count from 77 → 80 to reflect the three new YAML files [Agent 2 finding]

### New Files
- `scripts/little_loops/loops/rlhf-svg-generate.yaml`
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml`
- `scripts/little_loops/loops/rlhf-svg-refine.yaml`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
No other loops invoke `rlhf-animated-svg` via `loop:` delegation — it is user-invoked only (`ll-loop run rlhf-animated-svg`). Documentation references are listed under the Documentation section below.

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` — ENH-1936 decomposition precedent (rn-plan, rn-refine, rn-verify sub-loops)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `test_expected_loops_exist` (line 73): **must update** — add `"rlhf-svg-generate"`, `"rlhf-svg-evaluate"`, `"rlhf-svg-refine"` to the hardcoded `expected` set immediately after `"rlhf-animated-svg"` at line 153. The three new files land in the flat `loops/` dir and will cause set-equality assertion failure if omitted. [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` — **new class** `TestRlhfAnimatedSvgParentOrchestration`: assert extracted states absent from parent (`plan_animation`, `render_animation`, `verify_render`, `smoke_test`, `score`, `track_correlation`, `rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`); assert delegation states have `loop: rlhf-svg-generate/evaluate/refine` with correct `with:` keys; assert retained states present (`init`, `validate_input`, `check_oscillation`, `check_score_streak`, `write_final_summary`, `done`, `failed`); assert parent is ≤ 450 lines. Model: `TestRnPlanDelegatesResearchToOracle` (line 6185). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **new class** `TestRlhfSvgGenerateSubLoop`: assert required states (`plan_animation`, `render_animation`, `verify_render`, `done`, `plan_failed`); assert `context` block declares `input`, `run_dir`, `quality_target`, `global_iteration`, `design_tokens_context`, `explore_cutoff`, `exploit_cutoff`; assert phase-detection prompts reference `${context.global_iteration}` not `${state.iteration}`. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **new class** `TestRlhfSvgEvaluateSubLoop`: assert required states (`smoke_test`, `score`, `track_correlation`, `done`); assert `context` block declares `run_dir`, `quality_target`, `smoke_bypass_threshold`, `exploit_cutoff`; assert shell states reference `${context.run_dir}` (not `${captured.run_dir.output}`). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **new class** `TestRlhfSvgRefineSubLoop`: assert required states (`rank_components`, `review_critique`, `apply_refinements`, `self_diagnose`, `write_summary`, `done`); assert `context` block declares `run_dir`, `animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`; assert phase-detection prompts reference `${context.global_iteration}` not `${state.iteration}`; assert `review_critique` captures `fix_plan`. [Agent 3 finding]
- All four new loop files are automatically picked up by the `builtin_loops` fixture (`rglob + is_runnable_loop`) for structural validation tests (`test_all_validate_as_valid_fsm`, etc.) — no fixture changes needed. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` (lines 2215–2223) — update parent `rlhf-animated-svg` FSM flow diagram in the existing `### \`rlhf-animated-svg\`` section to show sub-loop delegation rather than the flat 24-state graph [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` (after line 2244) — add three new `### \`rlhf-svg-*\`` sections following the `rn-remediate`/`rn-decompose` pattern (line 684/741): each with context variables table, output artifacts, FSM flow, and standalone invocation example [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` (line 1460 overview table) — `rlhf-animated-svg` entry may need a note that phases are delegated to sub-loops; the three sub-loops may need their own overview-table rows following the `rn-remediate`/`rn-decompose` precedent [Agent 2 finding]

### Configuration
- N/A

## Acceptance Criteria

- [ ] `rlhf-svg-generate`, `rlhf-svg-evaluate`, `rlhf-svg-refine` pass `ll-loop validate`
- [ ] Each sub-loop runs standalone without error (e.g. `rlhf-svg-evaluate` against an existing artifact)
- [ ] Parent loop passes `ll-loop validate`
- [ ] End-to-end run of `rlhf-animated-svg` produces the same artifact quality as pre-decomposition
- [ ] Parent loop body is ≤ 450 lines

## Impact

- **Priority**: P3 — Developer experience improvement; not blocking any feature work
- **Effort**: Large — 2000-line loop split across 4 files with careful state/context threading
- **Risk**: Medium — Complex loop refactoring; behavior must be identical post-decomposition; mitigated by `ll-loop validate` and the ENH-1936 precedent
- **Breaking Change**: No — same external context parameters for `rlhf-animated-svg`

## Related

- ENH-1936: Decompose rn-implement.yaml monolith into sub-loops (done — same pattern)

## Status

**Open** | Created: 2026-06-09 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Deep per-site complexity: authoring three new sub-loop YAMLs from scratch (each ~400–700 lines) plus surgically extracting ~1600 lines from the parent requires deep, non-mechanical work at every change site — plan for substantial authoring time
- Tests are co-deliverables: sub-loop validation test classes must be authored alongside each sub-loop creation — implement tests first so structural assertions catch wiring errors early
- CONTRIBUTING.md count in the issue says 77→80 but current loop count is 78; implementer should use 78→81

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-09
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-2048: Create rlhf-svg-evaluate sub-loop
- ENH-2049: Create rlhf-svg-refine sub-loop
- ENH-2050: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)
- ENH-2051: Create rlhf-svg-generate sub-loop

## Session Log
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:confidence-check` - 2026-06-09T17:00:00Z - `04c5252e-d013-4e45-9c2b-a46f836805bc.jsonl`
- `/ll:wire-issue` - 2026-06-09T16:03:29 - `6a7b197c-9039-4df8-bd95-51eead836dc2.jsonl`
- `/ll:confidence-check` - 2026-06-09T16:00:00Z - `31d470e4-290a-4a71-9d0f-9807d7b7bf16.jsonl`
- `/ll:format-issue` - 2026-06-09T15:43:23 - `76321915-d9bd-42c3-b0f4-d22861417203.jsonl`
- `/ll:capture-issue` - 2026-06-09T15:39:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b09a5a68-6cd2-4934-b07a-972c01dc416b.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-06-09
- **Decomposed into**: ENH-2048, ENH-2049, ENH-2050, ENH-2051

Work for ENH-2044 is now carried by its child issues; this parent was closed by rn-decompose.
