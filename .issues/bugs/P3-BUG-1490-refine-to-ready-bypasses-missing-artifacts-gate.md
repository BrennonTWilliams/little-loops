---
id: BUG-1490
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T04:06:13Z'
completed_at: '2026-05-16T04:27:00Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-1490: `refine-to-ready-issue` bypasses `missing_artifacts` gate before `breakdown_issue`

## Summary

When `outcome_confidence < 75` and `decision_needed: false`, the `refine-to-ready-issue`
sub-loop routes directly to `breakdown_issue` (size-review) without checking whether
`missing_artifacts: true` is set. The outer `autodev` loop has a `check_missing_artifacts`
→ `run_wire` repair path, but it is only reachable after the sub-loop exits — and the
sub-loop's size-review runs first, wasting cycles and potentially decomposing an issue
that is already well-specified (e.g. FEAT-1486: 98/100 readiness).

## Motivation

The missing `missing_artifacts` gate causes the wrong repair tool to be applied:
- Size-review solves scope; `run_wire` solves specification completeness — they are not interchangeable
- Observed failure: FEAT-1486 (98/100 readiness) hit size-review, causing an unwanted loop interruption
- The outer `autodev` loop's repair path (`check_missing_artifacts` → `run_wire`) becomes
  structurally unreachable whenever the sub-loop runs `breakdown_issue` first

## Current Behavior

In `refine-to-ready-issue`, the post-confidence-check routing is:

```
check_outcome (fail) → check_decision_needed → breakdown_issue (size-review)
```

`missing_artifacts` is never checked inside the sub-loop. The outer `autodev` FSM has:

```
triage_outcome_failure → check_missing_artifacts → run_wire
```

But this path is only reached after the sub-loop completes its `breakdown_issue` state.

## Expected Behavior

