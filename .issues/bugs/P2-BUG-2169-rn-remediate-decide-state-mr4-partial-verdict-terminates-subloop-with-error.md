---
id: BUG-2169
title: "rn-remediate decide state MR-4 violation — partial verdict terminates sub-loop with error"
priority: P2
type: BUG
status: open
captured_at: '2026-06-15T15:41:00Z'
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


## Session Log
- `/ll:format-issue` - 2026-06-15T16:00:19 - `6af8e5ab-bf71-4158-bd83-ace02f8dce6e.jsonl`
