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
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3554: Templatize region-context tagging and context-dispatched escaping

## Summary

`ll-artifact templatize` regions are arbitrary byte spans, so a lifted value can sit in a text node, an ordinary attribute, a URL attribute, a `<script>` block or `on*=` handler, a `<style>` block, or a span that contains markup. Templatize records none of this. ENH-3558 (done) therefore made `refresh` escape every unannotated string leaf as HTML text: markup-spanning regions render as literal tags, and templatized URL regions get no `javascript:` protection. Record each region's context at templatize time and escape model-extracted values per context.

## Current Behavior

- `apply_regions` (`scripts/little_loops/cli/artifact/templatize.py:475`) splices each region's `[start, end)` span into `[[= expr =]]`, and each group's span via `_splice_group` (array items), with no check on what surrounds it. Regions come from a hand-written `--regions` map or from model discovery. It also escapes literal delimiters in the untouched bytes, so output offsets differ from input offsets.
- The emitted manifest carries no per-property context. `_validate_schema_shape()` (`scripts/little_loops/artifact_templates.py:102`) rejects any `data_schema` key outside `_SCHEMA_ALLOWED_KEYS` (`:35`). ENH-3558 added `x-ll-context` and `x-ll-trusted` to that set; `_CONTEXT_VALUES` (`:47`) accepts only `text` and `url`. Validation rejects `url` on non-string types, `x-ll-trusted` on non-string types, and `x-ll-trusted: true` combined with `url`.
- `escape_data(data, markup_keys, url_keys)` (`artifact_templates.py:355`) HTML-escapes every string leaf not in `markup_keys` and applies the URL scheme rule to `url_keys`. `schema_annotation_paths` (`:393`) returns the `(trusted_paths, url_paths)` 2-tuple that feeds it, and `extract_data` calls it at `extract.py:189`. `html.escape` is the wrong encoding in script and style contexts, and a markup-spanning region is escaped into visible tags.

## Expected Behavior

- Templatize classifies every region **and every group field** as one of `text`, `attr`, `url`, `script`, `script_string`, `style`, `markup`. It writes the classification per property (array-item properties included) into the manifest's `data_schema` as `x-ll-context`, extending `_CONTEXT_VALUES`. The script sub-position is persisted as its own context value (`script` vs `script_string`) because the two need incompatible encodings; a single `script` value would lose the information `escape_data` needs to pick one.
- Classification runs against the **original** artifact bytes, before `apply_regions` splices and shifts offsets. Region offsets are byte offsets but `html.parser` works on `str`, so decode UTF-8 and map byte offsets to character offsets. Non-ASCII fixtures are required.
- **A property bound by more than one region** (e.g. one value in a text node and in an `href`) takes the strictest context among them, by this order: `markup` > `style` > `script` / `script_string` > `url` > `attr` > `text`. Two contexts whose encodings are incompatible classify as `markup`, which fails closed unless trusted: `script` with `script_string`, either script context with any HTML context (`text`, `attr`, `url`), and `url` with either script context.
- `escape_data` dispatches on the recorded context:
  - `text` / `attr`: `_escape_text(v)` (`artifact_templates.py:322`), the existing ENH-3558 encoder. Do **not** use `html.escape(html.unescape(v))`: bare `html.unescape` decodes unterminated legacy references (`?x=1&copy=2` becomes `?x=1©=2`), which ENH-3558 fixed. `attr` requires a **quoted** attribute value; an unquoted value classifies as `markup`, since `html.escape` does not escape spaces, `=` or backticks.
  - `url`: the ENH-3558 scheme check (`_check_url`: allowlist `http`, `https`, `mailto`, relative, `#`, judged on the entity-decoded, control-stripped value), then `_escape_text`. URL attributes (navigation and passive media only): `<a href>`, `<area href>`, `<img src>`, `<audio src>`, `<video src>`, `<source src>`, `<track src>`, `<video poster>`, `cite`, `background`, `ping`. `srcset` (a comma-separated URL list) and `<meta http-equiv="refresh" content>` classify as `markup`. A region in a URL attribute classifies by its position in the value, because a fragment checked on its own is not safe: the scheme is a property of the **assembled** URL.
    - **`url`**: the region spans the **entire** attribute value (no literal text before or after it).
    - **`attr`**: the literal prefix before the region already fixes the scheme, so no value can change it. The prefix contains `<scheme>:` before any `/`, `?` or `#` (e.g. `href="https://x/[[= slug =]]"`), or it starts with `/`, `#`, `?` or `./`.
    - **`markup`**: every other position. This covers a region starting the value with literal text after it (`href="[[= v =]]script:alert(1)"` with `v="java"` passes a fragment-only check), and a region after a prefix that does not fix the scheme (`href="java[[= v =]]"` with `v="script:alert(1)"` passes the `attr` rule). Both compositions yield `javascript:alert(1)`.
  - **Resource-loading and navigation-hijacking attributes classify as `markup`**, not `url`: `<script src>`, `<iframe src>`, `<frame src>`, `<object data>`, `<embed src>`, `<link href>`, `<base href>`, `<form action>`, `formaction`. The scheme allowlist admits any `https:` value, which is enough to load attacker script (`script`/`iframe`/`object`/`embed`), attacker CSS (`link`), rebase every relative URL on the page (`base`), or send form submissions off-site (`action`/`formaction`). An unlisted attribute on an element not named above takes `attr`.
  - SVG `xlink:href` is not a URL attribute: SVG is foreign content and already classifies as `markup`.
  - Inside a `<script>` block:
    - **`script`** (code position, not inside a JS string): stamp `script_json(v)` (ENH-3557), a complete quoted JSON value.
    - **`script_string`** (inside a `"…"` or `'…'` string literal): the JSON string body without surrounding quotes, with **both** `"` and `'`, backslash, `<`, `>`, `&`, U+2028 and U+2029 escaped. Escaping both quote characters makes the encoding independent of which quote encloses the literal, so the quote character does not need to be persisted.
    - **inside a backtick template literal** or any position the tokenizer cannot resolve: `markup` (fail closed).
  - **`on*=` handler attributes classify as `markup`** in this issue. A handler value needs the JS encoding and then HTML-attribute escaping, which is a third encoding for each script sub-position. It is deferred to a follow-up; until then handler regions fail closed (raise unless trusted).
  - `style` (block or `style=` attribute) / `markup`: refuse (raise) unless the property is annotated `x-ll-trusted: true`.
- **Fail closed** on: HTML comments, RCDATA/raw-text elements other than `<script>`/`<style>` where the tokenizer is unsure, `<noscript>`/`<template>`, SVG/MathML foreign content, CDATA, `<iframe srcdoc>` (its value is a whole HTML document), `on*=` handler attributes, the resource-loading attributes listed under `url`, URL-attribute regions in a scheme-changing position (see `url`), and any tokenizer ambiguity. All classify as `markup`.
- **Validation matrix** in `_validate_schema_shape()`:
  - all seven contexts are permitted only on `type: string`;
  - `x-ll-trusted: true` is permitted only with `style` or `markup` (or no context);
  - `x-ll-trusted: true` combined with `url`, `script`, `script_string`, `text` or `attr` is a manifest error, extending the existing `url` rejection. Trust means "stamp verbatim", which would defeat those contexts' encodings.
- `x-ll-trusted` stays hand-set only: templatize never writes it, so classifying a region as `markup` can never grant trust.
- Manifests written before this change (no context annotation) default every property to `text`, which is the ENH-3558 behavior.

## Motivation

`refresh` is the path where a model writes values extracted from an untrusted source document into an HTML artifact that others open. ENH-3558 makes it safe for text regions and visibly broken for markup regions, and leaves URL/script regions only partly covered. Context tagging closes the remaining gap and makes markup regions usable again through an explicit trust annotation.

## Proposed Solution

1. **Classifier.** At templatize time, before `apply_regions`, run over each region and group-field span in the original artifact (stdlib `html.parser` driven over the decoded text, or a small tokenizer) and find the innermost context:
   - inside a quoted attribute value, and which attribute (resource-loading attributes → `markup`; the URL list above → `url` when the span is the whole value, `attr` when the literal prefix fixes the scheme, else `markup`; `on*` → `markup`; `style` → `style`; `srcdoc` → `markup`; else `attr`). Match on the (element, attribute) pair; `html.parser` lowercases both;
   - an unquoted attribute value → `markup`;
   - inside `<script>` raw text → `script` or `script_string`, from a minimal quote/comment scanner;
   - inside `<style>` raw text → `style`;
   - a text node → `text`;
   - a span crossing a tag boundary, or any fail-closed context above → `markup`.

   Then merge multiple bindings of one property by the strictest-context rule.
2. **Manifest.** Extend `_CONTEXT_VALUES` with `attr`, `script`, `script_string`, `style`, `markup`, and apply the validation matrix above. Templatize writes `x-ll-context` for each lifted property. No new schema key.
3. **Dispatch.** Replace the `(markup_keys, url_keys)` pair with a single path→context map:
   - add `contexts: Mapping[DataPath, RegionContext]` to `escape_data`, keeping `markup_keys` for trust;
   - add `schema_context_paths(schema) -> dict[DataPath, RegionContext]`;
   - reduce `schema_annotation_paths` to trusted paths only, or keep it as a thin wrapper;
   - update **both** production callers and the ENH-3558 tests: `extract.py:189` (`extract_data`) and `dashboard.py:368-369` (`build_dashboard_html`, which passes `url_keys=frozenset({"serve_events_url"})`; migrate it to `contexts={("serve_events_url",): "url"}` so the dashboard URL scheme rule keeps holding). The `script_string` encoder lives beside `script_json`; do not duplicate it. `text`, `attr` and `url` reuse `_escape_text` and `_check_url`.
4. **Host isolation.** Keep ENH-3558's rule (`strip_schema_annotations`): strip the annotations from a deep copy of `data_schema` before `_PROMPT_TEMPLATE` formatting and before `json_schema` is passed to `build_blocking_json` (`scripts/little_loops/cli/artifact/extract.py`, `extract_data`).
5. **Round trips.** `render_template` and `build_environment()` stay unchanged; `escape_data` never runs on the templatize round-trip path, so FEAT-3308 byte-exact round trips are unaffected.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — classify each region and group field against the original bytes, before `apply_regions` (`:475`); write the annotation into the schema that `build_manifest` (`:520`) receives.
- `scripts/little_loops/artifact_templates.py` — extend `_CONTEXT_VALUES` (`:47`) and the validation matrix in `_validate_schema_shape()` (`:102`); add context dispatch to `escape_data` (`:355`), reusing `_escape_text` (`:322`) and `_check_url` (`:333`); add `schema_context_paths` next to `schema_annotation_paths` (`:393`); add the `script_string` encoder next to `script_json` (`:438`).
- `scripts/little_loops/cli/artifact/extract.py` — `extract_data` (`:107`) reads contexts from the manifest, passes them at `:189`, and keeps stripping annotations (`strip_schema_annotations`, `:155`) before the prompt and host call.
- `scripts/little_loops/cli/artifact/dashboard.py` — `build_dashboard_html` (`:274`) calls `escape_data(..., url_keys=frozenset({"serve_events_url"}))` at `:368-369`; migrate to the `contexts` map when `url_keys` is folded in.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/render.py` (`render_to_disk`, used by `cmd_refresh`) — unchanged, but consumes the escaped data.
- `scripts/little_loops/fsm/persistence.py` — calls `render_template` as a render check; must keep working with annotated manifests.

### Similar Patterns
- ENH-3558's `escape_data` and URL scheme rule, and ENH-3557's `script_json` — reuse, do not duplicate.

### Tests
- `scripts/tests/test_artifact_templatize.py` — context classification per region and group field, including non-ASCII artifacts and multi-binding merges; round-trip tests stay green unchanged.
- `scripts/tests/test_feat3036_artifact_templates.py` — the new context values and the validation matrix; unknown keys still rejected.
- `scripts/tests/test_enh3558_escape_ingest.py` — ENH-3558's `escape_data` / `schema_annotation_paths` tests (`url_keys=` calls at `:74`, `:87`; 2-tuple unpack at `:129`) — update for the new signature.
- `scripts/tests/test_feat3310_artifact_extract.py` — per-context hostile refresh payloads (host call stubbed).

### Documentation
- `docs/reference/CLI.md` — `ll-artifact templatize` / `refresh` behavior per context and the trusted-property annotation.

### Configuration
- N/A

## Program Design

### Types
- `RegionContext` (new, `artifact_templates.py`): a `Literal["text", "attr", "url", "script", "script_string", "style", "markup"]` naming where a lifted value lands in the page.
- The script sub-position is not a separate type: the classifier maps code position to `script`, a `"`/`'` string literal to `script_string`, and backtick or unresolved positions to `markup`. Both script values are persisted in `x-ll-context`.

### Signatures
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` — unchanged splice; classification runs before it over the same spans (`templatize.py:475`).
- `build_manifest(name: str, output: str, schema: dict[str, Any], source: Path, extraction: dict[str, Any]) -> dict[str, Any]` — receives a schema already carrying the per-property annotations (`templatize.py:520`).
- `classify_region(artifact: bytes, start: int, end: int) -> RegionContext` (new, `templatize.py`) — pure; byte offsets over the original artifact; returns `markup` for anything ambiguous (fail closed).
- `escape_data(data: dict[str, Any], markup_keys: frozenset[str | DataPath] = frozenset(), contexts: Mapping[DataPath, RegionContext] | None = None) -> dict[str, Any]` — per-path context dispatch; `url_keys` is folded into `contexts` (`artifact_templates.py:355`).
- `schema_context_paths(schema: dict[str, Any]) -> dict[DataPath, RegionContext]` (new, `artifact_templates.py`) — reads `x-ll-context` at every depth, array items included.
- `extract_data(template: ArtifactTemplate, source_path: Path, config: Any, *, model: str | None, timeout: int) -> tuple[dict[str, Any], bytes]` — passes per-path contexts to `escape_data` and strips annotations before the prompt and host call (`extract.py:107`).

### Call Path
`cmd_templatize` -> `classify_region` (original bytes) -> `apply_regions` -> `build_manifest`
`cmd_refresh` -> `extract_data` -> `schema_context_paths` -> `escape_data` (context dispatch) -> `render_to_disk`

### Decision Rules
- Missing annotation on a property means `text` (legacy manifests keep ENH-3558 behavior).
- `style` and `markup` raise unless the property is annotated `x-ll-trusted: true`.
- A property bound in several places takes the strictest context; incompatible encodings (including `script` with `script_string`) merge to `markup`.
- In a URL attribute: `url` when the region is the whole value; `attr` when the literal prefix already fixes the scheme; `markup` otherwise.
- Resource-loading attributes (`script`/`iframe`/`frame` `src`, `object data`, `embed src`, `link href`, `base href`, `form action`, `formaction`), `srcdoc` and `on*` handlers classify as `markup`, never `url` or a script context.
- Unquoted attributes, comments, foreign content, backtick templates and any tokenizer ambiguity classify as `markup`.
- `text`, `attr` and `url` output goes through `_escape_text`; bare `html.unescape` is never used for output.
- `x-ll-trusted: true` is valid only with `style`, `markup`, or no context.

## Implementation Steps

1. Classifier: a pure function mapping (original artifact bytes, start, end) to one of the seven contexts, with unit tests per context, per fail-closed case, per URL position (whole value, scheme-fixing prefix, scheme-changing position), per script sub-position, and for non-ASCII offsets.
2. Manifest: extend `_CONTEXT_VALUES` and the validation matrix; have templatize write the context per lifted property (regions and group fields), merging multi-binding properties; legacy manifests read as `text`.
3. Dispatch: change `escape_data` to take a path→context map and pick the encoding per context, reusing `_escape_text` and `_check_url`; `style`/`markup` raise unless annotated trusted. Update the `extract.py:189` and `dashboard.py:368-369` callers and ENH-3558's tests.
4. Verify: per-context hostile `refresh` tests, annotation absent from host inputs, and `test_artifact_templatize.py` round trips unchanged.

## Impact

- **Priority**: P2 — only affects templatized templates refreshed from untrusted sources, and ENH-3558's default fails visible rather than open in the meantime.
- **Effort**: Medium-to-large — a context classifier with a JS string sub-scanner and byte/char offset mapping, a validation matrix, an `escape_data` signature change, a dispatch table, and per-context tests.
- **Risk**: Medium — misclassifying a region picks the wrong encoding; mitigated by failing closed on `style`/`markup` and on ambiguous classifications.
- **Breaking Change**: No — legacy manifests default to `text`.

## Scope Boundaries

- **In scope**: region-context classification in templatize, the manifest annotation and schema validation, context-dispatched `escape_data`, default-to-`text` for legacy manifests, tests per context.
- **Out of scope**: an encoder for `on*=` handler values (JS encoding plus HTML-attribute escaping, per script sub-position); handler regions fail closed as `markup` until a follow-up adds it. Changing `render_template`/`build_environment()` (`autoescape=False` stays); the dashboard and policy-builder sinks (ENH-3557, ENH-3558, ENH-3560); hand-written `data.json` given to `ll-artifact render` (documented trusted input); LLM-written HTML loops.

## Acceptance Criteria

- [ ] Templatize writes a context for every lifted property, group fields included. A fixture artifact with one region per context (text node, quoted attribute, whole `href` value, `<script>` code position, `<script>` string literal, `<style>` value, tag-spanning span) produces the expected seven classes (`text`, `attr`, `url`, `script`, `script_string`, `style`, `markup`).
- [ ] Fail-closed cases classify as `markup`: unquoted attribute, HTML comment, SVG foreign content (including `xlink:href`), backtick template literal, `srcset`, meta refresh, `<iframe srcdoc>`, an `onclick` handler value.
- [ ] A region spanning the whole value of `<script src>`, `<iframe src>`, `<object data>`, `<embed src>`, `<link href>`, `<base href>`, `<form action>` or `formaction` classifies as `markup`; the same region in `<a href>` or `<img src>` classifies as `url`.
- [ ] URL-attribute positions: a region after a scheme-fixing prefix (`href="https://x/[[= slug =]]"`, `href="/docs/[[= slug =]]"`) classifies as `attr`; a region that is the whole value classifies as `url`.
- [ ] Split-scheme compositions classify as `markup` and `refresh` raises on them unless trusted: `href="java[[= v =]]"` with `v="script:alert(1)"`, and `href="[[= v =]]script:alert(1)"` with `v="java"`.
- [ ] A property bound in a text node and an `href` gets `url`; one bound in a text node and a `<script>` gets `markup`; one bound in a `<script>` code position and a `<script>` string literal gets `markup`.
- [ ] Classification is correct for regions after multi-byte UTF-8 characters.
- [ ] `refresh` with hostile model output per context:
  - text/attr values are HTML-escaped by `_escape_text`, and ENH-3558's unterminated-reference tests stay green (`?x=1&copy=2` stays literal, not `?x=1©=2`);
  - `javascript:alert(1)` in a `url` property raises, and so do its evasion variants: mixed case (`JaVaScript:`), leading whitespace or control characters, a tab or newline inside the scheme (`java\tscript:`), and entity-encoded forms (`&#106;avascript:`, `&#x6A;avascript:`), which `_check_url` judges on the entity-decoded value;
  - a `</script>` in a `script` or `script_string` property does not close the block and decodes back to the input in JS; a `script_string` value containing `"` or `'` stays inside both a `"…"` and a `'…'` literal;
  - `style`/`markup` properties (including `onclick` handler values) raise unless annotated `x-ll-trusted: true`, and a trusted `markup` property stamps verbatim.
- [ ] `_validate_schema_shape()` rejects `x-ll-trusted: true` combined with `url`, `script`, `script_string`, `text` or `attr`, and any context on a non-string type.
- [ ] Templatize never writes `x-ll-trusted`.
- [ ] A manifest with no context annotations behaves exactly like ENH-3558 (all `text`).
- [ ] The annotation never appears in the prompt text or the `json_schema` passed to the host (host call stubbed).
- [ ] `test_artifact_templatize.py` round-trip tests pass unchanged.
- [ ] The dashboard caller (`dashboard.py`, `build_dashboard_html`) still rejects a disallowed scheme in `serve_events_url` after `url_keys` is folded into `contexts`.

## Related

- ENH-3558 (blocker, done; introduced `escape_data`, the `x-ll-context` / `x-ll-trusted` annotations, the URL rule, and the escape-as-text default this issue refines)
- ENH-3557 (done; `script_json`, reused for the `script` code-position context)
- ENH-3540 (cancelled; original spec, superseded by EPIC-3556)
- FEAT-3308 (byte-exact round-trip contract that must keep holding)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Verified 2026-09-24 against the working tree. All Current Behavior anchors hold: `templatize.py` `_splice_group:387`, `apply_regions:475`, `build_manifest:520`; `artifact_templates.py` `_SCHEMA_ALLOWED_KEYS:35`, `_CONTEXT_VALUES:47` (`{"text", "url"}`), `_validate_schema_shape:102` (rejections as described), `_escape_text:322`, `_check_url:333`, `escape_data:355`, `schema_annotation_paths:393`, `strip_schema_annotations:415`, `script_json:438`; `extract.py` `extract_data:107`, strip at `:155`, caller at `:187-189`. ENH-3558 and ENH-3557 are done; ENH-3540 is cancelled and superseded by EPIC-3556.

- **Fixed:** Proposed Solution step 3 said `escape_data` has "the one caller (`extract.py:189`)". A second production caller exists: `dashboard.py:368-369` (`build_dashboard_html`) passes `url_keys=frozenset({"serve_events_url"})`. Folding `url_keys` into `contexts` as proposed would have broken it. Added it to step 3, Implementation Step 3, Files to Modify, and a new Acceptance Criterion.
- **Fixed:** The Tests entry for ENH-3558's tests now names `scripts/tests/test_enh3558_escape_ingest.py` and the call sites the signature change affects.

Remaining: ENH-3558 has no `blocks:` frontmatter entry for ENH-3554 (its Related section does say "blocked on this issue"); left for a human to add, since this pass edits only this issue.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-24T23:38:37 - `ce8bec5b-7632-4ff9-a3da-7cdd35c70217.jsonl`
- `/ll:verify-issues` - 2026-09-24T22:56:15 - `4279401a-9acc-474c-b872-fd398cd78a8e.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:35:32 - `193eb57f-e9f6-4072-bd61-43000a1d97b1.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:09:53 - `b03f0e56-e701-4b6d-bb94-8f4cb425b852.jsonl`
- `/ll:capture-issue` - 2026-09-24T18:27:44 - `22a651e2-9185-4c57-93f1-1e1f8cfd0e15.jsonl`
