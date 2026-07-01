---
id: ENH-2428
type: enhancement
status: open
priority: P3
title: Score-plateau early-stop for generator-evaluator oracle
labels: [loops, harness, generator-evaluator]
relates_to: []
---

# Score-plateau early-stop for generator-evaluator oracle

## Problem

The `oracles/generator-evaluator` sub-loop has a stall guard (`check_stall` →
`diff_stall_gate`, `scripts/little_loops/loops/lib/common.yaml:148`) that watches
**git diff bytes**. This does not catch the real stagnation mode observed in the
`html-website-generator` run review (`html-website-generator-20260701T105614`):

- `index.html` grew 94 KB → 124 KB across 16 refine rounds, so the git diff was
  never identical and `diff_stall` never fired.
- Meanwhile the **visible, scored output plateaued after ~iter-1** — every round
  scored at or near the same rubric values with diminishing visual change.
- Result: the loop burned ~2h15m / most of its iteration budget buying almost no
  scored improvement, then hit the step/time ceiling.

A byte-diff signal is the wrong axis. We need a **score-plateau** signal: if the
rubric scores do not improve for N consecutive rounds, accept best-so-far and
route to `done`.

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

## Proposed approach

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

## Acceptance criteria

- [ ] A per-run score-history artifact is written under `${context.run_dir}/`
      (never bare `.loops/tmp/`).
- [ ] A `score_stall` evaluator (type or fragment) exists with a `max_stall`
      knob and an epsilon threshold, unit-tested in `scripts/tests/`.
- [ ] `oracles/generator-evaluator` routes to `done` when scores plateau for
      `max_stall` rounds, verified by a test that feeds a flat score history.
- [ ] `ll-loop validate oracles/generator-evaluator` stays green.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Source: `html-website-generator-run-review-20260701.md` (finding 3, "Diminishing
returns after iter-1" / "Add an early-stop on stagnation").
