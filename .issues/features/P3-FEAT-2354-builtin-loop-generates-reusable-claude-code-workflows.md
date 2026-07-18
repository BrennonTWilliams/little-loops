---
id: FEAT-2354
title: Built-in FSM loop that generates reusable Claude Code workflows
type: FEAT
priority: P3
status: open
captured_at: '2026-06-27T22:11:29Z'
discovered_date: 2026-06-27
discovered_by: capture-issue
parent: EPIC-1811
labels:
- loops
- meta-loop
- codegen
- harness
confidence_score: 96
outcome_confidence: 77
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# FEAT-2354: Built-in FSM loop that generates reusable Claude Code workflows

## Summary

Add a new built-in FSM loop — in the same family as our artifact-generator loops
(`html-website-generator`, `svg-image-generator`, `generative-art`, `p5js-sketch-generator`,
etc.) — that, instead of emitting an HTML/SVG/visual artifact, emits a **reusable Claude Code
workflow** that automates a repeatable piece of work.

**Output-target resolution (v1):** the original brainstorm spanned both little-loops FSM YAML
and Claude Code *dynamic workflow* JS scripts (the `agent()`/`pipeline()` scripts saved under
`.claude/workflows/`). The `/ll:refine-issue` research pass resolved v1 to **FSM-loop YAML**
(validatable with `ll-loop validate`); the JS target is a follow-on, now made concretely
tractable by the shim strategy in § Portability & Lock-in Analysis below. The title's
"Claude Code workflows" reflects the original ambition — read "workflow" in this issue as
"FSM-loop YAML artifact" unless the JS follow-on is explicitly named.

The recommended design (from the source brainstorm) is a **staged "compiler-lowering" loop**:
the workflow is generated through sequential FSM passes, each specializing in one semantic
"lowering" rather than producing the entire workflow in a single prompt. This is a **meta-loop**
(it generates harness artifacts), so it must follow the stricter meta-loop design rules in
`.claude/CLAUDE.md` § Loop Authoring (MR-1 through MR-6) — most importantly, every
`check_semantic`/`llm_structured` state must be paired with a non-LLM evaluator.

## Motivation

Today little-loops can generate visual/interactive artifacts via a whole family of generator
loops, but there is no built-in path to generate the *automation* artifact itself — a runnable
workflow that captures repeatable work. Users who want to automate a recurring multi-step task
must hand-author workflow scripts (or FSM YAML) directly. A generator loop closes that gap and
makes the harness self-extending: describe the repeatable work, get back a validated, minimal,
reusable workflow.

The "compiler-lowering" framing is the decisive design choice: it diagnoses *why* single-prompt
workflow generation fails (it conflates intent, structure, evaluation, and routing into one
intractable sub-problem) and fixes it structurally. Because each lowering pass maps onto an
existing non-LLM evaluator type already in the harness (`ll-loop validate` exit-code, schema
check, diff-stall), the meta-loop MR-1 requirement is satisfied **by architecture, not
convention** — and the generation trace is deterministic and debuggable rather than a single
opaque "the workflow doesn't behave correctly" verdict.

## Current Behavior

- Artifact-generator loops exist for visual/interactive outputs only:
  `scripts/little_loops/loops/{html-website-generator,svg-image-generator,generative-art,
  p5js-sketch-generator,canvas-sketch-generator,openscad-model-generator,pixi-generative-art,
  rlhf-svg-generate}.yaml`.
- No built-in loop emits a reusable Claude Code workflow. To create one, a user invokes
  `/ll:create-loop` (interactive wizard for FSM YAML) or hand-writes a Workflow script.
- `/ll:create-loop`'s "Optimize a harness" branch produces meta-loop scaffolding, but there is
  no generator loop whose *output artifact* is itself a reusable workflow.

## Expected Behavior

A new built-in loop (working name: `workflow-generator`) that:

1. Takes a generative brief (prose task description, and/or a mined session pattern) as input.
2. Runs sequential FSM lowering passes:
   - **Intent capture** — distill the brief into a structured intent spec.
   - **State-graph sketch** — propose the workflow's state graph. *(Diversity-injection point —
     see Proposed Solution.)*
   - **Evaluator attachment** — attach a non-LLM discriminator to each generated state.
   - **Routing-table resolution** — resolve transitions / route completeness.
   - **YAML (or Workflow-script) emission** — emit the artifact.
   - **Adversarial minimum-coupling shrink** — probe with edge-case inputs and excise any state
     whose removal does not change an outcome, producing the *smallest* workflow that passes all
     probes rather than the most complete one.
3. Validates the emitted artifact with `ll-loop validate` (non-LLM, exit-code) at the pass
   boundaries where it applies.
4. Writes per-iteration artifacts under `${context.run_dir}/` (MR-3) and snapshots each
   iteration's output (MR-5), since this is an iterative generate→evaluate cycle.

## Proposed Solution

TBD — requires investigation. Direction from the brainstorm (ranked shortlist):

- **Rank 1 — Compiler lowering (core).** Stage the generation as the FSM passes above; each pass
  is a tractable sub-problem with a non-LLM discriminator, satisfying MR-1 structurally.
- **Rank 2 — Scoped genetic graft (state-graph pass only).** At the single most-uncertain
  decision (the state-graph sketch), generate N candidate sketches in parallel and select the
  best by `ll-loop validate` exit-code before continuing. Scope recombination to this one pass to
  get global exploration where the design space is widest while keeping lowering deterministic
  and auditable everywhere else.
- **Rank 3 — Adversarial minimum-coupling shrink (final pass).** Operationalize "reusability is a
  property of minimum coupling, not completeness": remove a state, re-run the probe set, and keep
  the removal if no outcome changed. External, repeatable, binary — a sound non-LLM evaluator.

These three address orthogonal failure modes (conflation, local convergence, over-specification)
and compose into a single six-pass FSM without redundancy.

**Open design questions:**
- ~~Output target: emit FSM-loop YAML, a Workflow JS script, or selectable?~~ **Resolved:**
  FSM-loop YAML for v1 (see Codebase Research Findings below); Workflow JS is a follow-on with
  its own validation + portability story (see § Portability & Lock-in Analysis).
- Whether to support the "mine observed behavior" input mode (generate from `.ll/history.db` /
  session traces) in v1 or defer to a follow-on.
- How the shrink pass's "probe set" is defined for a non-executable-by-default workflow.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Output target — recommend FSM-loop YAML for v1.** Codebase evidence strongly favors YAML
  over Workflow JS: (a) the entire generator family already emits file artifacts that are
  validated by `ll-loop validate`; (b) emitted YAML can be re-validated with `ll-loop validate`
  (an `exit_code` evaluator), which makes the per-pass non-LLM discriminator real and satisfies
  MR-1 **by architecture**, exactly as the issue's Rank-1 lowering plan intends; (c) there is no
  in-repo validator for Workflow JS scripts, so a JS target would have no equivalent non-LLM
  gate. Treat "selectable / Workflow JS" as a follow-on, not v1. (Not a competing design choice
  requiring `/ll:decide-issue` — research resolves it toward a single default.)
- **MR-5 implication of `category: harness`.** Setting `category: harness` (the generator-family
  convention) makes `_validate_artifact_overwrite()` active. Since this is an iterative
  generate->evaluate cycle, declare `artifact_versioning: true` (loop snapshots each pass under
  `${context.run_dir}/`) rather than `artifact_versioning_ok: true` (which merely silences the
  warning for intentional overwrite). This keeps the per-iteration snapshots the brainstorm
  requires and aligns with the MR-5 acceptance criterion.
- **Shrink-pass probe set.** Define probes as a fixture set of brief->expected-outcome pairs
  written under `${context.run_dir}/probes/`; "outcome" for a YAML target is the deterministic
  result of `ll-loop validate` on the emitted artifact (and, where applicable, a `simulate` of
  the emitted loop). Removing a state and re-running `ll-loop validate` gives the external,
  binary, repeatable signal the issue's Rank-3 shrink pass calls for — no LLM judge needed.

## Portability & Lock-in Analysis (shim strategy)

