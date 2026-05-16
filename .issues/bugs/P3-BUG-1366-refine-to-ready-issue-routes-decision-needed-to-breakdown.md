---
discovered_date: 2026-05-04T00:00:00Z
discovered_by: autodev-debug-analysis
confidence_score: 100
outcome_confidence: 100
---

# BUG-1366: `refine-to-ready-issue` routes `decision_needed` issues to size-review instead of exiting cleanly

## Summary

When `check_outcome` fails in `refine-to-ready-issue`, the sub-loop routes directly to
`breakdown_issue` (`/ll:issue-size-review`) without checking whether `decision_needed: true`
is set. Low outcome confidence caused by unresolved option ambiguity (0/25 ambiguity score)
is misidentified as "scope too large" and triggers decomposition. The correct response is to
exit cleanly via `done` so the outer loop (`autodev`) can route to `/ll:decide-issue`.

## Location

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `check_outcome` state (lines 227–257 before fix)

## Current Behavior (before fix)

```
check_outcome (exit 1, outcome=61 < 75)  →  breakdown_issue  →  /ll:issue-size-review
```

When `decision_needed: true`, the `score_ambiguity` criterion scores 0/25, tanking outcome
confidence. `check_outcome` sees the score fail and immediately invokes size-review. The
outer `autodev` loop has a proper `triage_outcome_failure` → `run_decide` gate, but it
only runs after the sub-loop returns — by then size-review is already in progress.

Observed during `ll-loop run autodev BUG-1364` (debug log: `ll-autodev-debug.txt`):

```
[9/500]  check_readiness   → yes (95 ≥ 90)
[10/500] check_outcome     → exit 1 (61 < 75)  → breakdown_issue
[11/500] breakdown_issue   → /ll:issue-size-review BUG-1364 --auto  (interrupted)
```

## Expected Behavior

When `decision_needed: true`, `check_outcome` failure should exit the sub-loop via `done`
so `autodev`'s `check_decision_after_refine` fires and routes to `/ll:decide-issue`.

## Root Cause

`check_outcome` had a direct `on_no: breakdown_issue` edge with no `decision_needed` gate:

```yaml
check_outcome:
  on_yes: done
  on_no: breakdown_issue   # ← no gate: fires even when low score is caused by ambiguity
```

`autodev.yaml` already handled this correctly in its outer `triage_outcome_failure` state,
but that state is unreachable when the sub-loop fires size-review before returning.

## Fix

Added a `check_decision_needed` gate state between `check_outcome` failure and
`breakdown_issue` in `scripts/little_loops/loops/refine-to-ready-issue.yaml`.

```yaml
# check_outcome on_no now routes to:
check_decision_needed:
  action: "ll-issues check-flag ${captured.issue_id.output} decision_needed"
  fragment: shell_exit
  on_yes: done          # exit cleanly; autodev handles decide routing
  on_no: breakdown_issue
  on_error: breakdown_issue
```

Using `done` (not `failed`) is correct: both route to `copy_broke_down` in autodev, but
`done` is semantically accurate (sub-loop completed its work), and `write_broke_down` is
not called, keeping `autodev-broke-down = 0` so autodev's `check_broke_down` →
`recheck_scores` → `decide_current` → `run_decide` path fires as intended.

## Integration Map

### Files Modified
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_outcome` `on_no` re-routed; new `check_decision_needed` state added; routing comment at file top updated

### Dependent Loops
- `scripts/little_loops/loops/autodev.yaml` — outer loop; `check_decision_after_refine` and `triage_outcome_failure` states already handle `decision_needed` correctly on the post-sub-loop path

## Impact

- **Priority**: P3 — Fires on every issue with `decision_needed: true` that fails outcome confidence; triggers incorrect decomposition of issues that are correctly scoped but undecided
- **Effort**: Small — Two edits in one YAML file
- **Risk**: Low — Only adds a guard before existing `breakdown_issue` edge; `on_error: breakdown_issue` preserves existing behavior on gate failure

## Resolution

**Fixed** | Resolved: 2026-05-04

Inserted `check_decision_needed` state in `refine-to-ready-issue.yaml`. When
`decision_needed: true`, the sub-loop now exits via `done` without calling size-review,
allowing `autodev`'s `check_decision_after_refine` → `run_decide` path to handle the
decision correctly.

## Session Log
- analysis + fix - 2026-05-04T00:00:00Z - manual session (ll-autodev-debug.txt analysis)

## Status

**Completed** | Created: 2026-05-04 | Priority: P3
