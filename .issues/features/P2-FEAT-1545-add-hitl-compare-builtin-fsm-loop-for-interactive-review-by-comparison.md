---
id: FEAT-1545
title: Add hitl-compare built-in FSM loop for interactive review-by-comparison
type: FEAT
status: done
priority: P2
captured_at: '2026-05-17T07:08:30Z'
completed_at: '2026-05-17T07:48:35Z'
discovered_date: '2026-05-17'
discovered_by: capture-issue
labels:
- feature
- loops
- harness
- human-in-the-loop
- captured
relates_to:
- FEAT-1541
- FEAT-1534
confidence_score: 98
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1545: Add hitl-compare built-in FSM loop for interactive review-by-comparison

## Summary

Add a new built-in FSM loop `hitl-compare` (human-in-the-loop comparison) that takes
one or more inputs — raw text or file paths to refined/captured issues, frontend
designs, document versions, plans with open decisions, etc. — and produces a
single self-contained HTML artifact that lets a human review and select between
multiple options for each open decision. The loop first identifies what should
actually be put up for human review, prunes anything with an obvious winner
(implementation-level decisions that belong in normal planning/refinement),
generates a single-page HTML file with interactive toggle/select controls for
each remaining decision item, then iteratively evaluates and refines the
artifact using the GAN-style generator/evaluator pattern from
`html-website-generator.yaml` and `html-anything.yaml`. After the loop completes,
the human reviews the page, makes selections, and passes their decisions back
into the coding agent to update specs/issues/plans.

## Current Behavior

There is no built-in loop that produces a single-page interactive HTML artifact
for human review of multiple-option decisions across heterogeneous inputs.
Existing harness loops (`html-website-generator`, `html-anything`,
`svg-image-generator`) produce non-interactive output artifacts; the existing
decision support skills (`/ll:decide-issue`, `/ll:confidence-check`,
`/ll:go-no-go`) operate per-issue from inside the coding agent and don't
produce a comparison surface a human can browse, toggle, and select from.

## Expected Behavior

`ll-loop run hitl-compare "path/to/plan.md path/to/design-options.md"` (or
with raw text input) should:

1. Read all inputs (file paths or raw text) and extract candidate
   review items — decisions, design elements, functional requirement
   variants, document versions, etc. — each with two or more options.
2. Prune review items that have an obvious winner so the human is only
   asked to weigh in on the small set of genuinely undecided items.
3. Generate a single self-contained HTML page (all CSS/JS inline, no
   external deps, renders under `file://`) with one toggle/select control
   per remaining review item, side-by-side or option-cycling comparison
   UI per item, and a final "export selections" affordance.
4. Iteratively evaluate the rendered artifact via Playwright screenshot
   and refine it for clarity, scan-ability, and decision ergonomics for
   the remaining iteration budget.
5. Report the final HTML path so the human can open it, make their
   picks, and feed the resulting decisions back into the coding agent.

## Use Case

A developer has just run `/ll:refine-issue` on a batch of issues and
several emerge with `decision_needed: true` containing 2-3 viable
implementation options each. Rather than copy-pasting each issue's options
into chat and weighing them one at a time, they run
`ll-loop run hitl-compare ".issues/features/P2-FEAT-A.md .issues/features/P2-FEAT-B.md"`,
open the generated HTML page in their browser, toggle through the
comparison controls to make their picks, click "Export selections", and
paste the resulting markdown block back into the coding agent which then
updates each issue's selected option. Total elapsed human time: a few
minutes of focused review instead of a long back-and-forth chat thread.

A second canonical use case is design review: the developer hands in a
plan markdown plus a few raw-text alternatives for a UI surface, and the
loop produces a side-by-side comparison page so the human can make
taste-driven calls without the spam of implementation-level micro-decisions
that `/ll:refine-issue` should have already resolved.

## Motivation

Several existing workflows produce decision-laden artifacts (refined issues
with `decision_needed: true`, sprint planning output, multi-option plans,
design exploration) where the right next step is a quick human review across
a handful of small, well-framed choices. Today that review happens in chat,
which has poor side-by-side comparison ergonomics, no persistent selection
state, and no obvious "send these decisions back to the agent" handoff.
A single interactive HTML artifact gives the human a focused, scan-friendly
comparison surface and turns the round-trip from "agent presents N
decisions" → "human picks" → "agent updates specs" into a clean,
copy-pasteable handoff.