_Added 2026-07-18 — analysis of vendor coupling for the two output targets, and the shim idea
that changes the calculus for the Workflow-JS follow-on._

**Principle: lock-in lives at the execution seam, not in the file format.** For both targets,
the artifact itself is inert data/code; what matters is who owns the runtime that executes it.

- **FSM YAML (v1 target):** the artifact runs on `ll-loop`, which *we own*. The only vendor
  coupling is wherever the executor invokes the LLM for `llm`/`llm_structured` states — a
  single adapter seam in our own code. Generated YAML is therefore the *portable* layer of the
  stack; this feature adds to it rather than to any Anthropic-specific layer. (For comparison:
  OpenAI Codex custom prompts and Gemini CLI custom commands/extensions/hooks are prompt-level
  reuse only — neither vendor has an analogue to a validated, evaluator-gated state-machine
  artifact.)
- **Claude Code dynamic-workflow JS (follow-on target):** scripts are plain JavaScript, but all
  semantics flow through runtime-injected globals — `agent()`, `pipeline()`, `parallel()`,
  `phase()`, `log()`, `budget`, `args`. These are host functions of the Claude Code workflow
  runtime (subagent spawn, permissioning, sandbox, resume journal), not npm imports; under
  plain Node the script dies on `agent is not defined`. Same host relationship as a GitHub
  Actions YAML to GitHub's runner.

**The shim strategy.** The runtime-global contract surface is *small*, which makes the JS
target portable in principle with modest effort:

- A shim implementing `agent(prompt, {schema, label, model})` against any backend (Anthropic
  API, OpenAI, Gemini, a local model, `codex exec` subprocess) plus `pipeline()`/`parallel()`
  (~20 lines of Promise plumbing each) yields basic-fidelity execution of any generated script
  outside Claude Code.
- What a shim does NOT replicate: the permission/sandbox model, worktree isolation,
  resume-with-cached-results, schema-retry enforcement, per-agent tool access. Research-style
  fan-out scripts port trivially; file-mutating migration scripts that lean on worktree
  isolation and edit permissions do not.
- Net: the JS target is *framework coupling*, not a proprietary format — acceptable lock-in
  risk **provided we own a shim**, because that moves the execution seam back into code we
  control (same as the YAML/`ll-loop` situation).

**Implication for the JS follow-on's MR-1 gate.** The refine pass rejected JS for v1 because
"no in-repo validator exists" — the shim strategy weakens that objection. A lint-grade non-LLM
validator for generated workflow scripts is realistic: (a) JS parse check; (b) `meta` block
pure-literal check (required `name`/`description`, no computed values); (c) banned-API check
(`Date.now()`, `Math.random()`, argless `new Date()` — rejected by the real runtime); (d) JSON
Schema validity of every `schema:` option; (e) runtime-global allowlist (script references only
`agent/pipeline/parallel/phase/log/budget/args` + JS builtins); and, with the shim, (f) an
actual **dry-run probe**: execute the script under the shim with `agent()` stubbed to return
canned fixtures, asserting it runs to completion — a true behavioral, deterministic,
exit-code-style gate that YAML `ll-loop validate` cannot match. This keeps v1 sequencing
unchanged (YAML first proves the lowering pipeline) but upgrades the JS target from
"no non-LLM gate possible" to "gate is buildable, and partly *stronger* than the YAML gate."

**Suggested follow-on issues (not in scope here):**
1. `ll-workflow-shim` — minimal portable runtime (`agent`/`pipeline`/`parallel` + stub mode)
   with a pluggable backend adapter; doubles as the dry-run probe executor.
2. `workflow-generator` JS output target — add a selectable `output: workflow-js` mode gated by
   the lint-grade validator + shim dry-run above.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — new built-in loop (NEW).
- `scripts/tests/test_builtin_loops.py` — **required**: add `"workflow-generator"` to the
  `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` (lines ~74–166). That test
  is an **exact-set match** against `BUILTIN_LOOPS_DIR.glob("*.yaml")` — adding the YAML without
  this entry fails the suite. Also add a dedicated `TestWorkflowGeneratorLoop` class modeled on
  `TestHtmlWebsiteGeneratorLoop` (line ~3290).
