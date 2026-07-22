---
id: BUG-2734
title: autodev defers a ready, deliberately-non-decomposable Very Large issue as
  low_readiness instead of implementing it
type: BUG
status: open
priority: P2
captured_at: '2026-07-21T00:00:00Z'
discovered_date: '2026-07-21'
discovered_by: human
labels:
- automation
- loops
- fsm
relates_to:
- BUG-2731
- BUG-1230
---

# BUG-2734: autodev defers a ready, deliberately-non-decomposable Very Large issue as low_readiness

## Summary

When `/ll:issue-size-review --auto` classifies an issue **Very Large** but
**deliberately declines to decompose it** — because the candidate sub-tasks are
strictly sequential / share infrastructure / aren't independently shippable (and,
under `tdd_mode: true`, because splitting wiring from implementation is
forbidden) — the size-review's own recommendation is *"keep as one issue, it's
ready, proceed to implement."* autodev's graph cannot hear that recommendation.
`run_size_review` produces no child files, so `enqueue_or_skip` treats the
outcome as "no decomposition happened" and routes to `recheck_after_size_review`,
which re-applies the outcome-confidence gate and **defers a genuinely
implementation-ready issue as `low_readiness`** — even when its readiness score
is well above threshold.

## Current Behavior

Reproduced live on BUG-2731 (`ll-loop run autodev BUG-2731`, run
`autodev-20260721T200648`):

- `/ll:confidence-check` stamped `confidence_score: 95` (readiness, ≥ threshold)
  and `outcome_confidence: 56` (< outcome threshold 65).
- `run_size_review` (`/ll:issue-size-review BUG-2731 --auto`) scored it 11/11
  **Very Large** and emitted:
  `[BUG-2731] skipped: score 11 (ambiguous — strictly sequential/shared-infra
  children; recommend keeping as one issue)`, with the explicit next-step note
  *"proceed to implementation as a single issue (it's already at 95/100
  readiness)."* It created **zero** child issues by design.
- Because no children appeared, `enqueue_or_skip` exited 1 →
  `check_parent_resolved_post_size_review` (not resolved) →
  `recheck_after_size_review` → `check-readiness` failed on the outcome half
  (56 < 65) → `ll-issues set-status BUG-2731 deferred --by automation --reason
  low_readiness`.

Net result: an issue that size-review explicitly judged **ready to ship as-is**
was filed as "low readiness" and removed from active selection.

## Steps to Reproduce

1. Take an issue that is refined to passing readiness (`confidence_score ≥
   threshold`) but has sub-threshold `outcome_confidence`, and whose scope is a
   single atomic fix touching many call sites (not independently-shippable
   sub-tasks). BUG-2731 is a live example (readiness 95, outcome 56, Very Large).
2. Run `ll-loop run autodev <ID>`.
3. Observe the flow reach `run_size_review`, which scores the issue Very Large,
   deliberately declines to decompose (emitting `[ID] skipped: score N
   (ambiguous — ... recommend keeping as one issue)`), and creates no children.
4. Observe autodev route through `enqueue_or_skip` (no children) →
   `recheck_after_size_review` and defer the issue as `low_readiness`, despite
   size-review recommending immediate implementation.

## Expected Behavior

A "Very Large, deliberately not decomposed, readiness ≥ threshold" outcome from
`run_size_review` should route to **`implement_current`** (or otherwise be
surfaced for human decomposition), **not** silently deferred as `low_readiness`.
The `low_readiness` reason is also misleading here — readiness was 95; the only
sub-threshold signal was outcome-risk on a structurally-large-but-atomic fix.

## Impact

