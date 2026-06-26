---
decision_needed: false
id: BUG-2306
title: rn-remediate check_complexity_pre_implement degenerate gate bypasses ENH-2163
  enforcement for ABOVE_MINIMAL + non-zero change_surface
type: BUG
priority: P2
status: open
discovered_date: 2026-06-26
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: check_complexity_pre_implement
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
- loops
- rn-remediate
- loop-defect
- degenerate-gate
- enh-2163
relates_to:
- ENH-2163
- ENH-2153
- BUG-2007
confidence_score: 98
outcome_confidence: 84
score_complexity: 23
score_ambiguity: 18
score_change_surface: 21
score_test_coverage: 22
---

# BUG-2306: `check_complexity_pre_implement` degenerate gate bypasses ENH-2163 enforcement

## Summary

`rn-remediate.yaml` state `check_complexity_pre_implement` has `on_yes == on_no == on_error == check_wire_pre_implement`. The state computes a complexity check and exits 0 (ABOVE_MINIMAL) or 1 (MINIMAL), but both routes are identical — the routing signal is entirely discarded. As a result, ABOVE_MINIMAL issues that reach the readiness fast-path with a non-zero `change_surface` bypass `gate_implement` and go directly to `implement`, defeating ENH-2163's refine+wire enforcement contract.

## Current Behavior

`check_complexity_pre_implement` in `rn-remediate.yaml` is a degenerate gate: `on_yes`, `on_no`, and `on_error` all route to `check_wire_pre_implement`. The complexity band result (ABOVE_MINIMAL vs MINIMAL) is computed but never acted upon. When `check_wire_pre_implement` then finds a non-zero `change_surface` (exit 1), it routes directly to `implement`, bypassing `gate_implement`. ABOVE_MINIMAL issues with `change_surface > 0` reach implementation without the ENH-2163 refine+wire enforcement.

## Expected Behavior

`check_complexity_pre_implement` should have distinct routing based on band: ABOVE_MINIMAL issues should flow toward `gate_implement`, while MINIMAL issues may bypass it. At minimum, `check_wire_pre_implement`'s `on_no` branch (change_surface > 0) should route to `gate_implement` rather than directly to `implement`, ensuring ENH-2163 enforcement applies to all ABOVE_MINIMAL issues regardless of their `change_surface` value. No issue with ABOVE_MINIMAL complexity and `require_refine_and_wire=true` should reach `implement` without `gate_implement` being evaluated.

## Steps to Reproduce

1. Identify an issue with `score_complexity` ≥ threshold (ABOVE_MINIMAL band), `score_change_surface > 0`, and a confidence score ≥ 85 (passes `check_readiness`).
2. Ensure `require_refine_and_wire=true` is in effect for the loop run.
3. Run `ll-loop run rn-implement` targeting that issue (e.g., FEAT-2259 from the 2026-06-26T183836 run).
4. Observe the FSM trace: `assess → verify_scores_persisted → check_readiness(pass)` → `check_complexity_pre_implement(ABOVE_MINIMAL, exit=0)` → `check_wire_pre_implement(change_surface>0, exit=1)` → `implement`.
5. Confirm `gate_implement` was never entered — the ENH-2163 enforcement was bypassed.

## Evidence from rn-implement run 2026-06-26T183836

FEAT-2259 followed this path:
```
assess → verify_scores_persisted → check_readiness(pass: 94≥85)
  → check_complexity_pre_implement(ABOVE_MINIMAL, exit=0)
  → check_wire_pre_implement(change_surface=25>0, exit=1)
  → implement   ← gate_implement bypassed
```

The `gate_implement` state (which enforces "if `require_refine_and_wire=true` and band=ABOVE_MINIMAL, require refine+wire artifacts before implementing") is only reached when `check_wire_pre_implement` routes via `on_yes` (change_surface == 0) to the `wire` state. Issues with non-zero `change_surface` skip `gate_implement` entirely.

## Root Cause

