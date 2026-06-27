---
id: FEAT-2343
title: Interactive component generator built-in FSM loop
type: feature
status: done
priority: P3
discovered_date: 2026-06-27
discovered_by: planning-discussion
completed_at: 2026-06-27 18:02:11+00:00
relates_to:
- ENH-1869
- FEAT-2269
labels:
- fsm-loop
- harness
- builtin-loop
- interactive
- data-viz
- oracle
decision_needed: false
confidence_score: 100
outcome_confidence: 88
score_complexity: 17
score_test_coverage: 14
score_ambiguity: 18
score_change_surface: 16
---

# FEAT-2343: Interactive component generator built-in FSM loop

## Summary

Ship a built-in `interactive-component-generator` FSM loop that turns a
natural-language brief (or a referenced data file) into a single self-contained
HTML file of **interactive** components. Where `html-website-generator` renders
one static page, this loop ideates *many* candidate interactive components,
ranks them, builds the best 3–5 in isolation, smoke-tests that each actually
works, then selects the best 1–3 and composes them into one `index.html`.

It is a **fan-out generator-evaluator**: a divergent ideation front end and a
best-of-N selection/compose back end wrapped around the existing per-artifact
generate→screenshot→score→refine oracle. Most of it is assembled from patterns
the repo already ships, so the new surface area is small.

## Current Behavior (before)

The harness covered static and single-artifact HTML well —
`html-website-generator` (one page), `html-anything` (one classified artifact),
`svg-image-generator`, `pixi-data-viz`, `vega-viz` — but every one produces a
*single* artifact from a *single* idea. None of them ideate a set of candidate
interactive components, build several, verify the interactions function, and
keep only the strongest. Producing an interactive data explorer or widget panel
was an unguided one-shot prompt with no functional verification that the slider
recomputes or the filter filters.

## Expected Behavior (delivered)

`interactive-component-generator` accepts a NL description or a file reference
via `input_key: description` and runs:

1. **profile** the input — characterize the data's affordances (quantitative,
   temporal, categorical, relational, hierarchical, geospatial, text) so the set
   of *possible* interactions is grounded in the data shape.
2. **ideate** 8–15 candidate components spanning data-viz idioms and widgets.
3. **rank** them with a cheap pre-build rubric and keep the best `n_build`
   (default 4), writing a poppable worklist and a per-component dynamic rubric.
4. **build each** candidate in its own subdir by delegating to
   `oracles/generator-evaluator` unchanged (generate → Playwright screenshot →
   rubric score → refine), also emitting a machine-readable interaction manifest.
5. **smoke-test each** — render under `file://`, assert no `pageerror` and
   meaningful content, and *dispatch* every manifest interaction so a broken
   handler throws and is caught.
6. **score & record** each to a scoreboard.
7. **select** the best `n_final` (default ≤3) by smoke-pass → rubric →
   complementarity.
8. **compose** the winners into one self-contained `index.html` using a
   configurable isolation strategy.
9. **re-verify** the merged file (composition breaks things), run an optional
   external-vision gate, and finish.

The loop passes `ll-loop validate` and the full `validate_fsm` rule set.

## Use Case

A user points the loop at a CSV of regional sales — "make this explorable" —
and gets back one HTML file containing, say, a year scrubber over a choropleth,
a sortable/filterable category table, and a what-if margin calculator: the three
that scored highest out of a dozen ideas, each verified to actually respond to
input, composed into one offline-openable page.

## Architecture note: this is a fan-out, NOT a thin wrapper

`html-website-generator` and `html-anything` are thin wrappers that delegate the
*whole* artifact to `oracles/generator-evaluator`. This loop cannot be a thin
wrapper because its value is in the fan-out/fan-in around the oracle:

- **Divergence + ranking** (`ideate`, `rank`) has no analog in the single-artifact
  wrappers — it produces a candidate *pool* and a worklist.
- **Per-item iteration** reuses the `harness-multi-item` worklist pattern: a
  `pop_next` (`fragment: shell_exit`) pops one id from `queue.txt` and routes to
  `check_any_built` when empty; `record` loops back. Each iteration's
  `build_component` delegates to `oracles/generator-evaluator` with that
  component's run_dir/prompt/rubric — the oracle is reused **unchanged** (zero
  blast radius on its six existing callers).
- **Fan-in** (`select_best`, `compose`, `verify_final`) is new: composite-rank
  the scoreboard, merge the winners, and re-test the combined file.

The reused `vision_gate` is the optional external-vision evaluator pattern from
`html-website-generator` (graceful no-op unless `VISION_*` env is configured).

## States (mapping)

| Phase | FSM State(s) | Mechanism |
|------|-----------|-----------|
| Setup | `init` | Shell: mkdir + capture absolute `run_dir` |
| Profile | `profile_input` | Prompt: read file if referenced; write `brief.md` (affordance inventory) |
| Ideate | `ideate` | Prompt: 8–15 candidates → `candidates.md` |
| Rank | `rank` | Prompt: pre-build rubric → top `n_build` → `queue.txt` + `rubric-<id>.md` |
| Worklist pop | `pop_next` | `fragment: shell_exit` — pop one id; empty → `check_any_built` |
| Build | `prep_component` + `build_component` | `loop: oracles/generator-evaluator` per component → `comp-<id>/index.html` + `manifest.json` |
| Smoke | `smoke_component` | Shell/Playwright: no `pageerror` + content + dispatch manifest interactions |
| Record | `record` | Shell: append smoke + min-rubric to `scoreboard.jsonl`; loop to `pop_next` |
| Guard | `check_any_built` | `fragment: shell_exit` — empty scoreboard → `diagnose` |
| Select | `select_best` | Prompt: composite-rank → best ≤`n_final` → `selection.md` + `winners.txt` |
| Compose | `compose` | Prompt: merge winners into one self-contained `index.html` |
| Re-verify | `verify_final` | Shell/Playwright: re-run interactions in the merged file; bounded recompose via `.compose_rounds` |
| Vision | `vision_gate` | Optional external-vision gate (advisory in v1); reused from `html-website-generator` |
| Terminals | `done` / `diagnose` / `failed` | Report paths / diagnose / explicit failure |

