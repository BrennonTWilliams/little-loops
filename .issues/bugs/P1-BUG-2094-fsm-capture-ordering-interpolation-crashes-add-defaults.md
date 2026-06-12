---
id: BUG-2094
title: FSM loops reference captures from states that may not have executed (InterpolationError crashes)
type: BUG
priority: P1
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-1961
---

# BUG-2094: FSM loops reference captures from states that may not have executed

## Summary

The ENH-1961 capture-dominance validator flags ~20 states across 10 builtin loops that interpolate `${captured.X.*}` where the capturing state is bypassed on at least one execution path. A missing capture raises `InterpolationError` and errors the whole loop (`scripts/little_loops/fsm/executor.py:506-513`, `scripts/little_loops/fsm/interpolation.py:133`) — unless the reference uses the `:default=` syntax (`scripts/little_loops/fsm/interpolation.py:225-232`). Each flagged reference is a latent crash on the bypass path.

## Current Behavior

`ll-loop validate` reports "References ${captured.X.*} but 'X' is captured by state 'Y' which may not execute on all paths" for the states below. When the bypass path executes, the loop dies with `InterpolationError` instead of completing.

## Expected Behavior

Each genuine bypass-path reference uses `:default=` (e.g. `${captured.user_plan_decision.output:default=auto-approved}`) with a semantically sensible default. Verified false positives are documented in the `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` instead.

## Triage table (Bucket B — fix with `:default=`)

| Loop | State referencing | Capture | Bypass path |
|---|---|---|---|
| loop-composer.yaml | present_result | user_plan_decision, chain_review | auto-plan path (`check_auto_plan → execute_plan → … → present_result`) |
| loop-composer-adaptive.yaml | present_result | user_plan_decision, chain_review | same auto-plan path |
| goal-cluster.yaml | propagate_context | batch_success_record, batch_failed_record | each bypassed when the other branch ran |
| goal-cluster.yaml | synthesize_cluster_result | batch_success_record | failure branch |
| goal-cluster.yaml | present_result | cluster_summary, user_plan_decision | auto path |
| general-task.yaml | check_done | work_result, selected_step | resume path via `resume_check` |
| harness-optimize.yaml | propose, apply | state_name, benchmark_score | first-iteration path (`init_run → … → init_prev → propose`) — verify whether `init_prev` seeds these; if so move to allowlist as false positive |
| rl-coding-agent.yaml | diagnose | prev_reward | `act → refine → …` path |
| rn-build.yaml | check_harness_name | harness_name | neither `read_harness_name` nor `resume_read_harness` dominates |
| rn-build.yaml | synthesize_result | eval_result | path bypassing `eval_gate` |
| learning-tests-audit.yaml | build_report | stale_result | path bypassing `mark_stale_candidates` |
| integrate-sdk.yaml | diagnose_and_block | scaffold_result, verify_result | early-refute path — diagnostic state, use `:default=not-reached` |
| loop-router.yaml | present_choices | builtin_score, project_score | each bypassed by the other branch of `route_branch_project` |
| loop-router.yaml | present_result | new_loop_proposal, review_result | branch-dependent |

## Bucket A — verified sub-loop captures (false positives, no fix; keep allowlisted)

- adopt-third-party-api.yaml `enumeration` (produced by sub-loop; validator itself notes this)
- integrate-sdk.yaml `targets`/`enumeration` (sub-loop)
- examples-miner.yaml `run_optimizer` (sub-loop)
- goal-cluster.yaml / rn-build.yaml `plan_display` (sub-loop)

## Acceptance Criteria

- [ ] Every Bucket B reference above either uses `:default=` with a sensible default or is proven dominated (and the validator confirms)
- [ ] `harness-optimize` first-iteration seeding verified; reference fixed or reclassified to Bucket A
- [ ] Corresponding `capture-ordering` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` (the staleness test enforces this)
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
