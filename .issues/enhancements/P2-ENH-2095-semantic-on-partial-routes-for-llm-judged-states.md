---
id: ENH-2095
title: Add semantic on_partial routes to LLM-judged states that dead-end on partial verdicts
type: ENH
priority: P2
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-1917
---

# ENH-2095: Add semantic on_partial routes to LLM-judged states

## Summary

Nine LLM-judged states across nine builtin loops route only `on_yes`/`on_no`; a `partial` verdict has no route and dead-ends the loop (parent reads this as failed) — MR-4 / ENH-1917. Unlike the mechanical batch fixed in the 2026-06-12 audit (where yes and no shared a target), these states need a *conservative* routing decision: partial must go to the continue/retry branch, never the success/destructive branch.

## Current Behavior

`ll-loop validate` reports the ENH-1917 partial-route warning for each state below. A partial verdict at runtime dead-ends the loop.

## Expected Behavior

Each state routes `on_partial` to its conservative branch per this table:

| File | State | on_yes / on_no | Add | Rationale |
|---|---|---|---|---|
| agent-eval-improve.yaml | analyze_failures | route_quality / done | `on_partial: route_quality` | partial patterns are still actionable |
| dataset-curation.yaml | validate_schema | publish / fix_item | `on_partial: fix_item` | never publish on partial |
| eval-driven-development.yaml | route_eval | done / refine_issues | `on_partial: refine_issues` | partial pass is not done |
| harness-multi-item.yaml | check_skill | check_semantic / execute | `on_partial: execute` | retry |
| incremental-refactor.yaml | check_complete | done / execute_step | `on_partial: execute_step` | keep refactoring |
| issue-staleness-review.yaml | triage | close_issue / reprioritize | `on_partial: reprioritize` | never close on partial |
| loop-specialist-eval.yaml | check_skill | done / execute | `on_partial: execute` | retry |
| outer-loop-eval.yaml | generate_report | done / refine_analysis | `on_partial: refine_analysis` | refine further |
| loop-router.yaml | propose_new_loop | check_auto_create / present_result | `on_partial: present_result` | surface to user, don't auto-create |

`partial_route_ok: true` is recommended nowhere — every state has an obvious safe target.

Note: dataset-curation's fix also clears the warning bubbled into sft-corpus by `ll-loop validate` (sub-loop recursion).

## Acceptance Criteria

- [ ] All nine states route on_partial per the table
- [ ] `ll-loop validate` reports zero ENH-1917 warnings across builtin loops
- [ ] Corresponding `partial-route` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
