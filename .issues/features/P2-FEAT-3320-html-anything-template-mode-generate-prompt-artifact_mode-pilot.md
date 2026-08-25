---
id: FEAT-3320
type: FEAT
title: html-anything template-mode generate prompt (artifact_mode pilot)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:25:58Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- fsm
- templates
- prompt
depends_on:
- FEAT-3318
relates_to:
- FEAT-3036
learning_tests_required:
- playwright
- jinja2
---

# FEAT-3320: html-anything template-mode generate prompt (artifact_mode pilot)

## Summary

Split out of FEAT-3318 at the 2026-08-25 pre-implementation review. FEAT-3318 lands
the `artifact_mode: template` plumbing — the schema field, the static and runtime
gates, atomic directory promotion, and a round-trip test against a hand-written
`.llat/` fixture. None of that requires an LLM to produce a template.

This issue is the other half: teach `html-anything` to actually *generate* a
`manifest.yaml` + `template.*.j2` + `data.json` triple instead of a fused
`index.html`, selected per-run via `--context artifact_mode=template`. It is the
pilot that proves the epic's design principle 1 ("loops emit template + data
natively") works in practice, and the precondition for rolling the variant out to
the remaining eight HTML-family loops.

## Current Behavior

- `html-anything.yaml:117-186` delegates to `oracles/generator-evaluator` via a
  `loop:` thin wrapper, passing a `generate_prompt` that instructs the model to
  "Write a single self-contained HTML file to `${captured.run_dir.output}/index.html`"
  (`:133`). There is one prompt and one output shape.
- The oracle's evaluate cycle is built around that single file: a Playwright
  screenshot of `file://.../${context.artifact_path}` (`generator-evaluator.yaml:82`,
  `artifact_path` defaulting to `index.html` at `:52`), then an LLM rubric score
  over `screenshot.png` (`html-anything.yaml:151-155`).
- With FEAT-3318 landed, a loop *can* declare `artifact_mode: template` and have a
  `.llat/` directory promoted and validated — but no built-in loop produces one.
  Every route from a loop to a template still runs through `ll-artifact templatize`
  (FEAT-3308), the lossy LLM-extraction path.

## Expected Behavior

`ll-loop run html-anything --context artifact_mode=template` produces a validated
`.llat/` directory that `ll-artifact render` consumes by name, with the same
iterate-until-`ALL_PASS` quality cycle the `file` mode gets today. The default
(`file`) path is byte-for-byte unchanged.

## Motivation

FEAT-3318's plumbing is inert without a producer. It is also unproven: the whole
reason this was split out is that "an LLM reliably emits a schema-valid
manifest + Jinja2 body + conforming data.json, repeatedly, under critique
iteration" is an empirical claim, not a mechanical one. Proving it on one loop
before rewriting nine prompts is the cheap ordering.

## Proposed Solution

### The evaluate cycle is the hard part, not the generate prompt

The generate prompt rewrite is mostly mechanical. The problem is that a `.llat/`
directory has nothing to screenshot, and the oracle's entire quality loop —
screenshot, rubric score, critique, iterate — is downstream of a renderable HTML
file at a fixed path.

Proposed: **render the template to HTML on each iteration, then screenshot the
render.** The oracle already parameterizes the screenshot target
(`artifact_path`, `generator-evaluator.yaml:43,52`), so the wrapper passes a
rendered path rather than the template directory. This keeps the entire
evaluate/score/critique cycle unchanged and untouched — the template becomes an
extra upstream step, not a fork of the oracle.

Open question for implementation: whether the render runs as a state inside the
wrapper or as an addition to the generate prompt's own instructions (i.e. the
model runs `ll-artifact render` itself as its last action). Prefer the former —
a deterministic shell step is cheaper and cannot be skipped by a model that
decides it is done early.

Consequence worth checking against ENH-2903: a render failure produces no HTML,
which produces no screenshot, which the oracle already models as a
screenshot-miss with a consecutive-miss abandon gate
(`generator-evaluator.yaml:89-143`). A malformed template may therefore surface
as a screenshot-miss rather than as a template error — the abandon path should
report the render failure, not a generic missing-screenshot message.

### Mode selection

