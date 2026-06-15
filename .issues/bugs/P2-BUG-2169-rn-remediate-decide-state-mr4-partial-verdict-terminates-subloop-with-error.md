---
id: BUG-2169
title: "rn-remediate decide state MR-4 violation \u2014 partial verdict terminates\
  \ sub-loop with error"
priority: P2
type: BUG
status: done
captured_at: '2026-06-15T15:41:00Z'
completed_at: '2026-06-15T16:30:03Z'
discovered_date: '2026-06-15'
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: decide
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
- rn-remediate
- loop-defect
- mr-4
- evaluator
relates_to:
- BUG-2075
- BUG-2115
confidence_score: 98
outcome_confidence: 88
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 25
---

# BUG-2169: rn-remediate decide state MR-4 — partial verdict terminates sub-loop with error

## Summary

The `decide` state in `rn-remediate` defines only `on_success: re_assess` and `on_error: re_assess`, omitting `on_yes`, `on_no`, and `on_partial`. When the LLM evaluator returns `partial` (decision partially made but not fully resolved), the FSM finds no matching route and terminates the sub-loop with `terminated_by: error`.

Observed in run `2026-06-15T143021` (input ENH-2156): `/ll:decide-issue ENH-2156 --auto` ran successfully (exit 0, ~112s) and the LLM evaluator returned `partial` — the decision scan completed but found an open question in a non-standard section rather than the expected `## Open Questions` header. The sub-loop crashed at `decide` (iteration 6), surfacing in rn-implement as a `record_sub_loop_crash` entry with ENH-2156 unimplemented.

BUG-2075 (assessed, done) explicitly flagged `decide`, `wire`, `refine`, and `re_assess` as sibling states sharing this defect. BUG-2115 (re_assess, done) was then patched. The `decide` state remains unfixed.

## Steps to Reproduce

1. Run `ll-loop run rn-remediate` with an issue that requires a `decide` step (e.g., an issue with `decision_needed` status).
2. `/ll:decide-issue [ID] --auto` executes and exits 0, but the LLM evaluator returns verdict `partial` (e.g., decision scan completed but found an open question in a non-standard section rather than `## Open Questions`).
3. The FSM looks for `on_yes`, `on_no`, or `on_partial` routing in the `decide` state — none are defined (only `on_success`/`on_error` exist).
4. Observe: loop terminates with `loop_complete final_state=decide terminated_by=error` instead of routing to `re_assess`.

## Current Behavior

```
state: decide (rn-remediate)
action: /ll:decide-issue ENH-2156 --auto
verdict: partial
result: loop_complete final_state=decide terminated_by=error
outer: record_sub_loop_crash → ENH-2156 skipped
```

## Expected Behavior

`partial` verdict from `decide` should route to `re_assess` (same as `on_yes`/`on_no`), so the sub-loop continues to re-evaluate whether the partially-resolved decision is sufficient to proceed.

## Root Cause

`decide` uses `on_success`/`on_error` (shell exit-code routing) instead of `on_yes`/`on_no`/`on_partial` (LLM verdict routing). For a `slash_command` action type, the FSM evaluator is an LLM judge that emits yes/no/partial — `on_success` is not a recognized verdict routing key. A `partial` verdict finds no route and the FSM raises a routing error.

## Acceptance Criteria

1. `decide` state in `scripts/little_loops/loops/rn-remediate.yaml` defines `on_yes`, `on_no`, and `on_partial`, all routing to `re_assess`.
2. `ll-loop validate rn-remediate` passes with no MR-4 errors for the `decide` state (requires removing or narrowing `partial_route_ok: true` at the loop level once all sibling states are fixed).
3. A run where `decide` returns `partial` routes to `re_assess` rather than terminating with error.
4. `wire` and `refine` states are audited for the same pattern and fixed in the same PR if affected.

## Impact

- **Priority**: P2 — Sub-loop crash causes `decide`-state issues to be silently skipped by rn-implement, requiring manual re-run; observed in production run 2026-06-15T143021 with ENH-2156 unimplemented as a result.
- **Effort**: Small — Targeted YAML routing fix: replace `on_success`/`on_error` with `on_yes`/`on_no`/`on_partial` in the `decide` state; identical fix pattern to BUG-2115 (re_assess, done).
- **Risk**: Low — Well-understood routing change; no behavioral change when verdict is `yes` or `no`, only improves handling of `partial` verdicts that previously dead-ended.
- **Breaking Change**: No

## Implementation Notes

Replace `on_success`/`on_error` in the `decide` state with standard verdict routing:

```yaml
decide:
  fragment: with_rate_limit_handling
  action: "/ll:decide-issue ${context.issue_id} --auto"
  action_type: slash_command
  on_yes: re_assess
  on_no: re_assess
  on_partial: re_assess
  on_rate_limit_exhausted: rate_limit_diagnostic
```

Check `wire` and `refine` for the same `on_success` pattern (BUG-2075 noted them as siblings). If all sibling states are fixed, consider dropping `partial_route_ok: true` from the loop-level so MR-4 validation catches future regressions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — confirmed sibling defects and fix patterns:_