- No loop registry exists — discovery is a pure filesystem scan, so dropping the YAML into
  `scripts/little_loops/loops/` is sufficient for `ll-loop list`/`run`. `cmd_list()`
  (`scripts/little_loops/cli/loop/info.py:66`) calls `get_builtin_loops_dir()`
  (`scripts/little_loops/cli/loop/_helpers.py:825`) -> `rglob("*.yaml")` filtered by
  `is_runnable_loop()` (`scripts/little_loops/fsm/validation.py:2071`; requires `name` +
  `initial` + `states`/`flow`). `pyproject.toml`'s `little_loops/**` wheel glob bundles the new
  YAML automatically — no packaging change needed.

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — **required**: line 79 reads `**96 FSM loops**`; adding a runnable loop bumps the
  count to 97. `scripts/little_loops/doc_counts.py` (`verify_documentation()`) counts runnable
  loops via `loops_dir.rglob("*.yaml")` filtered by `is_runnable_loop()` and compares it against
  the count string in `DOC_FILES` (`README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`); only
  `README.md` carries the loop count. `ll-verify-docs` exits non-zero on the mismatch
  (`loops: documented=96, actual=97`). Run `ll-verify-docs --fix` or hand-edit the count. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles` — universal tests run over every
  runnable loop and will exercise the new file: `test_all_validate_as_valid_fsm` (fails on MR-1
  ERRORs), `test_all_have_description_field`, and `test_no_bare_bash_variable_in_shell_actions`
  (only the FSM namespaces `context|captured|prev|result|state|loop|env|messages|param` may use
  unescaped `${...}` in `shell` actions; every other brace must be written `$${...}`).
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — the generate->evaluate->score
  oracle sub-loop that generator-family loops delegate to via `loop: oracles/generator-evaluator`
  with a `with:` binding block.

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` and sibling generator loops — model
  the new loop's structure on these.
