---
id: ENH-2039
type: ENH
priority: P4
status: done
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: manual
confidence_score: 100
outcome_confidence: 95
score_complexity: 20
score_test_coverage: 15
score_ambiguity: 15
score_change_surface: 20
---

# ENH-2039: Ship `rlhf-animated-svg` as a built-in example loop

## Summary

Promoted a polished RLHF-style generate→score→refine loop from a local sandbox
(`ll-labs/loop-sandbox/.loops/rlhf-animated-svg.yaml`) into the shipped built-in loop
catalog at `scripts/little_loops/loops/`. The loop generates a zero-dependency animated
SVG HTML artifact from a natural-language description, smoke-tests it in headless
Playwright, scores multi-frame screenshots (1000/3000/5000/7000ms) against a
correctness/aesthetics/smoothness/completeness rubric via a vision API, and refines until
a quality threshold is met — with component-priority ranking, oscillation/score-streak
guards, concept-reset escalation, and cumulative optimization summaries. It is the
RLHF/animation sibling of the existing `svg-textgrad`, `p5js-sketch-generator`, and
`pixi-*` generator-evaluator harnesses.

## Current Behavior

The loop existed only in a local sandbox and was not discoverable via `ll-loop list`,
runnable via `ll-loop run`, or installable via `ll-loop install`.

## Expected Behavior

`ll-loop list --builtin` shows `rlhf-animated-svg` under the harness/animation category;
`ll-loop run rlhf-animated-svg` runs out-of-the-box with a built-in demo input (a bouncing
red ball), accepts `--input "<description>"` to override, and `ll-loop install
rlhf-animated-svg` copies it to `.loops/` for customization.

## Acceptance Criteria

- [x] `ll-loop list --builtin | grep rlhf-animated-svg` shows the loop as `[built-in]`
- [x] `ll-loop validate rlhf-animated-svg` exits 0 ("is valid")
- [x] `ll-verify-docs` loops count matches (83 == 83); not flagged
- [x] `pytest scripts/tests/test_doc_counts.py -k loop` passes (19 passed)
- [x] Loop runs without setup — Playwright / `VISION_*` gates degrade gracefully when absent

## Implementation Notes

Three changes:

1. **New loop** — `scripts/little_loops/loops/rlhf-animated-svg.yaml`: copied verbatim
   from the sandbox source, plus two top-level convention edits to match its siblings
   (`svg-textgrad`, `p5js-sketch-generator`, `pixi-generative-art`): added
   `category: harness` and `timeout: 7200`. All `states:` blocks and the bouncing-ball
   default `context.input` were left untouched. Input is already correctly wired via the
   default `input_key: input` — a no-arg run preserves the demo default
   (`cli/loop/run.py` only assigns context from `--input` when provided).
2. **Catalog row** — `scripts/little_loops/loops/README.md`: added a description row under
   the **Animation / Generative Art** section, after `svg-textgrad`.
3. **Enforced doc count** — root `README.md`: `82 FSM loops` → `83` (the count is enforced
   by `ll-verify-docs` / `scripts/little_loops/doc_counts.py`).

Validation rules satisfied without changes: the loop already had
`artifact_versioning: true` plus per-iteration `snapshots/output_iter_N.html` archiving
(MR-5), and its quality gates are shell/vision-based rather than LLM self-grades (MR-1).
`ll-loop validate` emits 3 benign WARNINGs for optional-capture references
(`${captured.fix_plan?}` / `self_diagnosis?`) that are carried from the tested source and
do not block.

## Scope Boundaries

- Adds one loop file and two documentation edits; no FSM engine, validator, or runner
  changes.
- The pre-existing, unrelated `skills: documented=63 vs actual=35` `ll-verify-docs`
  mismatch ("63" counts Codex bridge skills) was intentionally left untouched — out of
  scope.
- Did not run the optional slow end-to-end smoke (`--max-iterations 1`), which spawns a
  real LLM + Playwright session.

## Files

- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — new built-in loop (copy + `category`/`timeout`)
- `scripts/little_loops/loops/README.md` — catalog row, Animation / Generative Art section
- `README.md` — loop count 82 → 83

## Impact

- **Priority**: P4 - Low; adds a demonstrative built-in loop, no runtime behavior change to existing loops
- **Effort**: Small - One copied file plus two doc edits
- **Risk**: Low - Additive; the loop validates and is a tested sandbox artifact
- **Breaking Change**: No

## Labels

`loops`, `built-in`, `animation`, `enhancement`, `documentation`

## Status

**Done** | Created: 2026-06-08 | Priority: P4


## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T03:04:35 - `138d88e3-b60d-4e48-bafa-685bc6fe0e54.jsonl`
