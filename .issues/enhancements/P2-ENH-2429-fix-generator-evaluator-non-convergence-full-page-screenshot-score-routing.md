---
discovered_date: "2026-07-01"
discovered_by: run-review
confidence_score: 100
outcome_confidence: 95
status: done
completed_at: 2026-07-01T18:56:13Z
labels: [loops, harness, generator-evaluator]
relates_to: [ENH-2428]
---

# ENH-2429: Fix generator-evaluator non-convergence (full-page screenshot + score-driven routing)

## Summary

The `html-website-generator` loop produced a shippable artifact but never
converged — it ran to `max_steps` over ~135 min and the final generate call hit
an API timeout (run `html-website-generator-20260701T105614`, reviewed in
`html-website-generator-run-review-20260701.md`). Root cause was a harness
defect, not a model failure. This issue fixes the three directly-actionable
drivers; the remaining score-plateau early-stop is tracked separately in
[[ENH-2428]].

## Root Cause

1. **Viewport-only screenshot (primary).** The shared `oracles/generator-evaluator`
   captured a viewport-only Playwright screenshot, so the evaluator graded ~90%
   of the page blind. Every round manufactured "cannot be verified from this
   image" issues → generator "fixed" invisible things → screenshot still showed
   only the cover → repeat indefinitely.
2. **Prose-driven routing.** All four rubric criteria scored ≥ threshold 6
   (`ALL_PASS` by the numbers), but the pass/fail decision was tied to the
   non-empty "Issues to Address" prose list, so the loop stayed in `ITERATE`
   despite passing scores.
3. **Over-provisioned ceiling.** `max_steps: 30` / `timeout: 14400` (4h) gave a
   single-page generator far more headroom than needed, turning a "done at
   iter-3" into a wall-hit timeout.

## Changes

- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — added
  `--full-page` to the Playwright `screenshot` capture in the `evaluate` state.
  Shared oracle, so this fixes all five visual generators
  (`html-website-generator`, `html-anything`, `hitl-md`, `p5js-sketch-generator`,
  `svg-image-generator`).
- `scripts/little_loops/loops/lib/harness.yaml` — mirrored `--full-page` into the
  `playwright_screenshot` fragment default and updated its description.
- `scripts/little_loops/loops/html-website-generator.yaml` — hardened the rubric
  so the pass/fail decision is a pure function of the four numeric scores; an
  advisory "Issues to Address" list no longer blocks `ALL_PASS`, and the
  evaluator is told to score only what is visible (no manufactured "cannot
  verify" issues). Lowered `max_steps` 30→12 and `timeout` 14400→3600.

## Acceptance Criteria

- [x] Full-page screenshot captured in the shared oracle (`--full-page`).
- [x] `playwright_screenshot` fragment default also uses `--full-page`.
- [x] `html-website-generator` routing is score-only; passing scores are not
      blocked by a non-empty issues list.
- [x] `max_steps` / `timeout` lowered to single-page-appropriate values.
- [x] `ll-loop validate html-website-generator` and
      `ll-loop validate oracles/generator-evaluator` both green.
- [x] `python -m pytest scripts/tests/test_builtin_loops.py` passes (994 passed).

## Follow-up

- [[ENH-2428]] — score-plateau early-stop evaluator (the correct stagnation
  signal; existing `diff_stall_gate` watches git-diff bytes and never fired
  because `index.html` kept growing while scored output plateaued).

## Notes

Source: `html-website-generator-run-review-20260701.md`.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-01T18:56:47 - `daf99a23-69e4-4434-84d2-9211ce4c640c.jsonl`
