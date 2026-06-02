---
id: FEAT-1807
title: Adversarial-Redesign Figure Loop with AutoFigure
type: feature
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-05-30T05:25:35Z'
completed_at: '2026-05-31T05:50:52Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
labels:
- feat
- captured
- example-loop
- demo
- autofigure
confidence_score: 85
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1807: Adversarial-Redesign Figure Loop with AutoFigure

## Summary

Add an example FSM loop, `adversarial-redesign`, that demonstrates the
**generator-vs-critic** pattern using [AutoFigure](https://github.com/ResearAI/AutoFigure)
as the artifact generator. A generator agent produces an SVG diagram from a
text concept; a critic agent returns structured complaints; the loop regenerates
addressing each complaint and exits on score-improvement-stall or SVG-diff
convergence. Every round is recorded so the back-and-forth itself is the demo.

The killer demo property: the *transcript* of generator/critic exchange is as
interesting as the final diagram. It plays well as a split-screen recording —
critic complaints scrolling on the left, the SVG morphing on the right.

## Current Behavior

The `loops/` directory ships several example loops that demonstrate eval-driven
refinement on text/code artifacts (e.g. `examples-miner.yaml`,
`eval-driven-development.yaml`), but none produce a **visual artifact** as
output. There is also no example of the explicit
*generator-vs-critic* pattern where two agents trade structured critique across
rounds, with both the per-round diff and the critique transcript surfaced for
inspection.

This leaves a gap in the demo reel: every loop we can show today produces
text/code, which is less visually compelling than watching a diagram morph
in response to critique.

## Expected Behavior

A new example loop file `loops/examples/adversarial-redesign.yaml` (or wherever
example loops live per project conventions) that:

1. Takes a `concept` input (any natural-language description).
2. Seeds an initial SVG via an AutoFigure wrapper.
3. Runs a critic agent that returns structured JSON complaints
   (`{complaints: [...], structural_score: int}`).
4. Gates progress on **two** signals (per project loop authoring rules):
   - **Non-LLM**: AutoFigure's own `final_score` must rise each round
     (`output_numeric` evaluator); bail on stall.
   - **LLM-semantic**: critic must produce zero new structural complaints.
5. Regenerates the figure addressing every complaint.
6. Exits on SVG diff < ε for 2 consecutive rounds (`check_convergence`)
   OR max_iterations reached.
7. Persists every iteration's SVG + critic transcript under
   `.loops/runs/<run_id>/iter-N/` so the full back-and-forth is replayable
   for demo recording.

## Motivation

- **Demo gap**: today's example loops produce text/code; no loop produces a
  visual artifact that morphs across iterations. Visual artifacts are
  meaningfully more compelling for showing FSM mechanics to new users in a
  short video or slide.
- **Pattern coverage**: the explicit generator-vs-critic shape (two adversarial
  agents, structured complaint protocol) is not represented in existing
  examples. It is a common pattern worth a reference implementation.
- **CLI-Anything onramp**: AutoFigure is a strong proof point that
  ll-loops can wrap *any* CLI-Anything-style creative generator. Shipping a
  polished example reduces friction for users who want to harness other
  generators (Inkscape, Manim, image models, etc.).

## Use Case

A user wants to demo the FSM-loop concept to a teammate in under a minute.
They run:

```bash
ll-loop run adversarial-redesign --input concept="how a transformer attends"
```

They watch the terminal stream `iter-1 → critic flagged 4 issues → iter-2 →
score 6.2 → 7.8 → critic flagged 1 issue → iter-3 → converged`. Afterwards,
`.loops/runs/<id>/` contains `iter-1.svg` through `iter-3.svg` plus a
`transcript.md` interleaving each critic complaint with the regeneration
prompt it produced. The user opens the SVGs side-by-side and the morph is
self-evidently the FSM doing useful work — no explanation needed.

## Acceptance Criteria

- [ ] `loops/examples/adversarial-redesign.yaml` exists and passes
      `ll-loop validate` (no MR-1 violations — the `check_semantic` critic
      MUST be paired with at least one of `output_numeric` /
      `check_convergence` / `exit_code`).
- [ ] A thin wrapper script (e.g. `scripts/autofigure_wrapper.py`) returns
      `{svg_path, final_score, iteration}` as JSON on stdout for one
      AutoFigure generation call, enabling `output_numeric` evaluators
      to read `.final_score` deterministically.
- [ ] `ll-loop run adversarial-redesign --input concept="<any text>"`
      completes successfully end-to-end on a developer machine with
      AutoFigure installed and an OpenRouter (or compatible) API key
      configured via env var.
- [ ] Every iteration writes:
      - `iter-N.svg` (the generated diagram)
      - `iter-N-critique.json` (structured critic output)
      - to a run-scoped directory under `.loops/runs/<run_id>/`.
- [ ] A `transcript.md` is written at run end that interleaves each
      iteration's critique with the regeneration prompt it produced.
- [ ] Loop exits on EITHER: (a) AutoFigure `final_score` failing to
      improve for 2 consecutive rounds, (b) SVG diff < ε for 2
      consecutive rounds, (c) max_iterations (default 5).
- [ ] README or example index lists the new loop with a one-line
      pitch and an example invocation.
- [ ] Loop is documented as requiring AutoFigure as an optional dependency
      (not installed by default — separate `pip install` step documented
      in the loop's preamble comment).

## API/Interface

```yaml
# loops/examples/adversarial-redesign.yaml (sketch)
name: adversarial-redesign
description: Generator-vs-critic figure refinement demo using AutoFigure
inputs:
  concept: { type: string, required: true }
  max_iterations: { type: int, default: 5 }

states:
  seed:
    action: shell
    cmd: python scripts/autofigure_wrapper.py --concept "${inputs.concept}"
    capture: seed
    next: critic

  critic:
    action: llm_structured
    schema: { complaints: list[str], structural_score: int }
    prompt_ref: prompts/adversarial-critic.md
    next: score_floor

  score_floor:
    action: check_numeric
    expr: "${captured.regen.final_score} > ${captured.previous.final_score}"
    on_yes: regen
    on_no: exit

  regen:
    action: shell
    cmd: python scripts/autofigure_wrapper.py --concept "${inputs.concept}"
                                              --critique "${captured.critic.complaints}"
    capture: regen
    next: convergence

  convergence:
    action: check_convergence
    field: regen.svg_path
    rounds: 2
    on_converged: exit
    on_diverged: critic
```

```python
# scripts/autofigure_wrapper.py (sketch)
# usage: python autofigure_wrapper.py --concept "..." [--critique "..."]
# emits: {"svg_path": "...", "final_score": 8, "iteration": 1}
```

## Proposed Solution

1. **Add wrapper script** `scripts/autofigure_wrapper.py` that calls
   `AutoFigureAgent.generate(...)` and prints a single JSON line to stdout.
   Critique input becomes a constraint suffix on the AutoFigure description.
2. **Author the loop YAML** using the standard 5-phase shape but with the
   explicit critic state surfaced by name (rather than baked into a
   monolithic `do_work` prompt) so the FSM diagram visibly shows the
   adversarial round-trip.
3. **Author the critic prompt** in `prompts/adversarial-critic.md` —
   should produce structured complaints (not freeform), e.g.
   `{node_unlabeled: [...], edge_direction_ambiguous: [...], layout_overlap: bool}`.
4. **Wire per-iteration artifact persistence** via the loop's existing
   `capture:` mechanism + a small `do_work` end-state that materializes
   `transcript.md`.
5. **Document the optional AutoFigure dependency** in the loop's preamble
   comment (`pip install -e ./AutoFigure` + `playwright install chromium`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing visual loops exist**: `svg-image-generator.yaml` and
  `p5js-sketch-generator.yaml` in `scripts/little_loops/loops/` already
  implement the visual-artifact-generation pattern (init → generate → evaluate →
  score). These are the primary patterns to model after, not examples-miner.
- **`prompt_ref` does not exist**: No current loop YAML uses a `prompt_ref`
  field. The critic prompt must be inline in the YAML (as `action: |
  <prompt text>`) or referenced via a `${context.prompt_file}` variable.
  The API sketch in this issue uses `prompt_ref:` which would need to be
  implemented as a new FSM feature or replaced with inline prompts.
- **`llm_structured` is an evaluator, not an action type**: The API sketch
  uses `action: llm_structured` on the critic state, but `llm_structured` is
  only valid as an `evaluate.type`. The correct pattern is `action_type: prompt`
  for the critic to produce structured JSON output, then `evaluate: type: llm_structured`
  on a separate gating state. See `harness-single-shot.yaml:check_semantic` (line 113)
  for the canonical `llm_structured` evaluator pattern.
- **Convergence routing requires `route:` table**: The `convergence` evaluator
  produces verdicts `target`, `progress`, `stall`, `error` — not `converged`/`diverged`.
  These must be routed via a `route:` block (not `on_converged:`/`on_diverged:`).
  See `harness-optimize.yaml:gate` (line 178) for the canonical pattern.
- **MR-1 does NOT apply to this loop**: MR-1 validation (`validation.py:926`)
  only fires for meta-loops (loops that write harness artifacts). This loop
  generates SVGs, so `_is_meta_loop()` returns `False` and MR-1 is skipped.
  The acceptance criteria's MR-1 requirement is a design choice for correctness,
  not a validator-enforced requirement. The loop will pass `ll-loop validate`
  with or without non-LLM evaluators.
- **Per-iteration persistence is manual**: The FSM executor does not
  automatically save artifacts per iteration. The loop must include shell
  actions that explicitly write files to `${context.run_dir}/iter-${state.iteration}/`.
  See `svg-image-generator.yaml:init` (line 23) for the `run_dir` setup pattern.
- **Evaluator type corrections**: The API sketch references `check_numeric` and
  `check_convergence` which do not exist. The correct evaluator types are
  `output_numeric` (for score comparison, `evaluators.py:156`) and `convergence`
  (for diff-based exit gating, `evaluators.py:349`).
- **Wrapper script pattern**: Existing loops use inline Python heredocs
  (`python3 << 'PYEOF' ... PYEOF`) rather than separate wrapper scripts. A
  standalone `scripts/autofigure_wrapper.py` is a valid design choice but
  deviates from existing conventions. The `adopt-third-party-api.yaml` loop
  shows the inline heredoc pattern at its `parse_enumeration` state (line 58).
- **Test location**: Structural loop tests belong in `test_builtin_loops.py`,
  not `test_fsm_validation.py` (which tests the validation logic itself).
  Pattern: `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm()` auto-covers
  new loops added to the loops directory.

## Integration Map

### Files to Modify
- New: `loops/examples/adversarial-redesign.yaml` (or per project convention)
- New: `scripts/autofigure_wrapper.py`
- New: `prompts/adversarial-critic.md`

### Dependent Files (Callers/Importers)
- None at creation time; future demo scripts may invoke `ll-loop run adversarial-redesign`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — `resolve_loop_path()` (line 835) discovers loops via `get_builtin_loops_dir() / "<name>.yaml"` (line 852); only resolves flat files in `scripts/little_loops/loops/`; **subdirectory placement breaks name-based invocation**
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_install()` (line 37) uses non-recursive `BUILTIN_LOOPS_DIR.glob("*.yaml")` at line 49; subdirectory loops reported as unavailable
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` (line 53) uses recursive `rglob("*.yaml")`; would list a subdirectory loop as `examples/adversarial-redesign` (not `adversarial-redesign`)

### Similar Patterns
- `scripts/little_loops/loops/svg-image-generator.yaml` — **primary pattern**:
  visual artifact loop with init→plan→generate→evaluate→score states,
  `run_dir` setup, shell actions writing SVG artifacts, `output_contains`
  evaluator gates. This is the closest existing loop to the proposed design.
- `scripts/little_loops/loops/p5js-sketch-generator.yaml` — **secondary pattern**:
  visual artifact loop with identical init→plan→generate→evaluate→score→exit
  structure. Demonstrates per-iteration artifact persistence via
  `${context.run_dir}` in shell actions.
- `scripts/little_loops/loops/examples-miner.yaml` — example of structured
  capture + child-loop dereference
- `scripts/little_loops/loops/eval-driven-development.yaml` — example of
  numeric eval gate paired with semantic check (the pattern this loop
  must follow per MR-1)

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm()`
  (line 37) auto-validates all loops in the directory; no new test needed
  for basic validation. A per-loop structural test (following the
  `TestEvaluationQualityLoop` pattern at line 404) should verify:
  required states exist (`seed`, `critic`, `score_floor`, `regen`,
  `convergence`, `done`), evaluator types are correct, and capture
  wiring is complete.
- Optional integration test: skipped by default (requires AutoFigure +
  API key); gated behind a marker like `@pytest.mark.requires_autofigure`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_expected_loops_exist()` (line 66–135) uses **set equality** (`expected == actual`); **WILL BREAK** when loop is added to `scripts/little_loops/loops/` unless `"adversarial-redesign"` is added to the `expected` set — the fixture uses non-recursive `glob("*.yaml")` so the loop must be placed flat, not in a subdirectory
- `scripts/tests/test_builtin_loops.py` — add `TestAdversarialRedesignLoop` class following the `TestSvgImageGeneratorLoop` pattern (line 2876–2988); key assertions unique to this loop: `score_floor` state uses `output_numeric` or `output_json` evaluator, `convergence` state uses `convergence` evaluator with a `route:` table (not `on_converged:`/`on_diverged:`), shell states reference `${context.run_dir}`, both `seed` and `regen` shell states invoke `autofigure_wrapper.py`

### Documentation
- README or `docs/` example-loop index needs the new loop listed
- Loop YAML's preamble comment must call out the optional dependency

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — authoritative loop catalog organized by category section; add a table entry for `adversarial-redesign` with a one-line pitch and example invocation; referenced from `docs/reference/loops.md` and `docs/guides/LOOPS_GUIDE.md`

### Configuration
- N/A — no `.ll/ll-config.json` changes required; the loop reads
  `AUTOFIGURE_API_KEY` (or equivalent) from env directly.

## Implementation Steps

1. **Write `scripts/autofigure_wrapper.py`** — emit `{svg_path, final_score,
   iteration}` as JSON on stdout. Model after the inline Python heredoc
   pattern in `adopt-third-party-api.yaml:parse_enumeration` (line 58),
   or as a standalone script (deviates from existing convention but is
   cleaner for an external dependency). Add a unit test stubbing the
   AutoFigure call.
2. **Draft the critic prompt inline** in the loop YAML (not as a separate
   `prompts/adversarial-critic.md` file, since `prompt_ref` does not exist
   in the current FSM). Use `action_type: prompt` with a JSON schema
   constraint in the prompt text. See `harness-single-shot.yaml:check_semantic`
   (line 113) for the `llm_structured` evaluator pattern for gating on
   critic output.
3. **Compose `loops/examples/adversarial-redesign.yaml`** following the
   structure of `svg-image-generator.yaml` (init→generate→evaluate→score):
   - `seed` state: `action_type: shell` calling the wrapper, `capture: seed`
   - `critic` state: `action_type: prompt` producing structured JSON,
     `capture: critique`
   - `score_floor` state: `evaluate: type: output_numeric` comparing
     `${captured.regen.final_score}` against previous. Use `operator: ge`.
   - `regen` state: `action_type: shell` calling wrapper with critique,
     `capture: regen`
   - `convergence` state: `evaluate: type: convergence` with `route:` table
     (not `on_converged`/`on_diverged`). See `harness-optimize.yaml:gate`
     (line 178).
   - Per-iteration artifacts: add shell commands writing to
     `${context.run_dir}/iter-${state.iteration}/`. See
     `svg-image-generator.yaml:init` (line 23) for `run_dir` pattern.
   - Run `ll-loop validate` (MR-1 won't fire since this isn't a meta-loop).
4. **Run end-to-end** against a real AutoFigure install on at least 3
   distinct concepts; verify per-iteration artifacts + transcript.
5. **Add to loop index** — update `scripts/little_loops/loops/README.md`
   with a one-line pitch. Add a per-loop structural test in
   `scripts/tests/test_builtin_loops.py` following the
   `TestEvaluationQualityLoop` pattern (line 404).
6. **Add structural smoke test** — verify required states, evaluator types,
   capture wiring, and that `ll-loop validate` passes. The existing
   `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm()` (line 37)
   provides automatic baseline coverage for any loop in the directory.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Place the loop at `scripts/little_loops/loops/adversarial-redesign.yaml`** (NOT `loops/examples/adversarial-redesign.yaml`) — the issue's stated path is wrong: `loops/examples/` does not exist and `resolve_loop_path()` only resolves flat files in `scripts/little_loops/loops/`; placing in a subdirectory breaks `ll-loop run adversarial-redesign`, `ll-loop install`, and all `TestBuiltinLoopFiles` auto-validation
8. **Fix the `score_floor` evaluator type**: `evaluate_output_numeric()` (evaluators.py:156) calls `float(output.strip())` — it cannot parse JSON. If `autofigure_wrapper.py` emits `{"svg_path":..., "final_score": 8}`, use `evaluate.type: output_json` with a `.final_score` path, NOT `output_numeric`. Similarly `convergence` expects a bare float — either add a "score-only" mode to the wrapper, or use `output_json` for score gating.
9. **Update `test_expected_loops_exist`** — add `"adversarial-redesign"` to the `expected` set at line 68 of `scripts/tests/test_builtin_loops.py`; this test uses `expected == actual` equality and will fail immediately when the YAML is placed in the built-in directory
10. **Add `TestAdversarialRedesignLoop`** to `scripts/tests/test_builtin_loops.py` following the `TestSvgImageGeneratorLoop` pattern (line 2876)
11. **Update `scripts/little_loops/loops/README.md`** — add table entry with one-line pitch and example invocation (acceptance criterion; also required by `/ll:ready-issue` doc check)

## Impact

- **Priority**: P3 — high *demo* value, no functional blocker. Useful as a
  reference example for the generator-vs-critic pattern.
- **Effort**: Small — leverages existing FSM primitives; only new code is
  a ~50-line wrapper script, one YAML, and one prompt file.
- **Risk**: Low — example loop, isolated from other harness code. Optional
  dependency on AutoFigure means failure to install does not affect any
  core flow.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `.claude/CLAUDE.md` § Loop Authoring | Mandates non-LLM evaluator pairing with `check_semantic` (MR-1). This loop's `score_floor` + `convergence` states satisfy that rule. |
| `docs/ARCHITECTURE.md` | FSM executor contract that the loop YAML compiles against. |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-31_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- **API sketch uses incorrect FSM syntax throughout** — `action: llm_structured`, `check_numeric`, `check_convergence`, `on_converged`/`on_diverged` are all wrong. Corrections are documented in Codebase Research Findings and Implementation Steps (steps 2–3, 8). A developer reading only the YAML sketch will implement incorrectly.
- **`output_json` vs `output_numeric` for score gating** — wiring step 8 flags this as an open either/or choice (add score-only mode to wrapper OR use `output_json`). Implementation steps lean toward `output_json`, but the API sketch and ACs still reference `output_numeric`. Resolve before authoring the `score_floor` state.
- **Critic prompt location contradiction** — Proposed Solution §3 and an acceptance criterion mention `prompts/adversarial-critic.md`, but Codebase Research Findings correctly establish `prompt_ref` doesn't exist; inline is the right approach (step 2 resolves this). The `prompts/adversarial-critic.md` AC should be treated as cancelled.

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:ready-issue` - 2026-05-31T05:39:23 - `78218aaf-6884-4591-9aff-c393a35359ce.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00Z - `959041b3-877b-4e0b-bb02-ec35d5072a0a.jsonl`
- `/ll:wire-issue` - 2026-05-31T05:33:52 - `3fc496ef-4ed1-4b4c-ba55-c2bcb81eab1f.jsonl`
- `/ll:refine-issue` - 2026-05-31T05:29:23 - `32d2e25b-c814-4680-aabc-95d754a64e6a.jsonl`
- `/ll:format-issue` - 2026-05-31T05:21:58 - `9b1bc2bc-fb54-4fce-afcd-31ab48945e74.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:capture-issue` — 2026-05-30T05:25:35Z — `aebb9b72-3342-4acd-a90d-d77948da77a9.jsonl`

---

**Open** | Created: 2026-05-30 | Priority: P3
