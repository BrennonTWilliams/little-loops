---
discovered_date: 2026-06-10
discovered_by: debug-loop-run
source_loop: rn-implement
source_state: assess
labels:
- rn-remediate
- loop-defect
- mr-4
- evaluator
confidence_score: 99
outcome_confidence: 93
score_complexity: 24
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 25
---

# BUG-2075: rn-remediate assess terminates with error on partial verdict — missing on_partial/on_no route

## Summary

The `assess` state in `rn-remediate` defines only `on_yes: verify_scores_persisted` and omits both `on_no` and `on_partial`. When the LLM evaluator returns anything other than `yes`, the FSM has no route and terminates the sub-loop with `terminated_by: error`. In the observed run (2026-06-10T170225, input ENH-2023), the `/ll:confidence-check` action completed successfully (93/100 PROCEED, all claims re-verified), but its output truncated mid-sentence before a trailing log-append step completed. The LLM evaluator returned `partial` (core work done, persistence step unconfirmed), found no `on_partial` route, and the sub-loop crashed — surfacing in rn-implement as a `record_sub_loop_crash` entry with 0 implemented / 0 decomposed.

This is an MR-4 violation: an LLM-judged state with `on_yes` but no `on_partial` or `on_no` silently dead-ends when the judge returns a non-yes verdict.

## Current Behavior

The `assess` state in `rn-remediate` defines only `on_yes: verify_scores_persisted`, with no `on_no`, no `on_partial`, and no `next:`/`route:` fallback. When the LLM evaluator returns `partial` or `no`, the FSM has no matching route and terminates the sub-loop with `terminated_by: error`. The crash surfaces in the parent `rn-implement` loop as a `record_sub_loop_crash` entry reporting 0 implemented / 0 decomposed — even when the underlying `/ll:confidence-check` action completed successfully (93/100 PROCEED).

## Loop Context

- **Loop**: `rn-remediate`
- **State**: `assess`
- **Signal type**: fatal_error (FATAL_ERROR termination — terminated_by=error, last evaluate verdict=partial)
- **Occurrences**: 1 (run 2026-06-10T170225)
- **Last observed**: 2026-06-10T17:05:51Z

## History Excerpt

Events leading to this signal:

```json
[
  {"event": "state_enter", "ts": "2026-06-10T17:02:26.053804+00:00", "state": "run_remediation", "iteration": 7},
  {"event": "loop_start", "ts": "2026-06-10T17:02:26.078651+00:00", "loop": "rn-remediate", "depth": 1},
  {"event": "state_enter", "ts": "2026-06-10T17:02:26.078784+00:00", "state": "assess", "iteration": 1, "depth": 1},
  {"event": "action_complete", "ts": "2026-06-10T17:05:26.781623+00:00", "exit_code": 0, "duration_ms": 180683, "is_prompt": true, "depth": 1,
   "output_preview": "93/100 → PROCEED — scores stable and unchanged. All integration map claims re-verified..."},
  {"event": "evaluate", "ts": "2026-06-10T17:05:51.500489+00:00", "type": "default", "verdict": "partial", "confidence": 0.8,
   "reason": "Core assessment work succeeded (93/100 PROCEED) but output ends mid-sentence before confirming session log append completed.", "depth": 1},
  {"event": "loop_complete", "ts": "2026-06-10T17:05:51.501086+00:00", "final_state": "assess", "iterations": 1, "terminated_by": "error", "depth": 1},
  {"event": "route", "ts": "2026-06-10T17:05:51.501647+00:00", "from": "run_remediation", "to": "record_sub_loop_crash"},
  {"event": "action_complete", "ts": "2026-06-10T17:05:51.513992+00:00", "exit_code": 0,
   "output_preview": "[SUB_LOOP_CRASH] ENH-2023 — sub-loop infrastructure failure (crash/timeout/context error)"}
]
```

## Steps to Reproduce

