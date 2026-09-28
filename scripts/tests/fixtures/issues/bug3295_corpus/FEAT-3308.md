---
id: FEAT-3308
title: '`ll-artifact templatize`: save a generated artifact as a reusable template'
type: FEAT
priority: P2
status: done
discovered_by: manual
discovered_date: '2026-08-23'
parent: EPIC-3299
depends_on: []
relates_to:
- FEAT-3309
- ENH-3035
- FEAT-3036
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
learning_tests_required:
- jinja2-byte-exact-round-trip
size: Very Large
reconcile_attempted: true
confidence_score: 90
outcome_confidence: 58
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-3308: `ll-artifact templatize`: save a generated artifact as a reusable template

## Summary

Split out of FEAT-3036 Phase 4. Take an existing single-file HTML artifact — the
kind `html-website-generator`, `interactive-component-generator`, `html-anything`,
`pixi-data-viz` and friends emit into `${run_dir}/index.html` — plus the source
document it was generated from, and produce a reusable artifact template: the
manifest (with a `data_schema`), the templated body, and the `data.json` that
re-renders the original. Verified by round-trip fidelity.

This is the epic's **fan-out entry point**: it is how a user who liked one
artifact gets to view a second, third and twentieth document through it without
re-running the generating FSM loop.

## Current Behavior

`templatize` exists only as a ~6-line paragraph in FEAT-3036's phased plan,
described as "the gnarliest part, deliberately last," with the parent epic
stating that Phases 1–3 "deliver the drift-killing value even if Phase 4 slips."
No code exists at the time of filing:
<!-- ll-evidence-ok: historical Current Behavior snapshot predating this issue's own implementation; grep now returns matches from the completed work -->
`grep -rn templatize scripts/` returns nothing.

