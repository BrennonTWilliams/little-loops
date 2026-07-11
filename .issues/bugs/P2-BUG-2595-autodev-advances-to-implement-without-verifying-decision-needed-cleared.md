---
id: BUG-2595
title: autodev advances to implement_current after run_decide without verifying decision_needed cleared
type: BUG
priority: P2
status: open
captured_at: '2026-07-10T00:00:00Z'
discovered_date: '2026-07-10'
discovered_by: audit-loop-run
source_loop: autodev
source_state: recheck_after_decide
relates_to:
- BUG-2594
- BUG-1378
- BUG-2513
- BUG-1256
- BUG-1416
labels:
- loops
- fsm
- autodev
- decide-issue
- decision-gate
---

# BUG-2595: autodev advances to `implement_current` after `run_decide` without verifying `decision_needed` was cleared

## Summary

After `run_decide` runs `/ll:decide-issue --auto`, `autodev` verifies only that
readiness/outcome **scores** pass (`recheck_after_decide`) before routing to
`implement_current`. It never re-checks that `decision_needed` was actually
cleared. When `/ll:decide-issue --auto` silently no-ops — leaving
`decision_needed: true` and writing nothing to `.ll/decisions.yaml` — but the
scores already pass, the loop marches into `implement_current`, where `ll-auto
--only` correctly refuses to implement a gated issue and exits 1. That failure
is then routed to `check_learning_gate`, which misclassifies a **decision-gate**
block as a non-learning-gate outcome and drains the issue as a generic failure.
The issue is never implemented and no distinct "decision unresolved" outcome is
recorded.

## Current Behavior

Observed in run `2026-07-11T011831-autodev` (issue BUG-2588):

1. `check_decision_at_dequeue` saw `decision_needed: true` → routed to
   `run_decide`.
2. `run_decide` ran `/ll:decide-issue BUG-2588 --auto` (`next: mark_decide_ran`,
   `on_error: recheck_after_decide`). It exited 0 but **cleared nothing**:
   BUG-2588 still has `decision_needed: true` and there is **no BUG-2588 entry
   in `.ll/decisions.yaml`**.
3. `mark_decide_ran` → `rerun_confidence_after_decide` → `recheck_after_decide`.
4. `recheck_after_decide` ran `ll-issues check-readiness BUG-2588 --readiness 85
   --outcome ...`. BUG-2588's scores (`confidence_score: 97`,
   `outcome_confidence: 86`) pass → exit 0 → `on_yes: implement_current`.
5. `implement_current` ran `ll-auto --only BUG-2588` → manage-issue halted at
   **Phase 2.3 Decision Gate** (`decision_needed` still armed), emitted a plan
   for manual approval, exited 1 (the BUG-1256 fix working correctly).
6. `implement_current.on_no` routed to `check_learning_gate` — but a
   decision-gate block is not a learning-gate block, so (had it not crashed on
   BUG-2594) it would emit `OK` and fall through `check_impl_auth` →
   `dequeue_next`, dropping BUG-2588 as a generic failure with no
   decision-specific outcome.

Verbatim `ll-auto` output (captured `ll_auto_output`):
```
Phase 2.3: Decision Gate — HALTED ← you are here
### To clear the gate
Run one of these:
  /ll:decide-issue BUG-2588
  /ll:manage-issue bug fix BUG-2588 --force-implement
```
Verbatim `ll-auto` stderr:
```
Warning: BUG-2588 status=open (expected done/cancelled)
No meaningful changes detected - only excluded files modified: ['.issues/bugs/P3-BUG-2588-...']
```

This is distinct from prior decision-gate bugs:
- **BUG-1378** (done): `recheck_after_decide` read *stale/too-low* scores. Here
  scores are fresh and *passing* — the inverse failure.
- **BUG-2513** (done): bypass on `refine_current` *non-success* exits. Here
  `refine_current` was never entered (decision detected at dequeue).
- **BUG-1256** (done): `ll-auto` exited 0 on a gate block. That fix works — it
  exits 1 here. The remaining gap is that autodev advances into a guaranteed
  failure and then misclassifies it.

## Expected Behavior

After `run_decide`, `autodev` must confirm the decision gate is actually cleared
before advancing to `implement_current`. If `decision_needed` is still armed:

1. Do not route to `implement_current` (implementation is guaranteed to halt).
2. Route to a distinct "decision unresolved" outcome that is recorded in the run
   summary (so the operator sees "decide-issue produced no actionable decision"
   rather than a generic implementation failure), mirroring how learning-gate
   blocks are recorded distinctly.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: states `run_decide` (`next: mark_decide_ran` — success unverified)
  and `recheck_after_decide` (`ll-issues check-readiness ...` — validates scores
  only)
