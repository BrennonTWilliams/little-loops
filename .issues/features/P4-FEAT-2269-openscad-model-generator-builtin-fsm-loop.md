---
id: FEAT-2269
title: OpenSCAD model generator built-in FSM loop
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to:
- ENH-1869
labels:
- fsm-loop
- harness
- builtin-loop
- cad
- oracle
decision_needed: false
confidence_score: 98
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
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

## Current Behavior

The harness has no built-in CAD/manufacturing loop. The closest existing loop,
`svg-image-generator.yaml`, thin-wraps `oracles/generator-evaluator.yaml`, whose
`evaluate` state hardcodes `fragment: playwright_screenshot`
(`oracles/generator-evaluator.yaml:69`) and captures a single `screenshot.png`
read by `ll_rubric_score`. There is no path to render a `.scad` artifact via the
`openscad` CLI, no multi-angle capture, and no CAD-specific rubric. Generating a
parametric OpenSCAD model today is an unguided one-shot prompt with no
render-and-inspect verification — so geometry defects that compile cleanly
(missing walls, floating parts, features absent from one viewing angle) go
uncaught.

## Expected Behavior

A built-in `openscad-model-generator` loop turns a natural-language description
into a parametric `.scad` model through a generate → render → inspect → refine
cycle: it writes the `.scad` file, renders the first `view_count` camera presets
(default ≈3) via the `openscad` CLI, scores the rendered PNGs against the CAD
rubric (correctness, completeness, printability, parametrics), and iterates until
ALL_PASS or `max_steps`. An optional `VISION_*` external-vision gate scores the
views when configured and degrades to a no-op pass when unset or erroring. `done`
reports the `.scad` and rendered view paths with optional STL export, and the
loop fails gracefully with a clear message when `openscad` is not on PATH. The
loop passes `ll-loop validate`.

## Use Case

A maker describes a part in natural language — e.g. "a parametric snap-fit
enclosure for a 60×40mm PCB with M3 mounting bosses and a removable lid" — and
runs the `openscad-model-generator` loop. It generates a parametric `.scad` file
with Customizer-annotated dimension variables, renders it from iso/front/top
angles, and visually inspects the result. When the first pass leaves the lid
floating or a boss wall missing — a defect that compiles cleanly and is invisible
from a single angle — the multi-view score routes back to `generate` with a
targeted critique, and the model is corrected before the user ever opens it in
OpenSCAD.

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

> **Selected:** Option B (fork via `from:` inheritance) — zero blast radius on six existing callers; idiomatic oracle-variant pattern in this codebase.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-24.

**Selected**: Option B — create `oracles/generator-evaluator-cli.yaml` using `from: oracles/generator-evaluator`, overriding only `evaluate` and `snapshot`

**Reasoning**: The codebase has 9 existing `from:` usages for loop/oracle variants (e.g. `pixi-generative-art.yaml`, `deep-research-arxiv.yaml`), making `from:` inheritance the idiomatic zero-drift derivation mechanism — not a literal file copy. Option B via `from:` overrides only the two states that actually differ (`evaluate`: Playwright CLI → OpenSCAD CLI; `snapshot`: single file → multi-file), leaving all six existing callers untouched and eliminating drift risk. Option A requires all six callers to pass a `render_command` default binding (enforced by `_validate_with_bindings()`), spreading blast radius across `svg-image-generator.yaml`, `html-website-generator.yaml`, `html-anything.yaml`, `hitl-md.yaml`, `hitl-compare.yaml`, and a test fixture — for a shared-oracle generalization whose future-domain reuse benefit (`from: oracles/generator-evaluator-cli`) is equally available under Option B.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (parameterize shared oracle) | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |
| Option B (fork via `from:` inheritance) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- Option A: 6 callers bind `loop: oracles/generator-evaluator` (`svg-image-generator.yaml:63`, `html-website-generator.yaml:52`, `html-anything.yaml:116`, `hitl-md.yaml:149`, `hitl-compare.yaml:137`, `test_fsm_validation.py:2247`) — parameterizing the shared oracle's API is blast-radius on all six.
- Option B: `from:` inheritance (9 existing usages) is the codebase's canonical oracle-variant pattern; `generator-evaluator-cli.yaml` with `from: oracles/generator-evaluator` has zero drift risk and leaves all existing callers untouched.

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
- `done` reports `.scad` + rendered view paths; STL export is opt-in via `export_stl: true` context variable (default off).
- System dependency on the `openscad` CLI documented; the loop fails gracefully
  with a clear message when `openscad` is not on PATH.

