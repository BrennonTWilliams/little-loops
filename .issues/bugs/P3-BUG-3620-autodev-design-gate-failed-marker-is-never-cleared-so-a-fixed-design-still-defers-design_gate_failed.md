---
id: BUG-3620
type: BUG
title: Autodev design-gate-failed marker is never cleared, so a fixed design still
  defers design_gate_failed
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:16:53Z'
parent: EPIC-3565
relates_to:
- ENH-3606
- ENH-2870
---

# BUG-3620: Autodev design-gate-failed marker is never cleared, so a fixed design still defers design_gate_failed

## Summary

`autodev-design-gate-failed-<ID>` is written whenever `ll-issues check-design` returns 1, and
nothing ever removes it. The deferral branches in `recheck_after_size_review` and
`regate_after_atomic_remediation` test the **file**, not this visit's check-design result.
So after the design remedy fixes `## Program Design`, a later score-only FAIL is still
deferred as `design_gate_failed` (or re-arms the design remedy), instead of taking the
decision / stagnation / low-readiness / oversized_atomic branches.

## Current Behavior

Writers (all `touch` on `rc -eq 1`), `scripts/little_loops/loops/autodev.yaml`:
- `recheck_scores` ~:1904–1909
- `regate_after_atomic_remediation` ~:2302–2309
- `recheck_after_size_review` ~:2628–2635

Readers test file presence regardless of the current `DESIGN_FAIL`:
- `regate_after_atomic_remediation` ~:2354: marker present → arm
  `autodev-atomic-design-remedy-pending` (if remedy not attempted) or defer
  `design_gate_failed`
- `recheck_after_size_review` ~:2690: marker present → arm `refine_design` remedy (if not
  fired/attempted) or defer `design_gate_failed`

No clear anywhere: `init` (~:54–85) and `dequeue_next` (~:95–187) have no removal, and the
`dequeue_next` comment (~:166–169) says it "self-isolates without cleanup" because it is
per-issue by filename. That is true across issues but not across visits of the same issue.

Trace (one pass, one issue):
1. `recheck_after_size_review` visit 1: check-design rc=1 → marker touched; scores FAIL; no
   remedy fired → arms `refine_design`, touches `autodev-pre-deferral-remedy-fired`.
2. `check_pre_deferral_remedy` → `dispatch_design_remedy` → `refine_for_design` →
   `count_repair_cycle_refine_for_design` (touches `autodev-design-remedy-attempted-<ID>`,
   origin `reconcile`) → shared rescoring chain → `route_after_rescore` `RECONCILE` →
   `recheck_after_size_review`.
3. Visit 2: check-design rc=0 (design fixed) → `DESIGN_FAIL=false`, but readiness is still
   below threshold → GATE FAIL → marker file still present, remedy fired → deferred
   `design_gate_failed`. The `decision_needed`, `readiness_stagnated` and `low_readiness`
   branches (~:2725–2837) never run.

Same shape through `regate_after_atomic_remediation`: a marker left by an earlier
`recheck_scores` visit makes a design-passing, outcome-failing atomic issue arm the design
remedy and then defer `design_gate_failed` instead of `oversized_atomic`, so
`check_go_no_go_eligible` (scoped to `oversized_atomic`) never offers go/no-go.

## Expected Behavior

The `design_gate_failed` branches fire only when this visit's check-design failed
(`DESIGN_FAIL=true`). A design that now passes falls through to the score-based branches, and
the deferral reason (`deferred_reason` frontmatter, `autodev-skipped.txt` row, triage surface)
names the real cause.

## Proposed Solution

Either branch on `"$DESIGN_FAIL" = "true"` in the two readers (the marker then only carries
the signal to states that do not recompute it), or `rm -f` the marker when check-design
returns 0. Add a test for the trace above (design fixed, readiness still low → `low_readiness`
or `readiness_stagnated`, not `design_gate_failed`). If ENH-3606 moves these states first,
apply the fix in `prepare-issue.yaml`; the marker keeps its name either way.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` (or `prepare-issue.yaml` after ENH-3606)

### Tests
- `scripts/tests/test_autodev_loop.py` (`TestRecheckAfterSizeReview*`,
  `TestRegateAfterAtomicRemediationDesignGateBranch`, `TestRecheckScoresDesignGateEndToEnd`
  ~:1056–1107)
- ENH-3618 characterization scenario for the trace, once the harness lands

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` design-gate paragraph if it describes marker lifetime

## Impact

- **Priority**: P3 — wrong `deferred_reason` and a lost go/no-go path; no wrong implementation
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Steps to Reproduce

1. Issue with a failing `## Program Design` and readiness below threshold, dequeued by autodev.
2. Stub `/ll:refine-issue` (refine_for_design) to fix Program Design without raising
   confidence to threshold.
3. Observe `autodev-skipped.txt` row `ID  design_gate_failed` and
   `deferred_reason: design_gate_failed`, although `ll-issues check-design ID` exits 0.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `recheck_after_size_review` (~:2690) and `regate_after_atomic_remediation`
  (~:2354) branch on `if [ -f ${context.run_dir}/autodev-design-gate-failed-$ID ]; then`; no state removes the marker.
- **Cause**: the marker was introduced (ENH-2870) as a cross-state signal, but the readers
  that also recompute `DESIGN_FAIL` never reconcile the two.

## Acceptance Criteria

- [ ] A design-passing, readiness-failing revisit of `recheck_after_size_review` defers with a score reason (`readiness_stagnated` / `low_readiness`) or `decision_unresolved`, never `design_gate_failed`
- [ ] A design-passing, outcome-failing `regate_after_atomic_remediation` defers `oversized_atomic` (go/no-go eligible), not `design_gate_failed`, and does not arm the design remedy
- [ ] A genuine current design failure still arms the one-shot design remedy and then defers `design_gate_failed`

## Status

**Open** | Created: 2026-09-27 | Priority: P3