The pruning step is critical: without it, the loop would dump every
implementation-level micro-decision into the review surface, which is
exactly the spam the user wants to avoid. Implementation-level decisions
should be resolved by `/ll:refine-issue`, `/ll:wire-issue`, `/ll:decide-issue`
and the rest of the normal planning pipeline; this loop only surfaces
decisions where a human's taste/judgment/preference is the appropriate
deciding signal.

## Proposed Solution

A 7-state FSM harness modeled on `html-anything.yaml` and
`html-website-generator.yaml`:

```
init → identify → prune → generate → evaluate → score → done (+ failed terminal)
```

**Per-state sketch:**
- `init` (shell): create timestamped run dir under
  `.loops/tmp/hitl-compare/<TS>/`, `capture: run_dir` — mirrors
  `svg-image-generator.yaml:24-35` and `html-anything.yaml init`.
- `identify` (prompt): read all inputs (resolving file paths, treating
  non-existent paths as raw text), extract candidate review items into
  `${captured.run_dir.output}/items.md` — each item has a title, 2+ options
  with short rationales, and a `category` (decision / design / requirement /
  document-version / other).
- `prune` (prompt): re-read `items.md`, drop items with an obvious winner
  or that look implementation-level (anything where standard refinement
  pipelines should decide), write the surviving set to `review.md`. Log
  which items were pruned and why for traceability.
- `generate` (prompt): read `review.md` (+ any prior `critique.md`); write
  a single self-contained HTML file `index.html` with all CSS/JS inline,
  one comparison control per review item (radio/toggle/cycle UI), a
  final "Export selections" button that builds a copy-pasteable markdown
  block of `item → chosen option` pairs.
- `evaluate` (shell): Playwright screenshot of `file://...index.html`,
  `on_error: generate` for graceful degradation when Playwright is
  unavailable — pattern from `html-anything.yaml`.
- `score` (prompt): score the rendered page against a small fixed rubric
  (clarity, scan-ability, comparison ergonomics, export affordance,
  inline-only constraint), write `critique.md`, gate via
  `output_contains: ALL_PASS`; route to `generate` on fail,
  `on_error: failed`.
- `done` (prompt + `terminal: true`): report final paths (`index.html`,
  `items.md`, `review.md`, `critique.md`, `screenshot.png`) and tell the
  user how to feed selections back to the coding agent.
- `failed` (`terminal: true`).

**Shared fragments / chains to consider:**
- The `init` (`mkdir + capture run_dir`), `evaluate` (Playwright screenshot
  with graceful degrade), and `score` (rubric-based `ALL_PASS` gate)
  states are now near-duplicated across `html-website-generator.yaml`,
  `html-anything.yaml`, `svg-image-generator.yaml`, and would be again
  here. This is the third+ harness to copy that pattern; strong candidate
  for extracting a shared fragment library (e.g. `lib/harness.yaml`
  with `harness_init_run_dir`, `harness_playwright_screenshot`,
  `harness_rubric_score` fragments) and importing them via
  `import: - lib/harness.yaml`. See the Scope Boundary note on FEAT-1541
  that already flagged the same pattern duplication. Recommend doing the
  shared-fragment extraction as either part of this issue or as a
  fast-follow ENH so this loop doesn't entrench the copy-paste pattern
  a fourth time.
- The `identify → prune` chain is novel and specific to this loop; keep
  inline rather than fragmenting.

**Input handling:** `input_key: inputs` accepting whitespace-separated
tokens; for each token, if it resolves to an existing file path read the
file, otherwise treat the literal string as raw text content.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/README.md` — add `hitl-compare` row to Harness table
- `scripts/tests/test_builtin_loops.py` — add `"hitl-compare"` to the hardcoded `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` at lines 67–115 (symmetric set-equality check — currently 47 entries, must become 48); add new `TestHitlCompareLoop` class modeled on `TestHtmlAnythingLoop` at lines 2835–2978
- `docs/guides/LOOPS_GUIDE.md` — add row to Harness Examples table + `### hitl-compare` subsection following `### html-anything`
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `hitl-compare.yaml` bullet to Further Reading
- `README.md` — line 167 currently says `**45 FSM loops**` but the actual file count is already 47 (pre-existing drift of 2). After adding `hitl-compare` the directory will hold **48** files, so update line 167 to `**48 FSM loops**` (not 47) to correct the drift in the same pass.
- `CHANGELOG.md` — `### Added` entry under current release

### Files to Create
- `scripts/little_loops/loops/hitl-compare.yaml` — new 7-state FSM harness
- _(optional, recommended)_ `scripts/little_loops/loops/lib/harness.yaml` — shared fragments for `harness_init_run_dir`, `harness_playwright_screenshot`, `harness_rubric_score` if the shared-fragment extraction is done as part of this issue

