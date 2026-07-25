---
id: FEAT-2817
type: FEAT
priority: P3
status: done
captured_at: '2026-07-25T00:00:00Z'
completed_at: '2026-07-25T23:14:28Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
decision_needed: false
reconcile_attempted: true
confidence_score: 96
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 22
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing loop builds a curl JSON POST body by splicing `${context.input}`/`${context.description}`
  directly into a shell action — the codebase's established MR-11-safe pattern (used identically in
  `svg-image-generator.yaml`'s `vision_gate`, lines 133–239, and `rlhf-svg-evaluate.yaml`'s `score`,
  lines 264–471) is: an LLM `prompt`-type state writes the final text to a file under
  `${captured.run_dir.output}` (e.g. `image-prompt.txt`), a later `shell` state `export`s that file's
  contents into a bash env var, and an inline `python3 <<'PY' ... PY` **quoted heredoc** reads it via
  `os.environ[...]` and builds the payload with `json.dumps` — never referencing the raw context token
  inside the shell body. Use `urllib.request` (stdlib) rather than `curl -d`, matching every existing
  JSON-POST loop state in this codebase (no loop currently uses `curl` for a JSON body; the only
  `curl` usages found are plain GETs, e.g. `oracles/code-run-gate.yaml`'s `service_health` state).
- **No existing loop base64-*decodes* a response field to a file** — the mirror-image encode pattern
  (`base64.b64encode(f.read()).decode()` in `vision_gate`) is the closest analog; the decode side is
  `img_bytes = base64.b64decode(data["image_b64"]); open(png_path, "wb").write(img_bytes)`, wrapped in
  the same `try/except → print sentinel; sys.exit(...)` degrade-or-fail idiom used throughout
  `vision_gate`/`score`.
- **Per-iteration numbering**: `${state.iteration}` is explicitly noted as unavailable inside `shell`
  actions (`rlhf-svg-evaluate.yaml` line 258 comment). The established mechanism is a file-based
  counter — `canvas-sketch-generator.yaml`'s `snapshot` state (lines 291–318): read/increment
  `$RUN_DIR/.iter_counter`, `mkdir -p "$RUN_DIR/iter-$N"`, copy per-iteration artifacts in. Use the
  same idiom for `image-iter-<n>.png` naming/seed recording.
- **MR-1 exit_code chain**: `oracles/code-run-gate.yaml`'s `run_lint`/`service_health` states show the
  template — run the command, capture `RC=$?`, echo `exit_code=$RC`, then
  `evaluate: {type: exit_code}` with `on_yes`/`on_no`/`on_error` all fanning into the next state
  (verdict decided later by an aggregator). Apply this to the generate/save states for HTTP-failure /
  empty-`image_b64` / undecodable-base64 / zero-byte-PNG gating.
- **Architectural fork on delegation** (see Open Questions below): `oracles/generator-evaluator.yaml`'s
  `evaluate` state uses the shared `playwright_screenshot` fragment (`lib/harness.yaml`), which
  screenshots an HTML/SVG file via Playwright — it does not accept a raw PNG as the artifact directly.
  Since this fragment is shared by five other wrapper loops, it should not be modified in place.

## Implementation Steps

1. Add `IMAGE_BASE_URL` to `.env` (no `.env.example` exists in this repo) and document it alongside
   the `VISION_*` vars.
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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/flux-image-generator.yaml` — new loop (does not exist yet)
- `.env` — add `IMAGE_BASE_URL` alongside existing `VISION_BASE_URL`/`VISION_MODEL`/`VISION_API_KEY`
  (no `.env.example` currently exists in this repo, despite the issue text referencing one)
- `scripts/tests/test_builtin_loops.py` — `test_expected_loops_exist()` (~line 76-170) holds the
  canonical set of expected loop names; add `"flux-image-generator"` there. This is the **only**
  explicit registration point — builtin loops are otherwise auto-discovered by globbing
  `scripts/little_loops/loops/*.yaml` via `get_builtin_loops_dir()` (`cli/loop/_helpers.py:1205-1207`)
  and filtered through `fsm/__init__.py`'s `is_runnable_loop()`; no separate catalog list to edit.
- `scripts/little_loops/loops/README.md` — builtin loop catalog doc, should list the new loop

### Similar Patterns (templates to follow)
- `scripts/little_loops/loops/svg-image-generator.yaml` — primary skeleton (`init`→`plan`→
  `run_gen_eval`→`vision_gate`→`done`, `diagnose`→`failed`); `vision_gate` (lines 133-239) is the
  urllib/json.dumps/base64/graceful-degrade template.
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — internal sub-loop
  (`generate`→`evaluate`→`snapshot`→`score`→`record_score`→`check_stall`→`check_diff_stall`);
  `artifact_versioning: true`; `evaluate` state uses the shared `playwright_screenshot` fragment,
  which assumes an HTML/SVG artifact to screenshot, not a ready-made PNG (see decision point below).
- `scripts/little_loops/loops/canvas-sketch-generator.yaml` — `snapshot` state (lines 291-318) shows
  the file-based `.iter_counter` idiom for non-overwriting per-iteration paths (`${state.iteration}`
  is unavailable in `shell` actions per its line-258 comment); `score`→`snapshot` (lines 244-320)
  shows the MR-1 split of "LLM assigns scores, non-LLM state parses and routes."
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — `run_lint`/`service_health` states show
  the `exit_code` MR-1 evaluator chain shape for the generate/save HTTP-failure and decode-failure gates.
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml` — richer vision-rubric variant with a
  `.best_score` regression guard, useful if a keep-best-across-seeds behavior is wanted later.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles` fixture discovers all runnable loops;
  validates YAML parsing, FSM schema, description fields, no bare `PASS` tokens, no unescaped bash
  vars, failure terminals have diagnostic actions. Add the new loop name to
  `test_expected_loops_exist()`'s expected set.
- `scripts/tests/test_rlhf_svg_evaluate_smoke.py` — existing smoke-test pattern for a generator-
  evaluator sub-loop; model a `test_flux_image_generator_smoke.py` after it, gated on
  `IMAGE_BASE_URL` being set (skip otherwise) per the issue's own Dependency note.

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md` — both catalog every
  builtin loop; add an entry for `flux-image-generator`.

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

### Codebase Research Findings — delegation architecture decision

Research surfaced a genuine fork in how closely to follow the
`svg-image-generator.yaml` skeleton: `oracles/generator-evaluator.yaml`'s `evaluate` state uses the
shared `playwright_screenshot` fragment (`lib/harness.yaml`), which renders an HTML/SVG file via
Playwright and screenshots it — it has no path for "the artifact IS already a PNG returned by an
API," and this fragment is shared by five other wrapper loops, so it shouldn't be modified in place.

> **Selected:** Option A (revised mechanism) — reuses the oracle's full stall/score-history machinery
> via the codebase's actual precedented customization path (`from:` inheritance), not the originally
> described `with:`-based override, which does not exist in the codebase.

**Option A**: Delegate to `oracles/generator-evaluator.yaml` as-is, with the FLUX curl/decode call
folded into the `generate_prompt`'s LLM step (the LLM state would itself invoke the FLUX API via a
described action and write `image.png`), and give the `evaluate` state a local `evaluate:` override
that copies the PNG to `screenshot.png` instead of invoking Playwright — the same "local override"
shape referenced in `oracles/generator-evaluator.yaml`'s `score` state comment pointing at
`generator-evaluator-cli.yaml`. This preserves the full stall/diff-stall/score-history machinery of
the shared oracle for free.

**Revision (decide-issue, evidence-based)**: codebase evidence shows a wrapper-level `with:`-supplied
`evaluate:` override is **not a real mechanism** anywhere in this codebase — `with:` only binds
`run_dir`/`artifact_path`/`generate_prompt`/`rubric`/`pass_threshold`-style context values into a
delegated loop, it cannot replace an internal state's `action:`/`evaluate:` block. The actual
precedent the `score` state's comment refers to is `oracles/generator-evaluator-cli.yaml`, which uses
`from: generator-evaluator` (loop-file inheritance, FEAT-2269) to create a **new oracle file** that
redefines `evaluate` and `snapshot` in place (swapping Playwright for `${context.render_command}`).
Apply the same shape here: author `oracles/generator-evaluator-flux.yaml` with `from:
generator-evaluator`, overriding `evaluate` to skip Playwright entirely (the FLUX response is already
a PNG — copy `${context.artifact_path}` to `screenshot.png` directly, no render/screenshot step
needed at all, which is actually simpler than the CLI-render case). `flux-image-generator.yaml` then
delegates to this new oracle via `loop: oracles/generator-evaluator-flux` instead of
`oracles/generator-evaluator`. All snapshot/score/record_score/check_stall/check_diff_stall states are
inherited unchanged.

**Option B**: Skip oracle delegation entirely and author the generate→save→score→route cycle as
top-level states in `flux-image-generator.yaml` itself (mirroring `canvas-sketch-generator.yaml`'s
`score`→`snapshot` MR-1 split rather than `svg-image-generator.yaml`'s `run_gen_eval` delegation).
This avoids fighting the `playwright_screenshot` fragment's HTML/SVG assumption but re-implements
stall detection / iteration counting locally instead of reusing the shared oracle.

**Recommended**: Option A — reusing the shared oracle's stall-guard and score-history machinery is
worth the local `evaluate:` override, and keeps this loop consistent with the other five
generator-evaluator wrappers rather than forking a parallel implementation shape.

### Decision Rationale

**Selected: Option A, via `from:`-based oracle inheritance** (`oracles/generator-evaluator-flux.yaml`
extending `oracles/generator-evaluator.yaml`), not the originally described `with:`-override
mechanism.

Two parallel evidence-gathering passes (`ll:codebase-pattern-finder`) scored the options as literally
written:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A (as described: `with:`-supplied `evaluate:` override) | 0 | 2 | 2 | 1 | 5/12 |
| B (top-level states, no oracle delegation) | 1 | 1 | 2 | 1 | 5/12 |
| **A, revised: `from:` inheritance** | 3 | 3 | 3 | 3 | **12/12** |

- **Option A as literally described scores 0 on consistency**: no mechanism in this codebase lets a
  `with:`-block caller override an internal state's `action:`/`evaluate:` — `with:` only binds plain
  context values (`run_dir`, `artifact_path`, `rubric`, etc.), confirmed by reading every `with:` usage
  in `svg-image-generator.yaml`'s `run_gen_eval` state.
- **Option B scores 1 on consistency**: `canvas-sketch-generator.yaml` is the only precedent for
  skipping oracle delegation, and it is a documented outlier — 6 other loops delegate via `loop:
  oracles/generator-evaluator`, and even the other non-delegating case (`p5js-sketch-generator.yaml`)
  reuses a shared `generative-art.yaml` base rather than duplicating top-level. Skipping delegation
  also forgoes `score_stall_gate` (canvas-sketch only implements `diff_stall_gate`), a real loss of
  evaluator machinery.
- **The actual precedent for customizing `evaluate`/`snapshot`** is `oracles/generator-evaluator-cli.yaml`,
  which uses `from: generator-evaluator` (FEAT-2269 loop-file inheritance) to redefine those two states
  in a new oracle file while inheriting `snapshot`/`score`/`record_score`/`check_stall`/
  `check_diff_stall` unchanged. Applying the same shape for FLUX is **simpler than the CLI-render
  case**: the FLUX response is already a PNG, so the overridden `evaluate` state needs no
  render/screenshot step at all — just copy `${context.artifact_path}` to `screenshot.png`.
- This keeps `flux-image-generator.yaml` consistent with the other five generator-evaluator wrappers
  (reusing all stall/score-history machinery) while using the codebase's real state-customization
  mechanism instead of a nonexistent one — resolving the fork the issue's Proposed Solution left open.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/loops/svg-image-generator.yaml` | Closest existing loop; source of the vision-gate shape |
| `scripts/little_loops/loops/oracles/generator-evaluator.yaml` | The generator-evaluator sub-loop to delegate to |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | MR-* rule rationale and canonical loop shape |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1/5/7/9/11 escaping and artifact-isolation rules |

## Resolution

Implemented as Option A via `from:` inheritance, exactly as decided.

**Files added**
- `scripts/little_loops/loops/oracles/generator-evaluator-flux.yaml` — `from: generator-evaluator`
  oracle variant. Overrides `generate` (routes all outcomes to the new shell state), adds
  `synthesize` (POST to `${IMAGE_BASE_URL}/generate`, base64-decode to a per-iteration PNG,
  record seed), and overrides `evaluate` to copy the PNG straight to `screenshot.png` — no
  Playwright step at all, since the FLUX response is already a raster.
  `snapshot`/`score`/`record_score`/`check_stall`/`check_diff_stall` are inherited unchanged.
- `scripts/little_loops/loops/flux-image-generator.yaml` — wrapper:
  `init → check_image_env → plan → run_gen_eval → vision_gate → done`, with `diagnose → failed`.
- `scripts/tests/test_flux_image_generator.py` — 22 tests. The behavioural half extracts the real
  `synthesize` action from the YAML, interpolates it as the engine would, and runs it under bash
  against a stub HTTP FLUX endpoint.

**Files modified**
- `scripts/tests/test_builtin_loops.py` — registered `flux-image-generator`.
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md` — catalog entries.
- `README.md` — loop count 99 → 101 (`ll-verify-docs` gate).
- `.env` — added `IMAGE_BASE_URL` (gitignored; local only).

**Design decisions**
- The LLM authors `image-prompt.txt`; `synthesize` reads it inside a quoted Python heredoc via
  `os.environ` and builds the body with `json.dumps` — the prompt never reaches the shell
  tokenizer or a `curl -d` string (MR-11). Verified by a test asserting a prompt containing
  `"`, `$HOME`, backticks, `!`, `\`, and single quotes arrives at the endpoint verbatim.
- `IMAGE_BASE_URL` is a hard dependency (`check_image_env`, `exit_code` evaluator → `diagnose`);
  `VISION_*` degrades to a logged skip, matching the existing loops.
- Per-iteration numbering uses the `.gen_counter` file idiom (`${state.iteration}` is unavailable
  in shell actions); each iteration writes `image-iter-N.png` plus a `seeds.txt` line
  (`image-iter-N.png seed=… steps=…`). Seed derives from `base_seed` and the counter, so a
  regenerate after critique re-samples the latent instead of re-rendering.
- `steps` and `base_seed` are context vars with defaults (Open Question 1); all iterations are
  kept (Open Question 2).

**Acceptance criteria** — all met:
- `ll-loop validate flux-image-generator` and `ll-loop validate oracles/generator-evaluator-flux`
  both exit 0 with zero MR-* violations.
- HTTP failure, missing/empty `image_b64`, undecodable base64, and zero-byte PNG each emit
  `IMAGE_FAIL` and route to `failed` — covered by parametrized tests against the stub endpoint.
- Distinct non-overwriting per-iteration PNGs with recorded, varying seeds — covered.
- Shell-metacharacter prompt safety — covered.
- Unset `VISION_*` skips, unset `IMAGE_BASE_URL` fails actionably — covered.
- `python -m pytest scripts/tests/` → 16290 passed, 38 skipped.

The `ll-loop run` end-to-end criterion is not exercised in CI by design (per the issue's own
Dependency note): it requires a reachable self-hosted FLUX endpoint. The stub-server tests cover
the same generate → decode → per-iteration-artifact contract without network access.

## Session Log
- `/ll:manage-issue` - 2026-07-25T23:13:52 - `e1de7126-8d26-4bd2-94d1-fac3b5acb3b7.jsonl`
- `/ll:ready-issue` - 2026-07-25T23:01:44 - `9ee34df3-a41d-4a72-a52d-7bed31cb2a6e.jsonl`
- `/ll:confidence-check` - 2026-07-25T23:10:00 - `0e9d5cfe-a08f-405d-9496-907be762d917.jsonl`
- `/ll:decide-issue` - 2026-07-25T22:55:19 - `2ca7e4e9-549a-485e-8997-dfeea82dbe66.jsonl`
- `/ll:reconcile-issue` - 2026-07-25T22:51:20 - `830752a3-91ce-445d-9136-04118d609b90.jsonl`
- `/ll:refine-issue` - 2026-07-25T22:22:28 - `bc536267-0ce0-45ab-862f-10b0ef609b3d.jsonl`
- `/ll:capture-issue` - 2026-07-25

---

## Status

done