Consequently the only way to obtain a template today is to hand-author one —
manifest, schema and templated body carved by hand out of a ~100KB self-contained
HTML file. That is the exact expensive manual work the epic exists to remove, and
it is the reason artifacts from the HTML loop family stay one-off.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review.llat
```

produces a template directory that (a) validates under `load_manifest()`,
(b) re-renders **byte-identically** against the extracted `data.json`, and (c)
can then be pointed at any *other* architecture planning document via
`ll-artifact refresh`/`extract`.

**Output naming.** `-o` must resolve to a `<name>.llat` directory, because
`resolve_template()` (`artifact_templates.py:73`) only finds a template by name at
`templates_dir/<name>.llat`; a bare `arch-review` directory is reachable by path
only. If `-o` is given without the suffix, `templatize` appends `.llat` and logs
the resolved path. With no `-o`, the default is
`config.artifacts.templates_dir/<artifact-stem>.llat`.

## Motivation

The user-facing story the epic is for: a user generates an HTML artifact to review
one architecture planning document, finds it useful, and wants to view *all* their
architecture planning documents through it. Without `templatize`, that story has no
implementation — the generated artifact is a dead end and each additional document
costs another full FSM refinement run.

Deferring this to last inverts the epic's value: Phases 1–3 serve temporal refresh
of one bound source, which is the secondary use case (see EPIC-3299 § Use Cases).

## Proposed Solution

Three stages, each independently testable:

1. **Region discovery (LLM).** Given `artifact.html` and `source.md`, identify the
   spans of the artifact that are *derived from the source* versus the spans that
   are presentation. Emit a candidate `data_schema`, the extracted `data.json`, and
   — critically — a **region map**: the located spans themselves (see § Region map
   below). Repeated regions (per-section cards, list rows) must be detected as
   arrays, not flattened — this is the whole reason the design chose Jinja2 over the
   `.replace()` scheme in `cli/artifact/policy_builder.py`.
2. **Body templating (deterministic).** Replace each region span with the
   corresponding Jinja2 expression/block, leaving everything else byte-identical.
3. **Round-trip verify (deterministic).** `render_template(template, data.json)` and
   diff against the original artifact. **Any** non-empty diff is a hard failure —
   the fitness function, not an advisory warning. There is no normalized-diff
   tolerance in v1 (see § Round trip vs. token lifting).

### Region map

`discover_regions` returning only `(data_schema, data)` is **not sufficient** to
drive `apply_regions`: extracted *values* do not locate themselves in a ~100KB
artifact. Recovering positions by string search is ambiguous (a value occurring
twice, a value that is a substring of another) and cannot recover the repeat
grouping that the loop-templating criterion requires. The LLM stage therefore
returns a third output, a list of `Region` descriptors, each carrying:

- `start` / `end` — byte offsets into the original artifact, the authoritative
  location (an `anchor_before`/`anchor_after` context string is carried alongside
  for diagnostics and for re-locating on a near-miss, not as the primary key)
- `expr` — the Jinja2 expression that replaces the span (e.g. `section.title`)
- `group` — `None` for a scalar region, or a repeat-group id shared by every
  region belonging to the same iteration, plus the group's `for` binding and the
  array path in `data`

`apply_regions` is then a pure, LLM-free splice over sorted, non-overlapping spans:
overlapping or out-of-bounds spans are a hard error, not a best-effort merge. This
also makes stages 2–3 fully testable from a hand-written region-map fixture with no
LLM in the test path.

### Round trip vs. token lifting

Byte-exact round trip and design-token lifting are **mutually exclusive by
construction**: a lifted stamp point renders `ll.theme_css` (a CSS custom-property
block), which is by definition not the literal hex the original artifact contains.
Resolution for v1:

- The round-trip gate runs against the **unlifted** template. That is the fidelity
  contract, and it stays byte-exact with no tolerance.
- Token lifting is **report-only** in v1: `templatize` scans the artifact's CSS for
  values matching the resolved token map and writes an `unlifted-tokens.json`
  report plus a non-silent `logger.warn` naming the count and the token names. It
  does not rewrite them, and the emitted manifest does **not** set
  `theme: design-tokens`.
- Actually performing the lift (and the normalized-diff gate it would require) is
  deferred; see § Deferred to a follow-up.

Failure is loud and non-destructive, via build-then-promote rather than
write-then-rollback (there is no directory-scoped rollback helper in this codebase —
see Program Design findings): `templatize` builds the candidate template in a temp
directory, runs the round trip there, and only then `os.replace`s it into the `-o`
path. On a failed round trip it writes the candidate plus `roundtrip.diff` to
`<out>.rejected/` and exits non-zero, leaving any pre-existing `-o` template
untouched.

### Design-token stamp points

The HTML loops receive design tokens as **prompt text** —
`cli/loop/_helpers.py:1416-1424` seeds `context["design_tokens_context"]` via
`render_as_prompt_context`. A generated artifact therefore has token values baked in
as literal hex. The template kit (ENH-3035) stamps tokens **at render time** as CSS
variables via `render_as_css_vars_themed` (`design_tokens.py:688`).

`templatize` must reconcile the two: recognize baked literal token values in the
artifact's CSS and lift them back into stamp points, or the template is permanently
un-themeable and drifts from every other kit artifact. Per § Round trip vs. token
lifting, **v1 takes the report-only branch** — the command reports the unlifted
literals rather than silently accepting them, and the rewrite is deferred.

Building that report needs a `value -> token-name` inversion of
`DesignTokens.resolved` (`design_tokens.py:35`), which does not exist in the
codebase; every renderer iterates it forward-only. Note the inversion is not
injective — two tokens can resolve to the same hex — so a matched literal maps to a
*list* of candidate names and the report must say so rather than pick one.

### Manifest emission

`templatize` is the first writer of a `manifest.yaml`, and `load_manifest()`
(`artifact_templates.py:142-189`) accepts exactly
`{name, version, renderer, output, data_schema}` plus optional
`{theme, source, extraction}`. The emitted values:

- `name` — the `-o` directory stem (without `.llat`)
- `version` — `1`, the template-format version, bumped only by a FEAT-3036
  format change (it is not the user's artifact version)
- `renderer` — `jinja2` (the only accepted value)
- `output` — the original artifact's filename (e.g. `index.html`)
- `data_schema` — from stage 1, and it **must validate under
  `_validate_schema_shape()`** (`artifact_templates.py:85-140`): the allowed key set
  is exactly `{type, required, properties, items, enum, description}`. An LLM asked
  for "a JSON Schema" will volunteer `additionalProperties`, `minItems`, `format`,
  `oneOf` by default, all of which are a hard `ManifestError`. The `discover_regions`
  prompt must state the subset explicitly, and the emitted schema is validated
  in-process before anything is written.
- `source` — the source document path, relative to the project root; this is the
  binding `ll-artifact refresh` needs
- `extraction` — the extraction hints for FEAT-3309's `extract` (at minimum the
  `discover_regions` prompt used and the source's content type), so a second
  document can be extracted against the same contract that produced the original
- `theme` — **omitted** in v1 (see § Round trip vs. token lifting); the only other
  accepted value is `design-tokens`

### Fidelity constraints on extracted values

Two properties of the frozen environment (`build_environment()`,
`artifact_templates.py:242-262`) constrain what stage 1 may emit:

- **`autoescape=False`.** Values are stamped verbatim. Extracted values must
  therefore be captured **exactly as they appear in the artifact byte stream** —
  if the artifact contains `&amp;` or `&#39;`, `data.json` holds the escaped form,
  not the decoded character, or the round trip fails. Consequence for the fan-out
  case: `data.json` carries HTML-escaped text, so a *new* source document's values
  must be escaped the same way at extraction time (FEAT-3309's concern, recorded
  here in `manifest.extraction` so it is not rediscovered). Also note autoescape-off
  means a source document is injected raw into HTML — artifact templates render
  trusted input only, and that assumption belongs in the docs.
- **Delimiter collision.** `apply_regions` must scan the non-region spans for any
  pre-existing `[[=`, `[[%`, `[[#` (plausible in inlined JS/CSS string content) and
  wrap them in `[[% raw %]]`/`[[% endraw %]]`. Missing this is a silent round-trip
  failure whose diff points nowhere near the real cause.

### Input size ceiling