## Resolved design decisions

- **Oracle strategy**: Option B — `from:` fork (`oracles/generator-evaluator-cli.yaml`). Zero blast radius on five existing callers. _(decided by `/ll:decide-issue` 2026-06-24)_
- **Render mode**: Use `--render` (full CSG) on every pass, not `--preview`. The loop's value is accurate geometry inspection; `--preview` (OpenGL approximation) misses non-manifold geometry and interior features — exactly the defects the rubric targets. Use a generous per-view timeout (120 s) to absorb render time on complex models. _(decided 2026-06-24)_
- **View format**: Individual PNG per angle (not a stitched composite). Consistent with `rlhf-svg-evaluate.yaml`'s 4-frame interleaved-content-array pattern, which is the stated reference for the vision gate. _(decided 2026-06-24)_
- **STL export**: Opt-in only. `done` reports `.scad` + rendered view paths; STL export triggered by an explicit context variable (e.g. `export_stl: true`), defaulting to off. _(decided 2026-06-24)_

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Oracle evaluate state (exact generalization point):**
- `oracles/generator-evaluator.yaml` `evaluate` state (lines 68–78) uses `fragment: playwright_screenshot` with a local `action:` override calling `playwright screenshot file://$ABS_DIR/${context.artifact_path}`, producing exactly one file: `screenshot.png`. The `parameters:` block (lines 17–37) exposes `run_dir`, `generate_prompt`, `rubric`, `pass_threshold`, `artifact_path` — no `render_command` parameter exists. Adding one here is the Option A change point.
- `snapshot` state (lines 80–94) copies only `${context.artifact_path}` and hardcodes `screenshot.png`. Must be updated to handle N view files under either option.

**Multi-image scoring via `ll_rubric_score`:**
- `lib/harness.yaml` `ll_rubric_score` fragment (lines 15–44) is a `prompt`-type state: "Review the generated artifact in ${param.run_dir}" + rubric text. It does **not** reference any specific image path — the rubric string drives what the LLM reads. Multi-view requires only that the rubric text enumerate `views/view_0.png … views/view_{view_count-1}.png`; no fragment change needed.

**Closest multi-view pattern:**
- `rlhf-animated-svg.yaml` — captures multiple SVG snapshots iteratively via a shell state and references them by explicit path in the rubric string. Best existing analog for multi-view render + rubric evaluation.

**Vision gate coupling to single file:**
- `svg-image-generator.yaml` `vision_gate` (lines 130–236): reads `screenshot.png` at a hardcoded relative path inside a Python heredoc. Multi-view support requires iterating over `views/view_0.png … views/view_{view_count-1}.png`. The `ROUND_CAP = 3` anti-pingpong guard should be preserved verbatim.

**`ll-loop validate` constraints on the new loop:**
- MR-5 applies: `category: harness` loop with an iterative `generate → render_views` cycle overwrites view PNGs each pass. Declare `artifact_versioning: true` to satisfy.
- MR-1 satisfied by: `render_views` shell state's `evaluate: {type: output_contains, pattern: "CAPTURED"}` is a non-LLM evaluator.
- MR-3 satisfied by: all artifact writes under `${context.run_dir}/`.
- MR-4: ensure every LLM-judged state (`generate`, `score`) has routes for `on_no` and `on_partial` (or use `next:` for unconditional advance).

