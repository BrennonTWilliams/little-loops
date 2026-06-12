---
id: ENH-2098
title: Add check_substrate feasibility gate to rn-plan and rn-build
type: ENH
priority: P3
status: done
captured_at: '2026-06-12T14:10:00Z'
completed_at: '2026-06-12T21:39:49Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-2085
parent: EPIC-1811
confidence_score: 94
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2098: Add check_substrate feasibility gate to rn-plan and rn-build

## Summary

ENH-2085 introduced the optional `check_substrate` state (enumerate execution-environment constraints, validate proposed plan actions against them before execution) in the create-loop wizard template and `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:57-63`. The two planning loops most likely to run on unusual substrates — `rn-plan` (task → plan) and `rn-build` (spec → design → issues → harness) — still lack the gate, so infeasible plan steps surface only as opaque runtime failures.

## Current Behavior

`rn-plan.yaml` and `rn-build.yaml` have no `check_substrate` state. When either loop runs on a constrained execution environment, infeasible plan steps are not caught at plan-review time and instead propagate to execution, producing opaque runtime failures with no actionable routing back to plan revision.

## Expected Behavior

`rn-plan.yaml` and `rn-build.yaml` each gain a `check_substrate` state following the pattern in `harness-plan-research-implement-report.yaml` (placed after plan review, before research/execution), routing infeasible findings back to plan revision rather than forward to execution.

## Motivation

This enhancement extends the ENH-2085 substrate-safety gate to the two loops most exposed to unusual execution environments. `rn-plan` and `rn-build` are entry points for user-driven planning tasks where substrate constraints are most likely to vary; without the gate, an infeasible plan wastes a full execution run before failure is surfaced. Adding the state is low-cost (single-prompt copy), and it converts opaque runtime failures into actionable plan-revision cycles.

## Proposed Solution

- Copy the state shape from `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:57-63`; keep it optional/cheap (single prompt state with on_yes/on_no/on_partial routes — note MR-4).
- rn-build delegates heavily to sub-loops (goal-cluster); the gate belongs in rn-build's own plan-approval stretch, not inside the delegated loops.
- Update `skills/create-loop/loop-types.md` only if the placement guidance needs a second example (it already documents check_substrate per ENH-2085).

## Scope Boundaries

- **In scope**: Adding `check_substrate` state to `rn-plan.yaml` and `rn-build.yaml`; extending `test_builtin_loops.py` to cover the new state in both loops
- **Out of scope**: Adding `check_substrate` to other built-in loops (tracked separately if needed); modifying the `check_substrate` state shape or prompt; changes to sub-loops delegated by rn-build (e.g., `goal-cluster`)

## Implementation Steps

1. Read `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:57-63` to extract canonical `check_substrate` state shape
2. Insert state into `rn-plan.yaml` after plan-review stretch, before research/execution, with full on_yes/on_no/on_partial routing (MR-4)
3. Insert state into `rn-build.yaml` after plan-approval stretch, before delegated sub-loops, with full on_yes/on_no/on_partial routing (MR-4)
4. Run `ll-loop validate rn-plan` and `ll-loop validate rn-build` — confirm no MR-4 violations
5. Extend `scripts/tests/test_builtin_loops.py` following the ENH-2085 structural test pattern for both loops
6. Run `python -m pytest scripts/tests/test_builtin_loops.py` to confirm passing

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-plan.yaml` — add `check_substrate` state after plan-review
- `scripts/little_loops/loops/rn-build.yaml` — add `check_substrate` state after plan-approval
- `scripts/tests/test_builtin_loops.py` — extend structural test pattern from ENH-2085

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml` — source pattern to copy (read-only reference)

### Similar Patterns
- `scripts/little_loops/loops/harness-plan-research-implement-report.yaml:57-63` — canonical `check_substrate` state shape to replicate

### Tests
- `scripts/tests/test_builtin_loops.py` — extend ENH-2085 structural test to rn-plan and rn-build

### Documentation
- `skills/create-loop/loop-types.md` — conditional: update only if placement guidance needs a second example

### Configuration
- N/A

## Acceptance Criteria

- [ ] Both loops validate cleanly (`ll-loop validate`), including MR-4 routes on the new state
- [ ] A dry-run/simulate of each loop traverses the new state
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes (extend the ENH-2085 structural test pattern to the two loops)

## Impact

- **Priority**: P3 - Incremental safety-net; low urgency but reduces wasted execution runs on constrained substrates
- **Effort**: Small - Pattern copy from existing loop; two YAML files plus test extension
- **Risk**: Low - Additive change; existing routes unchanged; new state is optional/cheap (single prompt with full routing)
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fsm`

## Status

**Open** | Created: 2026-06-12 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-12T21:34:12 - `ca87223d-12f7-4c8d-97bc-1d32eee11f88.jsonl`
- `/ll:format-issue` - 2026-06-12T20:24:29 - `949b6d34-afdf-46bb-b4d9-22250e78bbe9.jsonl`
