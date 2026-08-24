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