Stage 1 sends the whole artifact plus the source document in one
`build_blocking_json` call, and the artifacts this targets run ~100KB. There is no
chunking strategy in v1. Instead the command enforces an explicit combined-input
ceiling (default configurable, sized against the host's context window) and fails
loud with the measured size when exceeded, rather than issuing a call that silently
truncates and returns a plausible-looking partial region map that then fails the
round trip for an unrelated-looking reason.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

This codebase holds two disagreeing conventions for an LLM-driven discovery/extraction stage
like `discover_regions`, and Phase B's "fail-closed against the emitted schema"
requirement is a decision between them, not something either pattern gives for free:

**Option A**: Schema-forced structured output via `build_blocking_json(json_schema=...)`, as
`advisor.consult()` does (`advisor.py:147-190`, `_VERDICT_SCHEMA`). The schema is materialized
into the host-CLI call at build time; the caller checks `_VERDICT_KEYS.issubset(result.keys())`
and raises `BlockingJsonError` on any mismatch — every failure is loud.

> **Selected:** Option A — schema-forced structured output, matching `advisor.consult()`'s
> raise-on-mismatch contract; see Decision Rationale below.

**Option B**: Prompt-embedded schema with a regex-scraped envelope, as
`learning_tests/extractor.py` does (`_default_llm_call:116`, `extract_learning_targets:195`).
`build_blocking_json` is called with no `json_schema=` argument; the contract is a
`TARGETS_JSON:{...}` marker the prompt asks the model to emit, scraped by regex. Every failure
mode (timeout, missing binary, non-zero exit, bad JSON, no regex match) degrades to an empty
result rather than raising — documented as "a best-effort safety net" (`extractor.py:126-128`).

**Recommended**: Option A — `discover_regions`'s own stated requirement (Phase B, step 4:
"fail-closed against the emitted schema") matches Option A's raise-on-mismatch contract, not
Option B's silent-degrade contract. A silently-empty `data_schema` would pass Option B's error
handling but fail this issue's round-trip verify stage in a way that looks like the LLM found
nothing, not that the LLM call itself failed.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **`cmd_render`'s Jinja2 environment is the frozen contract `templatize` must reuse, not re-derive** (analyzer, gap-fill, supersedes prior "FEAT-3036 Phase 1... wholly unimplemented" finding): `render()` now exists as `cmd_render` (`scripts/little_loops/cli/artifact/render.py:27`), delegating the actual Jinja2 mechanics to `scripts/little_loops/artifact_templates.py`. `build_environment()` (`artifact_templates.py:242-262`) constructs a `jinja2.sandbox.SandboxedEnvironment` with the frozen delimiter set (`[[= =]]`/`[[% %]]`/`[[# #]]`), `trim_blocks=True`, `lstrip_blocks=True`, `keep_trailing_newline=True`, `undefined=StrictUndefined`, `autoescape=False` — its own docstring states changing any of these is a template-format version bump that breaks FEAT-3308's byte-exact round-trip requirement. `apply_regions`/`verify_round_trip` must import and call `build_environment()` unchanged (it is a zero-argument factory) rather than constructing a separate `Environment`, or round-trip fidelity cannot be guaranteed by construction.
- **Manifest and template-body constraints `apply_regions`'s output must satisfy** (analyzer, gap-fill): `load_manifest()` (`artifact_templates.py:142-189`) requires exactly `_MANIFEST_REQUIRED_KEYS = {"name", "version", "renderer", "output", "data_schema"}` with `renderer` literally `"jinja2"` and, if present, `theme` literally `"design-tokens"` (no other value accepted); `data_schema` is validated by `_validate_schema_shape()` (`:85-140`) against a restricted JSON-Schema subset (`{type, required, properties, items, enum, description}` keys only) and forbids a top-level `ll` key (reserved for the render context — same check applied to `data.json` payloads by `validate_top_level_data()`, `:233-239`). `find_template_body()` (`:265-275`) requires exactly one `template.*.j2` file at the template root — zero or multiple matches raises `ManifestError`. Any template `apply_regions` emits must satisfy both constraints to be renderable by the existing `render` command.
- **Binary assets are out of scope for the extraction side too** (analyzer, gap-fill): `load_assets()` (`artifact_templates.py:278-291`) reads every file under `root/assets/` as UTF-8 text only — its own docstring states "Binary assets (data-URI encoding) are out of scope for v1." An artifact with inlined images/fonts as data URIs can still be templatized (the data URI is just a long string literal within the HTML), but `discover_regions`/`apply_regions` cannot extract them into separate binary asset files under the current loader.

### Decision Rationale

**Selected**: Option A — schema-forced structured output via `build_blocking_json(json_schema=...)`,
matching `advisor.consult()`'s raise-on-mismatch contract (`advisor.py:147-190`, `267-278`).

**Reasoning**: Option B's fail-soft-to-empty-result contract (`extractor.py:126-128`) directly
contradicts Implementation Step 3's explicit "fail-closed against the emitted schema" requirement —
a silently-empty `data_schema` would look identical to "the LLM found nothing" rather than "the
call failed," corrupting the round-trip verify stage's diagnosis. Option A's `BlockingJsonError`
raise-on-mismatch (`advisor.py:272-278`) is the codebase's only precedent that actually fails loud.
Note: `json_schema=` build-time enforcement is host-dependent (`host_runner.py:442-465` — Claude
Code drops the kwarg; only Codex materializes it as `--output-schema`); on the default host, the
"fail-closed" guarantee comes from replicating `advisor.py`'s explicit `issubset` key-check in
`discover_regions`, not from the builder alone.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 0 |
| Simplicity | 2 | 2 |
| Testability | 3 | 1 |
| Risk | 2 | 0 |
| **Total** | **9/12** | **3/12** |