### Reference Files (patterns to follow)
- `scripts/little_loops/loops/html-anything.yaml` — primary structural template (init, plan→generate, evaluate, score, done, failed)
- `scripts/little_loops/loops/html-website-generator.yaml` — generator/evaluator (GAN-style) refinement pattern
- `scripts/little_loops/loops/svg-image-generator.yaml` — timestamped run dir + `on_error` graceful-degrade pattern
- `scripts/little_loops/loops/lib/common.yaml` — shared fragment authoring conventions

### Tests
- `scripts/tests/test_builtin_loops.py` auto-discovers `*.yaml` files; new loop will be picked up, but the hardcoded expected-loops set must be updated (HARD BLOCK)
- New `TestHitlCompareLoop` class asserting: `name == "hitl-compare"`, `input_key == "inputs"`, state set, `evaluate` has `on_error: generate`, `score` has `on_error: failed`, `init` captures `run_dir`, key referenced filenames in actions (`items.md`, `review.md`, `critique.md`, `index.html`)

### Configuration
- N/A

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — defines `get_builtin_loops_dir()` and `resolve_loop_path()`; no change needed, auto-discovers new YAML [Agent 1 finding]
- `scripts/little_loops/cli/loop/run.py` — imports `get_builtin_loops_dir`, `resolve_loop_path`; sets `input_key` at lines 135–139; no change needed [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py` — enumerates builtin loops dynamically via `get_builtin_loops_dir()` glob; no change needed [Agent 1 finding]
- `scripts/little_loops/cli/loop/config_cmds.py` — imports `get_builtin_loops_dir`, `resolve_loop_path`; no change needed [Agent 1 finding]
- `scripts/little_loops/fsm/fragments.py` — defines `resolve_fragments()`; no change needed [Agent 1 finding]
- `scripts/little_loops/fsm/validation.py` — defines `validate_fsm()`, `load_and_validate()`; no change needed [Agent 1 finding]

### Documentation (additional)

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` line 122 — directory tree entry reads `├── loops/   # Built-in FSM loop definitions (44 YAML files)`; must be updated to `(48 YAML files)` to match the actual count after adding `hitl-compare.yaml` (current count is already 47 before this issue, so drift of 3 exists). Not caught by `ll-verify-docs` (`COUNT_TARGETS` does not include `loops`; ENH-1038 tracks the gap). [Agent 2 finding]

### Tests (additional)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_flow.py` — `test_all_builtin_loops_still_load()` auto-expands via filesystem glob; will automatically validate `hitl-compare.yaml` at collection time — no code change needed, but must not be broken by an invalid YAML [Agent 1/3 finding]
- `scripts/tests/test_hitl_compare.py` — (optional) dedicated test file following the `test_rn_plan.py` pattern (`TestRnPlanYaml` uses `load_and_validate` + `validate_fsm` + structural YAML assertions); if the `TestHitlCompareLoop` class in `test_builtin_loops.py` is judged sufficient, this file can be omitted [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Loader / discovery surface** (no code changes needed — built-in YAML is auto-discovered):
- `scripts/little_loops/cli/loop/_helpers.py:resolve_loop_path()` — resolution order ends at `get_builtin_loops_dir() / f"{name}.yaml"`, which maps to `scripts/little_loops/loops/`. Dropping `hitl-compare.yaml` there makes `ll-loop run hitl-compare` work with no registration step.
- `scripts/little_loops/fsm/validation.py:load_and_validate()` — runs `yaml.safe_load → resolve_inheritance → resolve_flow → resolve_fragments → FSMLoop.from_dict → validate_fsm → _validate_with_bindings`. All four `TestBuiltinLoopFiles` generic tests (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field`, `test_no_bare_pass_token_in_output_contains`) run automatically over `*.yaml`.

**Hard schema invariants the YAML must satisfy (otherwise generic tests fail):**
- Top-level `description:` MUST be a non-empty string (`test_all_have_description_field`).
- `output_contains` patterns may not be bare `"PASS"` (`test_no_bare_pass_token_in_output_contains`); use `ALL_PASS` (already planned for the `score` state) and `CAPTURED` (Playwright success token used by `evaluate`).
- `initial:` MUST name an existing state; at least one state MUST be `terminal: true`; every state referenced from any transition MUST exist; every non-terminal state MUST have routing (`next` or shorthand verdicts or `route` or `loop`). All enforced by `validate_fsm()` in `scripts/little_loops/fsm/validation.py`.
- `input_key: inputs` requires `context.inputs: ""` (or other default) in the top-level `context:` block — `cmd_run()` in `scripts/little_loops/cli/loop/run.py:126-139` writes the CLI positional arg to `fsm.context[fsm.input_key]`, and other pre-run logic expects the key to pre-exist with a default.
- `category: harness` is a recognized top-level key (`KNOWN_TOP_LEVEL_KEYS` in `validation.py:78-106`); existing harness loops set it.

**Input handling reality check:**
- The executor does **no** whitespace-token splitting or file-vs-text discrimination. `${context.inputs}` will contain the raw positional arg verbatim. The `identify` prompt must handle "split on whitespace; for each token, try reading as a file path, fall back to raw text" entirely in its prompt instructions (or via an upstream shell state). This matches the design intent in the Proposed Solution but is worth calling out as an implementation responsibility, not framework-provided.

**Capture substitution mechanics:**
- `scripts/little_loops/fsm/executor.py` stores `state.capture` output at `self.captured[<name>] = {"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ...}`. The `${captured.run_dir.output}` token resolves via `InterpolationContext.resolve()` in `scripts/little_loops/fsm/interpolation.py`. Captures persist for the entire run, so every state after `init` can embed `${captured.run_dir.output}/<filename>`.

**Init state exact pattern to copy** (`scripts/little_loops/loops/html-anything.yaml:27-38`, byte-identical to `svg-image-generator.yaml:24-35`):
```yaml
init:
  action_type: shell
  action: |
    TS=$(date -u +%Y%m%d-%H%M%S)
    DIR="${context.output_dir}/$TS"
    mkdir -p "$DIR"
    echo "$(pwd)/$DIR"
  capture: run_dir
  next: identify        # html-anything uses "plan" here; hitl-compare uses "identify"
```
Note: `$(pwd)` is required so the captured path is absolute and valid for `file://` URIs — enforced by `test_init_action_uses_absolute_path`.

**Evaluate state exact pattern to copy** (`scripts/little_loops/loops/html-anything.yaml:139-155`):
```yaml
evaluate:
  action_type: shell
  action: |
    playwright screenshot "file://${captured.run_dir.output}/index.html" "${captured.run_dir.output}/screenshot.png" 2>&1 && echo "CAPTURED"
  evaluate:
    type: output_contains
    pattern: "CAPTURED"
  on_yes: score
  on_no: generate
  on_error: generate
```
The `2>&1` is required by `test_evaluate_action_has_stderr_redirect`.

**Failed state exact pattern** (`scripts/little_loops/loops/html-anything.yaml:222-226`):
```yaml
failed:
  terminal: true
```
That's the entire body — no `action`, no `action_type`.

**Test class scaffolding** — `TestHitlCompareLoop` should at minimum cover (modeled on `TestHtmlAnythingLoop` at `scripts/tests/test_builtin_loops.py:2834-2978`):
- `test_required_top_level_fields`: `name == "hitl-compare"`, `initial == "init"`, `input_key == "inputs"`, `states` is dict.
- `test_required_states_exist`: `{"init", "identify", "prune", "generate", "evaluate", "score", "done", "failed"}` is a subset of `states.keys()`.
- `test_init_state_is_shell_with_capture`: `action_type == "shell"`, `capture == "run_dir"`, `next == "identify"`.
- `test_init_action_uses_absolute_path`: `"$(pwd)" in init.action`.
- `test_done_state_is_terminal`, `test_failed_state_is_terminal`: both `terminal is True`.
- `test_evaluate_state_is_shell`, `test_evaluate_state_has_output_contains_evaluator` (pattern `CAPTURED`), `test_evaluate_routes_to_score_on_yes`, `test_evaluate_routes_to_generate_on_no`, `test_evaluate_on_error_routes_to_generate`, `test_evaluate_action_has_stderr_redirect`.
- `test_score_state_uses_all_pass_pattern` (pattern `ALL_PASS`), `test_score_state_routes_to_done_on_pass`, `test_score_state_routes_to_generate_on_iterate`, `test_score_on_error_routes_to_failed`.
- `test_context_has_inputs_and_output_dir`: `"inputs" in context`, `context.output_dir == ".loops/tmp/hitl-compare"`.
- `test_identify_action_writes_items_md`, `test_prune_action_writes_review_md`, `test_generate_action_writes_index_html`, `test_done_reports_all_output_files` (`items.md`, `review.md`, `critique.md`, `index.html`, `screenshot.png` in `done.action`).
- `test_max_iterations_and_timeout_defined`.

**Documentation row format reference:**
- Harness table in `scripts/little_loops/loops/README.md:101` — single-line markdown table row: `` | `<name>` | <description> | ``
- Harness Examples table in `docs/guides/LOOPS_GUIDE.md:767` — same single-line row format.
- Per-loop subsection in `docs/guides/LOOPS_GUIDE.md:774-845` (`### html-anything`) — H3 header, Prerequisites blockquote, **Technique**, **When to use**, **Usage** (bash block), **Context variables** table, **FSM flow** ASCII diagram, **Notes** bullet list. Model the `### hitl-compare` subsection on this exact skeleton.

**Shared-fragment library context (informs the optional scope decision in Proposed Solution):**
- `scripts/little_loops/loops/lib/common.yaml` already exists with `shell_exit`, `retry_counter`, `llm_gate`, `with_rate_limit_handling` fragments.
- `scripts/little_loops/loops/lib/cli.yaml`, `lib/benchmark.yaml`, `lib/apo-base.yaml` show the multi-file `lib/` convention.
- A new `lib/harness.yaml` housing `harness_init_run_dir`, `harness_playwright_screenshot`, `harness_rubric_score` would be consumed via `import: - lib/harness.yaml` at the top of `hitl-compare.yaml` and (in a follow-up) the three existing harnesses. The `resolve_fragments()` call in `load_and_validate()` already supports this.

**Acceptance-criteria additions implied by the above (not yet in the AC list):**
- Top-level `description:` non-empty string is present.
- `context.inputs: ""` (or analogous default) is declared so `input_key: inputs` resolves cleanly.
- `category: harness` is set to align with other harness loops.

## Implementation Steps

1. Author `scripts/little_loops/loops/hitl-compare.yaml` with the 7-state FSM described in Proposed Solution.
2. _(Recommended)_ Extract shared `harness_init_run_dir` / `harness_playwright_screenshot` / `harness_rubric_score` fragments into `scripts/little_loops/loops/lib/harness.yaml` and import from `hitl-compare.yaml` (and follow-up PRs can migrate `html-anything.yaml` / `html-website-generator.yaml` / `svg-image-generator.yaml`).
3. Update `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `README.md`, `CHANGELOG.md`.
4. Update `scripts/tests/test_builtin_loops.py` — add to expected-loops set and add `TestHitlCompareLoop`.
5. Run `python -m pytest scripts/tests/test_builtin_loops.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `CONTRIBUTING.md` line 122 — change `(44 YAML files)` → `(48 YAML files)` to repair pre-existing drift (count was 44 when the comment was written, actual is 47 now, will be 48 after this issue)

7. Functional verification via at least three sample runs:
   - File input: a refined issue with `decision_needed: true` and an "Options" section.
   - Mixed input: a plan markdown + raw text describing 2 design alternatives.
   - Pruning verification: an input dominated by implementation-level micro-decisions should reduce to a small review set (or zero items, with the loop reporting "nothing to review" cleanly).
7. Confirm the generated HTML renders correctly under `file://`, that each control toggles between options, and that the "Export selections" affordance produces a copy-pasteable markdown block.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/hitl-compare.yaml` exists with 7 states (`init`, `identify`, `prune`, `generate`, `evaluate`, `score`, `done`) plus a `failed` terminal state.
- [ ] Loop declares `input_key: inputs` and accepts whitespace-separated tokens, treating each as a file path if it resolves on disk and as raw text content otherwise.
- [ ] `init` state creates a timestamped run dir under `.loops/tmp/hitl-compare/<TS>/` and captures it as `run_dir` (pattern mirrors `svg-image-generator.yaml`).
- [ ] `identify` state writes `${captured.run_dir.output}/items.md` containing each candidate review item with a title, 2+ options with short rationales, and a `category` tag (decision / design / requirement / document-version / other).
- [ ] `prune` state writes `review.md` containing only items requiring human judgment, and logs which items were pruned and why for traceability.
- [ ] `generate` state produces a single self-contained `index.html` (all CSS/JS inline, no external deps, renders under `file://`) with one comparison control per surviving review item and an "Export selections" affordance that yields a copy-pasteable markdown block of `item → chosen option` pairs.
- [ ] `evaluate` state runs a Playwright screenshot of the rendered HTML with `on_error: generate` for graceful degradation when Playwright is unavailable.
- [ ] `score` state evaluates the rendered page against a fixed rubric (clarity, scan-ability, comparison ergonomics, export affordance, inline-only constraint), writes `critique.md`, gates via `output_contains: ALL_PASS`, routes to `generate` on fail, and uses `on_error: failed`.
- [ ] `done` state is `terminal: true` and reports the final paths (`index.html`, `items.md`, `review.md`, `critique.md`, `screenshot.png`) plus instructions for feeding selections back to the coding agent.
- [ ] `scripts/tests/test_builtin_loops.py` expected-loops set includes `"hitl-compare"` and a new `TestHitlCompareLoop` class asserts: `name == "hitl-compare"`, `input_key == "inputs"`, the full state set, `evaluate` has `on_error: generate`, `score` has `on_error: failed`, `init` captures `run_dir`, and key referenced filenames (`items.md`, `review.md`, `critique.md`, `index.html`) appear in the relevant actions.
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py -v` passes.
- [ ] `README.md` FSM loop count is incremented; `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, and `CHANGELOG.md` are updated with `hitl-compare` entries.
- [ ] Functional verification: three sample runs (refined issue with `decision_needed: true`; mixed plan markdown + raw-text design alternatives; implementation-heavy input that should prune to ~0 items) each produce well-formed HTML or a clean "nothing to review" report.
- [ ] Top-level `description:` is set to a non-empty string (enforced by `test_all_have_description_field` in `scripts/tests/test_builtin_loops.py`).
- [ ] Top-level `context:` block declares `inputs: ""` (default) and `output_dir: ".loops/tmp/hitl-compare"` so `input_key: inputs` resolves cleanly via `cmd_run()` in `scripts/little_loops/cli/loop/run.py:126-139`.
- [ ] Top-level `category: harness` is set to match the existing harness loops (`html-anything`, `html-website-generator`, `svg-image-generator`).
- [ ] `README.md` line 167 is corrected to `**48 FSM loops**` (not 45), repairing the pre-existing drift of 2 between the documented count and `ls scripts/little_loops/loops/*.yaml | wc -l`.
- [ ] No `output_contains` evaluator anywhere in the loop uses the bare token `"PASS"` (enforced by `test_no_bare_pass_token_in_output_contains`). Use `ALL_PASS` and `CAPTURED` as already planned.

## Impact

- **Priority**: P2 — meaningful new harness category (interactive HITL artifacts) and the third+ harness following the same copy-paste pattern, making it a good forcing function for shared-fragment extraction.
- **Effort**: Medium — YAML authoring following established harness patterns; novel work is the `identify`/`prune` prompts and the interactive HTML scoring rubric. Optional shared-fragment extraction adds modest scope.
- **Risk**: Low — new file only; does not modify existing harnesses. Optional shared-fragment refactor of existing harnesses is the only risk-bearing change and can be deferred to a fast-follow ENH.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/html-anything.yaml` | Primary structural template (init, plan, generate, evaluate, score, done, failed) |
| `scripts/little_loops/loops/html-website-generator.yaml` | GAN-style generator/evaluator refinement loop |
| `scripts/little_loops/loops/svg-image-generator.yaml` | Timestamped run dir + `on_error` graceful-degrade pattern |
| `scripts/little_loops/loops/lib/common.yaml` | Shared fragment authoring conventions |
| FEAT-1541 (`.issues/features/P2-FEAT-1541-add-html-anything-generalized-html-artifact-harness.md`) | Scope Boundary note already flagged the harness pattern duplication this issue would extend |

## Session Log
- `/ll:ready-issue` - 2026-05-17T07:43:43 - `d7e4f13a-3acd-435c-a079-10fe48342d31.jsonl`
- `/ll:confidence-check` - 2026-05-17T07:45:00 - `63ea35fd-1756-4a65-bf42-4a38c5c4701b.jsonl`
- `/ll:wire-issue` - 2026-05-17T07:27:15 - `4d712238-1a06-4b9f-9d5b-5639228894d7.jsonl`
- `/ll:refine-issue` - 2026-05-17T07:20:50 - `6dd09366-ca88-452f-87df-e7e23ed6a020.jsonl`
- `/ll:format-issue` - 2026-05-17T07:13:28 - `b335707c-c3d5-4e5a-abbf-cce433334d6b.jsonl`
- `/ll:capture-issue` - 2026-05-17T07:08:30Z - `5ff0fc28-0ac8-422c-b957-293025b6214c.jsonl`

---

## Status

**Open** | Created: 2026-05-17 | Priority: P2