When `missing_artifacts: true` is set and `outcome < 75`, the sub-loop should exit cleanly
(without running size-review) so the outer `autodev` loop's `triage_outcome_failure` →
`check_missing_artifacts` → `run_wire` path can handle the repair. Size-review is the wrong
tool for a wiring/artifact gap — it solves scope, not specification completeness.

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml` (likely)
- **State sequence**: `check_outcome` → `check_decision_needed` → `breakdown_issue`
- **Missing gate**: No `check_missing_artifacts` step between `check_decision_needed` and
  `breakdown_issue`. The fix is to insert a gate that exits the sub-loop (`done` or
  `failed`) when `missing_artifacts: true`, allowing the outer FSM to route correctly.

## Steps to Reproduce

1. Run `ll-loop run autodev "FEAT-1486 -v"` (or any issue with `missing_artifacts: true`
   and `outcome_confidence < 75`)
2. Observe: sub-loop reaches `breakdown_issue` and runs `/ll:issue-size-review --auto`
3. Expected: sub-loop exits cleanly; outer loop routes to `run_wire`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — Insert `check_missing_artifacts` gate state between `check_decision_needed` and `breakdown_issue`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — Outer FSM invoking the sub-loop at `refine_current` (line 92); `triage_outcome_failure` → `check_missing_artifacts` path only becomes reachable after fix
- `scripts/little_loops/loops/issue-refinement.yaml` — Calls `refine-to-ready-issue` at line 30; same sub-loop exit behavior applies (verify no separate `missing_artifacts` handler)
- `scripts/little_loops/loops/recursive-refine.yaml` — Calls `refine-to-ready-issue` at line 170; uses `check_broke_down` to detect whether size-review ran; no `missing_artifacts` gate of its own

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml` in `check_missing_artifacts` (lines 419–427) — **Exact pattern to replicate**; difference: uses `${captured.input.output}` (autodev's variable) vs `${captured.issue_id.output}` (refine-to-ready's variable), and routes `on_yes: run_wire` in autodev vs should route `on_yes: done` in refine-to-ready (caller owns wire repair)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` in `check_decision_needed` (lines 260–269) — **Direct peer gate** inserted by BUG-1366; same `shell_exit` fragment, same `on_yes: done` / `on_no: breakdown_issue` structure; add `check_missing_artifacts` immediately after this state, before `breakdown_issue`

### Tests
- `scripts/tests/test_builtin_loops.py` — `test_all_validate_as_valid_fsm` (line 36–44): all loop YAMLs pass FSM validation; will pass after new state is added
- `scripts/tests/test_fsm_flow.py` — `TestBuiltinLoopRegression.test_all_builtin_loops_still_load` (line 325–331): all loop YAML files load without error

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestRefineToReadyIssueSubLoop`: add 5 new test methods to prevent regression (no existing test pins `check_decision_needed.on_no`):
  - `test_check_missing_artifacts_state_exists` — asserts state is present in `refine-to-ready-issue`
  - `test_check_missing_artifacts_uses_shell_exit_fragment` — asserts `fragment: shell_exit`
  - `test_check_missing_artifacts_on_yes_routes_to_done` — asserts `on_yes: done`
  - `test_check_missing_artifacts_on_no_routes_to_breakdown_issue` — asserts `on_no: breakdown_issue`
  - `test_check_decision_needed_on_no_routes_to_check_missing_artifacts` — asserts `check_decision_needed.on_no == "check_missing_artifacts"` (not `"breakdown_issue"`)
  Follow the pattern from `TestAutodevLoop.test_check_missing_artifacts_*` (lines 1576–1594 of `test_builtin_loops.py`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` line 293 — prose states `"Failure routes to breakdown_issue (low outcome confidence signals a scope problem…)"` — stale after fix; update to reflect the full gate chain: `check_outcome` → `check_decision_needed` → `check_missing_artifacts` → `breakdown_issue` (conditionally)

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/refine-to-ready-issue.yaml`; locate `check_decision_needed` (lines 260–269) — its `on_no` currently points to `breakdown_issue`
2. Change `check_decision_needed.on_no` and `check_decision_needed.on_error` from `breakdown_issue` to `check_missing_artifacts`
3. Insert the new `check_missing_artifacts` state immediately after `check_decision_needed` (before line 323 `breakdown_issue`):

   ```yaml
   check_missing_artifacts:
     # Gate before size-review: if missing_artifacts=true the low outcome score is
     # caused by absent files/unwired components, not scope. Exit via done so the
     # outer loop's triage_outcome_failure → check_missing_artifacts → run_wire path
     # can handle the repair. Mirrors check_decision_needed above and autodev.yaml:419.
     action: "ll-issues check-flag ${captured.issue_id.output} missing_artifacts"
     fragment: shell_exit
     on_yes: done
     on_no: breakdown_issue
     on_error: breakdown_issue
   ```

4. Verify `scripts/little_loops/loops/autodev.yaml` — confirm `triage_outcome_failure` (line 403) → `check_missing_artifacts` (line 419) path is structurally reachable once the sub-loop no longer calls `breakdown_issue` prematurely
5. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_flow.py -v` to confirm FSM validation passes with the new state
6. Add tests to `scripts/tests/test_builtin_loops.py` in `TestRefineToReadyIssueSubLoop` asserting the new state and updated routing (see Tests section for the 5 specific methods)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_GUIDE.md` line 293 — change `"Failure routes to breakdown_issue"` to reflect the full gate chain: failure routes through `check_decision_needed` → `check_missing_artifacts` → `breakdown_issue` (conditionally)

## Impact

- **Priority**: P3 - Causes incorrect loop routing and wasted cycles; does not corrupt data or block all usage
- **Effort**: Small - Additive gate state insertion in a single YAML loop definition
- **Risk**: Low - Additive change; does not alter existing routing when `missing_artifacts: false`
- **Breaking Change**: No

### System Impact
- Size-review runs on issues that are already well-specified (e.g., 98/100 readiness),
  creating noise and potentially decomposing issues that should stay whole
- The outer loop's `check_missing_artifacts` repair path is structurally unreachable for
  issues where `missing_artifacts=true` triggers during the sub-loop's confidence check
- Observed in FEAT-1486 autodev run (2026-05-16): loop was interrupted during the
  unnecessary size-review, leaving the issue unimplemented

## Acceptance Criteria

- [ ] `refine-to-ready-issue` checks `missing_artifacts` flag after `check_decision_needed`
      fails and before routing to `breakdown_issue`
- [ ] When `missing_artifacts: true`, the sub-loop exits (does NOT run size-review)
- [ ] The outer `autodev` loop's `triage_outcome_failure` → `check_missing_artifacts` path
      is reachable for issues with `missing_artifacts: true` and `outcome < 75`
- [ ] Existing behavior (size-review when `missing_artifacts: false`) is unchanged

## Labels

`bug`, `loops`, `autodev`, `fsm`, `refine-to-ready`

## Status

**Done** | Created: 2026-05-16 | Completed: 2026-05-16 | Priority: P3

## Resolution

Fixed by inserting `check_missing_artifacts` gate state between `check_decision_needed` and `breakdown_issue` in `refine-to-ready-issue.yaml`. Changed `check_decision_needed.on_no` and `check_decision_needed.on_error` from `breakdown_issue` to `check_missing_artifacts`. When `missing_artifacts: true`, the sub-loop now exits via `done`, allowing the outer `autodev` loop's `triage_outcome_failure → check_missing_artifacts → run_wire` path to handle repair. Also updated `docs/guides/LOOPS_GUIDE.md` to reflect the full three-gate chain and added 5 regression tests in `TestRefineToReadyIssueSubLoop`.

## Session Log
- `/ll:ready-issue` - 2026-05-16T04:23:59 - `99cac8da-4f28-42e6-8dbc-8095b5843f22.jsonl`
- `/ll:confidence-check` - 2026-05-16T04:25:00 - `e40b080a-efae-4ba3-a354-1a0e00ea6c7a.jsonl`
- `/ll:wire-issue` - 2026-05-16T04:19:21 - `eb28b6c9-84d0-4111-910a-5c9995456f1a.jsonl`
- `/ll:refine-issue` - 2026-05-16T04:14:50 - `eb40cea7-4a12-422f-a701-5d413a8ec138.jsonl`
- `/ll:format-issue` - 2026-05-16T04:10:46 - `bdf87445-2e6f-4176-b4f9-271ef09487e4.jsonl`
- `/ll:capture-issue` - 2026-05-16T04:06:13Z - `ffbdb77c-d0c6-43e0-a45d-2fb26e8e53b6.jsonl`
- `/ll:manage-issue` - 2026-05-16T04:27:00Z - `e40b080a-efae-4ba3-a354-1a0e00ea6c7a.jsonl`