**Key evidence**:
- `advisor.py:267-278` — Option A's raise-on-mismatch shape, directly copyable
- `extractor.py:116-227` — Option B's fail-soft design, explicitly documented as a "best-effort safety net," incompatible with this issue's fail-closed requirement
- `host_runner.py:442-465,736-770` — `json_schema=` is Codex-only at the builder level; Claude Code (default host) silently drops it, so caller-side key-checking is required regardless of option chosen

## Use Case

A user runs `/ll:create-loop`-generated `html-anything` over one architecture
planning document and gets a review artifact they like. They run
`ll-artifact templatize` on it, then `ll-artifact refresh` (or a batch render, see
FEAT-3309/EPIC-3299) against their other eleven planning documents,
paying one small extraction call each instead of twelve FSM refinement runs.

## Program Design

### Types

- `Region: {start: int, end: int, expr: str, group: str | None, anchor_before: str, anchor_after: str}` — one located span; `start`/`end` are byte offsets into the original artifact and are the authoritative location, anchors are diagnostics only
- `RegionGroup: {id: str, binding: str, array_path: str}` — a repeat group: the `for` binding name and the path in `data` to the array it iterates
- `DiscoveryResult: {data_schema: dict, data: dict, regions: list[Region], groups: list[RegionGroup]}`
- `UnliftedToken: {literal: str, candidate_names: list[str], occurrences: int}` — the inversion is not injective, hence a name *list*
- `TemplatizeResult: {template_dir: Path, data: dict, diff: str | None, unlifted_tokens: list[UnliftedToken]}`
- `ArtifactTemplate` (`artifact_templates.py:47-64`) — existing; `cmd_templatize` must emit a `manifest` dict that `load_manifest()` accepts so a subsequent `render` can construct one

### Signatures

- `cmd_templatize(args: argparse.Namespace, logger: Logger) -> int`
- `discover_regions(artifact_html: str, source_text: str, prompt: str | None) -> DiscoveryResult` — the LLM stage; the only function here that touches `host_runner`
- `apply_regions(artifact_html: str, result: DiscoveryResult) -> str` — deterministic body templating over sorted, non-overlapping spans; raises on overlap or out-of-bounds
- `escape_literal_delimiters(text: str) -> str` — wrap pre-existing `[[=`/`[[%`/`[[#` in `[[% raw %]]`
- `build_manifest(name: str, output: str, schema: dict, source: Path, extraction: dict) -> dict` — emits the manifest; validates against `_validate_schema_shape` before returning
- `verify_round_trip(template_dir: Path, data: dict, original: str) -> str | None` — renders via `render_template` and returns a unified diff, or None on byte-exact match. Runs against the temp build dir, before promotion.
- `report_token_literals(css: str, tokens: DesignTokens) -> list[UnliftedToken]` — report-only in v1 (replaces the previously-planned `lift_token_literals`, which rewrote the CSS; see § Round trip vs. token lifting)

### Call Path

`main_artifact` (`cli/artifact/__init__.py:38`) -> `cmd_templatize`
(new, `cli/artifact/templatize.py`) -> `discover_regions` -> `apply_regions`
(+ `escape_literal_delimiters`) -> `build_manifest` -> *write temp dir* ->
`verify_round_trip` -> `render_template` (`artifact_templates.py:304-328`) ->
`build_environment` (`:242-262`) -> *promote temp dir to `-o` via `os.replace`* ->
`report_token_literals`

`build_ll_namespace`/`_themed_css_vars`/`render_as_css_vars_themed` are **not** on
this path in v1, because the emitted manifest omits `theme` (§ Round trip vs. token
lifting). `report_token_literals` needs a resolved `DesignTokens` via
`load_design_tokens`, obtained the same way `_themed_css_vars`
(`cli/artifact/policy_builder.py:56-87`) obtains it.

### Codebase Research Findings

_Consolidated 2026-08-24 (post-FEAT-3036); stale pre-package-split `cli/artifact.py:NNN` citations pruned._