## Resolved design decisions

- **Smoke-test rigor** — light render + console-error gate (operator's call),
  *augmented* to also dispatch each component's declared interaction-manifest
  steps so a broken handler surfaces as a `pageerror`. Makes "works as advertised"
  real at ~zero added cost without full DOM-delta assertions.
- **Isolation strategy** — `compose_isolation` context knob (`iframe` | `shadow` |
  `scoped`), defaulting to **iframe `srcdoc`**. Because components are built
  independently (and may use heterogeneous libraries), structural isolation beats
  test-dependent isolation; `srcdoc` keeps the result a single self-contained file.
- **Build execution** — **sequential worklist** (idiomatic `harness-multi-item`
  pop-loop), not parallel `spawn`. Deterministic, simple to budget; 3–5 builds
  don't justify the orchestration cost of parallelism.
- **Self-containment vs. richness** — `allow_cdn` context knob, default `"false"`
  (vanilla JS/SVG/Canvas, offline). Matches the no-CDN house style of
  `html-website-generator`; set `"true"` for richer CDN libraries at the cost of
  needing network on open.
- **Two-stage scoring** — cheap pre-build rank to pick `n_build`, expensive
  post-build composite score (rubric + smoke + interaction-pass) to pick
  `n_final`. Keeps build budget off weak ideas.
- **Vision gate** — advisory in v1 (`on_no → done`); documented one-line change to
  `on_no → compose` to make it iterate (bounded by the existing `.compose_rounds`
  cap).

## Acceptance Criteria

- [x] Built-in `interactive-component-generator.yaml` accepts a NL description /
      file reference via `input_key` and runs ideate → rank → per-component
      build+smoke+score → select → compose → re-verify, passing `ll-loop validate`.
- [x] Per-component build delegates to `oracles/generator-evaluator` **unchanged**
      (no edits to the shared oracle or its other callers).
- [x] Fan-out uses the `harness-multi-item` worklist pattern (`pop_next` via
      `shell_exit`, `record` → `pop_next`, empty-queue guard).
- [x] `smoke_component` performs the render + console-error gate and dispatches
      the interaction manifest; `verify_final` re-runs interactions in the merged
      file with a bounded recompose loop.
- [x] Composition isolation is a context knob (`iframe` default); offline
      self-containment is the default (`allow_cdn: "false"`).
- [x] Per-run artifact isolation under `${context.run_dir}/` (MR-3); all
      LLM-judged states have complete routing (MR-4); no bare `PASS` sentinels.
- [x] Registered as a built-in: catalog rows, root README count, and the
      `test_expected_loops_exist` set; a structural test class added.

## Integration Map

### Files Created
- `scripts/little_loops/loops/interactive-component-generator.yaml` — the loop (primary deliverable).
- `.issues/features/P3-FEAT-2343-interactive-component-generator-builtin-fsm-loop.md` — this issue.

### Files Modified
- `scripts/little_loops/loops/README.md` — `interactive-component-generator` row under `## Harness / Templates`.
- `README.md` (root) — FSM loop count `94` → `95` (both pass `is_runnable_loop()`; `ll-verify-docs` enforces the count).
- `docs/guides/LOOPS_REFERENCE.md` — row in `### Harness Examples` table and addition to the GAN-architecture attribution sentence.
- `scripts/tests/test_builtin_loops.py` — added `"interactive-component-generator"` to `TestBuiltinLoopFiles.test_expected_loops_exist` (exact-set assertion), and added `TestInteractiveComponentGeneratorLoop` (structural assertions following `TestSvgImageGeneratorLoop`).

### Reused Unchanged
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — per-component build sub-loop.
- `scripts/little_loops/loops/lib/common.yaml` — `shell_exit` fragment for the worklist gates.
- `html-website-generator.yaml` `vision_gate` — optional external-vision pattern.

## Verification

- `little_loops.fsm.validation.load_and_validate` + `validate_fsm` → **0 issues**
  (all meta-loop rules MR-1…MR-6, multimodal-blind-spot, partial-route dead-end,
  artifact-overwrite, generator-fix-discipline).
- Reachability/reference check → 17 states, initial reachable, no unreachable
  states, `oracles/generator-evaluator` sub-loop resolves, terminals `done`/`failed`.
- `node --check` on both embedded Playwright scripts (`smoke_component`,
  `verify_final`) → valid.
- `ll-verify-docs` loops count consistent after the README bump (runnable-loop
  count = 95).

## Impact

- **Effort**: Medium — the loop YAML plus catalog/test registration; the
  per-component build, screenshot, score, refine, and vision machinery are reused.
- **Risk**: Low — additive loop; the shared oracle and its other callers are
  untouched.
- **Breaking change**: No.

## Follow-ups (optional, not blocking)

- Wire `vision_gate` `on_no → compose` to let final aesthetic critique drive a
  bounded recompose.
- Add a `docs/reference/loops.md` section and a golden-input smoke under
  `ll-loop test` for an end-to-end (non-structural) check.
- Parallel build mode via `on_handoff: spawn` if wall-clock on 5 builds matters.

## Status

**Done** | Created: 2026-06-27 | Completed: 2026-06-27 | Priority: P3
