---
id: ENH-2095
title: Add semantic on_partial routes to LLM-judged states that dead-end on partial
  verdicts
type: ENH
priority: P2
status: done
captured_at: '2026-06-12T14:10:00Z'
completed_at: '2026-06-12T19:24:21Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-1917
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 23
---

# ENH-2095: Add semantic on_partial routes to LLM-judged states

## Summary

Nine LLM-judged states across nine builtin loops route only `on_yes`/`on_no`; a `partial` verdict has no route and dead-ends the loop (parent reads this as failed) — MR-4 / ENH-1917. Unlike the mechanical batch fixed in the 2026-06-12 audit (where yes and no shared a target), these states need a *conservative* routing decision: partial must go to the continue/retry branch, never the success/destructive branch.

## Motivation

Nine builtin loops can silently dead-end at runtime when an LLM judge returns `partial` — the FSM has no route for that verdict and the parent interprets the run as failed. This produces incorrect failure signals and wastes iterations for loops that could have continued retrying. ENH-1917 / MR-4 introduced the validation rule; ENH-2095 applies the conservative fix to the remaining nine states that need a semantic routing decision (the previous batch fix only handled states where `on_yes` and `on_no` shared the same target).

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

## Proposed Solution

For each of the nine states in the table above, add `on_partial: <conservative-branch>` to the state definition in the corresponding YAML file. The conservative branch is always the continue/retry path — never the success or destructive branch. Then remove the nine `partial-route` entries from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`.

Example edit for `incremental-refactor.yaml :: check_complete`:
```yaml
# Before
on_yes: done
on_no: execute_step

# After
on_yes: done
on_no: execute_step
on_partial: execute_step
```

## Acceptance Criteria

- [x] All nine states route on_partial per the table
- [x] `ll-loop validate` reports zero ENH-1917 warnings across builtin loops
- [x] Corresponding `partial-route` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
- [x] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Scope Boundaries

- **In scope**: Adding `on_partial` to the 9 states listed in the Expected Behavior table; removing their corresponding `partial-route` entries from `TestValidatorWarningBudget.ALLOWLIST`
- **Out of scope**: Changing existing `on_yes`/`on_no` routes; modifying FSM executor logic or the MR-4 validation rule itself; addressing any MR-4 violations beyond the nine listed; setting `partial_route_ok: true` on any state

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/agent-eval-improve.yaml` — add `on_partial: route_quality` to `analyze_failures` state
- `scripts/little_loops/loops/dataset-curation.yaml` — add `on_partial: fix_item` to `validate_schema` state
- `scripts/little_loops/loops/eval-driven-development.yaml` — add `on_partial: refine_issues` to `route_eval` state
- `scripts/little_loops/loops/harness-multi-item.yaml` — add `on_partial: execute` to `check_skill` state
- `scripts/little_loops/loops/incremental-refactor.yaml` — add `on_partial: execute_step` to `check_complete` state
- `scripts/little_loops/loops/issue-staleness-review.yaml` — add `on_partial: reprioritize` to `triage` state
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — add `on_partial: execute` to `check_skill` state
- `scripts/little_loops/loops/outer-loop-eval.yaml` — add `on_partial: refine_analysis` to `generate_report` state
- `scripts/little_loops/loops/loop-router.yaml` — add `on_partial: present_result` to `propose_new_loop` state
- `scripts/tests/test_builtin_loops.py` — remove 9 `partial-route` entries from `TestValidatorWarningBudget.ALLOWLIST`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/sft-corpus.yaml` — sub-loop of dataset-curation; MR-4 warning propagated via sub-loop recursion clears automatically once dataset-curation is fixed

### Similar Patterns
- The 2026-06-12 batch fix (mechanical on_yes/on_no same-target cases) is the prior art for this pattern — grep `on_partial` in `scripts/little_loops/loops/` for examples

### Tests
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget` — ALLOWLIST entries must be removed to shrink the allowlist

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. For each of the 9 states in the Expected Behavior table, open the corresponding YAML file and add the `on_partial` key to the state definition
2. Remove the 9 `partial-route` entries from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
3. Run `ll-loop validate` across all builtin loops to confirm zero ENH-1917 warnings remain
4. Run `python -m pytest scripts/tests/test_builtin_loops.py` to confirm test suite passes

## Impact

- **Priority**: P2 — MR-4 warnings outstanding after the 2026-06-12 batch fix; nine loops affected
- **Effort**: Small — nine targeted one-line YAML edits plus allowlist cleanup in one test file
- **Risk**: Low — additive routing only; existing `on_yes`/`on_no` paths are unchanged
- **Breaking Change**: No

## Labels

`fsm-loops`, `routing`, `validation`, `maint`

## Status

**Open** | Created: 2026-06-12 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-12T19:15:36 - `184d4317-63b7-47f0-9b07-d9e3fe44c9f4.jsonl`
- `/ll:format-issue` - 2026-06-12T18:27:58 - `b949881c-905f-41d2-8e07-bcf80e4e5eeb.jsonl`
- `/ll:confidence-check` - 2026-06-12T00:00:00Z - `91fb6aeb-ff73-4199-95e8-ad0d184347c9.jsonl`