Genuinely implementation-ready work is silently removed from active autodev
selection and parked in the deferred-triage surface under a misleading reason
code. Any Very Large but atomic (non-decomposable) issue — a common shape for
cross-cutting fixes that thread one signal through many call sites — is affected.
The user must notice the deferral, diagnose that it was a routing artifact rather
than a real readiness gap, and manually un-defer. Severity is moderate: no data
loss and a clear manual workaround exists, but it defeats the point of
autonomous processing for exactly the issues that are ready to ship.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **State**: `enqueue_or_skip` (action at ~lines 877–924) decides the parent's
  fate **purely on the presence/absence of newly-created child files** (the
  `comm -13` ID diff → `autodev-new-children.txt`). It has no visibility into
  *why* no children were created:
  - a genuine decomposition failure / analysis-only run (BUG-1183 shape), vs.
  - a deliberate, reasoned "do not decompose — this is atomic and ready" verdict.
  Both collapse to the same `exit 1` → `on_no:
  check_parent_resolved_post_size_review` → ... → `recheck_after_size_review`
  path, whose `check-readiness` gate then defers on the outcome-confidence half
  (`autodev.yaml:1054–1077`, `low_readiness`).
- The size-review skill already prints a **distinct, machine-detectable verdict
  line** for this case
  (`skills/issue-size-review/SKILL.md:242` normal-auto behavior and the Phase-4
  "strictly sequential children with shared scope" guidance at SKILL.md:208):
  `[ID] skipped: score N (ambiguous — ... recommend keeping as one issue)`.
  That signal is written to the transcript and thrown away — the FSM never reads
  it.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml`
  - `run_size_review` (~lines 855–866): capture the skill's stdout to a run-dir
    file (mirror the `capture:` idiom used by `implement_current`, which tees to
    `ll_auto_last.txt`) so a downstream state can branch on the emitted verdict
    line.
  - `enqueue_or_skip` (~lines 868–927): on the no-children branch, before
    falling through to `recheck_after_size_review`, detect the deliberate
    "recommend keeping as one issue" verdict. When present **and** readiness
    already passes (`ll-issues check-readiness --readiness <t>` on the
    readiness half only, or a dedicated flag), route to `implement_current`
    rather than the deferral gate. Model the new branch structurally on the
    existing `check_parent_resolved_post_size_review` guard state.
- Consider a distinct deferral reason for the *genuine* no-decompose case that
  still fails readiness (e.g. `needs_decomposition` / `oversized_unsplit`)
  instead of overloading `low_readiness`, so `deferred-triage` can distinguish
  "too big, splitter punted" from "not ready."

### Dependent Behavior / Precedent

- `recheck_after_size_review` (`autodev.yaml:1044–1081`) is the current terminal
  gate; its `low_readiness` write is what this bug reroutes around for the
  ready-but-atomic case. Do **not** change its behavior for the genuinely
  low-readiness case.
- `check_parent_resolved_post_size_review` (`autodev.yaml:929–948`) is the
  closest structural template for a new "inspect size-review outcome and branch"
  shell-exit state.
- BUG-1230 (`autodev skips implementation when size-review declines
  decomposition`) is the sibling bug this overlaps with — that fix added the
  `recheck_after_size_review` score-recheck so leaf issues aren't dropped; this
  bug is the mirror case where the score-recheck itself is the wrong gate
  because the issue is ready but oversized-and-atomic. Reconcile with its
  intent.

## Acceptance Criteria

- [ ] When `run_size_review` emits a deliberate "Very Large, not decomposed,
      recommend keeping as one issue" verdict AND readiness ≥ threshold, autodev
      routes the issue to `implement_current`, not to a `low_readiness`
      deferral.
- [ ] A genuine no-decomposition-and-still-not-ready outcome continues to defer
      (unchanged), but with a reason code that does not misrepresent a
      readiness-95 issue as "low readiness" (e.g. `oversized_unsplit` or the
      existing `low_readiness` only when readiness actually fails).
- [ ] Regression coverage in `scripts/tests/test_builtin_loops.py`: a simulated
      `run_size_review` producing zero children + the "keep as one issue" verdict
      line + passing readiness routes to `implement_current`, not the deferral
      state.

## Notes

- Discovered while investigating why BUG-2731 (readiness 95, outcome 56, Very
  Large, atomic) was auto-deferred. BUG-2731 has been manually un-deferred
  (status → open) as the immediate remediation; this issue fixes the underlying
  routing gap so it doesn't recur for the next ready-but-atomic issue.

## Status

open
