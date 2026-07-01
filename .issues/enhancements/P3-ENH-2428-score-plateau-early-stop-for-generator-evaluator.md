---
id: ENH-2428
type: enhancement
status: open
priority: P3
title: Score-plateau early-stop for generator-evaluator oracle
labels:
- loops
- harness
- generator-evaluator
relates_to: []
confidence_score: 95
outcome_confidence: 59
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
decision_needed: true
---

# Score-plateau early-stop for generator-evaluator oracle

## Summary

The `oracles/generator-evaluator` sub-loop's stall guard watches git diff
bytes, which misses the real stagnation mode: visible/scored output plateaus
while the file keeps growing byte-for-byte. Add a **score-plateau** evaluator
that accepts best-so-far and routes to `done` when rubric scores stop
improving for `max_stall` consecutive rounds.

## Current Behavior

`check_stall` → `diff_stall_gate` (`scripts/little_loops/loops/lib/common.yaml:148`)
watches **git diff bytes**. This does not catch the real stagnation mode
observed in the `html-website-generator` run review
(`html-website-generator-20260701T105614`):

- `index.html` grew 94 KB → 124 KB across 16 refine rounds, so the git diff was
  never identical and `diff_stall` never fired.
- Meanwhile the **visible, scored output plateaued after ~iter-1** — every round
  scored at or near the same rubric values with diminishing visual change.
- Result: the loop burned ~2h15m / most of its iteration budget buying almost no
  scored improvement, then hit the step/time ceiling.

## Expected Behavior

A **score-plateau** signal replaces byte-diff as the primary stall axis: if
the rubric scores do not improve by more than a small epsilon for `max_stall`
(default 2) consecutive rounds, the loop accepts best-so-far and routes to
`done` instead of continuing to the step/time ceiling.

## Motivation

- The `html-website-generator` review found the loop burned ~2h15m — most of
  its iteration budget — buying almost no scored improvement after iter-1,
  because the stall guard watches the wrong signal (byte diff, not rubric
  score).
- A reusable `score_stall` evaluator fixes this for `oracles/generator-evaluator`
  and any other loop pairing an LLM `score` state with iterative refinement.
- Satisfies the MR-1 discriminator rule (non-LLM external evaluator paired
  with the LLM `score` state) noted in the Proposed Solution below.

## Context

The immediate churn drivers from the same review (full-page screenshot, and
score-driven termination that ignores the advisory "Issues to Address" list) were
already fixed directly in:
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` (`--full-page`)
- `scripts/little_loops/loops/lib/harness.yaml` (`playwright_screenshot` default)
- `scripts/little_loops/loops/html-website-generator.yaml` (rubric hardening +
  `max_steps` 30→12 / `timeout` 14400→3600)

This issue is the remaining, larger piece: a reusable **score-stall evaluator**
so the plateau is caught on the correct signal rather than relying only on the
lowered step ceiling as a backstop.

## Proposed Solution

- Persist each round's numeric rubric scores (the four criteria) to a small file
  under `${context.run_dir}/` (e.g. `.score_history` — per-run isolation per
  MR-3), written by the `score` state / `ll_rubric_score` path.
- Add a `score_stall` evaluator type (or a `score_stall_gate` fragment mirroring
  `diff_stall_gate`) that reads the history and returns `no` (plateaued) when the
  aggregate/weighted score has not improved by more than a small epsilon for
  `max_stall` (default 2) consecutive rounds.
- Wire `check_stall` in `generator-evaluator.yaml` to use the score-plateau
  signal (keep `diff_stall` as a secondary/OR condition if cheap).
- This is a non-LLM external evaluator, satisfying the MR-1 discriminator rule
  for the paired LLM `score` state.

## Scope Boundaries

- **In scope**: persisting per-round rubric scores under `${context.run_dir}/`;
  a `score_stall` evaluator (or fragment) with a `max_stall` knob and epsilon
  threshold; wiring `check_stall` in `oracles/generator-evaluator` to the
  score-plateau signal.
- **Out of scope**: removing `diff_stall` outright — it stays as a
  secondary/OR condition per the Proposed Solution; wiring `score_stall` into
  other oracle loops beyond `generator-evaluator` (the evaluator should be
  reusable, but adopting it elsewhere is separate follow-up work).

## Acceptance Criteria

- [ ] A per-run score-history artifact is written under `${context.run_dir}/`
      (never bare `.loops/tmp/`).
- [ ] A `score_stall` evaluator (type or fragment) exists with a `max_stall`
      knob and an epsilon threshold, unit-tested in `scripts/tests/`.
- [ ] `oracles/generator-evaluator` routes to `done` when scores plateau for
      `max_stall` rounds, verified by a test that feeds a flat score history.
- [ ] `ll-loop validate oracles/generator-evaluator` stays green.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — quality-of-life fix for harness resource usage; wastes
  iteration budget on real runs but is not a correctness bug.
- **Effort**: Small-Medium — new evaluator type/fragment plus a small
  per-round persistence write path, mirroring the existing `diff_stall_gate`
  pattern already in `common.yaml`.
- **Risk**: Low — additive evaluator; `diff_stall` is retained as a
  secondary/OR condition, so existing stall detection isn't removed.
- **Breaking Change**: No.

## Notes

Source: `html-website-generator-run-review-20260701.md` (finding 3, "Diminishing
returns after iter-1" / "Add an early-stop on stagnation").

## Status

**Open** | Created: 2026-07-01 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- Open decision — either extend the shared `ll_rubric_score` fragment
  (`scripts/little_loops/loops/lib/harness.yaml:16`, used by 7 loops:
  hitl-compare, html-anything, html-website-generator,
  interactive-component-generator, openscad-model-generator, hitl-md,
  svg-image-generator) to emit numeric per-criterion scores, or add a scoped
  numeric-scoring variant used only by `generator-evaluator`. Resolve before
  implementing: the change already spans a broad enumeration across 6+ core
  sites (`schema.py`, `evaluators.py`, `validation.py`, a fragment library,
  `generator-evaluator.yaml` wiring, plus tests); extending the shared prompt
  too would widen it further to 7 unrelated loops that don't consume
  `score_stall` at all.
- The Proposed Solution assumes numeric per-criterion rubric scores are
  already available to persist, but `ll_rubric_score` currently emits only a
  binary `ALL_PASS`/`NEEDS_WORK` verdict with no numeric output — the prompt
  and a capture/parse step (mirroring `rubric_score`/`rubric_parse_scores` in
  `lib/rubric-router.yaml`) must be added as part of this issue; that work
  isn't called out in the Proposed Solution or Acceptance Criteria.
- The exact epsilon threshold and whether plateau is judged on the aggregate
  score or all four criteria individually are undecided — pick sane defaults
  (e.g., epsilon relative to the 0-10 `pass_threshold` scale) during
  implementation.

## Session Log
- `/ll:format-issue` - 2026-07-01T20:26:06 - `6a483798-afef-41ef-99f1-d9709fa879a5.jsonl`
- `/ll:confidence-check` - 2026-07-01T20:34:06 - `39568524-616e-4270-8660-34ace681fd21.jsonl`
