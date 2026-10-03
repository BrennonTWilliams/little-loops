---
id: ENH-3718
type: ENH
title: Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T23:00:17Z'
parent: EPIC-3694
relates_to:
- BUG-3695
program_design_not_applicable: true
---

# ENH-3718: Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair

## Summary

Split out of BUG-3695 (EPIC-3694 children review, 2026-10-03). BUG-3695 landed the `--from-verify-evidence` carve-out and proved routing with scripted FSM tests (`scripts/tests/test_bug3695_directive_drift_repair.py`); scripted slash effects are not model behavior, so model compliance and convergence are still unmeasured.

Evaluate three independent `refine-to-ready-issue` runs from an identical fresh fixture reproducing AC-only check-B6 drift (ENH-3678 has since changed, so build a new fixture), each with a fresh run_dir, unchanged code and the current one-reconcile budget (`check_reconcile_limit`, `target: 2`). Record findings, AC/Step edits, AC-checker output, verdicts and iteration counts reaching VALID/ready.

Also evaluate a fixture-only drift case (expects an Implementation Step, no invented AC) and an irrelevant Tests/Documentation inventory (must create no requirement).

Investigate any failed replay or file a focused follow-up; never automatically raise the reconcile budget.


## Current Behavior

BUG-3695's repair path is covered only by scripted FSM tests (routing, evidence lifecycle, one-attempt budget). No run has shown a real model, given `reconcile-issue --from-verify-evidence` and a `DIRECTIVE_DRIFT` finding, adding an entailed AC/Step without inventing requirements, and converging within the one-reconcile budget.

## Expected Behavior

Three independent live runs from an identical AC-only drift fixture reach `VALID`/ready within the existing budget, or the failure is diagnosed. Fixture-only drift yields an Implementation Step with no invented AC, and an irrelevant Tests/Documentation inventory yields no new requirement.

## Motivation

Scripted effects cannot show model compliance, applicability churn, or incomplete first-pass B6 enumeration. Without live evidence, BUG-3695's "converges in one reconcile" claim is unproven and a failure would surface only as another 25-minute `GATE_UNMET` run.

## Proposed Solution

Build a fresh AC-only drift fixture (ENH-3678 has since changed), run `ll-loop run refine-to-ready-issue <fixture>` three times with a fresh run_dir each and unchanged code, then repeat once each for fixture-only drift and a context-only inventory. Record per-run findings, AC/Step edits, `check-acceptance-criteria` output, verdicts, iteration counts and whether the `[GATE_UNMET:DIRECTIVE_DRIFT_NON_CONVERGENCE]` line fired. Write results into this issue; do not raise `check_reconcile_limit`'s target.

## Integration Map

### Files to Modify
- None expected; findings are recorded in this issue. A failed replay may spawn a focused fix against `commands/verify-issues.md` (B6) or `commands/reconcile-issue.md`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `reconcile_issue`, `check_reconcile_limit`, `record_gate_unmet`

### Similar Patterns
- `scripts/tests/test_bug3695_directive_drift_repair.py` — the scripted routing coverage this complements

### Tests
- None added; this is an evaluation issue.

### Documentation
- None.

## Implementation Steps

1. Create the fresh AC-only drift fixture and a fixture-only and context-only variant.
2. Run three independent live runs of the AC-only fixture; capture run dirs, verdicts, edits, AC-checker output and iteration counts.
3. Run the fixture-only and context-only variants once each.
4. Record results and limitations here; investigate failures or capture focused follow-ups.

## Impact

- **Priority**: P4 - evidence for an already-landed fix, not a defect
- **Effort**: Small - five live runs plus write-up
- **Risk**: Low - read-only evaluation on throwaway fixtures

## Acceptance Criteria

- [ ] Three live AC-only-drift runs are recorded with verdicts, edits, checker output and iteration counts
- [ ] Fixture-only drift adds a Step and no invented AC; a context-only inventory adds no requirement
- [ ] Any failed replay is investigated or has a focused follow-up; the reconcile budget is not raised

## Scope Boundaries

- Out of scope: changing `check_reconcile_limit`, adding a fallback budget, or a fail-closed clear/write protocol.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-10-03T23:00:35 - `c4c6a704-e666-48df-b6fe-37ff869c1bae.jsonl`