1. Run `rn-implement` such that it enters the `run_remediation` state, invoking the `rn-remediate` sub-loop on an issue (observed: ENH-2023).
2. In the sub-loop's `assess` state, let `/ll:confidence-check ${context.issue_id} --auto` complete with its output truncated before the trailing session-log append step, so the LLM evaluator returns `partial` (or returns `no` on a genuine "not ready" verdict).
3. Observe: the FSM finds no `on_partial`/`on_no` route on `assess`, emits `loop_complete ... terminated_by: error`, and the parent `rn-implement` loop records a `[SUB_LOOP_CRASH]` entry with 0 implemented / 0 decomposed.

## Expected Behavior

A `partial` verdict from the `assess` LLM evaluator should not crash the sub-loop. The core confidence-check work (score evaluation, PROCEED/HOLD determination) is the primary deliverable; a missing trailing log-append step is a side-effect. Expected routing options:

1. **`on_partial: verify_scores_persisted`** — treat partial like yes when the core assessment is confirmed (confidence ≥ 0.7); the session log is non-blocking.
2. **`on_partial: assess`** (with `max_retries: 1`) — retry once if the log append is considered mandatory.
3. **`on_no` route** should also be defined (e.g. `on_no: refine`) to handle a genuine "not ready" verdict from the confidence check without crashing.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Anchor**: `assess` state
- **Cause**: The `assess` state is LLM-judged (action is a `/ll:confidence-check` prompt) but only defines `on_yes: verify_scores_persisted`. With no `on_partial`, `on_no`, `next:`, or full `route:` table, any non-`yes` verdict has no destination, so the FSM terminates with `terminated_by: error` instead of routing. This is the exact MR-4 dead-end pattern (`ll-loop validate` rule MR-4).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Actual state shape (lines 70–76).** The `assess` state does not literally spell `on_yes`. It is:

  ```yaml
  assess:
    fragment: with_rate_limit_handling
    action: "/ll:confidence-check ${context.issue_id} --auto"
    action_type: slash_command
    on_success: verify_scores_persisted        # on_success is an ALIAS for on_yes
    on_error: emit_implement_failed
    on_rate_limit_exhausted: rate_limit_diagnostic
  ```

  `on_success` normalizes to `on_yes` at config load, so the issue's "only `on_yes`" framing is functionally correct — but the implementer must add `on_partial`/`on_no` to **this** block (keeping `fragment`, `action_type`, `on_error`, and `on_rate_limit_exhausted`), not replace it.
- **Routing mechanism confirmed.** `_route()` in `scripts/little_loops/fsm/executor.py:1318-1371` resolves a `partial` verdict only via `if verdict == "partial" and state.on_partial`. With `on_partial` undefined it returns `None`; the main loop treats a `None` route as `terminated_by: error`. This exactly reproduces the observed `loop_complete ... terminated_by: error` after `evaluate ... verdict: partial`.
- **Sibling states share the same defect.** `decide` (line 269), `wire` (line 277), `refine` (line 290), and `re_assess` (line 302) are all `action_type: slash_command` with `on_success`/`on_error` and no `on_partial`. A `partial` verdict from any of them dead-ends identically. This is why `partial_route_ok: true` is set loop-wide (line 29) — see the AC note below. A complete fix should decide whether to add `on_partial` to these siblings too, or scope strictly to `assess` (observed crash site).

## Proposed Solution

In `scripts/little_loops/loops/rn-remediate.yaml`, add `on_partial` and `on_no` routing to the `assess` state:

```yaml
assess:
  action: /ll:confidence-check ${context.current_issue} --auto
  on_yes: verify_scores_persisted
  on_partial: verify_scores_persisted   # core work done; treat like yes
  on_no: refine                          # readiness check failed; route to remediation
```

If the session log persistence is considered mandatory, use `on_partial: assess` with `max_retries: 1` instead. Either way, `on_no` must be defined so that a genuine "not ready" verdict routes to remediation rather than crashing the sub-loop.

### Codebase Research Findings

_Added by `/ll:refine-issue` — apply-ready edit against the actual state (lines 70–76):_