When ENH-2163 was implemented, `check_complexity_pre_implement` was inserted as an intermediate gate in the fast-path but the branching was never completed:

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale assumption in ENH-2163**: `P3-ENH-2163-marker-gated-refine-wire-enforcement-rn-remediate.md` line 122 states `"check_wire_pre_implement → implement was left unchanged — it is only reachable when complexity < threshold (MINIMAL)"`. This assumption held only if `check_complexity_pre_implement` had distinct ABOVE_MINIMAL vs MINIMAL routing. Because it doesn't, ABOVE_MINIMAL issues enter `check_wire_pre_implement` and bypass the gate.
- **`gate_implement` already has the complexity band**: `verify_scores_persisted` (rn-remediate.yaml, ~line 100) writes `complexity_band_<ID>.txt` as a stable snapshot. `gate_implement` reads this file — it does not need complexity re-computed at gate time. Routing to `gate_implement` is sufficient; the gate itself handles the band check.
- **MR-4 validator does not catch this pattern**: `scripts/little_loops/fsm/validation.py:_validate_partial_route_dead_end` (line 1398) checks LLM-judged states only (`action_type: prompt/slash_command`). Shell `exit_code` states like `check_complexity_pre_implement` are excluded from MR-4, so the degenerate routing passes `ll-loop validate` without warning.

```yaml
# Current (degenerate):
check_complexity_pre_implement:
  action: |
    COMPLEXITY=$(jq -r '.score_complexity // 0' "$PRE" 2>/dev/null || echo 0)
    [ "$COMPLEXITY" -ge "$THRESHOLD" ] && exit 0 || exit 1
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: check_wire_pre_implement   # ABOVE_MINIMAL — same as MINIMAL!
  on_no: check_wire_pre_implement    # MINIMAL
  on_error: check_wire_pre_implement
```

## Proposed Solution

Route `check_wire_pre_implement`'s `on_no` (change_surface > 0) to `gate_implement` instead of directly to `implement`, so that the ENH-2163 enforcement applies to both change_surface paths:

```yaml
# check_wire_pre_implement:
check_wire_pre_implement:
  action: |
    CHANGE_SURFACE=$(jq -r '.score_change_surface // 0' "$PRE" 2>/dev/null || echo 0)
    [ "$CHANGE_SURFACE" -eq 0 ] && exit 0 || exit 1
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: wire                 # change_surface == 0 → wire (gate_implement reached via wire path)
  on_no: gate_implement        # change_surface != 0 → enforce ENH-2163 gate before implement
  on_error: implement
```

This ensures `gate_implement` is reached for all above-minimal issues, regardless of their `change_surface` value. The `check_complexity_pre_implement` state can then either be given distinct routing or collapsed into a no-op (since both paths now reach `gate_implement` which checks the band).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — change `check_wire_pre_implement.on_no` from `implement` to `gate_implement` (state at ~line 148; `on_no` at ~line 153)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — parent orchestrator; `run_remediation` state (~line 511) invokes `rn-remediate` via `with:`; no change needed here (does not pass `require_refine_and_wire`, so the sub-loop inherits the default `true`)

### Tests That Encode the Pre-Fix Behavior (Must Update)
- `scripts/tests/test_rn_remediate.py:489` — `test_check_complexity_pre_implement_on_yes_routes_to_wire_check` asserts all three routes of `check_complexity_pre_implement` point to `check_wire_pre_implement`; this test documents the degenerate state — update or annotate to reflect intended ABOVE_MINIMAL routing
- `scripts/tests/test_rn_remediate.py:613` — `test_minimal_ready_path_does_not_require_gate` asserts `cwpi["on_no"] == "implement"` and has a docstring claiming "only reachable when complexity < threshold"; after fix `on_no` must assert `"gate_implement"` and the docstring must be corrected
- `scripts/tests/test_rn_remediate.py:605` — `test_above_minimal_entry_points_route_through_gate` lists the two currently-wired entry points into `gate_implement`; must be extended to assert `check_wire_pre_implement.on_no == "gate_implement"` as a third entry point

