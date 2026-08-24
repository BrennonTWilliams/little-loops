---
id: FEAT-3308
title: '`ll-artifact templatize`: save a generated artifact as a reusable template'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-23'
parent: EPIC-3299
depends_on:
- FEAT-3036
relates_to:
- FEAT-3309
- ENH-3035
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
learning_tests_required:
- jinja2
verify_verdict: EVIDENCE_UNVERIFIED
size: Very Large
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
No code exists: `grep -rn templatize scripts/` returns nothing.

Consequently the only way to obtain a template today is to hand-author one —
manifest, schema and templated body carved by hand out of a ~100KB self-contained
HTML file. That is the exact expensive manual work the epic exists to remove, and
it is the reason artifacts from the HTML loop family stay one-off.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review
```

produces a template directory that (a) validates, (b) re-renders byte-identically
(or with reviewed, intentional diffs) against the extracted `data.json`, and (c)
can then be pointed at any *other* architecture planning document via
`ll-artifact refresh`/`extract`.

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
   are presentation. Emit a candidate `data_schema` plus the extracted `data.json`.
   Repeated regions (per-section cards, list rows) must be detected as arrays, not
   flattened — this is the whole reason the design chose Jinja2 over the
   `.replace()` scheme in `cli/artifact.py:132-137`.
2. **Body templating (deterministic).** Replace each discovered region with the
   corresponding Jinja2 expression/block, leaving everything else byte-identical.
3. **Round-trip verify (deterministic).** `render(template, data.json)` and diff
   against the original artifact. A non-empty diff outside a declared tolerance is
   a hard failure — the fitness function, not an advisory warning.

Failure is loud and non-destructive: on a failed round trip, write the candidate
template plus the diff to the output dir and exit non-zero, so the user can hand-fix
rather than silently receive a lossy template.

### Design-token stamp points

The HTML loops receive design tokens as **prompt text** —
`cli/loop/_helpers.py:1416-1424` seeds `context["design_tokens_context"]` via
`render_as_prompt_context`. A generated artifact therefore has token values baked in
as literal hex. The template kit (ENH-3035) stamps tokens **at render time** as CSS
variables via `render_as_css_vars_themed` (`design_tokens.py:688`).

`templatize` must reconcile the two: recognize baked literal token values in the
artifact's CSS and lift them back into stamp points, or the round trip will pass on a
template that is permanently un-themeable and drifts from every other kit artifact.
If full lifting is out of reach for v1, the command must *report* the unlifted
literals rather than silently accept them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

This codebase holds two disagreeing conventions for an LLM-driven discovery/extraction stage
like `discover_regions`, and Implementation Step 3's "fail-closed against the emitted schema"
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

**Recommended**: Option A — `discover_regions`'s own stated requirement (Implementation Step 3:
"fail-closed against the emitted schema") matches Option A's raise-on-mismatch contract, not
Option B's silent-degrade contract. A silently-empty `data_schema` would pass Option B's error
handling but fail this issue's round-trip verify stage in a way that looks like the LLM found
nothing, not that the LLM call itself failed.

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

- `TemplatizeResult: {template_dir: Path, data: dict, diff: str | None, unlifted_tokens: list[str]}`

### Signatures

- `cmd_templatize(args: argparse.Namespace, logger: Logger) -> int`
- `discover_regions(artifact_html: str, source_text: str, prompt: str | None) -> tuple[dict, dict]` — returns `(data_schema, data)`
- `apply_regions(artifact_html: str, regions: dict) -> str` — deterministic body templating
- `verify_round_trip(template_dir: Path, data: dict, original: str) -> str | None` — returns a diff or None
- `lift_token_literals(css: str, tokens: DesignTokens) -> tuple[str, list[str]]`

### Call Path

`main_artifact` (`cli/artifact.py:275`) -> `cmd_templatize` -> `discover_regions`
-> `apply_regions` -> `verify_round_trip` -> `render` (FEAT-3036 Phase 1) ->
`render_as_css_vars_themed` (`design_tokens.py:688`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

No existing code implements a "render → diff against original → fail loud, write artifacts,
non-destructive" pipeline anywhere in `scripts/little_loops/` — a repo-wide grep for
`round.?trip`/`non-destructive` returns nothing outside the issue files themselves.
`verify_round_trip`'s contract is therefore novel to this codebase, not a convention to match;
the two existing `cli/artifact.py` handlers it must otherwise stay consistent with
(`cmd_policy_builder`, `cmd_design_md_export`) both write output only after all preceding steps
succeed and never demonstrate a write-then-roll-back sequence (see Integration Map finding
above) — `cmd_templatize` must run the round-trip check before any `mkdir`/`write_text` of the
template output to match that existing no-partial-writes-before-failure convention, since
neither handler shows how to undo a completed write.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Error-handling/return-code convention** (analyzer, gap-fill): `cmd_policy_builder` (`cli/artifact.py:106-150`) and `cmd_design_md_export` (`:208-272`) share one shape: whole-body `try/except Exception as exc:  # noqa: BLE001` -> `logger.error(str(exc)); return 1` as the only catch-all; expected/anticipated failures get inline `logger.error(...); return 1` *inside* the try (not raised) — e.g. unresolvable `--profile` (`:217-222`), no design tokens available (`:229-233`); a narrower `except DesignMdColorCollisionError` (`:240-244`) shows the pattern for a domain-specific exception needing a domain-specific message; success is `logger.success(...); return 0`; both call `.mkdir(parents=True, exist_ok=True)` immediately before `Path.write_text` (`:142/144`, `:263/264`) with no rollback if the write fails. `cmd_templatize` should follow this exact shape rather than raising custom exceptions.
- **Subparser registration shape** (analyzer, gap-fill): `policy-builder`'s flat registration is `pb = subparsers.add_parser("policy-builder", help=...)` (`:301-304`) plus `pb.add_argument(...)` calls (`:305-311`); dispatch is `if args.command == "policy-builder": return cmd_policy_builder(...)` appended to the if-chain at `:351-356` before the `parser.error(...)` fallback. A `templatize` subcommand follows this same flat shape.
- **Atomic-write helpers exist but are unused by `artifact.py`** (analyzer, gap-fill — corrects/narrows the earlier "no round-trip/rollback pattern exists anywhere" finding): `scripts/little_loops/file_utils.py` defines `atomic_write(path, content, encoding="utf-8")` (`:16-32`, temp-file-then-`os.replace`, unlinks temp on exception) and `atomic_write_json(path, data)` (`:35-57`, JSON-serialize + round-trip-validate + delegate to `atomic_write`) — both **single-file** only, not currently imported by `cli/artifact.py` (which calls `Path.write_text` directly at `:144`/`:264`). No multi-file, directory-scoped write-then-verify-then-rollback helper exists anywhere in the codebase (checked `init/writers.py` too, which has no cleanup logic). `cmd_templatize`'s "write template dir; if round-trip fails, clean up" requirement has only the per-file primitive to build on; any multi-file transaction wrapper is new code.
- **Render call-site positioning for `lift_token_literals`** (analyzer, gap-fill): `render_as_css_vars_themed` (`design_tokens.py:688`) has exactly one production call site, `_themed_css_vars()` (`cli/artifact.py:64-95`, called only from `cmd_policy_builder:109`); `render_as_prompt_context` (`design_tokens.py:572`) is called only from `cli/loop/_helpers.py:1423`, unrelated to `artifact.py`. Neither renderer is called anywhere in `artifact.py` today outside `_themed_css_vars`. `lift_token_literals` needs a resolved `DesignTokens` object in hand (via `load_design_tokens`) before either renderer runs — i.e. it slots in exactly where `_themed_css_vars` currently resolves tokens, not inside the renderers themselves.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact.py` — new `templatize` subparser + handler alongside `policy-builder` (`:301`) and `design-md export` (`:313`)
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — new subcommand section

_Wiring pass added by `/ll:wire-issue`:_
- ~~`scripts/little_loops/config/features.py:369-384` — `ArtifactsConfig` dataclass needs the new templates-directory field alongside `default_output_dir`~~ / ~~`scripts/little_loops/config/core.py:916-918` — `BRConfig.to_dict()`'s `"artifacts": {"default_output_dir": ...}` block must add the new field's key/value~~ — **FEAT-3036 already landed `artifacts.templates_dir`** in both `config-schema.json` and `ArtifactsConfig`; this issue inherits it and must not re-add it (see Scope Boundary below).
- `scripts/pyproject.toml:40-51` — add a `jinja2` dependency pin with a justifying comment above it, following the `anthropic` pin's shape (`CLAUDE.md`'s minimize-dependencies rule); confirmed `jinja2` has zero matches anywhere in the repo today [Agent 2/3 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:52,110` — `main_artifact` re-export; unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py:339,476-478` — `ArtifactsConfig.from_dict()` load site and `.artifacts` property; unaffected by a new field but confirms this is the only other reader of the `artifacts` config block besides the schema/dataclass already cited [Agent 2 finding]
- `scripts/tests/test_enh3268_design_md_export.py:354,367,378,394,410` — imports `cmd_design_md_export`, `main_artifact` directly; the closest existing sibling-subcommand test to model `test_artifact_templatize.py`'s dispatch tests after [Agent 1/3 finding]

### Similar Patterns
- `cmd_policy_builder` (`cli/artifact.py:98`) — the existing stamp-and-write shape
- `hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — hand-written loop states that already copy `${run_dir}/index.html` out; prior art for wanting artifacts to outlive a run

