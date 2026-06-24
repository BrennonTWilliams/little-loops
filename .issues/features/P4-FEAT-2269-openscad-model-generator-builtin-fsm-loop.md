---
id: FEAT-2269
title: OpenSCAD model generator built-in FSM loop
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [ENH-1869]
labels: [fsm-loop, harness, builtin-loop, cad, oracle]
---

# FEAT-2269: OpenSCAD model generator built-in FSM loop

## Summary

Ship a built-in `openscad-model-generator` FSM loop that turns a natural-language
description into a parametric OpenSCAD model through the harness's
generate → render → inspect → refine cycle. It writes a `.scad` file, renders it
from multiple camera angles via the `openscad` CLI, scores the rendered views
against a CAD-specific rubric, and iterates until all criteria pass.

This is the first CAD/manufacturing domain for the harness pattern and a
compelling built-in example because correctness is **not** implied by
compilation: a `.scad` file can compile cleanly while still having a missing
wall, floating geometry, or a feature absent from one viewing angle. Visual
multi-angle inspection is therefore load-bearing — it forces the model to
verify the geometry rather than self-certify that the code "looks right." That
makes it a stronger demonstration of *why* a refine loop beats one-shot
generation than the existing web-render loops, where "compiles" and "looks
right" nearly coincide.

## Architecture note: this is NOT a thin wrapper

The closest existing loop is `svg-image-generator.yaml`, a thin wrapper over
`oracles/generator-evaluator.yaml`. OpenSCAD **cannot** thin-wrap that oracle as-is
for two reasons:

1. **The render mechanism is hardcoded.** The oracle's `evaluate` state is fixed
   to `fragment: playwright_screenshot` (`oracles/generator-evaluator.yaml:69`).
   It exposes `run_dir`, `generate_prompt`, `rubric`, `pass_threshold`,
   `artifact_path` as parameters — but **not** the capture/render command. An
   OpenSCAD render is a different command, so the swap the proposal assumed is
   a no-op only at the wrapper layer; the real change is in the oracle.
2. **Single-image vs. multi-view.** The oracle captures one `screenshot.png` and
   the `ll_rubric_score` fragment reads one image. The whole point of the CAD
   loop is multi-angle inspection, so both the render step and the rubric step
   must handle N views.

The effort therefore lives in the oracle generalization, not the loop YAML.
**Preferred approach: parameterize the oracle** with an optional
`render_command` (defaulting to the existing Playwright fragment) so the same
oracle handles any CLI-rendered artifact (CAD now; CNC/graphviz/manim later) —
a generalization that pays for itself beyond this one loop. A forked
`generator-evaluator-cli` oracle is the lower-blast-radius fallback if
parameterizing the shared oracle proves too invasive. Decide during refinement.

## Configurable view count (low default)

Render angle count is a **configurable context variable**, not a fixed 7. Default
to a small number (e.g. `view_count: 3` — iso + front + top) to keep the demo
fast and the LLM evaluation focused; allow raising it for complex models. Only
make it configurable if it doesn't add substantial complexity to the render
state — a simple "render the first N of an ordered camera-preset list" is in
scope; an elaborate per-view camera DSL is not.

## Separate vision-model support (existing pattern)

Reuse the existing optional external-vision evaluator pattern from
`svg-image-generator.yaml:130-236` (`vision_gate` state): if `VISION_BASE_URL`,
`VISION_MODEL`, and `VISION_API_KEY` are present in the project's `.env`, an
independent vision model scores the rendered views and appends failing criteria
to the critique for the next pass. **Graceful degradation is required**: when the
`VISION_*` vars are absent, or the vision API errors/returns unparseable output,
the gate is a no-op pass — never block a functionally-sound model on an optional
gate. A per-run round cap bounds ping-pong, same as the SVG loop.

## CAD-specific rubric

Replace the SVG aesthetic rubric with CAD criteria (threshold 6/10 per criterion,
matching the existing harness default):

- **correctness** (2x) — does the model match the description? All requested
  features present?
- **completeness** (2x) — parts connected, manifold, printable? No floating
  geometry or missing walls?
- **printability** (1x) — wall thickness, overhangs, manifold edges, print
  orientation considered?
- **parametrics** (1x) — key dimensions exposed as top-of-file variables with
  Customizer annotations? Color parameters present?

## States (mapping)

| Step | FSM State | Mechanism |
|------|-----------|-----------|
| Describe model | `init` + `plan` | `plan` expands NL → CAD brief (dimensions, constraints, printability, part count) |
| Write OpenSCAD | `generate` | Prompt writes `.scad` with parametric vars + Customizer comments |
| Render views | `render_views` | Shell: `openscad model.scad --camera … --render -o views/{view}.png` for the first `view_count` presets |
| Inspect views | `evaluate` / `score` | LLM reads the rendered PNGs, scores against the CAD rubric, emits `ALL_PASS` / `ITERATE` |
| Optional external vision | `vision_gate` | `VISION_*` env model, graceful no-op when unset |
| Refine | loop back to `generate` | Standard oracle routing |
| Final | `done` | Reports paths to `.scad`, rendered views; optional `openscad -o model.stl` |

## Acceptance Criteria

- A built-in `openscad-model-generator` loop YAML accepts a NL description via
  `input_key` and iterates generate → render → score → refine until ALL_PASS or
  `max_steps`, passing `ll-loop validate`.
- The render/rubric multi-view requirement is met by either parameterizing
  `oracles/generator-evaluator` with an optional `render_command` (default =
  existing Playwright fragment, so all current wrappers are unaffected) **or** a
  documented CLI-render oracle variant. Decision recorded.
- `view_count` is a context variable with a low default (≈3); the render state
  renders the first N camera presets. No per-view camera DSL.
- Optional `VISION_*` external-vision gate wired per the `svg-image-generator`
  pattern, with no-op graceful degradation when env vars are absent or the API
  errors.
- CAD rubric (correctness 2x, completeness 2x, printability 1x, parametrics 1x;
  threshold 6) embedded in the loop's `rubric` parameter.
- Per-run artifact isolation under `${context.run_dir}/` (CLAUDE.md meta-loop
  rule MR-3 / harness convention); per-iteration snapshots preserved.
- `done` reports `.scad` + rendered view paths; optional STL export.
- System dependency on the `openscad` CLI documented; the loop fails gracefully
  with a clear message when `openscad` is not on PATH.

## Open design questions (keep explicit; do not pre-decide)

- Parameterize the shared oracle (`render_command`) vs. fork a CLI-render
  oracle. Trade-off: cross-domain reuse vs. blast radius on existing wrappers.
- `--preview` (fast, lower-quality CSG) for early iterations vs. `--render`
  (full CSG) for the final pass — render time on slower hosts can be minutes for
  complex models; the `render_views` state needs generous timeouts.
- Individual PNG per angle (higher res per view) vs. one stitched composite
  sheet for LLM evaluation.
- STL export in `done`: always vs. opt-in.

## Reference

- `scripts/little_loops/loops/svg-image-generator.yaml` — closest existing loop;
  `vision_gate` state (lines 130-236) is the reusable `VISION_*` pattern.
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:69` — hardcoded
  `playwright_screenshot` evaluate state (the generalization point).
- `scripts/little_loops/loops/lib/` — `ll_rubric_score`, `diff_stall_gate`,
  `playwright_screenshot` fragments.
- ENH-1869 — the thin-wrapper-over-oracle architecture this builds on.
- `docs/research/2026-06-24 FSM Loop Proposal — OpenSCAD Model Generator.md` —
  originating research.

## Impact

- **Effort**: Medium — the loop YAML is small; the oracle generalization
  (render command + multi-view rubric) is the real work.
- **Risk**: Low-Medium — if the shared oracle is parameterized, the
  `render_command` default must preserve current wrapper behavior exactly.
- **Breaking change**: No (additive loop + backward-compatible oracle default).

## Status

**Open** | Created: 2026-06-24 | Priority: P4
