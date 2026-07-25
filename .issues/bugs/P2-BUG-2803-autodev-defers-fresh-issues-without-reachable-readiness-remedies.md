---
id: BUG-2803
status: done
captured_at: '2026-07-25T16:31:24Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
relates_to:
- BUG-2801
- ENH-2689
- FEAT-2751
- BUG-2734
confidence_score: 94
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 14
score_change_surface: 20
completed_at: '2026-07-25T16:48:35Z'
---

# BUG-2803: autodev defers fresh issues as low_readiness with all readiness remedies structurally unreachable

## Summary

`autodev.yaml` deferred BUG-2801 as `low_readiness` (Readiness 72 < 85;
Outcome 68 actually *passed* its 65 threshold) after applying only a single
`refine_current` pass — because for a freshly captured issue, every other
readiness-improving remedy in the loop is gated on frontmatter flags that a
first-pass issue can never have set:

- `run_wire` fires only on `missing_artifacts: true` — unset on fresh issues.
- `run_spike` fires only on `spike_needed: true` — unset on fresh issues.
- `reconcile_current` fires only when `check_reconcile_needed`'s plateau
  predicate holds (`pre != '' and pre == cur`, autodev.yaml:1158) — impossible
  on a first pass: a never-scored issue snapshots an *empty*
  `autodev-pre-readiness.txt` at dequeue (the FEAT-2751 snapshot reads
  `confidence` before refine has ever written one), so `pre == ''` and the
  plateau can never fire.
- `/ll:explore-api` learning tests are not in the deferral-avoidance chain at
  all.
- The guard-2 "earn-the-pass" remediation (`check_guard2_verdict` →
  `check_readiness_for_atomic_remediation`, autodev.yaml:1237) matched the
  Very-Large-declined verdict but requires Readiness already ≥ 85 — it only
  repairs the *outcome* half of the gate, so it fell through.

Net effect: the loop's stated policy — defer only in the rarest circumstances,
otherwise improve scores via size-review / spike / wire / reconcile /
learning tests — is violated for exactly the most common case (a fresh issue
below the readiness threshold). Every state fired as coded; the gap is in the
routing design, not an execution fault.

## Evidence (run autodev-20260725T101118)

- `.loops/runs/autodev-20260725T101118/autodev-skipped.txt`:
  `BUG-2801  low_readiness`
- `autodev-pre-readiness.txt`: empty (issue had no `confidence_score` at
  dequeue; scored 72 only after `refine_current`)
- `autodev-repair-cycle-count.txt`: `2` (counted refine + size-review — not
  two distinct remedies)
- `refine-to-ready-wire-done`: `0`; `autodev-broke-down`: `0`
- BUG-2801 frontmatter after run: `confidence_score: 72`,
  `outcome_confidence: 68`, `deferred_reason: low_readiness`,
  `deferred_by: automation`
- Sequence: dequeue → refine → confidence (72/68) → decide → re-confidence →
  size-review (Very Large, decomposition declined, no children) →
  guard-2 remediation gate failed on readiness → `recheck_after_size_review`
  → deferred.

## Root Cause

`scripts/little_loops/loops/autodev.yaml` — `recheck_after_size_review`'s
`low_readiness` deferral has no pre-deferral branch that checks whether any
readiness remedy was actually *attemptable*. The remedy states' arming flags
(`missing_artifacts`, `spike_needed`, plateau snapshot) are all populated by
prior passes or by refine outputs, so a first-pass issue reaches the deferral
with zero of them armed. Additionally `check_reconcile_needed`'s `pre != ''`
guard (line 1158) excludes never-scored issues from the reconcile remedy by
construction.

## Expected Behavior

Before writing a `low_readiness` deferral, when Readiness < threshold and
neither `spike_attempted` nor `reconcile_attempted` is set, route to at least
one remedy instead of deferring:

- Treat "empty pre-readiness snapshot AND readiness below threshold" as
  reconcile-eligible in `check_reconcile_needed` (relax the `pre != ''`
  requirement for the below-threshold case), and/or
- Arm `run_spike` when confidence-check subscores indicate the low readiness
  is ambiguity-driven (e.g. `score_ambiguity` dominant), and/or
- Add an explore-api / learning-test remedy branch for issues whose readiness
  gap is unproven-mechanism-shaped.

Deferral should remain the fallback only after at least one non-refine remedy
has been attempted and readiness still fails (at which point the existing
`readiness_stagnated` discriminator applies naturally, since a snapshot now
exists).

## Implementation Steps

1. In `check_reconcile_needed` (autodev.yaml:1124), extend the predicate:
   plateau OR (`pre == ''` AND current readiness < configured
   `readiness_threshold` AND NOT `reconcile_attempted`). Read the threshold
   via `ll-config get commands.confidence_gate.readiness_threshold`.
2. In `recheck_after_size_review`, before the `low_readiness` write, add a
   guard state: if `spike_attempted` and `reconcile_attempted` are both unset,
   route back into the remedy chain (spike if ambiguity-dominant, else
   reconcile) instead of deferring; increment the repair-cycle counter so the
   `readiness_stagnated` backstop still bounds total attempts.
3. Ensure `ll-loop validate scripts/little_loops/loops/autodev.yaml` passes
   (capture-reachability, MR rules) and update `scripts/tests/test_builtin_loops.py`
   coverage for the new routing.
4. Update the `.claude/CLAUDE.md` § Issue File Format deferral paragraph to
   describe the new pre-deferral remedy guarantee.

## Acceptance Criteria

- [x] A freshly captured issue with no prior `confidence_score` that scores
      below the readiness threshold gets at least one non-refine remedy
      (reconcile, spike, or learning-test) before any `low_readiness`
      deferral.
- [x] `check_reconcile_needed` fires for never-scored below-threshold issues
      (empty snapshot no longer excludes them).
- [x] Repeat failures after an attempted remedy defer as `readiness_stagnated`
      (existing discriminator), not `low_readiness`.
- [x] `ll-loop validate` passes; existing autodev tests remain green.

## Session Log
- `/ll:capture-issue` - 2026-07-25T16:31:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`
- `/ll:confidence-check` - 2026-07-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/87cad139-c02f-4df6-a260-edc6fe51c5ca.jsonl`
