---
id: BUG-2417
title: "rn-plan-apo is a no-op optimizer — writes a prompt file rn-plan never reads"
type: BUG
priority: P2
status: done
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Medium
relates_to:
- EPIC-2412
- FEAT-2413
labels:
- loops
- meta-loop
- rn-plan
- apo
- bug
---

# BUG-2417: rn-plan-apo is a no-op optimizer — writes a prompt file rn-plan never reads

## Summary

`rn-plan-apo.yaml` optimizes a `plan_prompt_file` (default
`.ll/prompts/rn-plan-planning.md`) that `rn-plan` **never reads**, so its
measure→propose→apply→re-measure spine is severed at the `apply_gradient` step: the
computed text gradient is written to a file that has no effect on subsequent
`run_planner` iterations. It additionally lacks the non-LLM external evaluator that
meta-loop rule MR-1 requires (its quality signal is `score_plans` plus an LLM-emitted
`CONVERGED`).

## Current Behavior

- `rn-plan-apo` runs `ll-loop run rn-plan` per benchmark task, scores the resulting
  plan trees, computes a gradient, and `apply_gradient` overwrites
  `.ll/prompts/rn-plan-planning.md`.
- `rn-plan` hardcodes its planning prompt **inline** in `generate_rubric` and the
  oracle prompts (`oracles/plan-research-iteration`, `plan-node-refine`); grep
  confirms `plan_prompt_file` / `rn-plan-planning` appear ONLY in `rn-plan-apo.yaml`.
- The `.ll/prompts/` directory does not exist in the repo.
- Convergence is LLM-emitted (the model decides `PLAN_QUALITY > target`); no non-LLM
  measurement of plan quality (MR-1 violation).

## Expected Behavior

Either the optimizer actually tunes rn-plan's behavior, or it is retired. When run, an
applied gradient must change subsequent `run_planner` output; convergence must be
gated by at least one non-LLM external evaluator.

## Steps to Reproduce

1. `grep -rn "plan_prompt_file\|rn-plan-planning" scripts/little_loops/loops/` — matches
   appear only in `rn-plan-apo.yaml`, never in `rn-plan.yaml`.
2. Run `ll-loop run rn-plan-apo` so `apply_gradient` overwrites
   `.ll/prompts/rn-plan-planning.md`.
3. Run `ll-loop run rn-plan` and inspect `run_planner` output.
4. Observe: the applied gradient has no effect on planning output because `rn-plan`
   inlines its planning prompt and never reads the file.

## Root Cause

Broken indirection contract: the optimizer assumes rn-plan externalizes its planning
prompt to `plan_prompt_file`, but rn-plan inlines it. No wiring connects the two.

## Proposed Solution

Pick one:

1. **Fix the spine:** externalize rn-plan's planning prompt to
   `.ll/prompts/rn-plan-planning.md` (create default on first run), have
   `generate_rubric`/oracle states read it via interpolation, so `apply_gradient`
   takes effect; add a non-LLM plan-quality signal (e.g. the FEAT-2413 run-gate on a
   plan's executable steps, or `output_numeric` on measured sub-task success) to
   satisfy MR-1; and add `ll-loop run --baseline` validation.
2. **Retire it:** delete `rn-plan-apo.yaml` and its benchmark references if prompt
   optimization for rn-plan is not a priority.

## Acceptance Criteria

- If fixed: an applied gradient demonstrably changes `run_planner` output across
  iterations, and `ll-loop validate rn-plan-apo` passes MR-1 without
  `meta_self_eval_ok`.
- If retired: the loop and its dangling references are removed and `ll-loop validate`
  is clean.

## Location

- `scripts/little_loops/loops/rn-plan-apo.yaml`
- `scripts/little_loops/loops/rn-plan.yaml` (`generate_rubric`)
- `scripts/little_loops/loops/lib/common.yaml` (`plan_rubric_score` fragment)

## Impact

- **Priority**: P3 - The optimizer is inert rather than actively harmful; it wastes
  runs and violates MR-1, but no user-facing output is corrupted.
- **Effort**: Medium - Either externalize and wire the planning prompt plus add a
  non-LLM signal and baseline validation, or delete the loop and its dangling
  references.
- **Risk**: Low - Both resolution paths are self-contained to `rn-plan-apo` and its
  references; `ll-loop validate` gates the result.
- **Breaking Change**: No

## Status

**Done** | Created: 2026-06-30 | Priority: P2

## Session Log

- 2026-07-03: Fixed via option 1 (fix the spine). `rn-plan` now owns a
  `plan_prompt_file` context entry (default `.ll/prompts/rn-plan-planning.md`,
  matching rn-plan-apo), seeds the file with default planning guidance in `init`
  when missing (never clobbering an optimized prompt), re-reads it every run via
  a new `load_planning_prompt` shell state, and interpolates
  `${captured.planning_prompt.output}` into the `generate_rubric` planning
  prompt — so `apply_gradient`'s overwrite now changes subsequent `run_planner`
  output. `rn-plan-apo`'s `run_planner` forwards
  `--context plan_prompt_file=...` to each `ll-loop run rn-plan` invocation so
  overridden paths stay contract-consistent. Priority raised P3 → P2. Tests:
  new `TestPlanningPromptWiring` class in `scripts/tests/test_rn_plan.py`
  (structural wiring, cross-loop default contract, functional bash tests for
  seed/no-clobber/clean-stdout) plus a forwarding test in
  `scripts/tests/test_rn_plan_apo.py`; all pass, and
  `ll-loop validate rn-plan` / `ll-loop validate rn-plan-apo` report valid with
  no MR-1 violation and no suppression flags. Note: convergence remains
  LLM-emitted (`CONVERGED` sentinel, matching apo-textgrad); a numeric
  non-LLM convergence gate on PLAN_QUALITY is a possible follow-on but MR-1
  does not fire on this loop (no `check_semantic`/`llm_structured` states).
