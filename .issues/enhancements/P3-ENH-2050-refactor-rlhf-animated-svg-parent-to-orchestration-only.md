---
id: ENH-2050
title: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)
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
confidence_score: 83
outcome_confidence: 78
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
decision_needed: false
size: Very Large
completed_at: '2026-06-09T17:20:18Z'
---

# ENH-2050: Refactor rlhf-animated-svg parent to orchestration-only (~400 lines)

## Summary

With the three sub-loops (ENH-2048, ENH-2049, ENH-2051) created, refactor `rlhf-animated-svg.yaml` to delegate each phase via `loop: + with:`, reducing it to ~400 lines of orchestration. Add the parent test class and update docs/CONTRIBUTING.

## Parent Issue

Decomposed from ENH-2044: Decompose rlhf-animated-svg loop into sub-loops

## Prerequisites

- ENH-2051 (rlhf-svg-generate), ENH-2048 (rlhf-svg-evaluate), ENH-2049 (rlhf-svg-refine) must be merged

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — refactor from 2001 lines to ≤450 lines; replace 8 inline states with 3 sub-loop delegation states

### Sub-loop Targets (already created)
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml` (687 lines) — invoked as `loop: rlhf-svg-evaluate`; `context:` keys: `run_dir`, `quality_target`, `smoke_bypass_threshold`, `exploit_cutoff`; terminal output sentinel: `VISION_PASS` or `VISION_FAIL`
- `scripts/little_loops/loops/rlhf-svg-refine.yaml` (666 lines) — invoked as `loop: rlhf-svg-refine`; `context:` keys: `run_dir`, `animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, `design_tokens_context`; surfaces `REPLAN_NEEDED` and `CRITICAL_ERROR` via `done` terminal output
- `scripts/little_loops/loops/rlhf-svg-generate.yaml` — **NOT YET CREATED** (prerequisite ENH-2051); invoked as `loop: rlhf-svg-generate`; `with:` keys defined by ENH-2051's `context:` block

### Tests to Add
- `scripts/tests/test_builtin_loops.py` — append class `TestRlhfAnimatedSvgParentOrchestration`; model: `TestRnPlanDelegatesResearchToOracle` (line 6187); sibling evaluate/refine test classes at lines 6308 and 6358

### Documentation to Update
- `CONTRIBUTING.md` (line 122) — "77 YAML files" → "81 YAML files" (actual root count is 80 now; +1 when ENH-2051 adds generate.yaml)
- `docs/guides/LOOPS_GUIDE.md` — three locations: line 1460 overview table, lines 2215–2223 FSM diagram, after line 2244 new sub-loop sections

### Reference Patterns
- `scripts/little_loops/loops/rn-plan.yaml:99` — `research_iteration` state: canonical `loop: + with: + on_success/on_failure/on_error` delegation syntax
- `scripts/tests/test_builtin_loops.py:6187` — `TestRnPlanDelegatesResearchToOracle`: one test method per absent state + `loop:` value assertion + `with:` key assertions
- `scripts/tests/test_builtin_loops.py:6308` — `TestRlhfSvgEvaluateSubLoop`: required-states set membership + context-key assertions (same file, close precedent)

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

Model: `TestRnPlanDelegatesResearchToOracle` (line 6185).

### 3. Update `CONTRIBUTING.md` (line 122)

Bump loop YAML count from 77 → 81 to reflect the three new YAML files added by ENH-2048, ENH-2049, and ENH-2051. (CONTRIBUTING.md currently reads "77 YAML files"; actual root count is already 80 with evaluate and refine in place — will be 81 after generate is added by ENH-2051.)

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 83/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- ENH-2051 (rlhf-svg-generate) is still `open` and `rlhf-svg-generate.yaml` does not exist; implementing the `loop: rlhf-svg-generate` delegation before this file is created will cause `ll-loop validate` to fail — complete ENH-2051 first, or implement only evaluate/refine delegation and accept the ≤450 line target will not be met until generate lands
- CONTRIBUTING.md currently reads "77 YAML files" while the actual count is 80; the implementation step updates to 81 (after ENH-2051 adds generate.yaml) — verify 81 is the correct final count before applying the bump

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-09
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-2056: Refactor rlhf-animated-svg.yaml to orchestration-only and write parent test class
- ENH-2057: Update CONTRIBUTING.md loop count and LOOPS_GUIDE.md for rlhf-svg sub-loops

## Session Log
- `/ll:refine-issue` - 2026-06-09T17:11:51 - `807fe928-1130-4bf2-adad-9a6fd2af3f02.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `852d825e-ec36-4b78-a79e-3e0c5457f603.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `2f6693f7-ace4-4f21-ba6e-fcd0b812cff0.jsonl`
- `/ll:confidence-check` - 2026-06-09T19:00:00Z - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`
- `/ll:issue-size-review` - 2026-06-09T00:00:00Z - `282714c3-7d9b-4b3a-9cf9-413e6bba8138.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-06-09
- **Decomposed into**: ENH-2056, ENH-2057

Work for ENH-2050 is now carried by its child issues; this parent was closed by rn-decompose.
