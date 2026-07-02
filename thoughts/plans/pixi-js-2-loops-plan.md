# Plan: Add `pixi-data-viz` and `pixi-generative-art` FSM Loops

## Context

The repo ships three example generator-evaluator FSM loops under
`scripts/little_loops/loops/`:

- `html-anything.yaml` — generalized HTML harness with dynamic per-type rubric
- `html-website-generator.yaml` — single-page website generator
- `p5js-sketch-generator.yaml` — multi-frame p5.js sketch generator

These cover static HTML and 2D-canvas creative coding, but nothing in the
catalog targets **PixiJS** — a WebGL-accelerated 2D renderer used for
generative art, particle systems, games, and high-density interactive data
visualization. The previous brainstorming turn enumerated four PixiJS harness
options; this plan implements two carved out of Option C
(classifier-driven `pixi-anything`) as standalone, narrowly-scoped loops:

1. **`pixi-generative-art`** — direct analog of `p5js-sketch-generator`, but
   targeting Pixi's GPU-native idioms (filters, blend modes, containers,
   particle systems) instead of p5's CPU canvas API.
2. **`pixi-data-viz`** — a generator-evaluator for animated data
   visualizations rendered in PixiJS, judging *encoding clarity* and
   *animation legibility* rather than pure aesthetics.

Both are non-meta loops (they only write inside `${context.run_dir}`), so
the validator's MR-1 rule does **not** require a non-LLM evaluator. Both can
follow the standard `init → plan → generate → evaluate (Playwright) → score
→ done / failed` shape proven by the p5js loop.

## Files to Create

```
scripts/little_loops/loops/pixi-generative-art.yaml
scripts/little_loops/loops/pixi-data-viz.yaml
```

No registry or `__init__.py` updates needed — loops are auto-discovered by
filename. No CLI changes. No schema changes.

## Shared Scaffold (Both Loops)

Mirror `p5js-sketch-generator.yaml` structurally:

| State      | Type   | Purpose                                                                                     |
| ---------- | ------ | ------------------------------------------------------------------------------------------- |
| `init`     | shell  | `mkdir -p` + guarded absolute-path echo (see note below), capture as `run_dir` (absolute file:// path) |
| `plan`     | prompt | Write `brief.md` to `${captured.run_dir.output}/brief.md`                                   |
| `generate` | prompt | Write self-contained `index.html` (Pixi from CDN, all sketch code inline)                   |
| `evaluate` | shell  | Multi-frame Playwright screenshots via `--wait-for-function`                                |
| `score`    | prompt | Read PNGs + brief, write `critique.md`, output `ALL_PASS` / `ITERATE`                       |
| `done`     | prompt (terminal) | Report output paths                                                              |
| `failed`   | terminal          | Explicit failure terminal                                                         |

### Shared top-level keys

```yaml
category: harness
input_key: description
initial: init
max_iterations: 20
on_handoff: spawn
timeout: 7200
context:
  description: ""
  pass_threshold: 6
  sample_frames: "0,90,240"
  design_tokens_context: ""
```

### Shared PixiJS conventions (enforced in `generate` prompt)

- Load Pixi v8 from CDN — the only external resource permitted:
  `<script src="https://pixijs.download/release/pixi.js"></script>`
- Use **`globalThis` access** for the Application — Pixi v8 is async-init
  (`await app.init({...})`), so wrap the sketch in `(async () => { ... })()`
  in the inline `<script>` body.
- **Deterministic seeding** is required (the screenshot harness depends on
  it). Seed a small PRNG (e.g. `mulberry32`) with a constant integer and use
  it for all randomness; drive all animation from a manually-incremented
  `window.__loopFrame` counter inside `app.ticker.add`. Never use
  `Date.now()` or `Math.random()` directly inside the ticker.
- Expose `window.__loopFrame` so `playwright screenshot --wait-for-function
  'window.__loopFrame >= N'` can pin captures to known frames (same trick
  the p5 loop uses with `window.frameCount`, but Pixi has no built-in
  global frame counter).
- Canvas size ≥ 1200×800 (no default tiny canvas).
- Encourage Pixi-distinctive features: `Filter` (Blur, Displacement, custom
  GLSL via `Filter.from(...)`), blend modes (`'add'`, `'multiply'`,
  `'screen'`), `Container` hierarchy, `ParticleContainer` where dense, sprite
  textures generated via `app.renderer.generateTexture`.

### Multi-frame `evaluate` state

Identical Python invocation to `p5js-sketch-generator.yaml` lines 127–139,
swapping the `window.frameCount >= N` predicate for `window.__loopFrame >= N`.

---

## Loop A — `pixi-generative-art.yaml`

**Description block**:

> Generator-evaluator harness for PixiJS generative art sketches.
> Iteratively generates a single self-contained HTML file embedding a
> deterministic, GPU-accelerated PixiJS sketch and judges it across
> multi-frame screenshots so motion is evaluated, not just composition.
> Mirrors the p5.js sketch generator but rewards Pixi-distinctive
> idioms — filters, blend modes, container hierarchies, particle systems.

**Plan prompt should require**:
- *Generative concept* — name the rule (flow field with displacement
  filter, agent system rendered through additive blending, shader-driven
  signed-distance composition, etc.).
- *Visual palette* — 3–6 hex colors, background, blend mode(s).
- *GPU strategy* — which Pixi feature does the heavy aesthetic lift
  (filter, blendMode, ParticleContainer, custom shader)? This field is
  the discriminator from p5.
- *Motion behavior* — what changes at frame 0 / 90 / 240.
- *Unique angle*.
- *Anti-patterns*: bare `Graphics` over white background; no filters/blend
  modes; canned Pixi "bunny" or "fish-pond" tutorial output; rainbow HSL
  cycling for its own sake.

**Score criteria** (same shape as p5 loop, threshold = `pass_threshold` per
criterion):

| Criterion        | Weight | Notes                                                                       |
| ---------------- | ------ | --------------------------------------------------------------------------- |
| `visual_impact`  | 2×     | Composition, palette, density across frames                                  |
| `originality`    | 2×     | Custom creative decision vs tutorial output; penalize default Pixi examples |
| `motion_quality` | 1×     | Meaningful evolution across frame 0/90/240; static or jittery = ≤3          |
| `gpu_craft`      | 1×     | Evidence of Pixi-native features (filters/blend modes/containers) — replaces generic `craft` with the GPU-specific bar that distinguishes this loop from p5 |

Routing identical to p5: `score.on_yes → done`, `on_no → generate`,
`on_error → failed`.

---

## Loop B — `pixi-data-viz.yaml`

**Description block**:

> Generator-evaluator harness for animated PixiJS data visualizations.
> Generates a single self-contained HTML file that embeds synthetic but
> plausible data and renders it through a deterministic PixiJS animation,
> then judges across multi-frame screenshots whether the encoding reads
> clearly and whether motion *aids* comprehension rather than obscuring it.

**Differences from `pixi-generative-art`**:

1. **`plan` prompt** asks the planner to commit to:
   - *Dataset shape* — what kind of data is being visualized (time-series
     of N metrics, weighted graph of M nodes, geographic point cloud,
     hierarchical tree, etc.). The planner fabricates a deterministic
     synthetic dataset spec; the generator embeds it inline.
   - *Encoding* — what visual variable carries which data variable
     (position, color, size, opacity). Must reference one of the
     Cleveland-McGill perceptual rankings as justification.
   - *Animation purpose* — what does motion *teach* the viewer? E.g. a
     transition between two states reveals delta; a sweep reveals an
     ordering; a sustained pulse highlights anomalies. Animation for its
     own sake is an explicit anti-pattern.
   - *Annotations* — axes, legend, units, title. Required, not optional.
   - *Anti-patterns*: unlabeled axes; rainbow-jet colormap for sequential
     data; 3D pie charts; spinning anything; motion that out-paces reading
     speed; bouncing/easing applied to data points (decorative, not
     informative).

2. **`generate` prompt** adds:
   - Embed the synthetic dataset as a JSON literal at the top of the inline
     script. Same seed → same numbers.
   - Use Pixi `Text` (with `BitmapFont` or embedded TTF data URL if a
     specific face is requested) for axis labels and legend — fonts are
     part of the eval.
   - Sample frames represent meaningful viz states:
     `sample_frames: "0,120,240"` — initial render with axes only,
     mid-transition, settled state.

3. **`score` criteria**:

   | Criterion              | Weight | Notes                                                                                                  |
   | ---------------------- | ------ | ------------------------------------------------------------------------------------------------------ |
   | `encoding_clarity`     | 2×     | Can a viewer figure out what the data means? Axes labeled, legend present, scale appropriate, units shown. Threshold 7 (higher than aesthetics — this is the platform constraint, mirroring how html-email demands inline_styles at threshold 8). |
   | `animation_legibility` | 2×     | Does motion *aid* comprehension? Smooth transitions between states reveal delta or ordering; jitter, over-fast change, decorative bounce = fail. |
   | `visual_design`        | 1×     | Aesthetic coherence; palette appropriate to data type (sequential / diverging / categorical).         |
   | `craft`                | 1×     | Typography, spacing, alignment, hit-detection for interactive bits, anti-aliasing of axes.            |

   Use per-criterion thresholds (not weighted average) — same pattern as
   `html-anything.yaml`, so a beautiful chart with unlabeled axes still
   fails. Override the default `pass_threshold` for `encoding_clarity` by
   making the rubric carry per-criterion thresholds inline (mirroring
   `html-anything`'s YAML-in-markdown rubric pattern is overkill here —
   instead, hard-code threshold 7 for `encoding_clarity` in the score
   prompt and threshold = `${context.pass_threshold}` for the other three).

---

## Reused Patterns / Files Referenced

- Multi-frame Playwright capture: copy verbatim from
  `scripts/little_loops/loops/p5js-sketch-generator.yaml:127-139`, swap
  the `frameCount` predicate.
- `init` shell pattern (capture absolute `run_dir`): copy from
  `p5js-sketch-generator.yaml:27-36`. **Note (BUG-2435):** the runner always
  injects `${context.run_dir}` as absolute, so a plain `$(pwd)/$DIR` echo
  doubles the path; use the guarded `case "$DIR" in /*) echo "$DIR" ;; *)
  echo "$(pwd)/$DIR" ;; esac` form instead (already applied to
  `pixi-data-viz.yaml`).
- `score` state's `output_contains: ALL_PASS` routing + `critique.md`
  format: model on `p5js-sketch-generator.yaml:147-208`.
- `done` and `failed` terminals: copy `p5js-sketch-generator.yaml:210-235`,
  adjust the final file list.
- Context-variable injection (`run_dir`, `design_tokens_context`) is
  handled by `scripts/little_loops/run.py:159-183` — no loop-side wiring.

## Verification

Before declaring done, run these in order:

1. **Syntax / schema validation** — auto-discovery + schema check:
   ```
   ll-loop validate pixi-generative-art
   ll-loop validate pixi-data-viz
   ```
   Expect: no errors. MR-1 should NOT fire (no harness-artifact writes).

2. **List shows both loops**:
   ```
   ll-loop list | grep pixi
   ```

3. **End-to-end smoke run** (one each, short input):
   ```
   ll-loop run pixi-generative-art --input description="a slow-blooming \
     additive-blend flow field of soft particles drifting through a deep \
     teal void, with displacement-filter shimmer at the seams"

   ll-loop run pixi-data-viz --input description="quarterly active-user \
     counts across 5 product surfaces, animated to reveal which surface \
     overtook another between Q3 and Q4"
   ```

   For each, after the run completes, verify in the run dir:
   - `brief.md` exists and contains the required sections.
   - `index.html` exists, opens in a browser, runs without console errors,
     animates over time, exposes `window.__loopFrame`.
   - `frame_0.png`, `frame_90.png` (or `frame_120.png`), `frame_240.png` exist.
   - `critique.md` has scores in the documented format.
   - For `pixi-data-viz`: axes are labeled and a legend is visible in at
     least one frame; for `pixi-generative-art`: a Pixi-native feature
     (filter, blend mode, or container hierarchy) is detectable in the
     inline script.

4. **Determinism check** — run each loop twice with the same input and
   confirm `frame_240.png` is byte-identical across runs (Pixi's seeded
   PRNG + frame-driven ticker should make this true; if it's not, the
   generate prompt's determinism clauses need tightening).

5. **Failure-path sanity** — temporarily rename or chmod-block the
   Playwright binary, run once, confirm the loop terminates at `failed`
   (not at `max_iterations`).