### Tests
- New test module under `scripts/tests/` (`test_artifact_templatize`) — round-trip fidelity against a checked-in fixture artifact + source pair
- `scripts/tests/test_policy_builder_emit.py` — unaffected, but the node gate (`test_policy_builder_node_gate.py`) must stay green

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py::test_artifacts_in_schema` (`:473-491`) — extend with assertions for the new `ArtifactsConfig` field (type + default), matching the existing `default_output_dir` assertion shape [Agent 3 finding]
- `scripts/tests/test_config_schema.py::TestSchemaValueParity.test_to_dict_values_match_schema_defaults` (`:1243-1265`) — will fail automatically if the new field's dataclass default (`config/features.py`) and its `config-schema.json` `default` diverge; no code change needed here beyond keeping the two in sync [Agent 2/3 finding]
- No fixture pairing an emitted HTML artifact with its generating source document exists yet in `scripts/tests/fixtures/` — the round-trip fixture has no in-repo precedent to copy; nearest transferable pattern is `_write_synthetic_profile`/`_reimport` in `test_enh3268_design_md_export.py:288-332,42-46` (write synthetic source under `tmp_path`, render, re-parse, assert fidelity) [Agent 3 finding]
- Model `test_artifact_templatize.py`'s dispatch tests on `test_policy_builder_emit.py::TestArtifactCLIDispatch` (`:204-230`) — mock-handler dispatch (patch `sys.argv` + target `cmd_*`, assert `main_artifact()` routes correctly) and the missing-subcommand `SystemExit` test, which extends automatically to `templatize` since it shares the same parser [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` § `artifacts` (`:910-924`) — add a table row + JSON example entry for the new field; the prose at `:912` ("Currently backs the `policy-builder` subcommand...") stops being accurate once `templatize` also reads this block and needs updating [Agent 2 finding]