- `scripts/little_loops/loops/harness-optimize.yaml` — meta-loop reference for MR-1..MR-6 shape.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml` — **closest existing example of sequential compiler-like lowering** (7 passes: classify → validate-exit-code → bake-rubric → validate-exit-code → delegate → shell-measure×2 → LLM-judge-over-measurements); the primary reference for the Rank-1 compiler-lowering design; every LLM pass has a `shell` + `type: exit_code` gate before the next LLM pass begins.
- `scripts/little_loops/loops/canvas-sketch-generator.yaml` — in-line multi-pass generator with `init → captured.run_dir.output` absolute-path pattern, `snapshot` state that copies each iteration to `iter-N/` (MR-5 compliance), and `finalize` best-picker; best reference for per-iteration snapshot wiring and the `output_numeric` + `diff_stall` non-LLM gate pair.
- `scripts/little_loops/loops/apo-beam.yaml` — compact beam-search N-candidates pattern (`generate_variants → score_variants → select_best → route_convergence` with `output_contains: CONVERGED`); the reference for the Rank-2 scoped genetic graft at the state-graph sketch pass.
- `scripts/little_loops/loops/lib/common.yaml:118,148` — reusable `convergence_gate` (line 118) and `diff_stall_gate` (line 148) fragments; use via `fragment: convergence_gate` / `fragment: diff_stall_gate` in applicable states to satisfy MR-1 with minimal boilerplate.

### Tests
- `scripts/tests/test_builtin_loops.py:76` — `TestBuiltinLoopFiles.test_expected_loops_exist` maintains an **exact allowlist** via `.glob("*.yaml")`; add `"workflow-generator"` to the `expected` set or CI fails immediately.
- `scripts/tests/test_builtin_loops.py:3290` — `TestHtmlWebsiteGeneratorLoop` / `TestSvgImageGeneratorLoop` (line ~3405) — model the new `TestWorkflowGeneratorLoop` class on these (standard shape: `LOOP_FILE`, `data` fixture, `test_required_top_level_fields`, `test_artifact_versioning_declared`, `test_done_state_is_terminal`).
- `scripts/tests/test_builtin_loops.py:7742` — `TestOpenSCADModelGeneratorLoop` — the most recent generator test class; includes `test_artifact_versioning_declared` and per-state MR-1 non-LLM evaluator assertions; use as the direct template for state-level evaluator tests.
- `scripts/tests/test_builtin_loops.py:482` — `TestBuiltinLoopScratchIsolation` — MR-3 guard; verify that no shell action writes to bare `/tmp/` paths outside `${context.run_dir}`.
- `scripts/tests/test_harness_optimize.py` — meta-loop test patterns; reference for MR-1..MR-6 conformance assertions on the meta-loop shape.

_Wiring pass added by `/ll:wire-issue`:_
- **Doc-count gate (not a unit-test break, but CI-gating):** `scripts/tests/test_doc_counts.py`
  exercises `doc_counts.py`; the real gate is `ll-verify-docs` comparing the `README.md` loop
  count against the live `rglob`+`is_runnable_loop` count. Bump the README count (see Files to
  Modify) or `ll-verify-docs` fails. [Agent 1/2 finding]
- **Additional universal tests that auto-cover the new YAML** (in `TestBuiltinLoopFiles`, no new
  code — but the YAML must satisfy them): `test_no_bare_pass_token_in_output_contains`
  (line ~168 — no `output_contains` evaluator may use a bare `pattern: PASS`; use `ALL_PASS`/`ITERATE`),
  `test_all_failure_terminals_have_diagnostic_action` (line ~255 — a `diagnose`/`diagnose_failure`
  state paired with a `failed`/`error`/`aborted` terminal must carry an `action:`/`fragment:` and
  not be terminal itself), and `TestBuiltinLoopValidatorRatchet` (~line 7540 — new loops must emit
  no `capture-ordering` / `partial-route` / `loop-reference` warnings without an ALLOWLIST entry). [Agent 3 finding]
- **MR-3 explicit per-class guard to copy:** `test_no_bare_loops_tmp_writes` (line ~6484, used in
  `TestExamplesMiner`) and `test_run_dir_used_throughout` (line ~6508 — asserts `${context.run_dir}`
  appears in every shell-state action). Add both to `TestWorkflowGeneratorLoop`. [Agent 3 finding]
- **Template precision:** the canonical per-state MR-1 assertion is
  `TestOpenSCADModelGeneratorLoop.test_render_views_has_output_contains_captured` (line ~7904 —
  asserts `evaluate.type == "output_contains"` + `pattern == "CAPTURED"`); replicate one such
  per-LLM-pass non-LLM-evaluator assertion per lowering pass. `TestInteractiveComponentGeneratorLoop`
  (line ~8031) is the most recent class and adds `test_max_steps_and_timeout_defined`. [Agent 3 finding]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` and/or `AUTOMATIC_HARNESSING_GUIDE.md` — document
  the new generator loop.
- `docs/reference/loops.md` — built-in loops catalog; add a `workflow-generator` entry.
- `.claude/CLAUDE.md` Automation & Loops listing if user-facing.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — **manually-maintained** catalog (no auto-generator or drift
  test exists — `loops_reference.py` / `ll-loop reference` / `test_loops_reference_doc.py` are
  **not present**, so hand-edit). Three required edit sites: (a) the `### Harness Examples`
  quick-reference table (~line 1249) — add a `workflow-generator` row alongside the other
  generator-family loops; (b) the GAN-style generator-evaluator cross-reference sentence
  (~line 1281) enumerating `html-website-generator`, `svg-image-generator`, … — add
  `workflow-generator` **iff** the loop delegates to `oracles/generator-evaluator`; (c) a new
  full `### workflow-generator — <subtitle>` detail section (invocation, context-vars table, FSM
  flow, output files, notes) modeled on `### html-website-generator` / `### openscad-model-generator`.
  NOTE: this file is already modified in the working tree for **BUG-2347** (unrelated
  `sprint-build-and-validate` section); add FEAT-2354 content alongside those pending edits. [Agent 2 finding]
