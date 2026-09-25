---
id: ENH-3599
type: ENH
title: Move spike and decision repair routing from autodev into refine-to-ready-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:50Z'
blocked_by:
- ENH-3597
- FEAT-3598
- FEAT-3573
blocks:
- ENH-3601
- ENH-3600
parent: EPIC-3565
relates_to:
- ENH-3577
---

# ENH-3599: Move spike and decision repair routing from autodev into refine-to-ready-issue

## Summary

Delete autodev's copies of the spike and decision repair routes and let the child own them,
driven by the run record (A) and the selector (B). Step C of the ENH-3577 decomposition —
the first routing migration, chosen because these states are literal duplicates.

## Current Behavior

These states exist in both `autodev.yaml` and `refine-to-ready-issue.yaml`:
`check_spike_needed`, `run_spike`, `route_spike_verdict`, `check_spike_budget`,
`record_spike_inconclusive`, `mark_spike_no_verdict_infra`, `check_decide_rate_limited`,
`record_decision_unresolved`. Autodev additionally has decision entry points
(`check_decision_at_dequeue`, `resolve_decision_at_dequeue`, `mark_decide_ran_at_dequeue`,
`check_decision_after_refine`, `decide_current`, `resolve_decision`,
`resolve_decision_direct`, `mark_decide_ran`, `check_rearmed_spike_after_decide`,
`check_decision_before_size_review`, `check_spike_needed_before_skip`,
`check_proof_gate_before_implement`), the rescoring triplets for `decide` and `spike`, and
the markers `autodev-decide-ran`, `autodev-spike-inconclusive.txt`,
`autodev-spike-no-verdict.txt`, `autodev-decision-unresolved.txt`,
`autodev-pre-spike-readiness.txt`, `spike-runs-*`.

## Expected Behavior

Autodev never invokes `/ll:spike` or `oracles/resolve-decision` directly. When the child
returns `blocked`/`deferred` for a decision or proof reason, autodev ledgers it from the run
record and moves on; when the issue still needs a decision/spike after a second-pass repair,
autodev re-enters the child rather than running its own route.

## Proposed Solution

- Route `refine_current` success by `RunRecord.outcome` instead of `check_passed` for the
  decision/proof dimensions.
- Remove the dequeue-time decision resolution (BUG-3569 already routes it through the
  refine pipeline) and the post-refine decision/spike states listed above.
- Remove the `decide`/`spike` rescoring triplets; the child's `confidence_check` owns
  rescoring (BUG-3588 freshness rules must carry over).
- Delete the listed marker files; ledger rows (`autodev-skipped.txt` etc.) are written from
  the run record.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (only if a route is missing in the child)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` (callers change, contract doesn't)

### Tests
- Behavioral, must pass unchanged: `test_spike_verdict_routing.py`,
  `test_autodev_decision_gate.py`, `test_autodev_scores_freshness.py`
- Structural, rewrite: `test_fsm_topology.py`, `test_builtin_loops.py`, `test_autodev_loop.py`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Large - removes ~30 autodev states and their markers
- **Risk**: High - rewrites routing in the most-used loop
- **Breaking Change**: No - loop-internal

## Program Design

### Types

- No new types; consumes `RunRecord` / `PreparationOutcome` from ENH-3597

### Signatures

- `read_run_record(run_dir: Path) -> RunRecord | None` — (from ENH-3597) read by the state that replaces `check_passed` for decision/proof routing

### Call Path

`autodev.yaml:refine_current` -> `refine-to-ready-issue.yaml:run_spike` -> `cmd_spike_verdict` -> `read_run_record` -> `autodev.yaml:dequeue_next`

## Scope Boundaries

- Only the spike and decision families; wire/reconcile/size-review/go-no-go stay until ENH-3601.
- `oracles/resolve-decision.yaml`'s contract is unchanged.
- Keep distinct skills for research, wiring, decisions and reconciliation; do not merge them into one prompt (ENH-3577).

## Acceptance Criteria

- [ ] No state in `autodev.yaml` runs `/ll:spike` or `oracles/resolve-decision`
- [ ] The eight duplicated states are gone from `autodev.yaml`
- [ ] The listed spike/decision marker files are no longer read or written by autodev
- [ ] Behavioral test set passes unchanged; refuted/inconclusive spike routing (BUG-3593) still holds end to end

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Expected Behavior and Call Path apply to autodev until ENH-3601 lands; afterwards autodev re-enters `prepare-issue`. After ENH-3601 (Option B) autodev re-enters the `prepare-issue` wrapper, not `refine-to-ready-issue` directly. The authoritative per-issue run record is the wrapper's record, which supersedes/wraps the child's; it is the one copied to `records/<ID>.json`. ENH-3597 must list the wrapper as a second record writer.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