Per FEAT-3318's § Mode selection: `artifact_mode` is a `context:` var on
`html-anything` (alongside `pass_threshold` / `design_tokens_context`), read by
`promote_run_artifact` with the top-level field as the default. Selection uses
the existing `ll-loop run --context artifact_mode=template`
(`cli/loop/__init__.py:294`) — no new CLI flag.

The generate prompt branches by interpolating that var. FSM prompts are static
text, so this is a conditional block in the prompt body, not two prompts.

**`html-anything.yaml` has no `artifact_output` block today** — `hitl-md.yaml` is
the only loop that declares one. FEAT-3318's static gate requires one whenever
the effective mode is `template`, so this issue must add it. Consequence to
handle deliberately: an `artifact_output` block is mode-independent, so adding it
makes `html-anything` start promoting `index.html` into `promotion_dir` on
**every** run — including default `file`-mode runs that this issue otherwise
leaves untouched. That is a behavior change to the unmodified path, and it needs
either an explicit sign-off or an `on:` allowlist narrow enough to keep the
default path quiet.

### Scope bound

`html-anything` only. The remaining eight HTML-family loops are a follow-up,
scoped once this pilot reports an actual success rate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **Mode-branch prose convention confirmed unchanged post-FEAT-3318**: `oracles/research-coverage.yaml`'s `academic_mode` remains the sole live example of "inline conditional prose, no template-conditional syntax" — declared in `context:` (`:29-39`) and interpolated raw into natural-language branches at `:57-64`, `:110-122`, `:150-179`, `:248-251`, `:280-330`, `:411-412` (e.g. "Query phrasing (academic_mode = ${context.academic_mode}): If academic_mode is true: ... If false: ..."). No newer instance of this convention landed elsewhere in the repo.
- **`artifact_path` override via `with:` confirmed unchanged**: `svg-image-generator.yaml:67-71` and `flux-image-generator.yaml:102-114` still pass `artifact_path` as a sibling key alongside `run_dir` in their `oracles/generator-evaluator` `with:` block. `html-anything.yaml`'s own `with:` block (`:122-182`) still passes only `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` — no `artifact_path` today.
- **`ll-artifact render` CLI contract** (`docs/reference/CLI.md:4512-4535`): resolves `<template>` path-first as a `.llat/` dir, falling back to `config.artifacts.templates_dir/<name>.llat`; render context is `data.json`'s top-level keys plus reserved `ll.theme_css`/`ll.assets`; a top-level `ll` key in `data.json` or `data_schema` is a validation error; `--output` names a directory, the actual filename comes from `manifest.yaml`'s `output:` key.
- **No FSM prompt anywhere instructs a model to emit the manifest+template+data triple** — confirmed again post-landing (grep for `manifest\.yaml|data_schema|\[\[=|renderer: jinja2` across the repo returns only FEAT-3318's own test fixtures, `artifact_templates.py`, the `ll-artifact` CLI modules, and one unrelated false positive in `cli-anything-bootstrap.yaml`). This issue's template-mode `generate_prompt` has zero prior art to model wording after.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-anything.yaml:117-186` — the `generate_prompt`
  template-mode branch, the `artifact_mode` context var, the per-iteration render
  step, and the `artifact_path` passed through `with:`
- `scripts/little_loops/loops/html-anything.yaml:187-201` — `finalize_done` reports
  `index.html`; template mode reports the `.llat/` contents instead

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:43,52,82` —
  `artifact_path`; the screenshot target this issue repoints. **Do not fork the
  oracle** — eight other loops delegate to it.
- `scripts/little_loops/cli/artifact/render.py:72` — `cmd_render`, invoked per
  iteration

### Tests
- `scripts/tests/test_builtin_loops.py` — conformance for the modified
  `html-anything.yaml` (both modes parse, validate, and route)
- A `file`-mode regression asserting the default path is unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py:62-68`
  (`test_policy_builder_renders_byte_identically_to_golden_fixture`) — the
  byte-for-byte-unchanged pattern to model the file-mode regression test after
  (golden fixture + exact `.read_bytes()` equality). Corrects the earlier
  refine-issue research note claiming no such shape exists in this codebase —
  it exists for CLI-command output, not loop YAML, so still needs adapting.
  [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:~13230-13269`
  (`test_snapshot_routes_to_score_gate`, `test_snapshot_writes_screenshot_misses_counter`,
  `test_score_gate_routes_fresh_screenshot_to_score`,
  `test_check_screenshot_abandon_routes_to_summary_on_cap`,
  `test_record_screenshot_skip_falls_through_to_stall_chain`,
  `test_screenshot_abandoned_summary_emits_abandoned_key`) — existing
  ENH-2903 abandon-gate coverage on `oracles/generator-evaluator.yaml`; must
  keep passing unmodified since the oracle is not forked. None currently
  assert on the literal abandon message text
  (`generator-evaluator.yaml:301`), so a render-failure-specific message can
  be added alongside it without touching these assertions. [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the
  template-mode invocation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (`html-anything` section, ~lines 1510-1582)
  — the `run_dir` context-var row lists file-mode-only outputs (`index.html`,
  `brief.md`, `rubric.md`, `critique.md`, `screenshot.png`), the context-variables
  table has no `artifact_mode` row, and the usage examples/override block show
  only the `file`-mode invocation. Needs an `artifact_mode` row plus a
  template-mode example. [Agent 2 finding]
- `docs/reference/loops.md` (`oracles/generator-evaluator` section, ~line 474)
  — the `artifact_path` parameter description and its `run_gen_eval`
  invocation example are file-mode only; add a note or example for the
  template-mode `with:` override (mechanism itself is unchanged — the oracle
  is not forked). [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **No existing loop invokes `ll-artifact render` as a state**: a grep for `ll-artifact render` across `scripts/little_loops/loops/**/*.yaml` returns zero hits. This issue's per-iteration render step has no direct precedent to model after — it is a genuinely new wiring shape, not an established convention.
- **Mode-branch conventions this codebase already holds** (two live, non-superseding shapes — pick one knowingly rather than defaulting):
  - *Inline conditional prose*: `oracles/research-coverage.yaml:29-39,57-65,110,150,248,280` interpolates the raw context value directly into prompt text (`${context.academic_mode}`) and phrases the branch as natural-language instructions ("If academic_mode is true: ... If false: ..."). There is no `{% if %}`/Jinja conditional syntax anywhere in the FSM prompt-rendering path (confirmed against `fsm/interpolation.py`) — this matches the issue's own Proposed Solution statement that "FSM prompts are static text, so this is a conditional block in the prompt body, not two prompts."
  - *Dedicated dispatch state*: `rn-implement.yaml:183-194` (`dequeue_next`) uses a `shell`/`exit_code`-evaluated state (`test "${context.schedule_mode}" = "value_ranked" && exit 0 || exit 1`) to route to one of two full downstream states (`fifo_pop` vs `select_next`), with both `on_no` and `on_error` falling back to the pre-existing legacy path.
  - Default-preservation guard convention (BUG-1947): a runner-injected context default that is an empty string (like `design_tokens_context: ""` in this same file) must be checked for **truthiness**, not key-existence, since the key is always declared — the same shape applies if `artifact_mode` is given an empty-string/`"file"` default rather than being absent when unset.
- **`artifact_path` override precedent**: two sibling wrapper loops already override the oracle's `artifact_path` parameter via their `with:` block — `svg-image-generator.yaml:71` (`artifact_path: "image.svg"`) and `flux-image-generator.yaml:111` (`artifact_path: "image.png"`) — confirming the mechanism this issue proposes reusing (repoint `artifact_path` at a rendered file) is the established way consumers customize the oracle's screenshot target without forking it.
- **ENH-2903's abandon gate has no cause-distinction mechanism today**: `evaluate`'s `on_yes`/`on_no`/`on_error` all route to the same `snapshot` state (`generator-evaluator.yaml:83-85`); a miss is tracked only as a consecutive-count (`.screenshot_misses`), with no signal anywhere for *why* a screenshot was missed. ENH-2903's own resolution explicitly rejected a harder `on_error: failed` split as "too blunt." A render-failure-specific message (this issue's Acceptance Criteria) has no existing mechanism to build on within the oracle's current routing shape, and the oracle is out of bounds to fork.
- **No existing conformance test asserts byte-for-byte-unchanged prompt text**: `test_builtin_loops.py`'s current `html-anything` coverage (and the closest analog, `academic_mode` coverage for `research-coverage.yaml`) asserts structural facts and text-fragment presence/absence, never full-string/hash equality on a `generate_prompt` value. This issue's "file-mode regression must stay byte-for-byte unchanged" acceptance criterion has no existing test shape to copy — the regression test will need a new assertion style (e.g. exact-string or hash comparison), not an extension of the existing fragment-presence style.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **No prompt anywhere in this codebase currently instructs a model to emit a `manifest.yaml` + `template.*.j2` + `data.json` triple** — that shape is produced today only by deterministic code, `cli/artifact/templatize.py:899-903` (`Path.write_bytes`/`write_text`), never by an LLM-facing prompt. This issue's template-mode `generate_prompt` branch has zero prior art to model wording after, beyond the schema contract itself (see Program Design).
- **`test_builtin_loops.py`'s established multi-mode conformance pattern** is `TestResearchCoverageOracle` (`:14025-14107`): a `parameters` block check (`"academic_mode" in params`, not-required) plus per-mode text-fragment presence checks on the raw `action` string (e.g. `"## BibTeX" in action`), never structural branch parsing or full-string equality. `TestHtmlAnythingLoop` (`:10303-10402`) already follows the same fixture/class shape but has no mode-branching tests yet — the new template-mode conformance test should extend it with fragment-presence assertions in this style, and the separate byte-for-byte file-mode regression (no existing shape to copy, confirmed absent by both research passes) needs its own exact-string/hash assertion, not an extension of the fragment-presence style.

## Program Design

### Types

N/A — no new data shape is introduced; `artifact_mode` is a plain string context
var, not a new dataclass/schema.

### Signatures

- `cmd_render(args: argparse.Namespace, logger: Logger) -> int`
  (`scripts/little_loops/cli/artifact/render.py:72`) — exit `0` on success, exit
  `1` uniformly for every failure category (unresolvable template, invalid
  manifest, missing/malformed/schema-invalid data, output-path collision, bad
  `--source`, lockfile-write failure).
- `run_gen_eval`'s existing `with:` binding (`html-anything.yaml:122,148,182`)
  passes `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` into
  `oracles/generator-evaluator`; this issue adds `artifact_path` as a new key in
  that same binding.

### Call Path

`ll-loop run html-anything --context artifact_mode=template` ->
`run_gen_eval` (`html-anything.yaml:117`) -> `oracles/generator-evaluator` with a
template-shaped `generate_prompt` + a rendered `artifact_path` ->
`ll-artifact render` (per iteration, for the screenshot) -> Playwright screenshot ->
rubric score -> `finalize_done` -> `promote_run_artifact` (FEAT-3318) ->
`<templates_dir>/{run_id}-html-anything.llat/`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **Current `context:` block** (`html-anything.yaml:24-28`) declares exactly `description`, `pass_threshold: 7`, `design_tokens_context: ""` — no `artifact_mode` key exists yet. FEAT-3318 (this issue's dependency) is itself still `status: open` with zero code hits for `artifact_mode` anywhere in the tree.
- **Current `run_gen_eval` `with:` block** (`html-anything.yaml:122,148,182`) passes exactly `run_dir`, `generate_prompt`, `rubric`, `pass_threshold` into `oracles/generator-evaluator` — it does **not** currently pass `artifact_path`, so the oracle's own default (`"index.html"`, `generator-evaluator.yaml:52`) applies implicitly today. Adding template mode means adding an `artifact_path` binding here for the first time.
- `cmd_render(args: argparse.Namespace, logger: Logger) -> int` (`scripts/little_loops/cli/artifact/render.py:72`) — exit `0` on success, exit `1` (uniformly, no distinct codes) for every failure category: unresolvable template, invalid manifest, missing/malformed/schema-invalid data, an existing-file collision at the output path, a bad `--source`, or a lockfile-write failure.
- **Rendered filename is manifest-controlled, not caller-controlled**: `render_to_disk` (`render.py:36-69`) writes to `output_dir / template.manifest["output"]` — only the containing directory is settable via `-o`, the filename itself comes from `manifest.yaml`'s `output` key. Consequence for this issue: the per-iteration `artifact_path` value passed to the oracle must be `<rendered-output-dir>/<manifest.output>`, not an arbitrary fixed name the wrapper chooses.
- **`promote_run_artifact` is currently a no-op for this loop**: it returns `None` whenever `fsm.artifact_output is None` (`fsm/persistence.py:753`), and `html-anything.yaml` declares no top-level `artifact_output:` key today. FEAT-3318 must land the `artifact_output`/`artifact_mode`-aware promotion logic before this issue's generate-prompt work has anything to promote into a `.llat/` directory — confirms the existing `depends_on: FEAT-3318` frontmatter edge is load-bearing, not incidental.
- `--context KEY=VALUE` (`cli/loop/__init__.py:294`, applied in `cli/loop/run.py:184-188`) is a fully generic mechanism — it does a plain `fsm.context[key] = value` string assignment with no artifact-specific dispatch. Setting `artifact_mode=template` today would only add an undeclared context key; nothing currently reads it.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **The render step has one available mechanism, and it is already exercised three times elsewhere**: FSM states have exactly four `action_type` values (`prompt`, `slash_command`, `shell`, `mcp_tool` — `fsm/schema.py:629-631,694`); there is no dedicated `type: shell`/`type: cmd` primitive. A shell state's `action:` is interpolated then run as `bash -c "<action>"` (`fsm/runners.py:117,284-306`), reached via `_action_mode()` (`fsm/executor.py:2843-2858`). Precedent for capturing an `ll-*` CLI invocation's output for a later state: `rn-remediate.yaml:467-495` (`capture: ll_auto_output`, running `ll-auto ... | tee ...; exit $?`) and the smaller `rn-remediate.yaml:113-116` (`ll-issues format-check "$ID"`). A `capture:` on a shell state writes `{output, stderr, exit_code, duration_ms, failure_type}` into `${captured.<name>.*}` (`fsm/executor.py:2369-2389`).
- **`oracles/generator-evaluator.yaml`'s full 11-state cycle** (`initial: generate`, `max_steps: 40`): `generate` (`:55-72`, routes `on_yes`/`on_no`/`on_partial` all to `evaluate`, `on_error: failed`) -> `evaluate` (`:74-85`, playwright screenshot of `${context.artifact_path}`, `on_yes`/`on_no`/`on_error` all to `snapshot`) -> `snapshot` (`:87-131`, ENH-2903, sole writer of `.screenshot_misses`) -> `score_gate` (`:133-154`) -> `check_screenshot_abandon` (`:156-179`, hardcoded cap 3) / `record_screenshot_skip` (`:181-191`) -> `score` (`:193-224`) / `record_score` (`:226-244`) -> `check_stall` (`:246-264`) -> `check_diff_stall` (`:266-279`, loops back to `generate` or `done`) -> terminals `done`/`failed`/`screenshot_abandoned_summary`->`screenshot_abandoned`/`max_steps_summary`.
- **Render-state insertion point**: between `generate` and `evaluate` — a new `render` state, routed to unconditionally from `generate` (mirroring `generate`'s existing "route everything downstream, let evaluate/snapshot/score_gate own the real gate" convention, `:55-72`'s ENH-1907 comment), itself routing unconditionally to `evaluate`. `evaluate`'s `${context.artifact_path}` is bound once at oracle-invocation time via the parent's `with:` block (`svg-image-generator.yaml:71`, `flux-image-generator.yaml:111` precedent) — it is not re-read per iteration from a captured value, so the wrapper must compute the rendered file's expected path itself (manifest-controlled filename, `render_to_disk`, `render.py:36-69`) rather than deriving it from the render state's `capture:`.
- **ENH-2903 abandon-gate mechanics, concretely**: `.screenshot_misses` is written solely by `snapshot` (`:97-130`); the abandon threshold check lives in a *separate* state, `check_screenshot_abandon` (`:156-179`, hardcoded `screenshot_max_step_attempts=3`). No file or context key anywhere records *why* a miss occurred. A render-failure-specific message (this issue's AC) needs a new side-channel — e.g. a `.miss_reason` file written by `snapshot` (or a new pre-`snapshot` state) and read only by `screenshot_abandoned_summary` (`:287-303`) when composing its final message — without touching `evaluate`'s undifferentiated routing (`:83-85`) or `check_screenshot_abandon`'s cap logic. `cmd_render` (`render.py:72`) itself has no distinct exit codes to key this off of (exit 1 uniformly for every failure category) — the differentiator would have to come from parsing `${captured.render_step.output}`/`.stderr` text.
- **The `.llat/` contract the template-mode generate prompt must describe precisely** (`artifact_templates.py`): `manifest.yaml` requires exactly `name, version, renderer, output, data_schema` (`renderer` must be `"jinja2"`); `data_schema` is a restricted JSON-Schema-like subset (`type ∈ {object,array,string,number,integer,boolean,null}`, keys limited to `type,required,properties,items,enum,description`, `:29-30,85-140`) that rejects a top-level `ll` key (`:190-197,245-248`, reserved for render context); exactly one `template.*.j2` file is required — zero or multiple both fail (`find_template_body`, `:275-285`); the Jinja environment uses **non-default delimiters** `[[= =]]` (variables), `[[% %]]` (blocks), `[[# #]]` (comments), `StrictUndefined`, `autoescape=False` (`build_environment`, `:252-272`) — a model instructed with plain `{{ }}`/`{% %}` Jinja syntax will produce an invalid template.

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **FEAT-3318 has landed (status: done, commit a63c5d939)** — the findings below supersede this issue's earlier claims that FEAT-3318 was still open with zero `artifact_mode` code hits. `html-anything.yaml` itself remains untouched by FEAT-3318 (confirmed: no `artifact_output`/`artifact_mode` in the file today) — the wiring is still entirely FEAT-3320's own scope.

- **Correction to the Call Path claim above**: default template-mode promotion is keyed by **loop name only**, not run id — `_promote_template_artifact` (`scripts/little_loops/fsm/persistence.py:802-897`) computes `dest = <config.artifacts.templates_dir>/<fsm.name>.llat` (line 843-846) when no `to:` override is set. The Call Path's `{run_id}-html-anything.llat/` naming does not match the landed code; the correct default destination is `<templates_dir>/html-anything.llat`. An explicit `to:` override (ending in `.llat` per the static gate's WARN check) is the only way to get a run-id-scoped or otherwise customized destination.
- **Effective-mode resolution, concretely**: `_effective_artifact_mode(fsm)` (`fsm/validation/structural_rules.py:857-863`) = `fsm.context.get("artifact_mode", fsm.artifact_mode)` — a `context:` key named `artifact_mode` takes precedence over the top-level `FSMLoop.artifact_mode` field (default `"file"`, schema.py:1451). This single function is shared by both the static gate and `promote_run_artifact`, "so the two can never disagree about which mode a run is in" (code comment). `_is_template_capable(fsm)` (`:866-879`) is deliberately broader — it fires when the effective mode is already `"template"` **or** `"artifact_mode"` is present as a `context:` key at *any* value (covers `context: {artifact_mode: file}` flipped per-run via `--context artifact_mode=template`).
- **Static gate, concretely**: `_validate_artifact_mode_deliverable(fsm)` (`fsm/validation/structural_rules.py:882-925`, wired at `:1027`) is an unconditional ERROR (no `_ok` suppression flag) when a template-capable loop has no `artifact_output` block; WARN if `artifact_output.to` is set but doesn't end in `.llat`. `ArtifactOutput` (`schema.py:1308-1356`): fields `from` (required), `to` (not required), `on` (terminal allowlist, default empty = all non-failure terminals) — note the PyYAML bareword-boolean landmine where an unquoted `on:` key parses as Python `True` (handled at `schema.py:1351`).
- **`_promote_template_artifact` mechanics** (`persistence.py:802-897`): requires `artifact_output.from` to resolve to a *directory* (not a file); stages into a sibling temp dir, stamps `manifest.yaml`'s `produced_by: <fsm.name>`, runs the full runtime gate (`load_manifest`, `find_template_body`, `load_data`, `validate_top_level_data`, a discarded `render_template`) on the staged copy before ever touching `dest`, then atomically swaps via `_templatize_promote(..., force=True)`. Failures (`ManifestError`, `DataValidationError`, generic exceptions) degrade to a logged warning + `None` return — never raises — matching the file-mode best-effort contract.
- **No other loop in the repo declares `artifact_mode: template`** — confirmed by both research passes (grep across `scripts/little_loops/loops/**/*.yaml` for `artifact_mode` returns zero hits). `hitl-md.yaml` remains the only loop with an `artifact_output:` block, and it is `file`-mode only (`hitl-md.yaml:48-51`). FEAT-3320 will be the first loop in the repo to actually exercise template mode — there is no landed example loop to model the wiring after, only FEAT-3318's own synthetic test fixtures.
- **Canonical minimal `.llat/` fixture** (ground truth for the generate-prompt's wording target): `test_fsm_persistence.py:1620-1636`, `_write_llat_fixture()` — writes `manifest.yaml` (`name: t`, `version: 1`, `renderer: jinja2`, `output: out.txt`, a one-field `data_schema`), exactly one `template.txt.j2` (`Hello [[= title =]]`), and `data.json` (`{"title": "World"}`). Agrees with the pre-existing `scripts/tests/fixtures/artifact_templates/{simple,theme,delimiters}.llat/` fixtures (FEAT-3036/ENH-3035) on required manifest keys and `renderer: jinja2`.

## Implementation Steps

1. Add the `artifact_mode` context var to `html-anything.yaml` and thread the
   effective mode into the `with:` block.
2. Branch the `generate_prompt` on it: template mode instructs the model to write
   `manifest.yaml` + exactly one `template.*.j2` + `data.json` under a `.llat/`
   directory in `run_dir`, per the contract `artifact_templates.py` enforces.
3. Add the per-iteration `ll-artifact render` step and repoint `artifact_path` at
   its output so the screenshot/score/critique cycle runs unchanged.
4. Make a render failure surface as a render error through the ENH-2903 abandon
   path rather than a bare screenshot-miss.
5. Update `finalize_done`'s reported output paths for template mode.
6. Conformance + `file`-mode regression tests; docs.
7. **Report the observed reliability** — how often the model produced a
   schema-valid template first try, and after critique. This number is the input
   to the follow-up decision about the other eight loops.

## Impact

- **Priority**: P2 — without a producer, FEAT-3318's plumbing is inert and every
  loop→template route stays on the lossy `templatize` path.
- **Effort**: Medium — one loop file, but the per-iteration render step and its
  failure path are real work.
- **Risk**: Medium — the reliability of LLM-emitted schema-valid templates is
  unproven; that is what this issue measures. Contained: the default mode is
  untouched and the shared oracle is not forked.
- **Breaking Change**: No — new behavior is opt-in behind a context var.

## Use Case

A user runs `html-anything` in template mode over an architecture document. The
run produces a `.llat/` the user renders against an updated `data.json` next
month — no LLM call, no `templatize` round trip, no fidelity loss.

## Acceptance Criteria

- [ ] `ll-loop run html-anything --context artifact_mode=template` produces a
      `.llat/` directory that passes FEAT-3318's runtime gate and is rendered by
      `ll-artifact render` with no `templatize` step.
- [ ] The default (`file`) path is unchanged — same prompt, same `index.html`, same
      reported outputs; a regression test pins this. This includes the promotion
      side effect of the newly-required `artifact_output` block: either
      default-mode runs do not promote, or the change is explicitly signed off and
      documented.
- [ ] `oracles/generator-evaluator.yaml` is **not** forked or branched on artifact
      mode; template mode is expressed entirely through its existing
      `artifact_path` / `generate_prompt` parameters.
- [ ] The screenshot/rubric/critique iterate cycle works in template mode — a
      low-scoring template is critiqued and regenerated, not abandoned.
- [ ] A template that fails to render surfaces the render error, not a generic
      missing-screenshot message.
- [ ] `test_builtin_loops.py` conformance passes for both modes.
- [ ] The issue records an observed first-try and post-critique success rate for
      schema-valid template emission.

## Related Key Documentation

- `.issues/features/P2-FEAT-3318-artifact-mode-template-loops-emit-template-data-natively.md`
  — the plumbing this consumes; see its § Generate-prompt variant and § Mode selection
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md`
  — the lossy fallback this exists to avoid (**done**)

## Status

**Open** | Created: 2026-08-25 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-25T18:05:42 - `15c28d79-5759-4915-8931-cf98fd12b048.jsonl`
- `/ll:wire-issue` - 2026-08-25T17:31:29 - `f8fad891-fb12-4a0c-8abb-8d32e08edbbf.jsonl`
- `/ll:refine-issue` - 2026-08-25T17:24:56 - `93455bb6-59d7-4ea1-9471-0a612ecdba4d.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:33:23 - `057ec3b7-ff77-4991-8763-e77045d2afc1.jsonl`
- `/ll:refine-issue` - 2026-08-25T16:33:14 - `057ec3b7-ff77-4991-8763-e77045d2afc1.jsonl`
