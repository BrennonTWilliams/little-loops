---
id: FEAT-3310
type: FEAT
title: 'Artifact templates: extract + refresh (Phase 2)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T03:57:16Z'
parent: EPIC-3299
depends_on:
- FEAT-3036
labels:
- planning-hub
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3310: Artifact templates: extract + refresh (Phase 2)

## Summary

Phase 2 of FEAT-3036's artifact-template design: add `ll-artifact extract` (LLM
source -> `data.json` mapping, schema-checked) and `ll-artifact refresh`
(`extract` + `render` composed against the bound source by default).

## Current Behavior

`ll-artifact render` (FEAT-3036 Phase 1) renders a `.llat/` template
deterministically against a hand-authored `data.json`. There is no way to
derive `data.json` from a source document without hand-authoring it.

## Expected Behavior

- `ll-artifact extract <template> <source-file> [--data <path>]` — an LLM step
  that maps *source-file* to `data.json` per the manifest's `data_schema` +
  `extraction.prompt`, using a direct `build_blocking_json(json_schema=...)`
  host call that fails loud (resolved in FEAT-3036 § Second-pass decisions ->
  *`extract`'s LLM invocation — resolved by FEAT-3308*: `advisor.py`'s shape,
  not `learning_tests/extractor.py`'s fail-soft prose-marker parse). Fails
  loudly if the output doesn't validate against `data_schema`.
  Carries `--model` and `--timeout` flags (new CLI surface — see
  § Pre-implementation decisions -> *`--model`/`--timeout` are new surface*).
  Guards source size before the host call: a source file above the configured
  byte ceiling is rejected with a typed error naming the limit, rather than
  being fed whole into a blocking host invocation.
- `ll-artifact refresh <template> [<source-file>] [--data <path>] [-o <dir>]` —
  `extract` + `render` in one shot, against the manifest's bound `source:` by
  default, and writing the `<template>.llat.lock` entry for the source it just
  consumed (see § Pre-implementation decisions -> *`refresh` owns the lockfile
  write*).

### Pre-implementation decisions (2026-08-25 review)

These close ambiguities found in a pre-implementation review of this issue and
FEAT-3311. They are decisions, not open questions.

**`manifest.source` is a scalar string, not a mapping.** FEAT-3036's design
sketch (`P3-FEAT-3036-...md:131-132`) writes `source: {path: ...}`, but the only
existing writer — `templatize.build_manifest` (`templatize.py:519-535`) — emits
`"source": str(source)`, a plain path string, and every `.llat/` produced to
date carries that shape. The scalar wins: it is what ships. `refresh` resolves
its default source as `manifest["source"]` (project-root-relative if not
absolute), **not** `manifest["source"]["path"]`.

**`load_manifest` gains inner-shape validation for `source` and `extraction`.**
Today `load_manifest` (`artifact_templates.py:142`) checks only that these are
allowed top-level keys. `extract.py` is their first reader, so a hand-written
manifest with `source: {path: ...}` (or an `extraction` that is not a mapping)
currently surfaces as an `AttributeError`/`TypeError` swallowed by
`cmd_*`'s trailing `except Exception` backstop and reported as an opaque exit 1.
Validation belongs in `load_manifest` — the module that owns every other
manifest shape rule — not locally in `extract.py`: `source` must be a non-empty
string; `extraction`, if present, must be a mapping. This resolves the open
question recorded under § Program Design → Decision Rules (wiring pass).

**A manifest with no usable `extraction.prompt` is a loud, typed failure.**
`extract` raises its module error naming the template and the missing key; it
never falls back to a synthesized default prompt. Note that
`templatize.build_manifest` writes `extraction` as `{"method": ..., "regions_map": ...}`
or `{"method": ..., "host": ..., "model": ...}` — neither carries `prompt`, so
templatize-produced templates need a hand-added `prompt` before `extract` works
on them. Say so in the error message.

**`json_schema` enforcement is host-dependent, so post-call validation is
load-bearing.** Claude Code drops `json_schema` silently
(`host_runner.py:442-465`); Codex materializes it (`:736-770`). The
`validate_top_level_data` call after the host returns is the *only* guarantee on
the Claude Code path — it is not defense in depth, and must not be skipped or
downgraded to a warning on the grounds that the schema was already passed.

### Pre-implementation decisions (2026-08-25 second review)

A second pre-implementation review found the decisions above left several
load-bearing details open, plus one factual error and one wrong precedent
claim. These close them. They are decisions, not open questions.

**`manifest.source` is normalized to project-root-relative on write.** The
only writer, `templatize.py:790` + `:885`, does `source_path = Path(args.source)`
and stores `str(source)` verbatim — i.e. relative to the *invocation cwd*, not
the project root. The § Pre-implementation decisions rule above ("`refresh`
resolves `manifest["source"]` project-root-relative if not absolute") therefore
disagrees with what `templatize` actually writes whenever cwd ≠ project root.
Resolution, symmetric on both sides:

- `templatize.build_manifest`'s caller (`templatize.py:885`) normalizes
  *source_path* to a project-root-relative path before storing it (absolute
  paths are stored absolute). This is a new edit to `templatize.py`, listed in
  § Files to Modify.
- `refresh` resolves `manifest["source"]` against `config.project_root` when it
  is not absolute, and **fails loud** with a typed error naming the resolved
  path if it does not exist — it never falls back to a cwd-relative
  interpretation.

**The source-size ceiling reuses `artifacts.templatize_max_input_bytes`.** The
knob already exists (`config-schema.json:1885-1889`, default `400000`, measured
in bytes not tokens) and guards exactly the same class of hazard: an unbounded
document fed into a blocking host call. `config-schema.json` is
`additionalProperties: false`, so a new `extract_max_input_bytes` would be a
schema edit plus a second knob users must reason about for no behavioural gain.
Reuse it, and widen its `description` from "`ll-artifact templatize`" to "`ll-artifact
templatize` and `ll-artifact extract`". The schema-description edit is listed in
§ Files to Modify.

**`--model`/`--timeout` are new surface, not an existing convention.** The
§ Expected Behavior text originally justified these as "matching the
LLM-boundary precedent it copies (`discover.py:395-464`)." That is wrong: the
*function* `build_blocking_json` takes both parameters, but no artifact
subcommand exposes them as flags — `discover.py:418` hardcodes
`model = DEFAULT_LLM_MODEL` and `:429` hardcodes `timeout=180`, and
`templatize` registers five arguments, none of them model or timeout. Adding
the flags is still the right call (`extract` is user-invoked per-source, unlike
`discover`, which is an internal stage of `templatize`) — but it is new CLI
surface and must be documented as such, not as convention-following.

Precedence, since `templatize`-produced manifests already carry an
`extraction.model` (`templatize.py:870-874`): **`--model` > `extraction.model` >
`fsm.schema.DEFAULT_LLM_MODEL`.** `extraction.host` stays purely diagnostic —
`extract` always resolves its host via `resolve_host()` (ambient, per
`LL_HOST_CLI` / `orchestration.host_cli`) and never honours a manifest-pinned
host, because a manifest committed on one machine must not silently redirect
another machine's host selection. `--timeout` defaults to `180`, matching
`discover.py:429`.

**`extraction.prompt` is a fragment, not the whole prompt.** `extract` owns a
module-level `_PROMPT_TEMPLATE` (the `discover.py:_PROMPT_TEMPLATE` shape) that
wraps three parts: the manifest's `extraction.prompt` text, the serialized
`data_schema`, and the source document text. The author's prompt describes
*what to extract*; the module supplies *the shape to return it in* and the
material. Treating `extraction.prompt` as the entire prompt would require every
template author to hand-inline their own `data_schema` and keep it in sync — a
guaranteed drift source, and pointless on the Codex path where the schema is
already materialized into the invocation.

**Flag naming: `--data <path>` is the data.json target on both verbs; `-o` is
reserved for the render output directory.** `render`'s `-o` already means an
output *directory* (`render.py:71-79`: the artifact lands at
`output_dir / manifest["output"]`). Giving `extract` a `-o` that means an output
*file* would put three meanings behind two names. So:

- `extract <template> <source-file> [--data <path>]` — writes the extracted
  data to *path*, defaulting to `<template>/data.json`.
- `refresh <template> [<source-file>] [--data <path>] [-o <dir>]` — `--data`
  is the same data.json target with the same default; `-o` passes through to
  the render half with `render`'s exact semantics and default
  (`config.artifacts.default_output_dir`).

**`refresh` owns the lockfile write (moved here from FEAT-3311).** FEAT-3311's
original AC 1 required a change to `cmd_refresh` — a function *this* issue
creates — so FEAT-3311 could not be tested end-to-end until this issue landed,
which its own confidence check flags as its top concern. Splitting on the file
boundary instead: this issue writes the lockfile from `cmd_refresh`; FEAT-3311
owns the reader (`status`) and the `render --source` writer. Each issue then
lands and tests independently.

Concretely, `cmd_refresh` must hold the resolved source path **and its bytes**
live across the render step (it already reads them for the extraction), and
after the render's output write succeeds, write/update
`<template>.llat.lock`. Format, states, and the reader are FEAT-3311's; the
write contract this issue must satisfy is:

```yaml
version: 1
renders:
  <project-root-relative source path>:
    sha256: <hex sha256 of the source bytes extract consumed>
    rendered_at: <ISO-8601 UTC, e.g. 2026-08-25T04:12:33Z>
    output: <project-root-relative path of the rendered artifact FILE>
```

`output` is the full rendered *file* path (`output_dir / manifest["output"]`),
not the `-o` directory. `rendered_at` is ISO-8601 UTC with a trailing `Z`,
second precision, and is diagnostic only — nothing classifies on it and no test
asserts its value, only its format (it is the one nondeterministic field in a
subsystem otherwise built on byte-exact round-trips). The write is atomic —
write to a sibling temp file and `os.replace` onto the lock path, mirroring
`templatize.py`'s tmp-dir-then-swap discipline — so an interrupted refresh
cannot leave a truncated lockfile that `status` must then reject as
unparseable. Merge semantics: load any existing lockfile and update only the
`renders[<source>]` entry, preserving other sources' entries (EPIC-3299's
one-template-many-sources case).

Because this issue ships first, **this issue creates
`cli/artifact/lockfile.py`**, the format's single home:
`LockfileError(ValueError)`, `load_lockfile(path) -> dict` (fail-closed on
unparseable YAML, non-mapping top level, missing/non-mapping `renders`, or an
unknown `version` — mirroring `load_manifest`'s frozenset-validation shape at
`artifact_templates.py:142-189`), `write_lockfile(path, entries)` (the atomic
merging write above), and `lock_path_for(root) -> Path` (`root.parent /
f"{root.name}.lock"`). `cmd_refresh` is its first caller; FEAT-3311's `status`
reader and `render --source` writer import the same module rather than
redefining the shape. **FEAT-3311 § Expected Behavior is the authoritative
spec for this format** — implement to it, and if the two issues disagree,
FEAT-3311 governs.

**Both verbs live in `extract.py`, and `__init__.py`'s docstring is amended to
say so.** `cli/artifact/__init__.py:12-14` states the convention explicitly:
"One module per subcommand (`policy_builder.py`, `design_md.py`,
`render.py`)". `refresh` is a thin compose over `extract` + `render` with no
independent logic, so a `refresh.py` that imports `cmd_extract` and
`render_template` would be a file of glue. Keep both in `extract.py` and update
the docstring to name the exception. This closes the "worth confirming at
implementation time" note under § Codebase Research Findings.

## Use Case

A user has authored `quarterly-risk-report.llat/` (FEAT-3036 Phase 1) and
wants to regenerate `quarterly-risk-report.html` after `docs/risk-register.md`
changes, without hand-editing `data.json`. They run `ll-artifact refresh
quarterly-risk-report`, which maps the changed register to a fresh
`data.json` via one small LLM call, validates it against the manifest's
`data_schema`, then renders deterministically — no full FSM loop re-run.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- `scripts/little_loops/cli/artifact/extract.py` (new) — `cmd_extract`, `cmd_refresh`, `add_extract_parser`, `add_refresh_parser`, per the issue's own Program Design → Call Path. **Resolved 2026-08-25** (§ Pre-implementation decisions, second review): both verbs stay in one module, and `__init__.py`'s one-module-per-subcommand docstring is amended to name the exception.
- `scripts/little_loops/cli/artifact/__init__.py:74-135` — `main_artifact()`'s subparser registration block (`add_render_parser(subparsers)` / `add_templatize_parser(subparsers)` at lines 119-120) and its flat `if args.command == "..."` dispatch chain (lines 127-135) both need new arms for `extract`/`refresh`. The module docstring (lines 1-15) enumerates every subcommand with its originating FEAT/ENH ID — needs an entry for FEAT-3310 **and** an amendment to its closing "One module per subcommand (`policy_builder.py`, `design_md.py`, `render.py`)" sentence (`:12-14`), which `extract.py`'s two verbs deliberately depart from.
- `scripts/little_loops/cli/artifact/templatize.py:790` + `:885` — `source_path = Path(args.source)` is stored verbatim by `build_manifest`, i.e. cwd-relative. Normalize to project-root-relative before storing, per § Pre-implementation decisions (second review) → *`manifest.source` is normalized to project-root-relative on write*. Without this, `refresh`'s project-root-relative resolution silently misses the source whenever `templatize` was run from a subdirectory.
- `scripts/little_loops/config-schema.json:1885-1889` — `artifacts.templatize_max_input_bytes` (default `400000`) is reused as `extract`'s source-size ceiling; widen its `description` to name `ll-artifact extract` alongside `templatize`. No new knob is added (the object is `additionalProperties: false`, so a new key would be a schema edit for no behavioural gain).
- `docs/reference/CLI.md:4509-4530` (`#### ll-artifact render`), `:4532-4564` (`#### ll-artifact templatize`) — the two-part doc pattern (prose → `**Flags:**` table → `**Examples:**` → `**Exit codes:**`) new `#### ll-artifact extract` / `#### ll-artifact refresh` sections must follow (AC requires this).
- `docs/reference/CLI.md:4566` carries a note: `**Note:** ... \`extract\` (FEAT-3309, deriving a \`data.json\` automatically for fan-out) and \`status\` (staleness detection) are not yet implemented.` This note attributes the not-yet-built `extract` to FEAT-3309, but FEAT-3309 ("Loop→artifact handoff: promote a run artifact to a durable path") is a different, already-completed issue — the ID in that note appears stale/incorrect and should be corrected to FEAT-3310 (or removed) when this issue lands.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/render.py:27-89` (`cmd_render`) — the direct precedent `refresh`'s render half composes: builds `ArtifactTemplate`, calls `resolve_template` → `load_manifest` → `load_data`/`validate_top_level_data` → `render_template`, all imported from `artifact_templates.py`.
- `scripts/little_loops/cli/artifact/templatize.py:545-566` (`verify_round_trip`) and `:897-899` (data.json write) — the closest existing precedent for building an in-memory `data` dict and calling `render_template` on it directly without a `load_data` disk round-trip, and for the write-to-disk shape if `refresh` persists the extracted `data.json`.
- `scripts/little_loops/cli/artifact/discover.py:395-464` (`discover_regions`) — the direct precedent for `extract`'s LLM call: `resolve_host()` → `runner.build_blocking_json(prompt=..., model=..., json_schema=SCHEMA)` → `run_blocking_json(invocation, timeout=N)`, wrapped in `try/except BlockingJsonError as exc: raise <ModuleError>(...) from exc`, plus a caller-side `issubset(raw.keys())` check since `json_schema` enforcement is host-dependent (Claude Code drops it silently; Codex materializes it — `host_runner.py:442-465` vs `:736-770`).
- `scripts/little_loops/advisor.py:267-290` (`consult`) — the second reference for the same `build_blocking_json(json_schema=...)` shape, cited directly in this issue's Program Design.

### Conventions in Force
- Subcommand registration: an `add_<name>_parser(subparsers)` function inside the subcommand's own module, called from `main_artifact()` — evidence: `render.py:91`, `templatize.py:965`, called at `__init__.py:119-120`. Older subcommands (`policy-builder`, `design-md`) instead build parsers inline in `__init__.py` — two coexisting styles.
- Handler signature: `cmd_<name>(args, logger) -> int`, narrow `except <DomainError>` arms above a trailing `except Exception as exc: # noqa: BLE001` backstop that logs and returns 1 — evidence: `render.py:27`, `templatize.py:775`.
- LLM-boundary isolation: `artifact_templates.py` and `render.py`/`templatize.py` docstrings state the module "must never import `host_runner` or `anthropic`" (`artifact_templates.py:9-11`); any LLM call is isolated in its own module, imported locally inside the calling function body rather than at module scope (`templatize.py:856`: `from little_loops.cli.artifact.discover import discover_regions` inside `cmd_templatize`) — evidence extract's own LLM call should follow the same isolation from `artifact_templates.py`.
- Fail-loud vs. fail-soft LLM-call convention (contested, not resolved elsewhere in the codebase): `discover.py`/`advisor.py` raise a typed exception on any host/parse failure and preserve the raw response (`.raw`/`.resolved` attributes) so a caller can still act on the rejected artifact; `learning_tests/extractor.py:116-146` explicitly fails soft (returns `""`, logs a warning) because "the learning gate is a best-effort safety net." This issue's own AC pins extract to the fail-loud shape — noted here only because it is the sole place in the codebase that frames these as alternatives to choose between.
- Test style (contested — two coexisting patterns, pick one knowingly): `render`'s tests (`test_feat3036_artifact_templates.py`) use a handler-level class calling `cmd_render(args, logger)` directly PLUS a separate dispatch-only class mocking `cmd_render` to assert argv routing (`TestCmdRender` line 375, `TestArtifactCLIDispatchRender` line 458). `templatize`'s tests (`test_artifact_templatize.py`) instead call `main_artifact()` end-to-end via a `_run(tmp_path, argv)` helper with no separate handler-level or dispatch-mock class. This issue's own Program Design cites the `render` style (`TestCmdRender`/`TestArtifactCLIDispatchRender`) as the pattern to follow.

### Tests
- `scripts/tests/test_feat3036_artifact_templates.py:375` (`TestCmdRender`), `:458` (`TestArtifactCLIDispatchRender`) — the pattern this issue's own Program Design names to extend.
- `scripts/tests/test_artifact_templatize.py:394` (`TestCmdTemplatizeEndToEnd`) — the alternative end-to-end-only test style (see Conventions in Force above).
- No `scripts/tests/test_feat3310_artifact_extract.py` exists yet.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_artifact_discover.py:18-29` (`_make_runner`), `:195-248` (`TestDiscoverRegions`) — the concrete mocking pattern for `extract`'s host boundary: patch `little_loops.cli.artifact.extract.resolve_host` and `...run_blocking_json` (module-under-test's imported names, not `host_runner`'s), with `side_effect=BlockingJsonError(...)` to assert the fail-loud translation to a typed domain error.
- `scripts/tests/test_feat3036_artifact_templates.py:399-411` (`test_schema_violation_exits_1_and_writes_nothing`) — direct precedent for the "no partial write" AC: asserts `code == 1` and `not out_dir.exists()`; `extract`'s schema-violation test should assert `not (root / "data.json").exists()` the same way.

### Configuration
- `scripts/little_loops/config-schema.json:1875-1895` — `artifacts.templates_dir` (default `artifacts/templates`) and `artifacts.default_output_dir` (default **`.`**, the project root), read via `BRConfig(Path.cwd())` in `cmd_render`/`cmd_templatize` — `extract`/`refresh` resolve the template root the same way. **Correction (2026-08-25, second review):** an earlier revision of this bullet gave `default_output_dir`'s default as `.loops/artifacts`; that is `artifacts.promotion_dir`'s default (FEAT-3309), a deliberately distinct key. `refresh`'s bare `-o`-less render therefore lands in the project root, matching `render`.
- `scripts/little_loops/config-schema.json:1885-1889` — `artifacts.templatize_max_input_bytes` (default `400000`, bytes not tokens): reused as `extract`'s source-size ceiling rather than adding a second knob (§ Pre-implementation decisions, second review).

### Documentation
- `docs/reference/CLI.md:4455-4468` — shared `### ll-artifact` header's `**Subcommands:**` table needs new `extract`/`refresh` rows.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:4457` — the `### ll-artifact` top-level prose paragraph enumerates each subcommand by name and phase ("`render` (FEAT-3036 Phase 1) ... `templatize` (FEAT-3314 Phase A) ...") — needs a sentence for `extract`/`refresh`, distinct from the `**Subcommands:**` table already noted above.
- `scripts/little_loops/cli/artifact/__init__.py:51-70` — `main_artifact()`'s `argparse.RawDescriptionHelpFormatter` epilog hand-writes its own `Examples:` and `Exit codes:` blocks as raw text (not generated from the subparsers) — this is live `--help` text, separate from CLI.md prose and from the subparser-registration/dispatch-chain edit already listed above. Needs new example invocations (`%(prog)s extract ...`, `%(prog)s refresh ...`) and exit-code prose for the fail-loud path.
- `docs/reference/CLI.md:4566` — **cross-issue coupling**: FEAT-3311 independently plans to edit this same not-yet-implemented-note line (to drop `status`). Whichever issue lands second must reconcile against the other's edit rather than blindly re-adding the sentence.

## Program Design

### Call Path

`cmd_extract` / `cmd_refresh` (new `cli/artifact/extract.py`) reuse
`little_loops.artifact_templates.{resolve_template, load_manifest,
validate_top_level_data}` from FEAT-3036 Phase 1 unchanged. `cmd_refresh` ->
`cmd_extract` (writes `data.json`) -> `render_template` (FEAT-3036 Phase 1,
also unchanged) -> lockfile write. `extract`'s host call follows `advisor.py`'s
`build_blocking_json(json_schema=...)` shape (resolved in FEAT-3036 §
Second-pass decisions), not `learning_tests/extractor.py`'s fail-soft
prose-marker parse.

`cmd_refresh` must keep the resolved source path **and its bytes** live across
the render step: the same bytes it fed to the extraction are what the lockfile
hashes. Re-reading the file after the render would open a TOCTOU window in
which a source edited mid-refresh gets stamped FRESH against bytes that never
produced the artifact — the exact dishonesty FEAT-3311's render-side decision
exists to prevent.

### Tests

New coverage lands in a dedicated `test_feat3310_artifact_extract.py` (or an
extension of `test_feat3036_artifact_templates.py`), following the
handler-level + dispatch-level test pattern established by
`cmd_render`/`TestArtifactCLIDispatchRender` in FEAT-3036.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

### Types

- `ArtifactTemplate.data_schema` (`artifact_templates.py:63`, thin accessor over `manifest["data_schema"]`) — the schema `extract`'s `build_blocking_json(json_schema=...)` call and post-call validation both key off.
- Manifest optional keys `source: str` and `extraction: dict` (`artifact_templates.py:26` `_MANIFEST_OPTIONAL_KEYS`) already exist in the schema-allowed key set but are unread by `artifact_templates.py` itself today — `templatize.py:519` (`build_manifest`) is the only current writer, and its `extraction` dict shape is `{"method": ..., "regions_map": ...}` or `{"method": ..., "host": ..., "model": ...}`, not `{"prompt": ...}`. This issue's `extraction.prompt` is new manifest surface with no existing reader or schema validation — `load_manifest` (`artifact_templates.py:142`) checks only that `extraction` is an allowed top-level key, not its inner shape.

### Signatures

- `resolve_template(template_arg: str, templates_dir: Path) -> Path` (`artifact_templates.py:67`) — raises `TemplateResolutionError`.
- `load_manifest(root: Path) -> dict[str, Any]` (`artifact_templates.py:142`) — raises `ManifestError`.
- `validate_top_level_data(data: Any, schema: dict) -> None` (`artifact_templates.py:233`) — raises `DataValidationError`.
- `render_template(template: ArtifactTemplate, data: dict[str, Any], config: BRConfig) -> str` (`artifact_templates.py:304`) — takes an already-validated in-memory `data` dict; never reads `data.json` itself.
- `HostRunner.build_blocking_json(self, *, prompt: str, model: str | None = None, json_schema: dict | None = None) -> HostInvocation` (Protocol, `host_runner.py:304-312`) — the call `extract` must make, per `discover_regions()` (`discover.py:395-464`) and `consult()` (`advisor.py:267-280`).
- `run_blocking_json(invocation: HostInvocation, timeout: int) -> dict[str, Any] | None` (`host_runner.py:2103`) — executes the built invocation; raises `BlockingJsonError` (`host_runner.py:2019`) on timeout/missing binary/non-zero exit/unparseable output. Callers additionally do their own `issubset(raw.keys())` key-membership check on the result, since `json_schema` enforcement is host-dependent (Claude Code drops it silently; Codex materializes it — `host_runner.py:442-465` vs `:736-770`).

### Decision Rules

- Fail-loud gate: `extract`'s host call must raise (not degrade to a default) on any of: `BlockingJsonError` from `run_blocking_json` (timeout, missing binary, non-zero exit, unparseable output), a `None` result, or a result whose keys don't satisfy the manifest's `data_schema` after `validate_top_level_data` — matching `discover_regions()`'s shape (`discover.py:417-464`: catch `BlockingJsonError`, re-raise as the module's own error `from exc`), explicitly not `learning_tests/extractor.py`'s fail-soft `return ""` pattern (`extractor.py:116-146`).
- No partial write: if `validate_top_level_data` rejects the extracted data, `data.json` must not be written (or left partially written) — `render.py`'s `cmd_render` establishes the precedent of validating fully before any output-path write occurs (`render.py`'s data validate step precedes the render/write step).
- Model resolution (**added 2026-08-25, second review**): `--model` > `manifest["extraction"]["model"]` > `fsm.schema.DEFAULT_LLM_MODEL`. `manifest["extraction"]["host"]` is diagnostic only and never overrides `resolve_host()`'s ambient selection (`LL_HOST_CLI` / `orchestration.host_cli`) — a manifest committed on one machine must not silently redirect another machine's host. `--timeout` defaults to `180`, matching `discover.py:429`.
- Prompt assembly (**added 2026-08-25, second review**): a module-level `_PROMPT_TEMPLATE` in `extract.py` composes `manifest["extraction"]["prompt"]` (what to extract) + the serialized `data_schema` (the shape to return) + the source text (the material), mirroring `discover.py:_PROMPT_TEMPLATE`. `extraction.prompt` is never used as the entire prompt.
- Lockfile write ordering (**added 2026-08-25, second review**): `cmd_refresh` writes `<template>.llat.lock` only after the render's output-file write succeeds, atomically (temp sibling + `os.replace`), merging into any existing `renders` mapping rather than replacing it. A lockfile-write failure is an exit-1 failure of `refresh` — the artifact is already on disk, so the error message must say the render succeeded and only the lock write failed, otherwise the user re-runs a paid LLM call to fix a filesystem problem.

_Wiring pass added by `/ll:wire-issue`:_
- `load_manifest` (`artifact_templates.py:142`) validates only that `extraction` is an allowed top-level manifest key — it does not validate the inner shape of `extraction.prompt`. `extract.py` will be the first consumer of `manifest.get("extraction", {}).get("prompt")`. **Resolved 2026-08-25** (§ Expected Behavior → Pre-implementation decisions): inner-shape validation for `source` and `extraction` lands in `load_manifest`, not locally in `extract.py`; a missing `extraction.prompt` is a typed loud failure at `extract` time.
- **Manifest `source` shape — resolved 2026-08-25.** FEAT-3036's design sketch and this issue's original AC said `source.path` (a mapping); `templatize.build_manifest` (`templatize.py:519-535`) writes `"source": str(source)` (a scalar). The scalar is authoritative. See § Expected Behavior → Pre-implementation decisions.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:4457` — add `extract`/`refresh` to the `### ll-artifact` top-level subcommand-enumeration prose.
- Update `scripts/little_loops/cli/artifact/__init__.py:51-70` — add `extract`/`refresh` examples and exit-code prose to the `main_artifact()` argparse epilog (separate from the subparser registration and dispatch-chain edits already in Files to Modify).
- Coordinate `docs/reference/CLI.md:4566` edit with FEAT-3311, which independently edits the same line.

_Second-review additions (2026-08-25):_
- Update `scripts/little_loops/cli/artifact/__init__.py:12-14` — amend the "One module per subcommand" docstring sentence to record `extract.py`'s two-verb exception.
- Update `scripts/little_loops/cli/artifact/templatize.py:885` — normalize `source_path` to project-root-relative before `build_manifest` stores it.
- Update `scripts/little_loops/config-schema.json:1885-1889` — widen `templatize_max_input_bytes`'s `description` to cover `ll-artifact extract`.
- `docs/reference/CLI.md` — the new `#### ll-artifact extract` section must document `--model`/`--timeout` as `extract`-only flags (no other artifact subcommand exposes them), the `--model` > `extraction.model` > `DEFAULT_LLM_MODEL` precedence, that `extraction.host` is diagnostic-only, and the reused `templatize_max_input_bytes` ceiling. The `#### ll-artifact refresh` section must document the `--data`/`-o` split and the lockfile write.

## Impact

- **Priority**: P3 — unblocks the "single bound source over time" secondary
  use case from EPIC-3299; FEAT-3036 Phase 1 (`render`) is a hard
  prerequisite.
- **Effort**: Medium — raised slightly by the second review, which moved the
  `refresh` lockfile write here from FEAT-3311.
- **Risk**: Low — additive on the CLI surface. Three non-additive changes:
  (a) tightening `load_manifest` to validate `source`/`extraction` inner shape,
  which rejects a mapping-shaped `source` that previously loaded silently — no
  `templatize`-produced manifest is affected (it writes the scalar form), and
  none of the three `scripts/tests/fixtures/artifact_templates/*.llat`
  manifests declare `source` or `extraction` at all;
  (b) normalizing `templatize`'s stored `source` to project-root-relative,
  which changes the manifest bytes `templatize` writes when it is invoked from
  a subdirectory (`test_artifact_templatize.py` asserts on manifest contents —
  check those cases);
  (c) widening `templatize_max_input_bytes`'s documented scope.

## Acceptance Criteria

- [ ] `ll-artifact extract` invokes the host directly via
      `build_blocking_json(json_schema=manifest.data_schema)`, fails loud (no
      fail-soft prose-marker fallback), and writes a `data.json` that passes
      `artifact_templates.validate_top_level_data` before considering the
      command successful.
- [ ] `ll-artifact extract` builds its prompt from a module-level
      `_PROMPT_TEMPLATE` composing `extraction.prompt` + the serialized
      `data_schema` + the source text — `extraction.prompt` is never used as
      the entire prompt.
- [ ] `ll-artifact extract` carries `--model` and `--timeout` flags, and
      rejects a source file over `artifacts.templatize_max_input_bytes` with a
      typed error naming the measured size and the limit, before the host call
      is built. No new config knob is added; the existing key's schema
      `description` is widened to name `extract`.
- [ ] Model resolution is `--model` > `manifest.extraction.model` >
      `fsm.schema.DEFAULT_LLM_MODEL`, and `manifest.extraction.host` never
      overrides `resolve_host()`'s ambient host selection. Unit-tested at each
      precedence level.
- [ ] `extract` takes `--data <path>` (default `<template>/data.json`) for its
      output; `-o` is not registered on `extract`. `refresh` takes both
      `--data <path>` (same default) and `-o <dir>` (passed through to the
      render half with `render`'s semantics and
      `config.artifacts.default_output_dir` default).
- [ ] `load_manifest` validates the inner shape of `source` (non-empty string)
      and `extraction` (mapping, if present); a manifest whose `extraction`
      carries no `prompt` fails `extract` with a typed error naming the
      template and the missing key — never a synthesized default prompt.
- [ ] `ll-artifact refresh` composes `extract` + `render`, defaulting the
      source file to the manifest's scalar `source` (project-root-relative if
      not absolute) when no `<source-file>` is given — see § Pre-implementation
      decisions; **not** `source.path`. A `source` that does not resolve to an
      existing file fails loud with a typed error naming the resolved absolute
      path; there is no cwd-relative fallback.
- [ ] `templatize` normalizes the `source` it stores in `manifest.yaml` to a
      project-root-relative path (absolute stays absolute), so a `templatize`
      run from a subdirectory produces a manifest `refresh` can resolve. Tested
      with a `templatize` invocation from a subdirectory of the project root.
- [ ] `refresh` writes its extracted `data.json` to `<template>/data.json` by
      default and accepts a `--data <path>` override, so refreshing a committed
      template need not mutate the tracked file in place. The write target is
      stated in `--help` and in `docs/reference/CLI.md`.
- [ ] A new `cli/artifact/lockfile.py` holds the format's single definition —
      `LockfileError`, `load_lockfile` (fail-closed on unparseable YAML,
      non-mapping top level, missing/non-mapping `renders`, unknown
      `version`), `write_lockfile` (atomic, merging), `lock_path_for` — built
      to FEAT-3311 § Expected Behavior, which governs on any disagreement.
      FEAT-3311's `status`/`render --source` import it rather than redefining
      the shape.
- [ ] `refresh` writes/updates `<template>.llat.lock` after a successful render
      (moved here from FEAT-3311 so this issue is independently testable),
      recording `sha256` of the **same source bytes the extraction consumed**,
      `rendered_at` as ISO-8601 UTC, and `output` as the project-root-relative
      path of the rendered artifact *file* (`output_dir / manifest.output`, not
      the `-o` directory). The write is atomic (temp sibling + `os.replace`)
      and merges into any existing `renders` mapping rather than replacing it.
- [ ] A lockfile-write failure exits 1 with a message stating that the render
      succeeded and only the lock write failed — so the user does not re-pay
      for an LLM call to fix a filesystem problem. Tested against an
      unwritable template directory.
- [ ] Tests cover: successful extraction + validation, a host call that
      returns data violating `data_schema` (fails loud, no partial write),
      `refresh`'s default-source resolution against a scalar `source`, a
      manifest with `extraction` but no `prompt`, a manifest with a
      mapping-shaped `source` (rejected by `load_manifest` with a
      `ManifestError`, not an `AttributeError` via the backstop), and a
      `refresh` against a template whose lockfile already carries a *different*
      source's entry (asserting that entry survives the merge).
- [ ] `docs/reference/CLI.md` documents `extract` and `refresh`, including the
      `--data`/`-o` split, the `--model`/`--timeout` flags and their precedence
      rules, the size ceiling, and `refresh`'s lockfile write.
- [ ] `cli/artifact/__init__.py`'s "One module per subcommand" docstring
      sentence records `extract.py`'s deliberate two-verb exception.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-25T03:42:12 - `3906fc07-f9f6-4960-99f5-5a221177c28d.jsonl`
- `/ll:confidence-check` - 2026-08-25T03:27:46 - `ea0c7571-8966-43cb-ad8b-4e022c051b10.jsonl`
- `/ll:wire-issue` - 2026-08-25T03:17:17 - `5da7f41e-bb5f-4d4a-b24d-114a6e916228.jsonl`
- `/ll:refine-issue` - 2026-08-25T03:05:50 - `fc3e123a-ccfd-4c37-938a-9f50f57ebb48.jsonl`
