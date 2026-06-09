---
id: ENH-2059
title: Wire VISION_* env vars into svg-image-generator via vision_gate state
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T00:00:00Z'
discovered_date: 2026-06-09
labels:
- loops
- fsm
- vision
completed_at: '2026-06-09T00:00:00Z'
---

# ENH-2059: Wire VISION_* env vars into svg-image-generator via vision_gate state

## Summary

Added a `vision_gate` state to `svg-image-generator.yaml` that calls an external vision
model via `VISION_BASE_URL`, `VISION_MODEL`, and `VISION_API_KEY` (.env) to score
generated SVGs independently of the host LLM. Follows the identical pattern established
in `html-website-generator.yaml` and `rlhf-svg-evaluate.yaml`.

## Motivation

`svg-image-generator` previously delegated its entire generate→screenshot→score pipeline
to `oracles/generator-evaluator`, which uses the `ll_rubric_score` fragment — an LLM
prompt that asks Claude to evaluate its own output. This self-certification has known
accuracy limits (SHOR Table 1). The other vision-driven harness loops gate on an
external vision model for an objective second opinion. `svg-image-generator` had no such
gate.

## Changes

### `scripts/little_loops/loops/svg-image-generator.yaml`

- `run_gen_eval` state: `on_yes: done` → `on_yes: vision_gate`
- New `vision_gate` state inserted between `run_gen_eval` and `done`:
  - Sources `.env`; guards on all three `VISION_*` vars — silently passes
    (`VISION_PASS: skipped`) when any are unset (graceful no-op)
  - Encodes `screenshot.png` as base64 and POSTs to `VISION_BASE_URL/chat/completions`
  - Scores the four SVG-specific criteria from the existing rubric:
    `visual_clarity`, `originality`, `craft`, `scalability` — threshold 6
  - On failure: appends `## Issues to Address (external vision critique, round N)` to
    `critique.md` so the next `run_gen_eval` pass acts on the specific failing criteria
  - Round cap of 3 (`.vision_rounds` file) prevents infinite refine/re-score ping-pong
  - API/parse/network errors produce `VISION_PASS` — never block a functionally-sound
    artifact on an optional gate
  - Routing: `on_yes: done`, `on_no: run_gen_eval`, `on_error: done`

## Validation

`ll-loop validate svg-image-generator` — passes with no new MR-* errors (pre-existing
`required_inputs` warning is unrelated).

## Reference

Pattern sourced from:
- `html-website-generator.yaml:143-250` — `vision_gate` state (identical structure)
- `rlhf-svg-evaluate.yaml:195-458` — multi-frame variant of the same pattern


## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T17:52:29 - `a06c834d-25bd-460e-b4d5-70c3bdffe175.jsonl`