- **Cause**: `run_decide`'s success path never verifies the flag was cleared,
  and the only gate between decide and implement (`recheck_after_decide`) checks
  readiness/outcome scores, not `decision_needed`. When scores already pass, a
  no-op decide leaks a still-armed issue into `implement_current`. The downstream
  `check_learning_gate` then treats the resulting decision-gate block as a
  non-learning-gate outcome (misclassification).

Note: the very issue under test (BUG-2588 — "save_decisions() silently drops
entry keys not declared on the dataclass") may explain *why* decide recorded
nothing, but the autodev routing gap is independent of that: any silent no-op
from `/ll:decide-issue --auto` (see BUG-1416) reproduces it.

## Steps to Reproduce

1. Pick an issue with `decision_needed: true` whose readiness/outcome scores
   already exceed the thresholds.
2. Ensure `/ll:decide-issue --auto` no-ops for it (no enumerable options / see
   BUG-1416), leaving `decision_needed: true`.
3. Run `ll-loop run autodev "<ID>"`.
4. Observe `recheck_after_decide` passes on scores → `implement_current` →
   `ll-auto --only` halts at the decision gate and exits 1.
5. Observe the failure routes to `check_learning_gate` and is not recorded as a
   decision-gate outcome; the issue is not implemented.

## Proposed Solution

Insert a decision-gate re-check between decide and implement, and give
`run_decide` a verified post-condition:

```yaml
  recheck_after_decide:
    action: |
      ll-issues check-readiness ${captured.input.output} \
        --readiness ${context.readiness_threshold} \
        --outcome ${context.outcome_threshold} \
        && echo "${captured.input.output}" >> ${context.run_dir}/autodev-passed.txt
    fragment: shell_exit
+   on_yes: assert_decision_cleared   # was: implement_current
    on_no: snap_and_size_review
    on_error: snap_and_size_review

+ assert_decision_cleared:
+   # Guard: after decide, the flag must be cleared before implementing.
+   # ll-auto would otherwise halt at manage-issue's decision gate.
+   action: ll-issues check-flag ${captured.input.output} decision_needed
+   evaluate: { type: exit_code }
+   on_yes: record_decision_unresolved   # flag still present → distinct outcome
+   on_no: implement_current             # flag cleared → safe to implement
+   on_error: implement_current
```

`record_decision_unresolved` writes the issue to a distinct outcome file (e.g.
`autodev-decision-unresolved.txt`) surfaced in the run summary, then advances the
queue — parallel to `mark_gate_blocked` for learning-gate blocks. (Confirm the
exact `check-flag` exit-code semantics for "flag present/true".)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `recheck_after_decide` routing;
  new `assert_decision_cleared` + `record_decision_unresolved` states; wire the
  new outcome into the summary.

### Dependent Files (Callers/Importers)
- Summary/reporting for autodev (wherever `autodev-gate-blocked.txt` /
  `autodev-passed.txt` are aggregated into the run summary) — add the new
  decision-unresolved bucket.

### Similar Patterns
- `mark_gate_blocked` (distinct learning-gate outcome) — mirror its shape for
  the decision-unresolved outcome.
- `rn-remediate` decide path — check for the same missing post-decide flag
  verification.

### Tests
- `scripts/tests/test_builtin_loops.py` — case where decide no-ops but scores
  pass; assert the loop records a decision-unresolved outcome and does not enter
  `implement_current`.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` / autodev docs — note the
  post-decide flag verification.

### Configuration
- N/A

## Motivation

Without a post-decide flag check, autodev wastes a full `ll-auto` implementation
attempt (270s+ here) on an issue that cannot possibly implement, then buries the
result as a generic failure — so operators cannot tell "decide produced no
decision" from "implementation failed." Recording the outcome distinctly makes
the failure actionable (remedy: run `/ll:decide-issue` manually or
`--force-implement`) and avoids the guaranteed-halt round trip.

## Impact

- **Priority**: P2 — leaks a still-gated issue into implementation, wasting a
  long `ll-auto` run and misclassifying the outcome; not data-corrupting, and
  manage-issue correctly refuses to implement, so no wrong code is written.
- **Effort**: Small — one guard state plus a distinct-outcome state mirroring
  `mark_gate_blocked`.
- **Risk**: Low — adds a gate on the path to implementation; the happy path
  (flag actually cleared) is unchanged.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-10 | Priority: P2