### Configuration
- `scripts/little_loops/config-schema.json` § `artifacts` (`:1870-1880`) — currently exactly one field (`default_output_dir`) with `additionalProperties: false`; a templates directory setting needs adding there before this lands

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `_themed_css_vars` (`cli/artifact.py:64-95`) is a theme-resolution + degrade-gracefully wrapper around `render_as_css_vars_themed` — it is not a literal-scanning/substitution function. No function in `cli/artifact.py` or `design_tokens.py` scans arbitrary HTML for baked-in design-token literals and reverse-maps them to token names; `lift_token_literals` has no direct precedent to call.
- `DesignTokens.resolved` (`design_tokens.py:35`) is the only existing `name -> value` map; every renderer (`render_as_css_vars` `:678`, `render_as_css_vars_themed` `:688`, `render_as_prompt_context` `:572`) iterates it in the forward direction only. No `value -> name` reverse index exists anywhere in the codebase — `lift_token_literals` would need to build this inversion from scratch, not reuse an existing lookup.
- `main_artifact` (`cli/artifact.py:275-357`) subparser registration is a flat, single-level pattern for `policy-builder` (`:301-311`, matching the issue's own description) versus a nested two-level pattern for `design-md export` (`:313-343`, second `add_subparsers(dest="subcommand")`). A new `templatize` subcommand following the issue's own "alongside policy-builder" framing would use the flat form. Dispatch is a manual if-chain (`:351-356`), not a registry — a `templatize` branch is one more `if args.command == "templatize": return cmd_templatize(...)` line, plus a manual addition to the hardcoded `epilog` string (`:282-298`) that lists commands and exit codes (not generated from the subparser tree).
- Existing `cli/artifact.py` subcommands (`cmd_policy_builder` `:106-150`, `cmd_design_md_export` `:208-272`) share one error-handling shape: whole-body `try/except Exception as exc:  # noqa: BLE001`, `logger.error(str(exc)); return 1` on the catch-all path; narrower early `logger.error(...); return 1` returns (no raise) for expected/validated failures; `logger.success(...); return 0` only after all file writes succeed. Neither handler demonstrates a write-then-verify-then-rollback sequence — `cmd_templatize`'s "fail loud and non-destructive" round-trip check would need to run before any `mkdir`/`write_text` of the template output to match this file's existing convention of not writing partial output before a validation failure.
- Confirmed via targeted grep (not just the code graph, which returned an empty result for `main_artifact` callers): `main_artifact` is referenced only at `cli/__init__.py:52` (import) and `:110` (re-export) — no other caller exists in the codebase.
- `ArtifactsConfig` (`scripts/little_loops/config/features.py:368-384`) is the dataclass backing `config-schema.json`'s `artifacts` block (`:1870-1880`, currently one field, `additionalProperties: false`) — a templates-directory setting needs adding in **both** places, not just the schema file already cited in this section.
- Confirmed via `grep -rn "^def render(" scripts/little_loops/` (no hits) and a repo-wide `grep -rln "FEAT-3036"` (matches only `.issues/` markdown, no source module): FEAT-3036 Phase 1's `render()`, manifest loader, and Jinja2 environment are wholly unimplemented — this issue's Implementation Step 1 ("Land FEAT-3036 Phase 1 — hard dependency") blocks on code that does not exist yet, not merely on an unmerged PR.
- `jinja2` is not present in `scripts/pyproject.toml`'s dependency list (confirmed absent) — adding it requires a justifying comment in the `anthropic`-pin style per `CLAUDE.md`'s minimize-dependencies rule. The only current in-repo placeholder-substitution precedent is `cmd_policy_builder`'s literal `.replace()` scheme (`cli/artifact.py:132-137`), which this issue's own text already cites as insufficient for repeated-region templating.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `scripts/little_loops/file_utils.py:16-32,35-57` — `atomic_write`/`atomic_write_json`, existing single-file atomic-write helpers not currently imported by `cli/artifact.py` (which writes via `Path.write_text` directly); reusable per-file primitive for `cmd_templatize`'s output writes, though no multi-file/directory-scoped rollback helper exists to build the "write dir; clean up on round-trip failure" requirement from [Agent 2 gap-fill finding]
- `scripts/pyproject.toml:70` — `main_artifact`'s only true "caller" is the `ll-artifact` console-script entry point (`ll-artifact = "little_loops.cli:main_artifact"`); confirms the existing `cli/__init__.py:52,110` finding is complete (import + re-export + entry point are the entire reference set, no in-repo Python call site) [Agent 2 gap-fill finding]

## Implementation Steps

1. Land FEAT-3036 Phase 1 (`render` + manifest format) — hard dependency.
2. Implement `apply_regions` + `verify_round_trip` deterministically, driven by a hand-written region map fixture (no LLM in the test path).
3. Implement `discover_regions` as the LLM stage, fail-closed against the emitted schema.
4. Add token-literal lifting and the unlifted-literals report.
5. Wire the subcommand, docs, and the fixture round-trip test.

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

- [ ] `ll-artifact templatize <artifact> <source> -o <dir>` produces a template directory that `ll-artifact render` accepts.
- [ ] Round-trip: rendering the produced template with the produced `data.json` reproduces the original artifact byte-identically, or the command exits non-zero and writes the diff.
- [ ] A repeated region in the source (N sections → N cards) is templatized as a Jinja2 loop over an array, not unrolled — asserted by a test with N=2 and N=5 data.
- [ ] Baked design-token literals are lifted into stamp points, or explicitly reported as unlifted; a test asserts the report is non-silent.
- [ ] The resulting template renders correctly against a *second, different* source document of the same kind — the fan-out case, not just the round trip.
- [ ] The generating FSM loop is not invoked at any point in `templatize` or in subsequent renders.

## Impact

- **Priority**: P2 — this is the epic's user-facing entry point; the epic's stated value is not deliverable without it. Raised above the P3 dashboard-lineage children deliberately.
- **Effort**: Large — region discovery over an opaque self-contained file is the hard problem in the epic.
- **Risk**: Medium — round-trip fidelity is a hard, automatable gate, which bounds the risk of a lossy result shipping silently.
- **Breaking Change**: No — new subcommand.

## Verification Notes

_Added by `/ll:verify-issues --check --auto` — 2026-08-23:_

- **Verdict: EVIDENCE_UNVERIFIED** (BUG-3282 check B7). `ll-verify-evidence` flags
  the span `` `grep -rn templatize scripts/` `` (Current Behavior, line 44) as
  attributed to FEAT-3036, unverifiable in any revision of that artifact.
  Independently re-ran the command against the current tree: it still returns
  nothing, so the underlying claim is true. The flag is very likely a
  misattribution artifact of the detector's proximity heuristic (the nearest
  preceding artifact reference, "Split out of FEAT-3036 Phase 4," line 28, gets
  credited with a span that is actually the issue author's own shell-command
  output, not a quote sourced from FEAT-3036). Per the command's documented
  precision (~0.13–0.20 on the paraphrase/misattribution class), this reads as a
  false positive rather than fabricated evidence. Persisted per spec regardless,
  since the check is advisory (no `reconcile_issue` routing) — no content change
  needed on this basis.
