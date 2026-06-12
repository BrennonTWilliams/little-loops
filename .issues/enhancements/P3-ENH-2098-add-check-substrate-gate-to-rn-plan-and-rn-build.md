---
id: ENH-2098
title: Add check_substrate feasibility gate to rn-plan and rn-build
type: ENH
priority: P3
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-2085
---

# ENH-2098: Add check_substrate feasibility gate to rn-plan and rn-build

## Summary

ENH-2085 introduced the optional `check_substrate` state (enumerate execution-environment constraints, validate proposed plan actions against them before execution) in the create-loop wizard template and `harness-plan-research-implement-report.yaml:57-63`. The two planning loops most likely to run on unusual substrates — `rn-plan` (task → plan) and `rn-build` (spec → design → issues → harness) — still lack the gate, so infeasible plan steps surface only as opaque runtime failures.

## Expected Behavior

`rn-plan.yaml` and `rn-build.yaml` each gain a `check_substrate` state following the pattern in `harness-plan-research-implement-report.yaml` (placed after plan review, before research/execution), routing infeasible findings back to plan revision rather than forward to execution.

## Implementation notes

- Copy the state shape from `harness-plan-research-implement-report.yaml:57-63`; keep it optional/cheap (single prompt state with on_yes/on_no/on_partial routes — note MR-4).
- rn-build delegates heavily to sub-loops (goal-cluster); the gate belongs in rn-build's own plan-approval stretch, not inside the delegated loops.
- Update `skills/create-loop/loop-types.md` only if the placement guidance needs a second example (it already documents check_substrate per ENH-2085).

## Acceptance Criteria

- [ ] Both loops validate cleanly (`ll-loop validate`), including MR-4 routes on the new state
- [ ] A dry-run/simulate of each loop traverses the new state
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes (extend the ENH-2085 structural test pattern to the two loops)
