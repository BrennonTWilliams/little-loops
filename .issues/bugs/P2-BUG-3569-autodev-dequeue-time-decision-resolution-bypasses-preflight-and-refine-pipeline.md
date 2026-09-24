---
id: BUG-3569
type: BUG
title: Autodev dequeue-time decision resolution bypasses preflight and refine pipeline
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:12Z'
parent: EPIC-3565
---

# BUG-3569: Autodev dequeue-time decision resolution bypasses preflight and refine pipeline

## Summary

`check_decision_at_dequeue` (BUG-2513) sends `decision_needed: true` issues to the shared
`resolve_decision` call state before refinement. That state's success path is
`mark_decide_ran` → `rerun_confidence_after_decide` → `recheck_after_decide`, whose `on_yes`
is `implement_current`. A decision resolved at dequeue therefore skipped
`check_blockers_at_dequeue`, `check_gate_at_dequeue`, and the whole `refine_current` pipeline
(refine, wire, normalize, verify, concrete gates). With passing pre-existing scores, it went
straight to ll-auto. ll-auto's own ready-issue check partly covered this (it blocks on open
dependencies), but the FSM's advertised preparation invariant did not hold.

## Current Behavior

Before the fix: dequeue → decision flag → resolve → rescore → `implement_current`, with no
blocker, gate, refine, wire or verify.

## Expected Behavior

A decision resolved at dequeue resumes normal preflight at `check_blockers_at_dequeue`, then
gate check, then `refine_current`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2
- **Effort**: Small
- **Risk**: Medium. Adds refine cost for entry-time decision issues.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `check_decision_at_dequeue`, `resolve_decision`
- **Cause**: one call state served four entry points with a single return path tuned for the
  post-refine entries

## Resolution

- New call state `resolve_decision_at_dequeue` (same `oracles/resolve-decision` sub-loop,
  bound per call state like `resolve_decision_direct`). Its `on_success` goes to the new
  `mark_decide_ran_at_dequeue`. Failure and error go to `check_decide_rate_limited`, as before.
- `mark_decide_ran_at_dequeue` writes `autodev-decide-ran` (so `decide_current` does not
  re-run decide), then re-checks the flag: armed (residual group) → `record_decision_unresolved`;
  cleared → `check_blockers_at_dequeue`.
- `check_decision_at_dequeue.on_yes` now targets `resolve_decision_at_dequeue`.
- Tests: `test_dequeue_decision_resumes_preparation_not_implementation` plus updated routing
  assertions in `test_autodev_decision_gate.py` and `test_builtin_loops.py` (the loop-state set
  now includes `resolve_decision_at_dequeue`).
- Landed in commit `9a5d0f523`. The `test_builtin_loops.py` updates were uncommitted at
  capture time, and `test_fsm_topology.py` needs the autodev count set to 87.

Behavior change: an entry-time decision issue now pays for a full refine cycle before
implementation. That is intentional, since it is the same contract every other issue gets.

## Acceptance Criteria

- [x] No path from `check_decision_at_dequeue` reaches `implement_current` without passing `refine_current`
- [x] Residual armed flag at dequeue is held via `record_decision_unresolved`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2
