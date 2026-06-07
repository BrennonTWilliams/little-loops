---
id: ENH-2010
title: Add vega-viz generate-score-refine loop for Vega/Vega-Lite visualizations
type: ENH
priority: P3
status: done
captured_at: '2026-06-07T17:25:00Z'
discovered_date: 2026-06-07
discovered_by: capture-issue
labels:
- enhancement
- loops
- fsm
- harness
- visualization
confidence_score: 100
outcome_confidence: 80
size: Medium
---

# ENH-2010: Add vega-viz generate-score-refine loop for Vega/Vega-Lite visualizations

## Summary

Added a new built-in FSM loop, `scripts/little_loops/loops/vega-viz.yaml`, that
turns a natural-language description into a refined, self-contained HTML
visualization artifact rendered via `vega-embed`. It follows the GAN-inspired
generator/evaluator pattern from
[docs/research/harness-design-for-long-running-application-development.md](../../docs/research/harness-design-for-long-running-application-development.md)
and joins the existing family of generate→screenshot→score→refine visual loops
(`pixi-data-viz`, `pixi-generative-art`, `p5js-sketch-generator`,
`svg-image-generator`, `html-website-generator`).

The loop is a sibling of `pixi-data-viz.yaml` but swaps the hand-coded canvas
engine for the Vega grammar, which unlocks two capabilities Pixi-based loops
cannot have: a real deterministic **compile gate** and **path-optional binding
to real data**.

## Context

Brainstormed and built in a single session. Vega data-viz is an unusually good
fit for the generator/evaluator harness because it spans both domains the
research article addresses at once: the subjective axis (is the chart clear and
well-designed?) and the verifiable axis (does the spec parse and render?). The
verifiable axis gives a genuine non-LLM gate "for free," which is exactly what
the project's loop best-practices (CLAUDE.md § Loop Authoring) push for, even
though — as a `category: harness` data-operating loop that emits an HTML
artifact rather than modifying harness files — it is not a meta-loop bound by
rule MR-1.

Design forks were resolved with the user:
- **Grammar**: default to Vega-Lite, escalate to full Vega only when the request
  needs custom/interactive composition.
- **Data source**: path-optional — bind to a supplied CSV/JSON when present,
  otherwise synthesize clearly-labeled sample data.
- **Output**: score on a static-capable render but ship interactive HTML, with
  an interactive Playwright capture pass.

## What was built

An 11-state FSM:

```
init → resolve_data → plan → generate ─► validate ─► capture ─► score → record ─► done
                          ▲      │fail        │fail          │            │PASS
                          │      ▼            ▼              (next)        └─►(terminal)
                          └── repair       generate
                          └──────────────── generate ◄────── record (ITERATE)
                                                              failed (terminal)
```

Key design decisions baked into the loop:

- **Deterministic compile gate (`validate`)** — the verifiable axis Pixi lacks.
  Vega-Lite is compiled with `npx vl2vg` then the compiled Vega is rendered to a
  throwaway PNG with `vg2png` (catches data/scale errors too); full Vega is
  rendered directly. Non-zero exit routes to a dedicated **`repair`** state fed
  `compile_error.txt` verbatim, so structural breaks are fixed with the actual
  error message while `generate` handles quality. Break-fixing and
  taste-refinement are kept on separate routes.
- **Path-optional real data (`resolve_data`)** — normalizes a supplied CSV/JSON
  to `data.json` and derives `schema.txt` (fields, inferred types, row count) so
  the judge can check faithfulness against the *actual* fields; otherwise emits
  `SYNTHETIC` and the generator fabricates labeled illustrative data.
- **Vega-Lite default, escalate to Vega** — the `plan` brief justifies the
  grammar; `generate` writes exactly one spec file; `vega-embed` renders either.
  Data is inlined into the spec so both the headless compile and the file://
  browser render are hermetic (no CORS/fetch issues).
- **Interactive Playwright capture (`capture`)** — loads the chart in headless
  Chromium and captures three states (settled, hover/tooltip, brush/selection)
  as PNGs fed to the LLM judge as multimodal input. The generator exposes
  `window.__vegaView` / `window.__vegaReady` for the harness.
- **Skeptical judge with two hard gates (`score`)** — `faithfulness` and
  `honesty` are hard-gated at `hard_gate: 7`; `effectiveness` and `craft` sit at
  `pass_threshold: 6`. Per-criterion gating (not a weighted average) so a single
  hard-gate miss fails the iteration. Criteria are grounded in viz literature
  (Mackinlay expressiveness/effectiveness, Cleveland-McGill).
- **Snapshot + pick-best (`record`)** — every scored iteration is snapshotted to
  `iter-N/`; `best.html`/`best_score.txt` always track the highest score, so the
  best result survives even if the loop ends by exhausting `max_iterations`
  mid-cycle. Routing is a deterministic parse of the judge's written `VERDICT`,
  which is more robust than trusting a final stdout token. Declares
  `artifact_versioning: true` (MR-5).

## Files changed

- **Added** `scripts/little_loops/loops/vega-viz.yaml` (new built-in loop).

## Validation

- `ll-loop validate vega-viz` → valid (11 states; initial `init`; max 20
  iterations). The initial `required_inputs` advisory was resolved by adding
  `required_inputs: ["description"]`.
- `ll-loop diagnose-evaluators vega-viz` → "Insufficient history (0 runs,
  need 10)" — expected for a brand-new loop; revisit after real runs.
- MR-rule posture: per-run artifact isolation under `${context.run_dir}` (MR-3);
  per-iteration versioning declared (MR-5); LLM `score` state paired with two
  non-LLM gates (`validate` exit/output, `capture` output_contains) plus the
  deterministic `record` router; no LLM-judged state dead-ends on a non-yes
  verdict (MR-4) since all LLM states use unconditional `next:` and routing
  lives on shell states.

## Runtime dependencies

`node`/`npx` (present) reach `vega-cli` + `vega-lite` and
`@playwright/test`/Chromium. First run downloads the vega packages via
`npx -y`; for speed/offline use, pre-install:
`npm i -g vega-cli vega-lite && npx playwright install chromium`.

## How to run

```bash
ll-loop run vega-viz --input "Monthly active users by plan tier over the last year, highlight the Q3 churn dip"
# with real data:
ll-loop run vega-viz --input "Revenue by region" --context data_path=/abs/path/revenue.csv
```

## Follow-ups (not blocking)

- **Precise interaction targeting**: hover/brush use synthetic mouse input at
  computed canvas coordinates (best-effort), which is why interaction quality is
  absorbed by the soft `effectiveness` criterion rather than hard-gated. The
  generator already exposes `window.__vegaView`, so a future revision could
  drive named selection signals (`view.signal(...)`) deterministically.
- **Smoke run**: exercise the full `npx`/Playwright path end-to-end once to
  confirm tooling resolution in this environment.
- **Evaluator health**: run `ll-loop diagnose-evaluators vega-viz` after ≥10
  runs to confirm the score gate's verdict actually varies (Bernoulli variance
  ≥ 0.05).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-07T22:21:17 - `e479704c-8195-4021-8581-044520e59891.jsonl`