- All 21 spot-checked code/doc citations (`cli/artifact.py`, `design_tokens.py`,
  `host_runner.py`, `advisor.py`, `learning_tests/extractor.py`,
  `config/features.py`, `config/core.py`, `config-schema.json`, test files,
  `CONFIGURATION.md`, `CLI.md`) still match at HEAD. A few (design-md `export`
  registration cited at `:313` vs. actual `:319`; `cmd_design_md_export` cited
  body range `:208-272` vs. actual def start `:192`; `advisor.py:147-190` cited
  as enforcement context vs. the raise itself at `:267-278`) are off by a small
  number of lines within the same function/block — normal drift tolerance, not
  flagged as OUTDATED.
- Dependencies (FEAT-3036, ENH-3035, FEAT-3309, EPIC-3299) all open; no
  completed-issue match, so no regression analysis applies. `depends_on`/
  `relates_to`/`parent` backlinks all confirmed present in the referenced files.
- No active required decision rules in the decisions log — DECISIONS_VIOLATION
  does not apply.
- Confirmed `grep -rn templatize scripts/` still returns nothing and `jinja2`
  is still absent from `scripts/pyproject.toml` — the issue's core "no code
  exists yet" premise holds.

## Related Key Documentation

- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub; read first
- `docs/reference/CLI.md` — `ll-artifact`

## Status

**Open** | Created: 2026-08-23 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `artifacts.templates_dir` was already added to `config-schema.json` and `ArtifactsConfig` by FEAT-3036 (done). This issue inherits that field rather than re-adding it — the earlier Wiring Phase / Integration Map entries claiming ownership of it are struck through above. FEAT-3304 owns the separate `artifacts.export` block.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-24T16:11:04 - `b85ae83c-887b-4e17-9a4e-1911475585d3.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:49:23 - `9abc72d4-6fec-4dd7-b8b5-0bb4825d634b.jsonl`
- `/ll:verify-issues` - 2026-08-24T02:45:59 - `7bc562d1-bc37-48e1-a2c6-eed764be416d.jsonl`
- `/ll:decide-issue` - 2026-08-24T02:30:33 - `231886c3-196b-4c6d-973f-a50e5f1e0fea.jsonl`
- `/ll:refine-issue` - 2026-08-24T02:26:50 - `967e4306-7dca-4e12-8af9-2d4291dc72fb.jsonl`
- `/ll:wire-issue` - 2026-08-24T02:37:01 - `0846a3fe-556d-4b20-b884-efdd9a3fc6d7.jsonl`
