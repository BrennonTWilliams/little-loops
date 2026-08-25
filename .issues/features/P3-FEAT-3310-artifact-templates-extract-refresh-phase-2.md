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

- `ll-artifact extract <template> <source-file> [-o data.json]` — an LLM step
  that maps *source-file* to `data.json` per the manifest's `data_schema` +
  `extraction.prompt`, using a direct `build_blocking_json(json_schema=...)`
  host call that fails loud (resolved in FEAT-3036 § Second-pass decisions ->
  *`extract`'s LLM invocation — resolved by FEAT-3308*: `advisor.py`'s shape,
  not `learning_tests/extractor.py`'s fail-soft prose-marker parse). Fails
  loudly if the output doesn't validate against `data_schema`.
- `ll-artifact refresh <template> [<source-file>]` — `extract` + `render` in
  one shot, against the manifest's bound `source:` by default.

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

- `scripts/little_loops/cli/artifact/extract.py` (new) — `cmd_extract`, `cmd_refresh`, `add_extract_parser`, `add_refresh_parser`, per the issue's own Program Design → Call Path. Both verbs live in one module (the issue names `extract.py`, not separate `extract.py`/`refresh.py` files), which is a narrower grouping than `render.py`/`templatize.py`'s one-verb-per-module convention — worth confirming at implementation time.
- `scripts/little_loops/cli/artifact/__init__.py:74-135` — `main_artifact()`'s subparser registration block (`add_render_parser(subparsers)` / `add_templatize_parser(subparsers)` at lines 119-120) and its flat `if args.command == "..."` dispatch chain (lines 127-135) both need new arms for `extract`/`refresh`. The module docstring (lines 1-15) enumerates every subcommand with its originating FEAT/ENH ID — needs an entry for FEAT-3310.
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
- `scripts/little_loops/config-schema.json:1875-1895` — `artifacts.templates_dir` (default `artifacts/templates`) and `artifacts.default_output_dir` (default `.loops/artifacts`), read via `BRConfig(Path.cwd())` in `cmd_render`/`cmd_templatize` — `extract`/`refresh` resolve the template root the same way.

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
also unchanged). `extract`'s host call follows `advisor.py`'s
`build_blocking_json(json_schema=...)` shape (resolved in FEAT-3036 §
Second-pass decisions), not `learning_tests/extractor.py`'s fail-soft
prose-marker parse.

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

_Wiring pass added by `/ll:wire-issue`:_
- `load_manifest` (`artifact_templates.py:142`) validates only that `extraction` is an allowed top-level manifest key — it does not validate the inner shape of `extraction.prompt`. `extract.py` will be the first consumer of `manifest.get("extraction", {}).get("prompt")`; whether `load_manifest` should gain inner-shape validation for this new key, or whether `extract.py` validates it locally, is an open implementation decision not resolved by existing code.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `docs/reference/CLI.md:4457` — add `extract`/`refresh` to the `### ll-artifact` top-level subcommand-enumeration prose.
- Update `scripts/little_loops/cli/artifact/__init__.py:51-70` — add `extract`/`refresh` examples and exit-code prose to the `main_artifact()` argparse epilog (separate from the subparser registration and dispatch-chain edits already in Files to Modify).
- Coordinate `docs/reference/CLI.md:4566` edit with FEAT-3311, which independently edits the same line.

## Impact

- **Priority**: P3 — unblocks the "single bound source over time" secondary
  use case from EPIC-3299; FEAT-3036 Phase 1 (`render`) is a hard
  prerequisite.
- **Effort**: Medium
- **Risk**: Low — pure addition, no changes to Phase 1's render path.

## Acceptance Criteria

- [ ] `ll-artifact extract` invokes the host directly via
      `build_blocking_json(json_schema=manifest.data_schema)`, fails loud (no
      fail-soft prose-marker fallback), and writes a `data.json` that passes
      `artifact_templates.validate_top_level_data` before considering the
      command successful.
- [ ] `ll-artifact refresh` composes `extract` + `render`, defaulting the
      source file to the manifest's `source.path` when no `<source-file>` is
      given.
- [ ] Tests cover: successful extraction + validation, a host call that
      returns data violating `data_schema` (fails loud, no partial write),
      and `refresh`'s default-source resolution.
- [ ] `docs/reference/CLI.md` documents `extract` and `refresh`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-25T03:17:17 - `5da7f41e-bb5f-4d4a-b24d-114a6e916228.jsonl`
- `/ll:refine-issue` - 2026-08-25T03:05:50 - `fc3e123a-ccfd-4c37-938a-9f50f57ebb48.jsonl`
