---
id: BUG-1985
title: 'rn-remediate: CONVERGED_STALLED with decision_needed still true routes to NEEDS_DECOMPOSE instead of NEEDS_MANUAL_REVIEW'
type: BUG
priority: P2
status: open
captured_at: '2026-06-06T00:00:00Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
decision_needed: false
confidence_score: 90
outcome_confidence: 80
score_complexity: 10
score_test_coverage: 15
score_ambiguity: 10
score_change_surface: 15
relates_to:
- BUG-1416
- BUG-1378
labels:
- rn-implement
- rn-remediate
- loop-defect
- routing
---

# BUG-1985: rn-remediate CONVERGED_STALLED + decision_needed still true routes to decompose

## Summary

When `rn-remediate`'s `decide` state runs `/ll:decide-issue --auto` and resolves a question, `re_assess` (a second confidence-check) can re-detect a *different* unresolved open question and re-set `decision_needed: true`. If pre/post scores are unchanged (delta=0), `check_convergence` emits `CONVERGED_STALLED`, which unconditionally routes to `emit_needs_decompose → NEEDS_DECOMPOSE`. The parent loop then sends the issue to `rn-decompose → run_size_review`, decomposing an issue whose only real blocker was an automated-unresolvable design question — not size.

Observed in run `2026-06-06T220136` on FEAT-1809:
- `decide` resolved the fork-vs-flag question (already marked `✅ RESOLVED`)
- `re_assess` re-set `decision_needed: true` for Q2 (combined `max_iterations × max_replans` cap, no formal option blocks)
- Convergence delta = 0 → `CONVERGED_STALLED`
- FEAT-1809 was decomposed into FEAT-1983 + FEAT-1984 — unnecessary, since the issue was implementation-ready (readiness=90) with a single unresolvable numeric design question

## Current Behavior

In `check_convergence` action (loops/rn-remediate.yaml):

```bash
elif [ "$TOTAL_DELTA" -le 2 ]; then
  echo "CONVERGED_STALLED"
```

No check on `decision_needed` in post-scores. A stall caused by an irresolvable decision looks identical to a stall caused by an issue that genuinely can't improve — both route to decomposition.

## Expected Behavior

When `check_convergence` detects `CONVERGED_STALLED` AND the post-scores JSON still has `decision_needed: true`, the issue is blocked by a human-required decision, not by size. The correct token is `NEEDS_MANUAL_REVIEW`, not `CONVERGED_STALLED`. The parent loop should route this to a `mark_blocked` or `escalate` state, not `rn-decompose`.

## Steps to Reproduce

1. Run `ll-loop run rn-implement FEAT-ID` on an issue where:
   - `decision_needed: true` with an open question that has no formal `### Option` blocks
   - readiness ≥ 85, outcome < 75
2. Observe: `check_decision_needed → decide → re_assess` cycle runs
3. `decide-issue` resolves only stale/already-answered questions; re_assess re-sets `decision_needed: true`
4. `check_convergence` emits `CONVERGED_STALLED` (delta=0)
5. Issue is decomposed rather than flagged for human review

## Root Cause

`check_convergence` in `loops/rn-remediate.yaml` reads pre/post score deltas from JSON files but does not read `decision_needed` from the post-scores snapshot. The stall branch emits `CONVERGED_STALLED` unconditionally, so a "stalled because a human-required decision is unresolvable by automation" case is indistinguishable from a genuine "scores cannot be improved, issue is too large" case.

## Proposed Solution

In `check_convergence`'s shell action, after computing `TOTAL_DELTA`, check `decision_needed` from the post-scores JSON:

```bash
elif [ "$TOTAL_DELTA" -le 2 ]; then
  # Distinguish: stalled because unresolvable decision vs genuinely too large
  POST_DECISION=$(jq -r '.decision_needed // "false"' "$POST" 2>/dev/null)
  if [ "$POST_DECISION" = "true" ]; then
    echo "NEEDS_MANUAL_REVIEW"
  else
    echo "CONVERGED_STALLED"
  fi
```

Add `route_conv_manual_review` state after `route_conv_improved`:

```yaml
route_conv_manual_review:
  evaluate:
    type: output_contains
    pattern: "NEEDS_MANUAL_REVIEW"
    source: "${captured.convergence.output}"
  on_yes: emit_needs_manual_review
  on_no: emit_needs_decompose
  on_error: emit_needs_decompose

emit_needs_manual_review:
  action: |
    echo "MANUAL_REVIEW_NEEDED" > "${context.run_dir}/subloop_outcome_${context.issue_id}.txt"
  action_type: shell
  next: failed
```

The parent (`rn-implement`) `classify_remediation` routing chain then needs a `route_rem_manual_review` state before falling through to `route_rem_decompose`.

## Implementation Steps

1. Edit `check_convergence` action in `loops/rn-remediate.yaml` to check `decision_needed` from post-scores and emit `NEEDS_MANUAL_REVIEW` when stalled with decision still pending.
2. Add `route_conv_manual_review` and `emit_needs_manual_review` states to `rn-remediate.yaml`.
3. Add `route_rem_manual_review` state to `rn-implement.yaml`'s `classify_remediation` routing chain, pointing to a `mark_blocked` state that writes `MANUAL_REVIEW_NEEDED` to the skipped file.
4. Run `ll-loop validate loops/rn-remediate.yaml loops/rn-implement.yaml` and confirm MR-4 passes.
5. Add test: convergence stall with `decision_needed: true` in post-scores emits `NEEDS_MANUAL_REVIEW`.

## Impact

- **Priority**: P2 — causes implementation-ready issues blocked by an unresolvable automated decision to be incorrectly decomposed, splitting work that doesn't need splitting
- **Effort**: Medium — 3 YAML files, 1 new state per loop, new routing chain entry
- **Risk**: Low — additive path; existing `CONVERGED_STALLED` path is unchanged when `decision_needed` is false
- **Breaking Change**: No
- **Blast radius**: Any `rn-implement` run where the issue has an open question with no formal option blocks and scores stall after a `decide` pass

## Session Log
- `/ll:audit-loop-run` - 2026-06-06 - from run 2026-06-06T220136 (FEAT-1809)