### Similar Patterns (Reference)
- `scripts/tests/fixtures/fsm/assess-degenerate-gate.yaml` — test fixture for the self-loop degenerate gate pattern (Signal 2 for `audit-loop-run`); not the same variant as BUG-2306 but illustrates how the existing test corpus handles degenerate routing

### Documentation
- `.issues/enhancements/P3-ENH-2163-marker-gated-refine-wire-enforcement-rn-remediate.md` — line 122 contains the stale assumption; append a note after fix lands
- `.issues/enhancements/P3-ENH-2153-fix-rn-remediate-wire-refine-bypass-gaps.md` — implementation notes routing scenarios table encodes the old path (`CHANGE_SURFACE=15 → both gates on_no → implement`); update after fix lands to show `on_no → gate_implement` [Agent 2 finding]
- `.issues/enhancements/P3-ENH-2223-rn-remediate-full-rewrite-overtriggered-complexity-gate-and-diagnose-catchall.md` — desk-check table in Implementation Steps (~lines 111–113) shows `CHANGE_SURFACE=15 → implement`; update to show `gate_implement` in the path after fix [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — lines 488–572 document the full `rn-remediate` state machine; line 514 documents `require_refine_and_wire`; no immediate update needed (existing prose remains accurate), but note here if `check_wire_pre_implement.on_no` routing is ever added to the routing diagram [Agent 1 finding]

## Implementation Steps

_Added by `/ll:refine-issue` — concrete steps based on codebase analysis:_

1. **Fix routing in `rn-remediate.yaml`**: In the `check_wire_pre_implement` state (~line 148), change `on_no: implement` to `on_no: gate_implement`. Optionally give `check_complexity_pre_implement` distinct routing (ABOVE_MINIMAL → `gate_implement` directly, MINIMAL → `check_wire_pre_implement`) but this is not required — both bands already reach `gate_implement` once `check_wire_pre_implement.on_no` is fixed.

2. **Update `test_minimal_ready_path_does_not_require_gate` (test_rn_remediate.py:613)**: Change assertion from `cwpi["on_no"] == "implement"` to `cwpi["on_no"] == "gate_implement"`. Correct the docstring: `check_wire_pre_implement` is reachable from BOTH complexity bands, not just MINIMAL.

3. **Update `test_check_complexity_pre_implement_on_yes_routes_to_wire_check` (test_rn_remediate.py:489)**: Decide whether this test should continue asserting the degenerate state or be updated to verify distinct routing. If `check_complexity_pre_implement` remains degenerate (both bands → `check_wire_pre_implement`), the test body stays correct but its docstring ("gate_implement enforces refine+wire markers") should be updated to reflect that enforcement is via `check_wire_pre_implement.on_no`.

4. **Extend `test_above_minimal_entry_points_route_through_gate` (test_rn_remediate.py:605)**: Add assertion that `data["states"]["check_wire_pre_implement"]["on_no"] == "gate_implement"` to lock in the new entry point.

5. **Run `ll-loop validate scripts/little_loops/loops/rn-remediate.yaml`** to confirm no new validation warnings introduced.

6. **Run `python -m pytest scripts/tests/test_rn_remediate.py -v`** to verify all updated tests pass.

## Impact

Issues with ABOVE_MINIMAL complexity and non-zero `change_surface` that have naturally high confidence scores (passing `check_readiness`) can be implemented without the refine+wire step that ENH-2163 intended to enforce. In practice, high-confidence scores already imply the issue has been well-prepared, so observable harm is low — but the architectural contract is violated and the protection is silently absent.

---

**Open** | Created: 2026-06-26 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-06-26T20:00:00 - `3e2e5b14-7243-4e79-aea2-444e191dcd41.jsonl`
- `/ll:wire-issue` - 2026-06-26T19:52:53 - `9b5fd194-6c0f-4987-b385-6c128857e4a1.jsonl`
- `/ll:refine-issue` - 2026-06-26T19:43:09 - `d2cfe14e-bfb2-45e8-9709-2ac170c906cc.jsonl`
- `/ll:format-issue` - 2026-06-26T19:36:44 - `9070b866-966d-4148-abd2-945051b13068.jsonl`