The snippet above uses `${context.current_issue}` and drops the existing fragment/error routes. The real loop parameter is `${context.issue_id}`, and the fragment + error routes must be preserved. Apply this as an **additive** edit:

```yaml
assess:
  fragment: with_rate_limit_handling
  action: "/ll:confidence-check ${context.issue_id} --auto"
  action_type: slash_command
  on_success: verify_scores_persisted
  on_partial: verify_scores_persisted     # ADD: core assessment done; treat like success
  on_no: refine                            # ADD: genuine "not ready" → remediate, don't crash
  on_error: emit_implement_failed
  on_rate_limit_exhausted: rate_limit_diagnostic
```

- `verify_scores_persisted` (line 78) and `refine` (line 290) are both existing states — valid route targets, no new states needed.
- The `on_partial: assess` + `max_retries` variant works too, but `with_rate_limit_handling` + `slash_command` does not declare `max_retries` today; treating `partial` as success (route to `verify_scores_persisted`, which gates on the persisted scores via `exit_code`) is the lower-risk path and still catches a genuinely missing score downstream.

## Impact

- **Lost work**: A successful confidence assessment (93/100 PROCEED, all claims re-verified) is silently discarded because a non-blocking session-log append step didn't confirm.
- **False crash signal**: The parent `rn-implement` loop records a spurious `[SUB_LOOP_CRASH]` with 0 implemented / 0 decomposed, masking the real outcome and potentially halting autonomous remediation progress.
- **Fragility**: Any `partial` or `no` verdict from `assess` — normal evaluator variance, not just truncation — crashes the sub-loop, making `rn-remediate` unreliable under automation (`ll-auto`, `ll-parallel`, recursive `rn-*` runs).

## Acceptance Criteria

- [ ] `assess` state in `rn-remediate.yaml` defines `on_partial` (routes to `verify_scores_persisted` or retries via `max_retries`)
- [ ] `assess` state defines `on_no` (routes to `refine` or another remediation state)
- [ ] `ll-loop validate rn-remediate` reports no MR-4 warnings for `assess`
- [ ] A test in `test_builtin_loops.py` asserts that `assess.on_partial` and `assess.on_no` are both defined

### Codebase Research Findings — AC accuracy note

_Added by `/ll:refine-issue`:_

- **AC-3 is already trivially satisfied and is a weak gate.** `partial_route_ok: true` is set at the loop top level (line 29), which suppresses MR-4 across the **entire** loop. `ll-loop validate rn-remediate` already prints `rn-remediate is valid` regardless of whether `assess` has `on_partial`. Treat AC-4 (the unit test) as the real regression gate; AC-3 does not detect this defect. Optionally, this issue could narrow `partial_route_ok` removal to a follow-up once all `slash_command` siblings (`decide`/`wire`/`refine`/`re_assess`) get explicit `on_partial` routes — only then can the suppression be safely dropped so MR-4 catches future regressions.
- **AC-4 test pattern.** Model the new test on the existing `test_<state>_on_no_routes_to_X` cases in `scripts/tests/test_builtin_loops.py` (e.g. the `verify_scores_persisted`/`check_readiness`/`check_outcome` route assertions). Load the `rn-remediate` loop fixture, fetch the `assess` state dict, and assert `state.get("on_partial")` and `state.get("on_no")` are both non-`None` (and, ideally, equal to `verify_scores_persisted` and `refine` respectively).

## Labels

`bug`, `loops`, `rn-remediate`, `mr-4`, `captured`

## Status

**Open** | Created: 2026-06-10 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-10T17:30:49 - `ad577b1d-7dad-484f-a66a-b97a3d7b50fd.jsonl`
- `/ll:refine-issue` - 2026-06-10T17:22:47 - `70d57987-45fa-4847-b696-68ca2b6d045c.jsonl`
- `/ll:format-issue` - 2026-06-10T17:18:33 - `dc479c35-508c-4756-b42a-1756c606cb41.jsonl`
- `/ll:confidence-check` - 2026-06-10T18:00:00 - `ec600de1-4538-4b97-8849-575bfbae9852.jsonl`
