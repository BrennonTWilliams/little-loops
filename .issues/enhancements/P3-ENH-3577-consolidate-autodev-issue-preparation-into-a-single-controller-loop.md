---
id: ENH-3577
type: ENH
title: Consolidate autodev issue preparation into a single controller loop
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
---

# ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Summary

Consolidate autodev's per-issue preparation into one single-issue controller (extending
`refine-to-ready-issue`), so the outer `autodev` loop owns only queue orchestration and
accounting. Today repair and rescoring policy is split between parent and child. Autodev
re-implements spike, reconcile, size-review, design-remedy and decision routing, with its own
marker files (`autodev-pre-deferral-remedy.txt`, `autodev-decide-ran`, the fired markers),
and `ll-issues show` + inline Python predicates are copied across states. The route-specific
contract gaps in EPIC-3565's children come directly from this duplication.

## Current Behavior

Autodev (~87 states) duplicates the child loop's repair routing, with its own marker handshakes and copied inline predicates.

## Expected Behavior

The child owns all per-issue preparation and returns a typed outcome. Autodev owns only the queue, dispatch and accounting.

## Motivation

- The outer loop has about 87 states, with a large inline `finalize_done`.
- Learning-proof ownership is spread across confidence-check, ready-issue and the learning
  primitive, which each treat refuted/stale records differently.
- Each duplicated route is a place where the readiness invariant can silently fail to apply.

## Proposed Solution

1. The child returns typed outcomes (`ready`, `decomposed`, `cancelled`, `blocked`,
   `deferred`, `retryable_error`) plus child IDs and evidence references, in one per-issue
   run record.
2. One deterministic assessment + repair selector: read the issue once, run
   format/design/AC/decision/proof checks, and choose the next unmet obligation. Replace the
   copied shell/Python predicates and handshake files with a shared implementation that
   emits structured output. Do not replace it with one large LLM prompt.
3. Keep distinct skills for research, wiring, decisions and reconciliation. Their edit
   contracts are useful boundaries.
4. One budget owner for learning proof; risk-conditional go/no-go.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`

### Dependent Files (Callers/Importers)
- Loops invoking refine-to-ready-issue (e.g. `rn-*` loops, `recursive-refine` wrappers)

### Similar Patterns
- `oracles/resolve-decision.yaml` extraction (ENH-3075)

### Tests
- `scripts/tests/test_builtin_loops.py`, `test_autodev_loop.py`, `test_autodev_decision_gate.py`, `test_fsm_topology.py`

### Documentation
- `docs/ARCHITECTURE.md` loop section

### Configuration
- N/A

## Implementation Steps

1. Land BUG-3571, BUG-3572, FEAT-3573, BUG-3574, ENH-3575 and ENH-3576 with real-FSM regression tests
2. Define the typed per-issue outcome/run-record schema
3. Build the shared deterministic assessment + repair selector
4. Move parent repair routing into the child; delete duplicated states and markers
5. Re-run the regression scenarios

## Impact

- **Priority**: P3
- **Effort**: Very Large
- **Risk**: High. This is a large refactor of heavily used loops.

## Scope Boundaries

- Blocked until the behavioral fixes (BUG-3571, BUG-3572, FEAT-3573, BUG-3574, ENH-3575, ENH-3576) land with real-FSM regression
  tests (stateful stub skills/CLIs asserting outcomes and evidence freshness, not state
  names). Consolidating first would lose the behavior those tests protect.
- No state-count target.

## Acceptance Criteria

- [ ] Autodev contains no repair routing that duplicates the child's
- [ ] A single typed per-issue outcome drives the outer ledger
- [ ] The regression scenarios listed in EPIC-3565 pass unchanged before and after

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3