- **No round-trip/rollback precedent exists.** A repo-wide grep for `round.?trip`/`non-destructive` returns nothing outside `.issues/`. `verify_round_trip`'s contract is novel to this codebase. `file_utils.py:16-32,35-57` provides `atomic_write`/`atomic_write_json` (single-file only, temp-then-`os.replace`); no directory-scoped transaction helper exists (`init/writers.py` has no cleanup logic either). The build-in-temp-then-promote flow (§ Round trip vs. token lifting) is the directory-level generalization of `atomic_write`'s own pattern, and is new code.
- **Error-handling shape to match.** `cmd_policy_builder` (`cli/artifact/policy_builder.py:90`) and `cmd_design_md_export` (`cli/artifact/design_md.py:57`) share one shape: whole-body `try/except Exception as exc:  # noqa: BLE001` -> `logger.error(str(exc)); return 1` as the only catch-all; anticipated failures get inline `logger.error(...); return 1` *inside* the try (not raised); a narrower `except DesignMdColorCollisionError` shows the domain-specific-message pattern; success is `logger.success(...); return 0`. `cmd_templatize` follows this rather than letting custom exceptions escape the handler.
- **`ArtifactTemplate` is the cross-cutting carrier type** (`artifact_templates.py:47-64`): what `load_manifest()` + `resolve_template()` produce and `render_template()` consumes. `build_manifest`'s output must satisfy `load_manifest()`'s required-keys check plus `_validate_schema_shape` for a subsequent `render` to consume it.
- **`artifact_templates.py` must never import `host_runner` or `anthropic`** (module docstring, design principle 2). `apply_regions`/`verify_round_trip` may live there or in a sibling module; `discover_regions` — the only LLM-touching function — must not.
- **Config loading is per-handler.** Every `cmd_*` constructs `config = BRConfig(Path.cwd())` in its own body; `cmd_render` resolves `templates_dir = config.project_root / config.artifacts.templates_dir` at `render.py:38`. `cmd_templatize` does the same, and is the first `cli/artifact/` **writer** to `templates_dir` (`render` only reads from it).
- **`DesignTokens.resolved` (`design_tokens.py:35`) is forward-only.** Every renderer (`render_as_css_vars` `:678`, `render_as_css_vars_themed` `:688`, `render_as_prompt_context` `:572`) iterates it name -> value. No value -> name index exists anywhere; `report_token_literals` builds the inversion from scratch and must handle the non-injective case.
- **Subparser wiring point.** Registration is `policy-builder` at `cli/artifact/__init__.py:66-76`, `design-md export` (nested `add_subparsers`) at `:78-109`, `render` via `add_render_parser(subparsers)` at `:111`. `templatize` follows the `render` precedent: an `add_templatize_parser(subparsers)` in the new `cli/artifact/templatize.py`, called immediately after `:111` (before `parse_args()` at `:113`), a fourth arm in the dispatch if-chain (`:118-124`), plus manual additions to the epilog `Examples:`/`Exit codes:` block (`:49-62`) and `__all__` (`:29-35`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` (new module) — `add_templatize_parser` subparser + `cmd_templatize` handler, registered from `cli/artifact/__init__.py:111` immediately after `add_render_parser(subparsers)`; also add to `__all__` (`:29-35`) and the epilog `Examples:`/`Exit codes:` block (`:49-62`)
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — new subcommand section

_Wiring pass added by `/ll:wire-issue`:_
- ~~`scripts/little_loops/config/features.py:369-384` — `ArtifactsConfig` dataclass needs the new templates-directory field alongside `default_output_dir`~~ / ~~`scripts/little_loops/config/core.py:916-918` — `BRConfig.to_dict()`'s `"artifacts": {"default_output_dir": ...}` block must add the new field's key/value~~ — **FEAT-3036 already landed `artifacts.templates_dir`** in both `config-schema.json` and `ArtifactsConfig`; this issue inherits it and must not re-add it (see Scope Boundary below).
- ~~`scripts/pyproject.toml:40-51` — add a `jinja2` dependency pin~~ — **landed by FEAT-3036** (`jinja2>=3.1`, with its justifying comment); inherited, not re-added.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:52,110` — `main_artifact` re-export; unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:339,476-478` — `ArtifactsConfig.from_dict()` load site and `.artifacts` property; unaffected by a new field but confirms this is the only other reader of the `artifacts` config block besides the schema/dataclass already cited [Agent 2 finding]
- `scripts/tests/test_enh3268_design_md_export.py:354,367,378,394,410` — imports `cmd_design_md_export`, `main_artifact` directly; the closest existing sibling-subcommand test to model `test_artifact_templatize.py`'s dispatch tests after [Agent 1/3 finding]

### Similar Patterns
- `cmd_policy_builder` (`cli/artifact/policy_builder.py:90`) — the existing stamp-and-write shape
- `hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — hand-written loop states that already copy `${run_dir}/index.html` out; prior art for wanting artifacts to outlive a run

### Tests
- New test module under `scripts/tests/` (`test_artifact_templatize`) — round-trip fidelity against a checked-in fixture artifact + source pair. The fixture must deliberately contain: a repeated region (N=2 and N=5 variants), a literal `[[=`/`[[%` inside inlined JS or CSS, HTML entities (`&amp;`, `&#39;`) inside a templatized region, and at least one baked design-token hex literal — these are the four silent-failure classes the ACs gate on. Phase A tests drive it via `--regions <map.json>` with **no LLM in the test path**.
- `scripts/tests/test_policy_builder_emit.py` — unaffected, but the node gate (`test_policy_builder_node_gate.py`) must stay green

_Wiring pass added by `/ll:wire-issue`:_
- ~~`test_config_schema.py::test_artifacts_in_schema` / `TestSchemaValueParity` — extend for the new `ArtifactsConfig` field~~ — **no new config field is added by this issue** (`templates_dir` landed with FEAT-3036); no `test_config_schema.py` change is needed.
- No fixture pairing an emitted HTML artifact with its generating source document exists yet in `scripts/tests/fixtures/` — the round-trip fixture has no in-repo precedent to copy; nearest transferable pattern is `_write_synthetic_profile`/`_reimport` in `test_enh3268_design_md_export.py:288-332,42-46` (write synthetic source under `tmp_path`, render, re-parse, assert fidelity) [Agent 3 finding]
- Model `test_artifact_templatize.py`'s dispatch tests on `test_policy_builder_emit.py::TestArtifactCLIDispatch` (`:204-230`) — mock-handler dispatch (patch `sys.argv` + target `cmd_*`, assert `main_artifact()` routes correctly) and the missing-subcommand `SystemExit` test, which extends automatically to `templatize` since it shares the same parser [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` § `artifacts` (`:910-924`) — the prose at `:912` ("Currently backs the `policy-builder` subcommand...") stops being accurate once `templatize` reads *and writes* `templates_dir`; update it. No new field, so no new table row.

### Configuration
- `scripts/little_loops/config-schema.json` § `artifacts` — `templates_dir` field already landed by FEAT-3036 (`config-schema.json:127,1883`, `ArtifactsConfig.templates_dir` at `config/features.py:212,378`, default `"artifacts/templates"`); `cmd_templatize` reads `config.artifacts.templates_dir` at the same site `cmd_render` does (`cli/artifact/render.py:38`) rather than adding a new field — see Scope Boundary below

### Codebase Research Findings

_Consolidated 2026-08-24 (post-FEAT-3036); superseded pre-package-split citations pruned. The wiring, error-handling, and config-loading findings live in § Program Design → Codebase Research Findings and are not repeated here._

- **`main_artifact`'s full reference set** is `cli/__init__.py:52` (import), `:110` (re-export), and the `ll-artifact = "little_loops.cli:main_artifact"` console script (`scripts/pyproject.toml:70`) — no in-repo Python call site.
- **`jinja2>=3.1` is pinned** in `scripts/pyproject.toml` with a justifying comment, landed by FEAT-3036. This issue inherits it and must not re-add it.
- **The only in-repo placeholder-substitution precedent** is `cmd_policy_builder`'s literal `.replace()` scheme, which this issue's own text cites as insufficient for repeated-region templating — hence Jinja2.
- **Dispatch test to extend**: `TestArtifactCLIDispatch` in `scripts/tests/test_policy_builder_emit.py:204`, importing `cmd_policy_builder, main_artifact` at `:15`; confirmed current under the package split.

## Implementation Steps

Three phases. **Phase A is independently shippable and contains no LLM call** — it
is the whole fidelity mechanism, testable end-to-end from a fixture. Phase B adds
the LLM discovery that makes it usable without a hand-written region map. If this
issue needs splitting for size, split on the A/B boundary.

**Phase A — deterministic templating (no LLM)**

1. Implement `Region`/`RegionGroup`/`DiscoveryResult`, `apply_regions`,
   `escape_literal_delimiters`, and `build_manifest`, reusing `build_environment()`
   (`artifact_templates.py:242-262`) unchanged rather than constructing a separate
   Jinja2 `Environment`. `apply_regions` splices sorted, non-overlapping spans and
   raises on overlap/out-of-bounds.
2. Implement the temp-build -> `verify_round_trip` -> `os.replace`-promote flow,
   with the `<out>.rejected/` + `roundtrip.diff` failure path.
3. Wire `templatize` behind `--regions <map.json>` (Phase A's entry point: read a
   hand-written region map instead of calling an LLM) plus the fixture round-trip
   test at N=2 and N=5.

**Phase B — LLM region discovery**

4. Implement `discover_regions` using schema-forced structured output via
   `build_blocking_json(json_schema=...)` (Option A — see Decision Rationale),
   fail-closed by replicating `advisor.consult()`'s `issubset` key-check
   (`advisor.py:267-278`), since `json_schema=` build-time enforcement is Codex-only.
   The prompt must state the `data_schema` allowed-key subset and the
   capture-values-as-they-appear-in-the-byte-stream rule (§ Fidelity constraints).
5. Enforce the input-size ceiling before the call; fail loud with measured sizes.
6. Validate the returned `data_schema` with `_validate_schema_shape` in-process
   before any write.

**Phase C — token report**

7. Build the `value -> [token-name]` inversion of `DesignTokens.resolved` and
   `report_token_literals`; write `unlifted-tokens.json` and a non-silent warning.
8. Docs (`CLI.md`, `CONFIGURATION.md`, `ARCHITECTURE.md`) and `__all__`/epilog
   registration in `cli/artifact/__init__.py`.

### Deferred to a follow-up

Actually **rewriting** baked token literals into `ll.theme_css` stamp points (and
emitting `theme: design-tokens`) is out of scope. It cannot coexist with the
byte-exact round-trip gate, so it needs its own normalized-diff fitness function —
a separate design decision, not a step here. `report_token_literals` exists so the
follow-up has an inventory to work from and so a lossy template is never silently
accepted in the meantime.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Add the new templates-directory field to `ArtifactsConfig` (`config/features.py:369-384`) and `config-schema.json` § `artifacts` (`:1870-1880`) together, with matching defaults~~ / ~~Update `BRConfig.to_dict()` (`config/core.py:916-918`) to serialize the new field~~ — **already landed by FEAT-3036**; this issue inherits `artifacts.templates_dir`, not re-adds it (see Scope Boundary below).
- Update `docs/reference/CONFIGURATION.md` § `artifacts` (`:910-924`) — table row, JSON example, and the now-stale "Currently backs the `policy-builder` subcommand" prose
- Extend `test_config_schema.py::test_artifacts_in_schema` (`:473-491`) for the new field; verify `TestSchemaValueParity.test_to_dict_values_match_schema_defaults` (`:1243-1265`) passes with matching defaults
- ~~Add a `jinja2` dependency pin to `scripts/pyproject.toml` (`:40-51`) with a justifying comment, following the `anthropic` pin's shape~~ — **FEAT-3036 Phase 1 lands the pin** (it is an acceptance criterion there); this issue inherits it. If Phase 1 has not landed, this issue is blocked, not the place to add the pin.
- Write `test_artifact_templatize.py` following `test_policy_builder_emit.py`'s direct-`Namespace`/mock-handler dispatch conventions (`:204-230`) and `test_enh3268_design_md_export.py`'s `_make_config`/`_write_synthetic_profile`/`_reimport` fixture helpers (`:288-332,42-46`) for the round-trip fixture, since no checked-in artifact+source fixture pair exists to copy

## Acceptance Criteria

**Inherited contract (do not re-decide here).** FEAT-3036 § Second-pass decisions
freezes the delimiter set (`[[= =]]` / `[[% %]]` / `[[# #]]`) and the Jinja2
environment settings that determine whitespace (`trim_blocks`, `lstrip_blocks`,
`keep_trailing_newline`, `StrictUndefined`, `autoescape=False`). Byte-exact
round-trip fidelity is only achievable *because* those are frozen — `templatize`
must emit templates against that exact environment and may not relax the round
trip to a normalized diff without a matching change in FEAT-3036.

**Phase A**

- [ ] `ll-artifact templatize <artifact> <source> -o <name>.llat` produces a directory that `load_manifest()` accepts and that `ll-artifact render <name>` resolves **by name** under `templates_dir` (not by path only).
- [ ] Round-trip: rendering the produced template with the produced `data.json` reproduces the original artifact byte-identically. Any non-empty diff exits non-zero, writes `<out>.rejected/` + `roundtrip.diff`, and leaves a pre-existing `-o` template untouched — asserted by a test that pre-populates `-o` and forces a failure.
- [ ] A repeated region in the source (N sections → N cards) is templatized as a Jinja2 loop over an array, not unrolled — asserted by a test with N=2 and N=5 data.
- [ ] An artifact containing a literal `[[=` / `[[%` / `[[#` in inlined JS or CSS still round-trips byte-exactly — asserted by a fixture that includes one.
- [ ] An artifact containing HTML entities (`&amp;`, `&#39;`) in a templatized region round-trips byte-exactly; the test asserts `data.json` stores the escaped form.
- [ ] `apply_regions` raises on overlapping or out-of-bounds spans rather than merging best-effort.

**Phase B**

- [ ] The emitted `data_schema` passes `_validate_schema_shape()`; a test feeds a `discover_regions` response containing `additionalProperties`/`minItems` and asserts the command fails loud before writing anything.
- [ ] A `discover_regions` response missing required keys raises rather than degrading to an empty result (Option A contract), asserted with a mocked host call.
- [ ] A combined artifact+source input over the configured ceiling exits non-zero naming the measured size, with no host call issued.
- [ ] The emitted manifest carries `source` and `extraction`, and omits `theme`.

**Phase C / cross-cutting**

- [ ] Baked design-token literals are reported as unlifted in `unlifted-tokens.json` and a non-silent log line; a test asserts the report is non-empty for a fixture with baked tokens and that a literal matching two token names reports both candidates.
- [ ] The resulting template renders correctly against a *second, different* source document of the same kind — the fan-out case. **Oracle:** the fixture ships a hand-authored `data.json` for the second document and the test asserts the render matches a checked-in expected output. (Deriving that `data.json` automatically is `ll-artifact extract`, i.e. FEAT-3309, and is explicitly not in scope here.)
- [ ] The generating FSM loop is not invoked at any point in `templatize` or in subsequent renders.

## Impact

- **Priority**: P2 — this is the epic's user-facing entry point; the epic's stated value is not deliverable without it. Raised above the P3 dashboard-lineage children deliberately.
- **Effort**: Large — region discovery over an opaque self-contained file is the hard problem in the epic. Phase A (deterministic, no LLM) is roughly half of it and is independently shippable; if this issue is split for size, split on the A/B boundary.
- **Risk**: Medium — round-trip fidelity is a hard, automatable gate, which bounds the risk of a lossy result shipping silently. The residual risk is concentrated in Phase B's region-map quality, which the gate catches but cannot repair.
- **Breaking Change**: No — new subcommand.

## Verification Notes

_Pruned 2026-08-24 during pre-implementation review; superseded notes removed._

- The 2026-08-24 **OUTDATED** verdict has been acted on: FEAT-3036 landed, `cli/artifact.py` no longer exists as a flat file, and `render()`/`jinja2` are now present. Every citation in this issue is re-anchored to the package layout, and the "FEAT-3036 is a hard dependency" premise is resolved (`depends_on: []`; FEAT-3036 `done`).
- The 2026-08-23 **EVIDENCE_UNVERIFIED** flag on the `grep -rn templatize scripts/` span was a detector proximity-heuristic misattribution — the grep is the issue author's own shell output, not a quote sourced from FEAT-3036. The underlying claim was independently re-confirmed true; no content change was warranted.
- **Not yet verified:** § Region map, § Round trip vs. token lifting, § Manifest emission, § Fidelity constraints on extracted values, and § Input size ceiling are design decisions made during this review, not codebase-derived findings. They have not been through `/ll:verify-issues`.

## Related Key Documentation

- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub; read first
- `docs/reference/CLI.md` — `ll-artifact`

## Status

**Done** | Created: 2026-08-23 | Priority: P2

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-24
- **Reason**: Issue too large for single session (size score 11/11, Very Large); the issue's own text names the split axis ("If this issue needs splitting for size, split on the A/B boundary").

### Decomposed Into
- FEAT-3314: `ll-artifact templatize` Phase A: deterministic templating (no LLM)
- FEAT-3315: `ll-artifact templatize` Phase B: LLM region discovery
- FEAT-3316: `ll-artifact templatize` Phase C: token report, fan-out verification, docs

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `artifacts.templates_dir` was already added to `config-schema.json` and `ArtifactsConfig` by FEAT-3036 (done). This issue inherits that field rather than re-adding it — the earlier Wiring Phase / Integration Map entries claiming ownership of it are struck through above. FEAT-3304 owns the separate `artifacts.export` block.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-24_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

### Gaps to Address
- `format-check`'s `unapplied_decision` detector flags ~35 identifiers (`discover_regions`, `apply_regions`, `load_manifest()`, `theme`, `[[= =]]`, etc.) across Proposed Solution/Program Design/Implementation Steps/Acceptance Criteria as belonging to the rejected Option B path from the Decision Rationale — this appears to be a proximity false-positive (these identifiers are Option A's own vocabulary, not Option B's `extractor.py` pattern), but it capped Criterion C (Ambiguity) at 10/25 per the Decision Cap rule; consider running `/ll:decide-issue` or manually re-confirming the decision block's phrasing so the detector stops matching, since the underlying decision (Option A) is not actually in question.
- `format-check`'s `missing_behavior_parity` flags `cli/artifact/policy_builder.py` and `scripts/little_loops/artifact_templates.py` (no explicit "### Behavior Parity" subsection contrasting `templatize` against them) and `stale_cli_flag` flags the not-yet-implemented `ll-artifact templatize/refresh/extract` subcommands (expected — this issue is what adds them) — both capped Criterion 4 (Issue Well-Specified) at 10/20; the CLI-flag flags are inherent to a forward-looking FEAT and can be disregarded, but a short Behavior Parity note contrasting the new templating approach against `policy_builder.py`'s `.replace()` scheme (already discussed narratively in Proposed Solution) would clear that half of the cap.

### Outcome Risk Factors
- **Deep per-site complexity** (Criterion A: Complexity 5/25 — Breadth 5/12, Depth 0/13): the core deliverable (`discover_regions`, `apply_regions`, the temp-build → verify → promote transaction) is genuinely novel architecture with no in-repo precedent — the issue's own research explicitly states "No round-trip/rollback precedent exists... novel to this codebase." Expect the highest implementation risk to concentrate in the temp-build/promote flow and the region-splicing algorithm, not the CLI wiring.
- **Ambiguity floor from the Decision Cap** (Criterion C: 10/25): see Gaps to Address above — resolve the `unapplied_decision` false-positive (or confirm it is not one) before treating ambiguity as fully closed.

Learning test target `jinja2-byte-exact-round-trip` was `missing` at check time; auto-provisioned via `/ll:explore-api` this session — all 7 claims proven (`.ll/learning-tests/jinja2-byte-exact-round-trip.md`), no Phase 3 hard override triggered.

## Session Log
- `/ll:issue-size-review` - 2026-08-24T18:42:59 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:confidence-check` - 2026-08-24T18:33:03 - `fc7f522d-5285-4cfe-80ae-165743f58e1d.jsonl`
- `/ll:reconcile-issue` - 2026-08-24T18:21:58 - `bf2ea761-d864-4b19-8078-67d47afee296.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:16:50 - `4cf0eddb-35dc-406e-937b-500628a507cf.jsonl`
- `/ll:verify-issues` - 2026-08-24T18:08:33 - `0ba47155-a1c2-4ae2-a900-cfc8dd2149a3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-24T16:11:04 - `b85ae83c-887b-4e17-9a4e-1911475585d3.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:49:23 - `9abc72d4-6fec-4dd7-b8b5-0bb4825d634b.jsonl`
- `/ll:verify-issues` - 2026-08-24T02:45:59 - `7bc562d1-bc37-48e1-a2c6-eed764be416d.jsonl`
- `/ll:decide-issue` - 2026-08-24T02:30:33 - `231886c3-196b-4c6d-973f-a50e5f1e0fea.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:26:50 - `967e4306-7dca-4e12-8af9-2d4291dc72fb.jsonl`
- `/ll:wire-issue` - 2026-08-24T02:37:01 - `0846a3fe-556d-4b20-b884-efdd9a3fc6d7.jsonl`