**Configurable view list pattern (`generative-art.yaml`):**
- `generative-art.yaml` uses `sample_frames: "0,90,240"` as a context variable and splits it in the shell state: `frames = '${context.sample_frames}'.split(',')`. The `view_count` context variable for OpenSCAD should follow this same pattern — a comma-separated preset list (e.g., `view_presets: "iso,front,top"`) so the render state iterates over named camera positions without a per-view DSL. The `sample_frames` pattern is the exact precedent.
- `rlhf-svg-evaluate.yaml` implements a more sophisticated 4-frame vision gate as a Python heredoc that iterates over available frame files, constructs an interleaved content array (`[text, image_url, text, image_url, …]`), and calls the vision API. This is a better template than `svg-image-generator.yaml`'s simpler single-image gate for the multi-view use case.
- **`$${...}` double-dollar escaping**: In FSM shell state `action:` strings, `${...}` is interpolated by the FSM template engine; bash variable references must use `$${...}` (e.g., `openscad $${RUN_DIR}/model.scad`) to avoid "expected namespace.path" errors — see `oracles/generator-evaluator.yaml:70` for the canonical example.

**Test class references:**
- `scripts/tests/test_builtin_loops.py:3388` — `TestSvgImageGeneratorLoop`; contains delegation tests (`test_run_gen_eval_delegates_to_generator_evaluator`, `test_run_gen_eval_with_bindings_present`, `test_inline_generate_evaluate_score_states_removed`, `test_init_state_is_shell_with_capture`). Add `TestOpenSCADModelGeneratorLoop` following this pattern.
- `scripts/tests/test_builtin_loops.py:3273` — `TestHtmlWebsiteGeneratorLoop`; alternate reference for loops that use `${context.run_dir}` directly without an `init` capture state.

**Option A thin-wrapper callers (unaffected under Option B):**
- `svg-image-generator.yaml`, `html-website-generator.yaml`, `html-anything.yaml`, `hitl-md.yaml`, `hitl-compare.yaml` — all delegate to `loop: oracles/generator-evaluator`. Under Option A each must pass a `render_command` default binding (the existing Playwright shell action) to preserve current behavior; enforced by `_validate_with_bindings()` in `validation.py:364`.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/openscad-model-generator.yaml` — new built-in FSM loop (primary deliverable)
- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml` — **Option B only**: fork of `generator-evaluator.yaml` with parameterized CLI render action and multi-file snapshot; leaves shared oracle untouched

### Files to Modify

**Option A — Parameterize shared oracle:**
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — add `render_command` to `parameters:` (lines 17–37); update `evaluate` state (lines 68–78) to use `${context.render_command}` in place of hardcoded `playwright screenshot` action; update `snapshot` state (lines 80–94) to copy all `views/view_*.png` rather than single `screenshot.png`
- `scripts/little_loops/loops/lib/harness.yaml` — optionally add an `openscad_render` fragment alongside `playwright_screenshot` (lines 2–13) for reuse in future CLI-render loops

**Shared regardless of option:**
- `scripts/tests/test_builtin_loops.py` — add `TestOpenSCADModelGenerator` class
- `scripts/little_loops/loops/README.md` — add `openscad-model-generator` to built-in loops catalog

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` (root) line 163 — update `"92 FSM loops"` count to 94; both new YAML files pass `is_runnable_loop()`, so `ll-verify-docs` exits non-zero without this edit [Agent 2 finding]

### Dependent Files (Callers of `oracles/generator-evaluator`)
Affected under Option A only; unaffected under Option B:
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/html-anything.yaml`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/little_loops/loops/hitl-compare.yaml`

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml` lines 130–236 (`vision_gate`) — VISION_* graceful-degradation + round-cap pattern; copy verbatim, update `screenshot.png` to iterate over `views/view_0.png … views/view_{view_count-1}.png`
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — multi-image iterative shell capture; rubric references multiple frame paths by name
- `scripts/little_loops/loops/lib/harness.yaml` lines 15–44 (`ll_rubric_score`) — rubric text drives image path resolution; no fragment change needed for multi-view

