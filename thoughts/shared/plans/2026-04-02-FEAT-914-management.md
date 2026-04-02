# FEAT-914: Greenfield Project Builder Meta-Loop — Implementation Plan

## Overview

Create two new built-in FSM loop YAML files and update the test/README infrastructure.

## Phase 0: Write Tests (Red)

Add `eval-driven-development` and `greenfield-builder` (plus 5 pre-existing missing loops) to `test_builtin_loops.py:48-75` expected set. Tests will fail until the YAML files are created.

**Test specifications:**
- `test_expected_loops_exist` must include all 33 stems (26 existing + 5 undocumented + 2 new)
- `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` will auto-validate new files

## Phase 1: Write `eval-driven-development.yaml`

Inner loop — implements the eval→fix→refine cycle.

**States (9 + terminal):**
1. `implement` — `action_type: shell`, `ll-auto --priority P1,P2`, `capture: implement_result`, `next: commit_impl`
2. `commit_impl` — `action_type: prompt`, `/ll:commit`, `next: run_harness`
3. `run_harness` — `action_type: shell`, `ll-loop run ${context.harness_name}`, `capture: run_harness`, `next: capture_issues`
   - Uses shell interpolation workaround (not `loop:` field) per rl-coding-agent.yaml:37-44
4. `capture_issues` — `action_type: prompt`, analyzes `${captured.run_harness.output}`, creates issues via `/ll:capture-issue`, `next: commit_eval`
5. `commit_eval` — `action_type: prompt`, `/ll:commit`, `next: route_eval`
6. `route_eval` — pure routing state, `evaluate.type: llm_structured`, `source: ${captured.run_harness.output}`, routes `on_yes: done`, `on_no: refine_issues`
7. `refine_issues` — `loop: issue-refinement`, `context_passthrough: true`, `on_yes: tradeoff_review`, `on_no: tradeoff_review`
8. `tradeoff_review` — `action_type: prompt`, `/ll:tradeoff-review-issues`, `next: implement`
9. `done` — `terminal: true`

**Config:** `max_iterations: 20`, `timeout: 14400`, `on_handoff: spawn`
**Context:** `harness_name: ""` (required), `readiness_threshold: 90`, `outcome_threshold: 75`

## Phase 2: Write `greenfield-builder.yaml`

Outer loop — drives the full greenfield lifecycle.

**States (12 + terminal):**
1. `init` — `action_type: shell`, validate spec files exist + read, `capture: spec_content`, `next: tech_research`
2. `tech_research` — `action_type: prompt`, analyze spec + research tech decisions, write `docs/research.md`, `capture: tech_research`, `next: design_artifacts`
3. `design_artifacts` — `action_type: prompt`, produce `docs/data-model.md`, `docs/contracts/`, `docs/quickstart.md`, `capture: design_artifacts`, `next: commit_design`
4. `commit_design` — `action_type: prompt`, `/ll:commit`, `next: harness_planning`
5. `harness_planning` — `action_type: prompt`, plan harness per AUTOMATIC_HARNESSING_GUIDE.md, output YAML to `.loops/`, `capture: harness_plan`, `next: harness_issues`
6. `harness_issues` — `action_type: prompt`, create P1 FEAT issues for harness, `next: spec_decomposition`
7. `spec_decomposition` — `action_type: prompt`, decompose spec into FEAT/ENH issues via `/ll:capture-issue`, normalize, `next: commit_issues`
8. `commit_issues` — `action_type: prompt`, `/ll:commit`, `next: issue_refinement`
9. `issue_refinement` — `loop: issue-refinement`, `context_passthrough: true`, `on_yes: tradeoff_review`, `on_no: tradeoff_review`
10. `tradeoff_review` — `action_type: prompt`, `/ll:tradeoff-review-issues`, `next: commit_tradeoff`
11. `commit_tradeoff` — `action_type: prompt`, `/ll:commit`, `next: eval_driven_improvement`
12. `eval_driven_improvement` — `loop: eval-driven-development`, `context_passthrough: true`, `on_yes: done`, `on_no: done`
13. `done` — `terminal: true`

**Config:** `max_iterations: 20`, `timeout: 28800`, `on_handoff: spawn`
**Context:** `spec: ""` (required), `max_issues: 30`, `harness_name: ""`

## Phase 3: Update Infrastructure

1. **test_builtin_loops.py** — Add 7 stems to expected set (33 total)
2. **loops/README.md** — Add entries for both loops under a new "Greenfield" section

## Success Criteria

- [ ] `ll-loop validate eval-driven-development` passes
- [ ] `ll-loop validate greenfield-builder` passes
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes
