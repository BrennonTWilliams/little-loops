---
id: ENH-3554
type: ENH
title: Templatize region-context tagging and context-dispatched escaping
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:27:36Z'
labels:
- security
- artifacts
blocked_by:
- ENH-3558
---

# ENH-3554: Templatize region-context tagging and context-dispatched escaping

## Summary

`ll-artifact templatize` regions are arbitrary byte spans, so a lifted value can sit in a text node, an ordinary attribute, a URL attribute, a `<script>` block or `on*=` handler, a `<style>` block, or a span that contains markup. Templatize records none of this. ENH-3540 therefore defaults `refresh` to escaping every unannotated string leaf as HTML text: markup-spanning regions render as literal tags, and templatized URL regions get no `javascript:` protection. Record each region's context at templatize time and escape model-extracted values per context.

## Current Behavior

- `apply_regions` (`scripts/little_loops/cli/artifact/templatize.py`, around `:480-510`) splices each region's `[start, end)` span into `[[= expr =]]` with no check on what surrounds it. Regions come from a hand-written `--regions` map or from model discovery.
- The emitted manifest carries no per-property context. `_validate_schema_shape()` (`scripts/little_loops/artifact_templates.py:88`) rejects any `data_schema` key outside `_SCHEMA_ALLOWED_KEYS` (`:33`).
- After ENH-3540, `escape_data` HTML-escapes every string leaf not on the markup allowlist. `html.escape` is the wrong encoding in URL, script, and style contexts, and a markup-spanning region is escaped into visible tags.

## Expected Behavior

- Templatize classifies every region as one of `text`, `attr`, `url`, `script`, `style`, `markup` and writes the classification per property into the manifest's `data_schema`.
- `escape_data` dispatches on the recorded context:
  - `text` / `attr`: `html.escape(html.unescape(v), quote=True)` (the ENH-3540 rule).
  - `url`: the ENH-3540 scheme allowlist (`http`, `https`, `mailto`, relative, `#`), then HTML-escape.
  - `script`: JS-string-literal encoding in the `script_json` style (no `<`, `>`, `&`, U+2028, U+2029; backslashes and quotes escaped).
  - `style` / `markup`: refuse (raise) unless the property is explicitly annotated trusted.
- Manifests written before this change (no context annotation) default every property to `text`, which is the ENH-3540 behavior.

## Motivation

`refresh` is the path where a model writes values extracted from an untrusted source document into an HTML artifact that others open. ENH-3540 makes it safe for text regions and visibly broken for markup regions, and leaves URL/script regions only partly covered. Context tagging closes the remaining gap and makes markup regions usable again through an explicit trust annotation.

## Proposed Solution

1. **Classifier.** At templatize time, for each region, parse the artifact bytes around `[start, end)` (stdlib `html.parser` or a small tokenizer) to find the innermost context: inside a tag's attribute value (and which attribute: `href`/`src`/`action`/`formaction`/`srcset` → `url`, `on*` → `script`, `style` → `style`, else `attr`), inside `<script>` / `<style>` raw text, a text node, or a span that crosses a tag boundary (`markup`).
2. **Manifest.** Add one annotation key to `_SCHEMA_ALLOWED_KEYS` (name to be decided; must not collide with JSON Schema keywords) and accept it in `_validate_schema_shape()`. Templatize writes it for each lifted property.
3. **Dispatch.** Extend ENH-3540's `escape_data` to read the per-path context and dispatch as above.
4. **Host isolation.** Keep ENH-3540's rule: strip the annotation from a deep copy of `data_schema` before `_PROMPT_TEMPLATE` formatting and before `json_schema` is passed to `build_blocking_json` (`scripts/little_loops/cli/artifact/extract.py`, `extract_data`).
5. **Round trips.** `render_template` and `build_environment()` stay unchanged; `escape_data` never runs on the templatize round-trip path, so FEAT-3308 byte-exact round trips are unaffected.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — classify each region's context in or next to `apply_regions`; write the annotation when building the manifest (`build_manifest`).
- `scripts/little_loops/artifact_templates.py` — add the annotation key to `_SCHEMA_ALLOWED_KEYS`, accept it in `_validate_schema_shape()`, and extend ENH-3540's `escape_data` with context dispatch.
- `scripts/little_loops/cli/artifact/extract.py` — `extract_data` reads contexts from the manifest and keeps stripping the annotation before the prompt and host call.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/render.py` (`render_to_disk`, used by `cmd_refresh`) — unchanged, but consumes the escaped data.
- `scripts/little_loops/fsm/persistence.py` — calls `render_template` as a render check; must keep working with annotated manifests.

### Similar Patterns
- ENH-3540's `escape_data`, `script_json`, and URL scheme rule — reuse, do not duplicate.

### Tests
- `scripts/tests/test_artifact_templatize.py` — context classification per region; round-trip tests stay green unchanged.
- `scripts/tests/test_feat3036_artifact_templates.py` — the new schema key is accepted, unknown keys still rejected.
- `scripts/tests/test_feat3310_artifact_extract.py` — per-context hostile refresh payloads (host call stubbed).

### Documentation
- `docs/reference/CLI.md` — `ll-artifact templatize` / `refresh` behavior per context and the trusted-property annotation.

### Configuration
- N/A

## Program Design

### Types
- `RegionContext` (new, `artifact_templates.py`): a `Literal["text", "attr", "url", "script", "style", "markup"]` naming where a lifted value lands in the page.

### Signatures
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` (existing, `templatize.py:474`) — unchanged splice; classification runs alongside it over the same spans.
- `build_manifest(name: str, output: str, schema: dict[str, Any], source: Path, extraction: dict[str, Any]) -> dict[str, Any]` (existing, `templatize.py:519`) — writes the per-property context annotation into `data_schema`.
- `classify_region(artifact: bytes, start: int, end: int) -> RegionContext` (new, `templatize.py`) — pure; returns `markup` for anything ambiguous (fail closed).
- `extract_data(template: ArtifactTemplate, source_path: Path, config: Any, *, model: str | None, timeout: int) -> tuple[dict[str, Any], bytes]` (existing, `extract.py:102`) — passes per-path contexts to `escape_data` and strips the annotation before the prompt and host call.

### Call Path
`cmd_templatize` -> `apply_regions` / `classify_region` -> `build_manifest`
`cmd_refresh` -> `extract_data` -> `escape_data` (context dispatch) -> `render_to_disk`

### Decision Rules
- Missing annotation on a property means `text` (legacy manifests keep ENH-3540 behavior).
- `style` and `markup` raise unless the property is annotated trusted.

## Implementation Steps

1. Classifier: a pure function mapping (artifact bytes, start, end) to one of the six contexts, with unit tests per context and a fail-closed result (`markup`) for anything ambiguous.
2. Manifest: add the annotation key to the schema allowlist and have templatize write it per lifted property; legacy manifests read as `text`.
3. Dispatch: extend `escape_data` to pick the encoding per context; `style`/`markup` raise unless annotated trusted.
4. Verify: per-context hostile `refresh` tests, annotation absent from host inputs, and `test_artifact_templatize.py` round trips unchanged.

## Impact

- **Priority**: P2 — only affects templatized templates refreshed from untrusted sources, and ENH-3540's default fails visible rather than open in the meantime.
- **Effort**: Medium — a context classifier, one manifest key, a dispatch table, and per-context tests.
- **Risk**: Medium — misclassifying a region picks the wrong encoding; mitigated by failing closed on `style`/`markup` and on ambiguous classifications.
- **Breaking Change**: No — legacy manifests default to `text`.

## Scope Boundaries

- **In scope**: region-context classification in templatize, the manifest annotation and schema validation, context-dispatched `escape_data`, default-to-`text` for legacy manifests, tests per context.
- **Out of scope**: changing `render_template`/`build_environment()` (`autoescape=False` stays); the dashboard and policy-builder sinks (ENH-3540); hand-written `data.json` given to `ll-artifact render` (documented trusted input); LLM-written HTML loops.

## Acceptance Criteria

- [ ] Templatize writes a context for every lifted property; a fixture artifact with one region per context (text, attr, `href`, `onclick`, `<script>` string, `<style>` value, tag-spanning span) produces the expected six classes.
- [ ] `refresh` with hostile model output per context: text/attr values are HTML-escaped; `javascript:alert(1)` in a `url` property raises; a `</script>` in a `script` property does not close the block and decodes back to the input in JS; `style`/`markup` properties raise unless annotated trusted, and a trusted `markup` property stamps verbatim.
- [ ] A manifest with no context annotations behaves exactly like ENH-3540 (all `text`).
- [ ] The annotation never appears in the prompt text or the `json_schema` passed to the host (host call stubbed).
- [ ] `test_artifact_templatize.py` round-trip tests pass unchanged.

## Related

- ENH-3540 (parent work; introduces `escape_data`, `script_json`, the URL rule, and the escape-as-text default this issue refines)
- FEAT-3308 (byte-exact round-trip contract that must keep holding)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-24T18:27:44 - `22a651e2-9185-4c57-93f1-1e1f8cfd0e15.jsonl`