### Tests
- `scripts/tests/test_builtin_loops.py` — add `TestOpenSCADModelGenerator`; mock `openscad` binary; assert YAML loads, `ll-loop validate` exits 0, state routing is correct
- `scripts/tests/test_fsm_validation.py` — no changes; new loop must pass existing MR-1 through MR-6 rules

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_expected_loops_exist` (lines 74–164) has a hardcoded `expected` set; add `"openscad-model-generator"` or the exact-set assertion fails on merge [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — add `TestGeneratorEvaluatorCliOracle` class; follow `TestGeneratorEvaluatorOracle` at line 5720; if oracle uses `from: oracles/generator-evaluator`, also add `resolved_data` fixture per `TestP5jsSketchGeneratorLoop` pattern at line 3511 [Agent 3 finding]

### Documentation
- `scripts/little_loops/loops/README.md` — add `openscad-model-generator` to `## Harness / Templates` table
- `scripts/little_loops/loops/README.md` — also add `oracles/generator-evaluator-cli` row to `## Oracle Sub-loops` table with caller note [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — add `openscad-model-generator` row to `### Harness Examples` table (~line 1217); add to GAN-attribution sentence (~line 1247); add `### openscad-model-generator` section with `> **Prerequisites**: openscad CLI` callout — this is where all harness loop system-dependency docs live [Agent 2 finding]

## Implementation Steps

1. **Decide oracle strategy** — Run `/ll:decide-issue FEAT-2269` to choose between Option A (parameterize `oracles/generator-evaluator.yaml`) or Option B (fork `oracles/generator-evaluator-cli.yaml`). Option A yields cross-domain reuse for future CLI-rendered artifacts (CNC, graphviz, manim). Option B has zero blast radius on the five existing thin-wrapper callers. Record the decision in `decisions.yaml`.

2. **Oracle work (only one path executes):**
   - *Option A*: Add `render_command` to `parameters:` in `oracles/generator-evaluator.yaml:17`; update `evaluate` state (line ~68) to replace `playwright screenshot …` action with `${context.render_command}` interpolation; update `snapshot` state (line ~80) to copy all `views/view_*.png` files instead of single `screenshot.png`.
   - *Option B*: Create `oracles/generator-evaluator-cli.yaml` as a copy of `generator-evaluator.yaml`; replace the Playwright evaluate action with a parameterized CLI shell action; update snapshot for multi-file handling; leave `oracles/generator-evaluator.yaml` untouched.

3. **Write `openscad-model-generator.yaml`:**
   - Set `category: harness` and `artifact_versioning: true` (required — MR-5 fires for iterative `generate → render_views` cycle that overwrites view PNGs each pass).
   - States: `init` → `plan` → `generate` → `render_views` → oracle sub-loop → `vision_gate` → `done`.
   - `render_views` shell state: loop over `view_count` camera presets (iso, front, top…) calling `openscad $${RUN_DIR}/model.scad --camera <preset> --render -o $${RUN_DIR}/views/view_$${n}.png`; set `timeout: 120` per view (full CSG; never use `--preview` — it misses non-manifold geometry); check `command -v openscad` first and route `on_no` to a descriptive `done`-exit when not on PATH; evaluator: `output_contains: "CAPTURED"` (satisfies MR-1).
   - Rubric text: enumerate `${context.run_dir}/views/view_0.png … view_{view_count-1}.png` explicitly — `ll_rubric_score` at `lib/harness.yaml:34` delegates image path resolution entirely to the rubric string.
   - `vision_gate`: follow `rlhf-svg-evaluate.yaml`'s 4-frame interleaved-content-array pattern (not `svg-image-generator.yaml`'s single-image pattern); iterate over `views/view_0.png … views/view_{view_count-1}.png`; preserve `ROUND_CAP = 3`.
   - `done`: report `.scad` + `views/view_*.png` paths; conditionally run `openscad -o model.stl` only when `${context.export_stl}` is `true` (default off).