- `docs/reference/loops.md` — beyond the new `## workflow-generator` catalog section, extend the
  `## oracles/generator-evaluator` "Used by `html-website-generator`, `svg-image-generator`, …"
  sentence (~line 396) to include `workflow-generator` **iff** it delegates via a
  `loop: oracles/generator-evaluator` state. [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `workflow-generator.yaml` to the
  `## See Also` "Real-world generator-evaluator harness" list (~line 1099, currently
  `html-anything.yaml` / `html-website-generator.yaml` / `svg-image-generator.yaml`). [Agent 2 finding]
- `scripts/little_loops/loops/README.md` — loop-directory README; check whether it enumerates
  generator loops and add `workflow-generator` if so (advisory). [Agent 1 finding]

### Configuration
- N/A (uses existing `loops.run_defaults`; per-run artifacts under `${context.run_dir}/`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Meta-loop auto-detection (no opt-in needed).** `_is_meta_loop()`
  (`scripts/little_loops/fsm/validation.py`) flags a loop if any state action matches
  `loops/[\w-]+\.yaml`, `skills/.../SKILL.md`, `agents/*.md`, `commands/*.md`, or
  `.claude/(CLAUDE.md|settings)`; or it imports `lib/benchmark.yaml`; or any action contains the
  token `yaml_state_editor`/`replace_action`. Because this loop *emits a `loops/*.yaml`
  artifact*, it is classified as a meta-loop automatically and the MR-1 **ERROR** gate applies.
- **MR rule enforcement locations** (all in `scripts/little_loops/fsm/validation.py`):
  MR-1/MR-2 `_validate_meta_loop_evaluation()`; MR-3 `_validate_artifact_isolation()` (regex
  `\.loops/tmp/[\w./-]+`); MR-4 `_validate_partial_route_dead_end()`; MR-5
  `_validate_artifact_overwrite()` (**only fires for `category: harness`**); MR-6
  `_validate_generator_fix_discipline()`. Suppression flags live on the `FSMLoop` dataclass
  (`scripts/little_loops/fsm/schema.py`): `meta_self_eval_ok`, `shared_state_ok`,
  `partial_route_ok`, `artifact_versioning`, `artifact_versioning_ok`, `generator_fix_ok`.
- **Non-LLM evaluator types that satisfy MR-1** (`NON_LLM_EVALUATOR_TYPES`, derived in
  `validation.py`; impls in `scripts/little_loops/fsm/evaluators.py`): `exit_code`,
  `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`,
  `action_stall`, `harbor_scorer`, `mcp_result`, `classify`. The LLM evaluators
  `llm_structured` / `comparator` / `contract` do **not** count.
- **`${context.run_dir}` injection.** `cmd_run()` (`scripts/little_loops/cli/loop/run.py`) sets
  `fsm.context["run_dir"] = .loops/runs/<name>-<YYYYMMDDTHHMMSS>/` and `mkdir(parents=True,
  exist_ok=True)` *before* executor construction; `cmd_resume()`
  (`scripts/little_loops/cli/loop/lifecycle.py`) re-injects it on resume. Use
  `${context.run_dir}` directly in `shell` actions (valid namespace, no `$$` escaping).
- **Generator-family convention** (model on `html-website-generator.yaml` /
  `svg-image-generator.yaml`): top-level `category: harness`, `input_key: description`,
  `required_inputs: ["description"]`, `max_steps` + `timeout`; an `init` shell state that does
  `echo "$(pwd)/$DIR"` with `capture: run_dir` to get an absolute path; delegation to
  `loop: oracles/generator-evaluator` with `with:` keys `run_dir`, `generate_prompt`, `rubric`,
  `pass_threshold` (+ optional `artifact_path`). Rubrics must end with a binary sentinel like
  `ALL_PASS`/`ITERATE` — a bare `PASS` token fails `test_no_bare_pass_token_in_output_contains`.

## Implementation Steps

1. Scaffold `workflow-generator.yaml`, modeling structure on `html-website-generator.yaml`
   and borrowing the meta-loop shape from `harness-optimize.yaml`.
2. Implement the six sequential lowering passes (intent capture → state-graph sketch →
   evaluator attachment → routing-table resolution → artifact emission → adversarial
   minimum-coupling shrink).
3. Pair every `check_semantic`/`llm_structured` state with a non-LLM evaluator
   (`ll-loop validate` exit-code, schema check, diff-stall) to satisfy MR-1 by architecture.
4. Add per-run `${context.run_dir}/` artifact isolation (MR-3) and per-iteration snapshots
   (MR-5) for the generate→evaluate cycle.
5. Resolve the remaining open design questions (probe-set definition for the shrink pass;
   mined-input mode) and scope the genetic graft to the state-graph pass. (Output target is
   resolved: FSM YAML for v1; Workflow JS deferred to the shim follow-on — see § Portability
   & Lock-in Analysis.)
6. Add `test_builtin_loops.py` coverage and verify with `ll-loop validate` (MR-1..MR-6) plus a
   `ll-loop diagnose-evaluators` discriminator-health check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors for the steps above:_

1. Scaffold from `scripts/little_loops/loops/html-website-generator.yaml` (top-level fields +
   `plan -> run_gen_eval` delegation) and `scripts/little_loops/loops/harness-optimize.yaml`
   (the `baseline_score -> propose -> apply -> score -> gate -> commit/revert` meta-loop spine;
   `gate` uses `fragment: convergence_gate` with a 4-way `route:` of target/progress/stall/error
   — itself a non-LLM evaluator).
2. For the MR-1 pairing pattern, follow `harness-single-shot.yaml`'s
   `check_concrete` (`exit_code`) -> `check_semantic` (`llm_structured`, with
   `source: "${captured.<state>_result.output}"`) -> `check_invariants` (`output_numeric`)
   chain so every LLM-judged pass is bracketed by a deterministic gate.
3. Wire each lowering pass's discriminator to `ll-loop validate` on the in-progress artifact via
   a `shell` state with `evaluate: {type: exit_code}` (see `harness-optimize.yaml`'s
   `load_directive`/`check_queue`).
4. Keep all intermediate files under `${context.run_dir}/` (MR-3) and set
   `artifact_versioning: true` for per-pass snapshots (MR-5).
5. Add `"workflow-generator"` to `test_expected_loops_exist`'s `expected` set FIRST (otherwise
   the existing suite goes red), then add `TestWorkflowGeneratorLoop` mirroring
   `TestHtmlWebsiteGeneratorLoop`/`TestSvgImageGeneratorLoop`
   (`scripts/tests/test_builtin_loops.py:3290`+), including a `test_no_bare_loops_tmp_writes`
   MR-3 guard.
6. Verify: `python -m pytest scripts/tests/test_builtin_loops.py -k workflow_generator -v`,
   `ll-loop validate workflow-generator`, and `ll-loop diagnose-evaluators workflow-generator`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation
(all doc/catalog edits are manual — no auto-generator exists for any of them):_

7. **Bump the loop count in `README.md`** (line 79, `96 FSM loops` → `97`) — gated by
   `ll-verify-docs` / `doc_counts.py`. Without this, the docs-count check fails CI.
8. **Update `docs/guides/LOOPS_REFERENCE.md`** — add a `workflow-generator` row to the
   `### Harness Examples` table, extend the GAN-style cross-reference sentence (iff delegating to
   `oracles/generator-evaluator`), and add a new full `### workflow-generator` detail section.
   Coordinate with the pending BUG-2347 edits already in the working tree.
9. **Update `docs/reference/loops.md`** — add a `## workflow-generator` catalog section and extend
   the `## oracles/generator-evaluator` "Used by …" sentence (iff delegating).
10. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`** — add `workflow-generator.yaml` to the
    `## See Also` real-world generator-evaluator harness list.
11. **Verify docs wiring**: run `ll-verify-docs` (count parity) and `ll-check-links` (no broken
    anchors introduced by the new doc sections) alongside the existing
    `pytest … -k workflow_generator`, `ll-loop validate`, and `ll-loop diagnose-evaluators` checks.

## Use Case

A user has just finished a tedious, repeatable multi-step task (e.g., "triage a new bug report:
read it, grep for the offending code, confirm repro, draft a fix plan, open a PR"). They run the
new generator loop with a one-paragraph description of that work and get back a validated,
minimal, reusable Claude Code workflow they can re-invoke on the next bug — without writing any
FSM/YAML by hand.

## Acceptance Criteria

- [ ] `ll-loop validate workflow-generator` passes with zero MR-1..MR-6 violations (or
      documented top-level suppression flags with justification).
- [ ] `ll-loop list` enumerates `workflow-generator` as a built-in loop.
- [ ] Given a prose brief, a run emits a workflow artifact and writes all intermediate
      artifacts under `${context.run_dir}/`, with a per-iteration snapshot retained for each pass.
- [ ] When the output target is FSM YAML, the emitted artifact itself passes `ll-loop validate`.
- [ ] Every `check_semantic`/`llm_structured` state in the loop is paired with a non-LLM
      evaluator (verified by `ll-loop validate` MR-1 and an automated test).
- [ ] The adversarial shrink pass reduces the emitted state count versus the pre-shrink draft
      on at least one probe fixture, demonstrating minimum-coupling behavior.
- [ ] `test_builtin_loops.py` covers validation + meta-loop conformance (MR-1 paired evaluators,
      MR-3 run_dir isolation, MR-5 artifact versioning) and passes.

## Impact

- **Priority**: P3 — Net-new capability that closes the "generate the automation artifact
  itself" gap; valuable and self-extending, but no existing behavior depends on it and there is
  a manual fallback (`/ll:create-loop`, hand-authoring), so it is not blocking.
- **Effort**: Large — A six-pass meta-loop with novel evaluator wiring (per-pass non-LLM
  discriminators), a first-of-its-kind adversarial minimum-coupling shrink pass, plus tests and
  docs. Existing generator loops provide structural precedent but not the lowering pipeline.
- **Risk**: Medium — Additive (a new file; no change to existing loops) keeps blast radius low,
  but meta-loop self-evaluation validity and the shrink pass's probe-set definition are
  non-trivial; the MR-1..MR-6 gates and a `diagnose-evaluators` health check mitigate.
- **Breaking Change**: No.

## Related Key Documentation

- [docs/guides/HARNESS_OPTIMIZATION_GUIDE.md](../../docs/guides/HARNESS_OPTIMIZATION_GUIDE.md) —
  meta-loop optimizer taxonomy and the `diagnose → propose → apply → measure-externally` shape.
- [docs/guides/AUTOMATIC_HARNESSING_GUIDE.md](../../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md) —
  `ll-loop run --baseline` validation that a harness beats an unguided LLM call.
- `.claude/CLAUDE.md` § Loop Authoring — MR-1..MR-6 meta-loop design rules this loop must satisfy.

## Source

Captured from brainstorm: `.loops/runs/brainstorm-20260627T164631/brainstorm.md`.

## Session Log
- issue-review (Cowork session) - 2026-07-18 - Resolved output-target question to FSM YAML v1 in Summary; added § Portability & Lock-in Analysis (shim strategy) with lint-grade validator sketch + shim dry-run gate for the Workflow-JS follow-on; suggested `ll-workflow-shim` and `output: workflow-js` follow-on issues.
- backlog-grooming - 2026-07-03T00:00:00Z - Parented to EPIC-1811 (was unparented; assigned per /ll:create-epics-from-unparented sweep).
- `/ll:wire-issue` - 2026-06-27T22:49:38 - `154c9238-9065-452a-b00a-b2db627068e4.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:37:06 - `567c4d00-9ba7-4b64-8c58-6d0231d254b8.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:37:00 - `6d019a8f-4362-4bbd-9ab1-93c73b60cd68.jsonl`
- `/ll:refine-issue` - 2026-06-27T22:29:52 - `1e821262-4150-4a9e-ab67-e0b3c244e06d.jsonl`
- `/ll:format-issue` - 2026-06-27T22:17:48 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:capture-issue` - 2026-06-27T22:11:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e61208ac-a505-4f00-9646-b676ce7f4f5f.jsonl`

---

## Status

**Current Status**: open
