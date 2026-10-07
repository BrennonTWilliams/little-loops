---
id: BUG-3763
type: BUG
title: refine-to-ready-issue has no rung to rewrite Program Design after a decision
  flips the design
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:18Z'
---

# BUG-3763: refine-to-ready-issue has no rung to rewrite Program Design after a decision flips the design

## Summary

`refine-to-ready-issue` has no state that can rewrite a `## Program Design` section after `/ll:decide-issue` selects a different option than the one the section was written for. The loop dead-ends at `record_gate_unmet` → `failed` even though every other gate is clean.

Observed on BUG-3761 (run `.loops/.history/2026-10-07T000313-refine-to-ready-issue`, 33 iterations, 38 min, `failed`):

1. `resolve_decision_mid_refine` ran `/ll:decide-issue --auto`, which selected Option B (predicates on existing columns, no migration). Program Design and the Impact Effort/Risk lines were written for rejected Option A (a `channel` column, migration). decide-issue Phase 7c is bounded-scope by design and reports the section as flagged, not edited.
2. `verify_issue` → `DIRECTIVE_DRIFT` → `check_reconcile_limit` → `reconcile_issue`. `/ll:reconcile-issue` fixed the Acceptance Criteria but refused Program Design and Impact as out of contract (its rewrite scope is Implementation Steps, Acceptance Criteria, Integration Map).
3. Second verify → `DIRECTIVE_DRIFT` → reconcile budget spent → `check_gate_refine_limit` → `refine_followup` (`/ll:refine-issue --gap-analysis`). Additive-only, so it cannot remove the Option A text; `ll-issues format-check` still reports `unapplied_decision`.
4. Third verify → `VERIFY:other` → `check_gate_refine_limit` counter hit 2 (limit `lt 2`) → `record_gate_unmet` → `failed`; run record `deferred`.

The routing worked as designed; the gap is capability. No rung in the repair ladder owns Program Design / Impact rewrites.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

After a decision flips the design, the loop repairs Program Design and Impact to match the selected option (or routes to a rung that can), and only fails when that repair itself fails.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Pick one (needs a decision):

- **A.** Extend the `reconcile-issue` rewrite contract to Program Design and Impact Effort/Risk, so the existing `DIRECTIVE_DRIFT` → `reconcile_issue` rung can clear `unapplied_decision`.
- **B.** Add a rung that runs `/ll:refine-issue --full-rewrite` (or a targeted Program Design rewrite) when `format-check` reports a residual `unapplied_decision` after reconcile.
- **C.** Have decide-issue Phase 7c rewrite Program Design/Impact when the rejected option's text dominates the section.

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

- **Severity**: Loop-level dead end for any issue whose decision flips after Program Design was written; wastes ~38 min of model time per attempt.
- **Affected**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`, `skills/ll-reconcile-issue/SKILL.md`, `skills/decide-issue/SKILL.md`.

## Acceptance Criteria

- A fixture issue with a selected Option B and a Program Design section describing rejected Option A reaches `done` (or a ready state) in `refine-to-ready-issue` without manual edits.
- `ll-issues format-check` reports no `unapplied_decision` after the repair.
- The repair does not run more than once per `check_*_limit` budget and still fails closed to `record_gate_unmet` when it cannot converge.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-10-07T00:49:25 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