4. **Validate**: `ll-loop validate openscad-model-generator.yaml` — confirm MR-1 (render_views evaluator), MR-3 (all writes under `run_dir`), MR-4 (all LLM-judged states have `on_no`/`on_partial` routes or `next:`), MR-5 (suppressed by `artifact_versioning: true`).

5. **Test**: Add `TestOpenSCADModelGenerator` in `scripts/tests/test_builtin_loops.py`; mock `openscad` binary; assert YAML loads without error and `ll-loop validate` exits 0.

6. **Update catalog**: Add `openscad-model-generator` entry to `scripts/little_loops/loops/README.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `TestBuiltinLoopFiles.test_expected_loops_exist` in `scripts/tests/test_builtin_loops.py` — add `"openscad-model-generator"` to the hardcoded `expected` set (critical: exact-set assertion fails without this)
8. Add `TestGeneratorEvaluatorCliOracle` class in `scripts/tests/test_builtin_loops.py` — follow `TestGeneratorEvaluatorOracle` at line 5720; if oracle uses `from: oracles/generator-evaluator`, use `data` + `resolved_data` fixture pair per `TestP5jsSketchGeneratorLoop` at line 3511
9. Update `README.md` (root) line 163 — increment `"92 FSM loops"` to 94; `ll-verify-docs` counts runnable loops via `rglob`, both new YAMLs are counted
10. Add `oracles/generator-evaluator-cli` row to `## Oracle Sub-loops` table in `scripts/little_loops/loops/README.md`
11. Add `openscad-model-generator` to `docs/guides/LOOPS_REFERENCE.md` — row in `### Harness Examples` table, entry in GAN-attribution sentence (~line 1247), and new `### openscad-model-generator` section with `> **Prerequisites**` callout for `openscad` binary install

## Impact

- **Effort**: Medium — the loop YAML is small; the oracle generalization
  (render command + multi-view rubric) is the real work.
- **Risk**: Low-Medium — if the shared oracle is parameterized, the
  `render_command` default must preserve current wrapper behavior exactly.
- **Breaking change**: No (additive loop + backward-compatible oracle default).

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-24_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 74/100 → Acceptable (just below 75 threshold)

### Outcome Risk Factors
- Three render-path implementation choices left to implementor judgment (`--preview` vs. `--render` for early iterations; individual PNG per angle vs. stitched composite; STL export always vs. opt-in) — `rlhf-svg-evaluate.yaml`'s 4-frame pattern effectively resolves the PNG question in favor of individual files, but the render-quality tradeoff should be settled before writing the `render_views` state to avoid timeout-tuning rework
- `test_expected_loops_exist` exact-set assertion at `test_builtin_loops.py:74` will cause CI failure if `"openscad-model-generator"` is not added to the hardcoded set — documented in step 7 but easy to miss when writing test classes bottom-up
- External `openscad` CLI binary requires test mocking — the mock must intercept the `render_views` shell state subprocess call; unvalidated against the new loop YAML structure until the file is written

## Session Log
- `/ll:confidence-check` - 2026-06-24T22:15:00 - `99a0a893-83eb-4eb3-9d41-6e42559224b6.jsonl`
- `/ll:confidence-check` - 2026-06-24T21:30:00 - `6b13d994-35f5-46a7-b0d0-1c904a388fbe.jsonl`
- `/ll:wire-issue` - 2026-06-24T21:13:42 - `51fb05c0-16b7-46b6-930c-7ce607ef3f4d.jsonl`
- `/ll:decide-issue` - 2026-06-24T20:43:11 - `488ef513-57b0-4a32-88de-2e01a29a0bdc.jsonl`
- `/ll:refine-issue` - 2026-06-24T20:30:57 - `de730a3f-9cf8-4a76-8678-a41c35dafd15.jsonl`
- `/ll:format-issue` - 2026-06-24T19:48:57 - `18c9e93a-fde6-4c52-9a3f-e96c3083df94.jsonl`
