---
id: FEAT-3314
title: '`ll-artifact templatize` Phase A: deterministic templating (no LLM)'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: FEAT-3308
depends_on: []
relates_to:
- FEAT-3308
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
---

# FEAT-3314: `ll-artifact templatize` Phase A: deterministic templating (no LLM)

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md)
(the parent issue's own text: *"Phase A is independently shippable and contains
no LLM call — it is the whole fidelity mechanism, testable end-to-end from a
fixture... If this issue needs splitting for size, split on the A/B boundary."*).

Implements the deterministic half of `ll-artifact templatize`: given an
artifact plus a hand-written region map (`--regions <map.json>`), splice the
regions into Jinja2 expressions/blocks, emit a `manifest.yaml` + `data.json`,
and verify byte-exact round trip via a build-in-temp-then-promote flow. No LLM
call is on this path — Phase B ([FEAT-3315](P2-FEAT-3315-ll-artifact-templatize-phase-b-llm-region-discovery.md))
adds `discover_regions` on top of this.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Current Behavior

No code exists: `grep -rn templatize scripts/` returns nothing. The only way
to obtain a template today is to hand-author one out of a self-contained HTML
file.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review.llat --regions map.json
```

produces a template directory that (a) validates under `load_manifest()`,
(b) re-renders **byte-identically** against the extracted `data.json`, and
(c) can then be pointed at via `ll-artifact render` **by name** under
`templates_dir`.

**Output naming.** `-o` must resolve to a `<name>.llat` directory, because
`resolve_template()` (`artifact_templates.py:73`) only finds a template by
name at `templates_dir/<name>.llat`; a bare `arch-review` directory is
reachable by path only. If `-o` is given without the suffix, `templatize`
appends `.llat` and logs the resolved path. With no `-o`, the default is
`config.artifacts.templates_dir/<artifact-stem>.llat`.

## Use Case

A user has generated an artifact (e.g. a `docs/ARCHITECTURE.md` review page)
via an existing HTML loop and wants to re-run the same layout against a
different source document without re-invoking the loop or hand-writing a new
template. They already know which spans of the artifact came from the
source (they can point at the headings/body text) and hand-write a region
map (`map.json`) locating those spans. Running `ll-artifact templatize
<artifact> <source> -o <name>.llat --regions map.json` gives them a
`templates_dir`-resolvable template they can immediately `ll-artifact
render <name>` against new `data.json`, with a hard guarantee (byte-exact
round trip) that the extraction did not silently drop or corrupt anything
from the original.

## Proposed Solution

1. **Region types.** `Region: {start: int, end: int, expr: str, group: str |
   None, anchor_before: str, anchor_after: str}` — one located span; `start`/
   `end` are byte offsets into the original artifact and are the
   authoritative location, anchors are diagnostics only. `RegionGroup: {id:
   str, binding: str, array_path: str}` — a repeat group: the `for` binding
   name and the path in `data` to the array it iterates. `DiscoveryResult:
   {data_schema: dict, data: dict, regions: list[Region], groups:
   list[RegionGroup]}` is the shared contract Phase B will also produce.

2. **`apply_regions`.** A pure, LLM-free splice over sorted, non-overlapping
   spans: overlapping or out-of-bounds spans are a hard error, not a
   best-effort merge.

3. **`escape_literal_delimiters`.** Scan the non-region spans for any
   pre-existing `[[=`, `[[%`, `[[#` (plausible in inlined JS/CSS string
   content) and wrap them in `[[% raw %]]`/`[[% endraw %]]`. Missing this is
   a silent round-trip failure whose diff points nowhere near the real cause.

4. **`build_manifest`.** Emits `{name, version: 1, renderer: "jinja2",
   output, data_schema, source, extraction}`, `theme` omitted. Must validate
   against `_validate_schema_shape()` (`artifact_templates.py:85-140`) before
   writing.

5. **Fidelity constraints.** `autoescape=False` in the frozen environment
   means values are stamped verbatim — extracted values must be captured
   exactly as they appear in the artifact byte stream (e.g. `&amp;` stays
   `&amp;` in `data.json`, not decoded).

6. **Round trip + promote.** `verify_round_trip(template_dir, data,
   original)` renders via `render_template` (`artifact_templates.py:304-328`)
   and diffs against the original. **Any** non-empty diff is a hard failure.
   Failure is loud and non-destructive: `templatize` builds the candidate in
   a temp directory, runs the round trip there, and only then `os.replace`s
   it into the `-o` path. On failure it writes the candidate plus
   `roundtrip.diff` to `<out>.rejected/` and exits non-zero, leaving any
   pre-existing `-o` template untouched.

7. **CLI wiring.** `templatize` follows the `render` precedent
   (`cli/artifact/__init__.py:111`): `add_templatize_parser(subparsers)` in
   new `cli/artifact/templatize.py`, called after `add_render_parser`, a
   fourth arm in the dispatch if-chain (`:118-124`), plus additions to the
   epilog `Examples:`/`Exit codes:` block (`:49-62`) and `__all__`
   (`:29-35`). Entry point for this phase is `--regions <map.json>` — reading
   a hand-written region map instead of calling an LLM (Phase B replaces
   this with `discover_regions` when `--regions` is absent).

## Program Design

### Types

- `Region: {start: int, end: int, expr: str, group: str | None, anchor_before: str, anchor_after: str}`
- `RegionGroup: {id: str, binding: str, array_path: str}`
- `DiscoveryResult: {data_schema: dict, data: dict, regions: list[Region], groups: list[RegionGroup]}`
- `ArtifactTemplate` (`artifact_templates.py:47-64`) — existing; `cmd_templatize` must emit a `manifest` dict that `load_manifest()` accepts

### Signatures

- `cmd_templatize(args: argparse.Namespace, logger: Logger) -> int`
- `apply_regions(artifact_html: str, result: DiscoveryResult) -> str` — raises on overlap or out-of-bounds
- `escape_literal_delimiters(text: str) -> str`
- `build_manifest(name: str, output: str, schema: dict, source: Path, extraction: dict) -> dict`
- `verify_round_trip(template_dir: Path, data: dict, original: str) -> str | None` — renders via `render_template`, returns a unified diff or `None`. Runs against the temp build dir, before promotion.

### Call Path

`main_artifact` (`cli/artifact/__init__.py:38`) -> `cmd_templatize` (new,
`cli/artifact/templatize.py`) -> [read `--regions <map.json>`] -> `apply_regions`
(+ `escape_literal_delimiters`) -> `build_manifest` -> *write temp dir* ->
`verify_round_trip` -> `render_template` (`artifact_templates.py:304-328`) ->
`build_environment` (`:242-262`) -> *promote temp dir to `-o` via `os.replace`*

### Codebase Research Findings

- **`cmd_render`'s Jinja2 environment is the frozen contract to reuse, not
  re-derive**: `build_environment()` (`artifact_templates.py:242-262`)
  constructs a `jinja2.sandbox.SandboxedEnvironment` with the frozen
  delimiter set (`[[= =]]`/`[[% %]]`/`[[# #]]`), `trim_blocks=True`,
  `lstrip_blocks=True`, `keep_trailing_newline=True`,
  `undefined=StrictUndefined`, `autoescape=False`. `apply_regions`/
  `verify_round_trip` must import and call `build_environment()` unchanged
  rather than constructing a separate `Environment`.
- **Manifest and template-body constraints**: `load_manifest()`
  (`artifact_templates.py:142-189`) requires exactly
  `_MANIFEST_REQUIRED_KEYS = {"name", "version", "renderer", "output",
  "data_schema"}` with `renderer` literally `"jinja2"`; `data_schema` is
  validated by `_validate_schema_shape()` (`:85-140`); `find_template_body()`
  (`:265-275`) requires exactly one `template.*.j2` file at the template
  root.
- **No round-trip/rollback precedent exists.** `file_utils.py:16-32,35-57`
  provides `atomic_write`/`atomic_write_json` (single-file only); no
  directory-scoped transaction helper exists. The build-in-temp-then-promote
  flow is the directory-level generalization of `atomic_write`'s own
  pattern, and is new code.
- **Error-handling shape to match**: `cmd_policy_builder`
  (`cli/artifact/policy_builder.py:90`) and `cmd_design_md_export`
  (`cli/artifact/design_md.py:57`) share whole-body `try/except Exception as
  exc:  # noqa: BLE001` -> `logger.error(str(exc)); return 1`; success is
  `logger.success(...); return 0`. `cmd_templatize` follows this.
- **Config loading is per-handler.** `cmd_render` resolves `templates_dir =
  config.project_root / config.artifacts.templates_dir` at `render.py:38`.
  `cmd_templatize` does the same — `templates_dir` already exists
  (landed by FEAT-3036), not re-added.
- **`artifact_templates.py` must never import `host_runner` or `anthropic`**
  (module docstring) — irrelevant to this phase since no LLM call is made,
  but constrains where `apply_regions`/`verify_round_trip` may live.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` (new module) —
  `add_templatize_parser` subparser + `cmd_templatize` handler, registered
  from `cli/artifact/__init__.py:111` immediately after
  `add_render_parser(subparsers)`; also add to `__all__` (`:29-35`) and the
  epilog `Examples:`/`Exit codes:` block (`:49-62`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:52,110` — `main_artifact` re-export; unchanged
- `scripts/tests/test_enh3268_design_md_export.py:354,367,378,394,410` —
  imports `cmd_design_md_export`, `main_artifact` directly; the closest
  existing sibling-subcommand test to model `test_artifact_templatize.py`'s
  dispatch tests after

### Similar Patterns
- `cmd_policy_builder` (`cli/artifact/policy_builder.py:90`) — the existing
  stamp-and-write shape

### Tests
- New test module `scripts/tests/test_artifact_templatize.py` — round-trip
  fidelity against a checked-in fixture artifact + source pair. The fixture
  must deliberately contain: a repeated region (N=2 and N=5 variants), a
  literal `[[=`/`[[%` inside inlined JS or CSS, HTML entities (`&amp;`,
  `&#39;`) inside a templatized region — the silent-failure classes this
  phase's ACs gate on. Driven via `--regions <map.json>` with **no LLM in
  the test path**.
- Model dispatch tests on `TestArtifactCLIDispatch`
  (`test_policy_builder_emit.py:204-230`) — mock-handler dispatch (patch
  `sys.argv` + target `cmd_*`, assert `main_artifact()` routes correctly)
  and the missing-subcommand `SystemExit` test.
- No fixture pairing an emitted HTML artifact with its generating source
  document exists yet in `scripts/tests/fixtures/`; nearest transferable
  pattern is `_write_synthetic_profile`/`_reimport` in
  `test_enh3268_design_md_export.py:288-332,42-46`.

### Documentation
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — new subcommand
  section (Phase A surface: `--regions` flag)

## Acceptance Criteria

- [ ] `ll-artifact templatize <artifact> <source> -o <name>.llat --regions <map.json>` produces a directory that `load_manifest()` accepts and that `ll-artifact render <name>` resolves **by name** under `templates_dir` (not by path only).
- [ ] Round-trip: rendering the produced template with the produced `data.json` reproduces the original artifact byte-identically. Any non-empty diff exits non-zero, writes `<out>.rejected/` + `roundtrip.diff`, and leaves a pre-existing `-o` template untouched — asserted by a test that pre-populates `-o` and forces a failure.
- [ ] A repeated region in the source (N sections → N cards) is templatized as a Jinja2 loop over an array, not unrolled — asserted by a test with N=2 and N=5 data.
- [ ] An artifact containing a literal `[[=` / `[[%` / `[[#` in inlined JS or CSS still round-trips byte-exactly — asserted by a fixture that includes one.
- [ ] An artifact containing HTML entities (`&amp;`, `&#39;`) in a templatized region round-trips byte-exactly; the test asserts `data.json` stores the escaped form.
- [ ] `apply_regions` raises on overlapping or out-of-bounds spans rather than merging best-effort.

## Impact

- **Priority**: P2 — blocks Phase B and Phase C; the fidelity mechanism is
  the epic's core deliverable.
- **Effort**: Medium — deterministic code with no LLM in the loop, but the
  temp-build/promote transaction and region-splicing algorithm are novel to
  this codebase.
- **Risk**: Medium — round-trip fidelity is a hard, automatable gate, which
  bounds the risk of a lossy result shipping silently.
- **Breaking Change**: No — new subcommand.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub; read first
- `docs/reference/CLI.md` — `ll-artifact`

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-24T18:48:18 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
