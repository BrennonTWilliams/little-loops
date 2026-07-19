---
id: ENH-2692
title: "rn-refine final_score rubric verdict has no effect on control flow"
type: ENH
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- degenerate-gate
---

# ENH-2692: rn-refine final_score rubric verdict has no effect on control flow

## Summary

`final_score` in `loops/rn-refine.yaml` scores the reassembled root plan
against the 9-dimension rubric and emits `ALL_VERY_HIGH` or `ITERATE`, but
both `on_yes` and `on_no` route to the same next state (`preflight_check`).
The loop's own description says the reassembled plan is "refined to rubric
convergence," but nothing downstream of `final_score` actually depends on
whether convergence was reached — an `ITERATE` verdict proceeds through
`preflight_check`/`finalize` exactly like `ALL_VERY_HIGH` would.

## Evidence

Run `2026-07-19T161520-rn-refine`
(`.loops/.history/2026-07-19T161520-rn-refine/`): `final_score` returned
`ITERATE` at iteration 53, and the loop proceeded to `preflight_check`
at iteration 54 regardless (which then separately aborted for an unrelated
reason — see ENH-2690). Had `preflight_check`'s invariant passed, the run
would have written back a plan that never reached rubric convergence, with no
record that the finalize path bypassed the loop's own quality bar.

## Proposed Solution

Either:
1. Give `final_score` a real `on_no` path (e.g. one more `refine_iteration`-style
   pass on the reassembled root, bounded by a max-root-iterations cap), or
2. If root-level rubric convergence is intentionally advisory (per-node
   convergence during the walk is the real gate), update the loop
   `description` to say so explicitly, so the rubric score in the final
   report isn't read as a pass/fail signal it doesn't function as.

## Acceptance Criteria

- [ ] Either `final_score`'s verdict visibly affects whether the plan is
      written back, or the loop's `description` is corrected to state the
      rubric is reporting-only at the root level.

## Impact

- **Priority**: P3 — did not change this run's outcome (a separate invariant
  aborted first), but the rubric threshold in the loop's stated contract is
  currently non-binding at the point that matters most (final write-back).
- **Effort**: Small — either a `description` wording fix, or adding a bounded
  loop-back state in `loops/rn-refine.yaml`.

## Related Files

- `loops/rn-refine.yaml` (`final_score`)

## Status

**Open** | Created: 2026-07-19 | Priority: P3