**`wire` state** (line 375) — current defect matches `decide`; comment explains success routes through `mark_wired` to preserve BUG-2007 marker-gate behavior:
```yaml
wire:
  fragment: with_rate_limit_handling
  action: "/ll:wire-issue ${context.issue_id} --auto"
  action_type: slash_command
  # BUG-2007 marker-gate: success → mark_wired → re_assess; error → refine (rewrite warranted)
  on_yes: mark_wired
  on_no: refine
  on_partial: mark_wired
  on_rate_limit_exhausted: rate_limit_diagnostic
```
`on_partial: mark_wired` — partial wire still marks and lets `re_assess → check_convergence` decide if a full refine pass is needed, preserving the BUG-2007 intent without forcing an unconditional rewrite.

**`refine` state** (line 392) — same defect; success routes through `mark_refined` for the marker-gate:
```yaml
refine:
  fragment: with_rate_limit_handling
  action: "/ll:refine-issue ${context.issue_id} --auto --full-rewrite"
  action_type: slash_command
  # Marker-gate: success → mark_refined → re_assess; failure → terminal
  on_yes: mark_refined
  on_no: emit_implement_failed
  on_partial: mark_refined
  on_rate_limit_exhausted: rate_limit_diagnostic
```

**`partial_route_ok: true` removal** — this flag is on line 30 of `rn-remediate.yaml` and suppresses MR-4 validation globally for the entire loop. Once `decide`, `wire`, and `refine` are all fixed, remove the flag so `ll-loop validate` re-enables per-state MR-4 enforcement as a regression guard.


## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — primary file; `decide` (line 367), `wire` (line 375), and `refine` (line 392) states need routing key replacement; top-level `partial_route_ok: true` (line 30) should be removed once all three states are fixed

### Dependent Files (Context Only — No Code Changes)
- `scripts/little_loops/fsm/executor.py` — `_route()` handles verdict dispatch; `StateConfig.from_dict()` in `schema.py` aliases `on_success` → `on_yes` at parse time, so `on_success` correctly reaches `on_yes` but `partial` finds no handler and returns `None` → `_finish("error")`
- `scripts/little_loops/fsm/validation.py` — `_validate_partial_route_dead_end()` / `_is_llm_judged()` implement MR-4; currently short-circuits on `partial_route_ok: true` before checking any per-state routing
- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass defines `on_yes`, `on_no`, `on_partial`, `on_success`, `on_error` fields and aliasing logic
- `scripts/little_loops/loops/lib/common.yaml` — `with_rate_limit_handling` fragment (line 61); adds retry/backoff config only, contributes no routing keys

### Similar Patterns (Fixed Reference)
- `rn-remediate.yaml` state `re_assess` (line 422) — gold-standard pattern from BUG-2115: uses `on_success`, `on_partial`, `on_no`, `on_error` together; `on_success` and `on_partial` both route to `verify_re_assess_scores`, `on_no` → `refine`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestRnRemediateAssessRouting` (line 6832): assertion pattern for `assess` state routing; add parallel tests for `decide`, `wire`, `refine` in this class
- `scripts/tests/test_builtin_loops.py` — `TestValidatorWarningBudget`: ratchet test that will catch regression if `partial-route` warnings reappear for `rn-remediate` after `partial_route_ok` is removed
- `scripts/tests/test_fsm_validation.py` — `TestPartialRouteDeadEnd` (line 1245): unit tests for `_validate_partial_route_dead_end()`; validates that `slash_command` states without `on_partial` fire MR-4

### Documentation
- No documentation changes required; MR-4 rule is already documented in `.claude/CLAUDE.md`

## Implementation Steps

1. **Fix `decide` state** — replace `on_success`/`on_error` with `on_yes`/`on_no`/`on_partial` in `rn-remediate.yaml` (see Implementation Notes)
2. **Fix `wire` state** — replace `on_success`/`on_error` with verdict routing; `on_yes: mark_wired`, `on_no: refine`, `on_partial: mark_wired` (partial wire still marks and lets `re_assess` evaluate sufficiency)
3. **Fix `refine` state** — replace `on_success`/`on_error` with verdict routing; `on_yes: mark_refined`, `on_no: emit_implement_failed`, `on_partial: mark_refined` (partial refine still marks and lets `re_assess` evaluate)
4. **Remove `partial_route_ok: true`** from loop top-level (line 30) — only safe after all three sibling states are fixed; removing it re-enables MR-4 validation as a regression guard
5. **Add regression tests** in `test_builtin_loops.py::TestRnRemediateAssessRouting` for `decide`, `wire`, and `refine` states following the `assess` pattern (lines 6842–6854)
6. **Run validation**: `ll-loop validate rn-remediate` — should pass with no MR-4 errors after removal of `partial_route_ok: true`
7. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py::TestRnRemediateAssessRouting -v`

## Session Log
- `/ll:ready-issue` - 2026-06-15T16:24:25 - `7fb5de02-80e2-4951-a337-e824c62c01a2.jsonl`
- `/ll:refine-issue` - 2026-06-15T16:17:35 - `b312a960-ff84-4b0f-9adc-3c7c888753c3.jsonl`
- `/ll:format-issue` - 2026-06-15T16:00:19 - `6af8e5ab-bf71-4158-bd83-ace02f8dce6e.jsonl`
- `/ll:confidence-check` - 2026-06-15T17:08:00Z - `a79cce22-176e-48d5-b717-e7488b24376a.jsonl`
- `/ll:confidence-check` - 2026-06-15T18:00:00Z - `9e2d5060-ec4b-4c25-9374-f87e60cf3f88.jsonl`
