---
id: FEAT-2817
type: FEAT
priority: P3
status: open
captured_at: "2026-07-25T00:00:00Z"
discovered_date: 2026-07-25
discovered_by: capture-issue
---

# FEAT-2817: Built-in FLUX Image Generator-Evaluator Loop

## Summary

Add a new built-in FSM loop (`scripts/little_loops/loops/flux-image-generator.yaml`) that applies the
generator-evaluator pattern to raster image generation: a state POSTs a prompt to a self-hosted FLUX
image API (`${IMAGE_BASE_URL}/generate`), decodes the returned base64 payload to a PNG under the run
dir, an LLM vision rubric scores the PNG, and the loop routes back to regenerate with the critique
until all criteria pass or `max_iterations` is hit.

## Current Behavior

The built-in loop catalog has five generator-evaluator loops that produce visual artifacts —
`svg-image-generator.yaml`, `rlhf-svg-evaluate.yaml`, `interactive-component-generator.yaml`,
`openscad-model-generator.yaml`, `html-website-generator.yaml` — and each evaluates its artifact by
rendering/screenshotting it and scoring the screenshot with the `VISION_BASE_URL` / `VISION_MODEL` /
`VISION_API_KEY` vision gate (see `svg-image-generator.yaml`'s `vision_gate` state).

Every one of these generates the artifact *as code* (SVG markup, HTML, OpenSCAD) via the LLM. There is
no loop that generates a **raster image from a diffusion model API**, so prompt-quality iteration for
text-to-image work has no harness — the prompt-refinement cycle is entirely manual.

`IMAGE_BASE_URL` is not yet a recognized env var anywhere in the repo (`.env` currently declares only
`VISION_BASE_URL`, `VISION_MODEL`, `VISION_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`).

## Expected Behavior

`ll-loop run flux-image-generator --input "a clean vector illustration of a server rack, diagram style"`
runs a closed generate → save → score → regenerate cycle:

1. **generate** — POST the current prompt to the FLUX endpoint:
   ```bash
   curl -sS -X POST "$${IMAGE_BASE_URL}/generate" \
     -H "Content-Type: application/json" \
     -d '{"prompt":"...","seed":123,"steps":4}'
   ```
   Response shape:
   ```json
   {"image_b64":"...","width":1024,"height":1024,"seed":123,"steps":4,"time_seconds":38.5}
   ```
2. **save** — base64-decode `image_b64` into a per-iteration PNG under `${captured.run_dir.output}/`
   (e.g. `image-iter-<n>.png`), never a flat overwritten path (MR-5 / artifact versioning).
3. **score** — send the PNG to the vision model via `VISION_BASE_URL` / `VISION_MODEL` /
   `VISION_API_KEY` using the same inline-Python request shape as `svg-image-generator.yaml`'s
   `vision_gate`, with a rubric scoring 1–10 per criterion and emitting one JSON object.
4. **route** — all criteria ≥ threshold → `done`; otherwise write a critique to
   `${captured.run_dir.output}/critique.md`, refine the prompt from the failing criteria, and loop
   back to **generate** with a new seed until `max_iterations`.

Graceful degradation matches the existing loops: missing `IMAGE_BASE_URL` fails the run with a clear
message (it is the loop's core dependency); missing `VISION_*` vars skip the gate with a pass and a
`skipped (VISION_* env not configured)` note rather than hard-failing.

## Motivation

Text-to-image prompt engineering is exactly the loop-shaped workload the FSM engine exists for —
generate, score against a rubric, feed the critique back — but it is the one visual-artifact modality
the built-in catalog does not cover. It also exercises a genuinely different generator substrate
(an HTTP diffusion endpoint rather than an LLM emitting code), which validates that the
generator-evaluator oracle isn't implicitly coupled to code-producing generators.

## Use Case

A user wants a diagram-style illustration for the docs. They run
`ll-loop run flux-image-generator --input "a clean vector illustration of a server rack, diagram style"`.
Iteration 1 renders a photorealistic rack — the vision rubric scores *style adherence* 3/10 and writes
a critique. The loop rewrites the prompt to emphasize flat vector styling, re-generates with a new
seed, scores 8/10 across all criteria, and exits `done` with the PNG and the full iteration history
under the run dir. The user gets a usable image without hand-tuning prompt phrasing across a dozen
manual curl calls.

## Impact

- **Scope**: additive — one new loop YAML plus one new env var. No existing loop, CLI, or Python module
  changes behavior.
- **Risk**: low. The loop is opt-in; the only shared surface touched is the built-in loop catalog and
  its test file.
- **Dependency**: requires a reachable self-hosted FLUX endpoint, so the test coverage must not assume
  network access — gate live-endpoint tests on `IMAGE_BASE_URL` being set and skip otherwise, matching
  how the `VISION_*` gates degrade.

## Proposed Solution

Model the loop on `scripts/little_loops/loops/svg-image-generator.yaml` (274 lines), which already
establishes the full shape: `init` → `plan` → `run_gen_eval` (delegating to
`oracles/generator-evaluator.yaml`) → `vision_gate` → `done`, with `diagnose` / `failed` terminals.

Key differences from the SVG loop:

- **Generator is a `shell` state, not an LLM state.** The LLM's role shrinks to *prompt authoring and
  refinement*; image synthesis is the curl POST. This inverts the usual split and means the
  non-LLM evaluator requirement (MR-1) is naturally satisfiable: the shell generate/save states give
  `exit_code` evaluators (HTTP failure, empty `image_b64`, undecodable base64, zero-byte PNG) in the
  routing chain alongside the LLM rubric.
- **Vision scoring is the primary evaluator, not an optional gate.** Unlike the SVG loop where the
  vision gate is a bolt-on over an LLM self-score of the markup, here there is no artifact text to
  self-score — the PNG is the only thing to judge. Decide whether the vision call still degrades to a
  pass when `VISION_*` is unset (consistent with existing loops) or whether an unconfigured vision
  model should short-circuit to a single-shot generate. Recommend: degrade to pass, single iteration,
  with an explicit log line.
- **Seed handling.** Vary the seed per iteration so a re-generate after critique isn't a no-op
  re-render of the same latent; record the seed alongside each PNG so a good result is reproducible.

Escaping rules that apply (from `.claude/CLAUDE.md` § Loop Authoring): bash `${VAR}` inside FSM shell
actions must be written `$${VAR}` (MR-7 / MR-9 — single `$` for command substitution and bare vars,
`$$` only for the brace form); the user-supplied `${context.input}` prompt must land in a safe
position (single-quoted string or quoted heredoc) before reaching bash, and must be JSON-escaped
before it reaches the curl `-d` payload (MR-11).

## Implementation Steps

1. Add `IMAGE_BASE_URL` to `.env` / `.env.example` and document it alongside the `VISION_*` vars.
2. Author `scripts/little_loops/loops/flux-image-generator.yaml` following the
   `svg-image-generator.yaml` skeleton, substituting the shell generate + base64-decode states for the
   LLM SVG-authoring state.
3. Build the request body with Python `json.dumps` (not shell string interpolation) so arbitrary
   prompt text can't break the JSON or the shell tokenizer.
4. Write the rubric for raster output — prompt adherence, subject clarity, composition, artifact/
   distortion freedom — rather than the SVG rubric's markup-oriented criteria.
5. Wire per-iteration artifact paths under `${context.run_dir}` / `${captured.run_dir.output}` and set
   `artifact_versioning: true` (MR-5).
6. Register the loop wherever the built-in catalog is enumerated, and add coverage to
   `scripts/tests/test_builtin_loops.py`.
7. Run `ll-loop validate flux-image-generator` and confirm zero MR-* violations.

## Acceptance Criteria

- [ ] `ll-loop validate flux-image-generator` exits 0 with no MR-1/MR-5/MR-7/MR-9/MR-11 violations.
- [ ] `ll-loop run flux-image-generator --input "<prompt>"` produces at least one PNG under the run
      dir and a `critique.md` when scoring fails.
- [ ] Each iteration writes a distinct, non-overwriting PNG path with its seed recorded.
- [ ] HTTP failure, empty/undecodable `image_b64`, or a zero-byte PNG routes to a failure/diagnose
      state rather than being scored as a pass.
- [ ] A prompt containing shell metacharacters (`"`, `$`, backtick, `!`) generates correctly and does
      not inject or break tokenizing.
- [ ] Unset `VISION_*` degrades with a logged skip instead of a hard failure; unset `IMAGE_BASE_URL`
      fails with an actionable message.
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes with the new loop registered.

## Open Questions

- Should `seed` / `steps` be exposed as loop context variables with defaults (`steps: 4`), or hardcoded?
  Recommend context vars with defaults.
- Should the loop keep every iteration's PNG, or prune to the best-scoring one at `done`? Recommend
  keep-all (cheap, and the progression is the useful artifact).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/svg-image-generator.yaml` | Closest existing loop; source of the vision-gate shape |
| `scripts/little_loops/loops/oracles/generator-evaluator.yaml` | The generator-evaluator sub-loop to delegate to |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-* rule rationale and canonical loop shape |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1/5/7/9/11 escaping and artifact-isolation rules |

## Session Log
- `/ll:capture-issue` - 2026-07-25

---

## Status

open
