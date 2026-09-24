---
id: ENH-3558
type: ENH
title: Escape-by-default ingest for template data and extract output
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
labels:
- security
- artifacts
blocked_by:
- ENH-3557
learning_tests_required:
- jinja2-byte-exact-round-trip
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3558: Escape-by-default ingest for template data and extract output

## Summary

Add an idempotent `escape_data` helper with a path-based markup allowlist and a URL scheme rule. Apply it where untrusted strings enter a data dict: `build_dashboard_html` and `extract_data`. Add two manifest schema annotations (`x-ll-context`, `x-ll-trusted`) so templates can declare URL and verbatim properties, strip them from the schema sent to the host, and make the extract prompt ask for decoded plain text. `render_template` stays byte-identical.

Carved out of cancelled ENH-3540 (Scope §2, §3, Option A decision); see that file for the full research trail.

## Current Behavior

- **The frozen template env has `autoescape=False`** (`scripts/little_loops/artifact_templates.py`, `build_environment`). Every data key is stamped raw unless the caller hand-escapes it. `build_dashboard_html` (`cli/artifact/dashboard.py:307-336`) does so per key with `html.escape`; a new key added without it is an XSS sink. The env is frozen for FEAT-3308 byte-exact round trips, so the fix cannot live in the env.
- **`extract`/`refresh` is the most direct prompt-injection to stored-XSS route.** `extract_data()` (`cli/artifact/extract.py:102`) sends an arbitrary source document to a model via `resolve_host()` / `run_blocking_json`, interpolating the source text verbatim into `_PROMPT_TEMPLATE` (`:51-58`). The model's JSON is written to `data.json` (`cmd_extract` `:227`, `cmd_refresh` `:289`), and `cmd_refresh` renders it through `render_template` under the `autoescape=False` env. Nothing escapes the model-chosen strings, so a hostile source document controls both the prompt and the raw HTML output.
- **`render_template` itself cannot escape.** FEAT-3308 defines `data.json` values as the artifact byte form; `verify_round_trip()` (`templatize.py`) requires `render_template(template, data) == original bytes`. Escaping inside `render_template` would double-escape templatize-produced data and fail every round trip in `test_artifact_templatize.py`.
- **Entity-encoded model output would be double-escaped.** `_PROMPT_TEMPLATE` says nothing about encoding. For an HTML source, the model can copy `&amp;` verbatim; a plain `html.escape` then yields `&amp;amp;`.
- **`html.escape` does not neutralize `javascript:` URLs.** `javascript:alert(1)` contains no character `html.escape` changes.
- **`html.unescape` is not a safe idempotence primitive.** It applies HTML5 legacy-entity rules, decoding some named references without a trailing `;`. Verified: `https://x/?a=1&not=2` → `https://x/?a=1¬=2`, `a&copy=1` → `a©=1`, `&notes` → `¬es`. A naive `html.escape(html.unescape(v))` corrupts query strings and ordinary text.
- **Extract output may carry undeclared keys.** `validate_data` (`artifact_templates.py:209`) validates only keys present in `properties` and ignores the rest, so the model can return extra keys, at any depth, with arbitrary names.
- **Templatize can lift markup fragments.** Regions are arbitrary byte spans (`apply_regions`, `templatize.py:474-510`); nothing restricts a region to a text node, and the manifest records no per-region context. So escaping every string leaf on `refresh` renders markup inside a markup-spanning region as literal text (safe but visibly broken).
- **The manifest has no annotation slot.** `_validate_schema_shape()` rejects any `data_schema` key outside `_SCHEMA_ALLOWED_KEYS = {type, required, properties, items, enum, description}` (`artifact_templates.py:33`).
- **The schema reaches the host twice.** `extract_data()` passes `template.data_schema` into the prompt (`extract.py:150-152`) and as `json_schema` to `build_blocking_json` (`:163`). Codex materializes that schema, so an unknown keyword risks rejection.

## Expected Behavior

- Template data strings from code-built dicts and from `extract` model output are HTML-escaped by default, idempotently, unless their property path is on the markup allowlist.
- Declared URL properties reject non-allowlisted schemes (`javascript:`, `data:`, `vbscript:`, including whitespace/case/control-character variants).
- Templates declare URL and verbatim properties through two manifest annotations; neither annotation reaches the host.
- `_PROMPT_TEMPLATE` asks the model for decoded plain text.
- On `refresh`, a region whose value contains markup renders as escaped text (fail visible, never fail open) until ENH-3554 adds region-context tagging.
- `render_template` bytes for existing templates are unchanged; FEAT-3308 round trips pass unchanged.

## Motivation

`refresh` is where a model writes values extracted from an untrusted document into an HTML artifact others open. The dashboard is safe today only because each key was hand-escaped; the comment at `dashboard.py:306-308` calls escaping "the rule that has to survive the next flag someone adds". This issue turns that into an enforced default.

## Proposed Solution

**Option A (decided in ENH-3540): escape at ingest.** `escape_data` walks a data dict and escapes every string leaf whose path is not allowlisted. Code-built dicts call it directly; `extract_data()` calls it on the model's validated JSON before returning, with the allowlist derived from the manifest annotations. `data.json` then always holds artifact byte form, the contract FEAT-3308 already defines. `ll-artifact render` of a hand-written `data.json` stays verbatim and is documented as trusted input. Option B (escape at render as a manifest opt-in) was rejected: it leaves templatize-produced templates raw on `refresh` and contradicts the byte-form contract.

1. **`escape_data`** in `artifact_templates.py` (see Program Design). Returns a new dict; never mutates the input. Non-string leaves (int, float, bool, None) pass through. It walks the **data**, not the schema, so undeclared keys the model adds are escaped like declared ones. String mapping keys at non-trusted paths are escaped by the same rule (a template iterating `.items()` would otherwise stamp model-chosen keys raw); path matching always uses the original, unescaped key. Schema-declared keys are identifiers in practice, so this is a no-op for them.
2. **Manifest annotations.** Add two keys to `_SCHEMA_ALLOWED_KEYS` and validate them in `_validate_schema_shape()`:
   - `x-ll-context`: where the value lands. This issue accepts `text` (the default when absent) and `url`. Any other value is rejected at manifest load. `url` is only permitted on a `type: string` node. ENH-3554 extends the enum with `attr`, `script`, `style`, `markup` and has templatize write it automatically.
   - `x-ll-trusted`: boolean, author opt-in to verbatim stamping (the markup allowlist). Only a template author sets it by hand; templatize never writes it. Permitted only on a `type: string` node (trust never covers a subtree; an author trusts each leaf explicitly). Non-boolean values (e.g. the string `"true"`) are rejected.
   - `x-ll-trusted: true` combined with `x-ll-context: url` on the same node is rejected at manifest load: a verbatim URL bypasses the scheme rule, and there is no legitimate need for both.
   - Why two keys, not one: under ENH-3554, templatize auto-classifies tag-spanning regions as `x-ll-context: markup`. If one key meant both "where it lands" and "stamp verbatim", every auto-classified markup region would be auto-trusted. Keeping trust as a separate, hand-set key means a classifier can never grant trust.
   - The `x-` prefix cannot collide with JSON Schema keywords. The data validator (`validate_top_level_data` and the extract validator) must ignore both keys.
3. **Path derivation.** `schema_annotation_paths(schema)` walks `data_schema` and returns `(trusted_paths, url_paths)`. A path is a tuple of segments — property names, with the `ARRAY_ITEM` sentinel for array items (e.g. `("items", ARRAY_ITEM, "body")`). **Not dotted strings**: since undeclared keys pass validation, a model could return a top-level key literally named `"items[].body"` and, under string paths, inherit the trust of the nested path. Tuple paths make that collision impossible. Template authors never write paths; they put the annotation on the property's schema node. Flat code-built dicts (the dashboard) pass plain top-level key names; `escape_data` treats a `str` entry as the one-segment path `(name,)`.
4. **Dashboard.** Replace the five per-key `html.escape` calls (`dashboard.py:315,316,319,321,336`) with one `escape_data(data, markup_keys=DASHBOARD_MARKUP_KEYS, url_keys=frozenset({"serve_events_url"}))` call after the dict is built and after `validate_top_level_data` (the same validate-then-escape order as extract). `DASHBOARD_MARKUP_KEYS` is documented next to its definition: `snapshot_gzip_b64`, `sql_wasm_b64` (base64), `sql_wasm_js`, `serve_htmax_js` (vendored JS, `</script>`-checked at vendoring time), `serve_interaction_url_js`, `serve_history_url_js` (already `script_json`-encoded by ENH-3557).
5. **Extract.** In `extract_data()`:
   - Deep-copy `data_schema` and strip both annotations recursively before formatting `_PROMPT_TEMPLATE` and before passing `json_schema` to `build_blocking_json`.
   - Validate the model output against the schema **first**, then call `escape_data`. (Escaping first would break `enum` matches for values containing `&`, `<`, `>`, or quotes.)
   - Catch the URL-rule `ValueError` from `escape_data` and re-raise it as `ExtractError` naming the offending path, so `cmd_extract`/`cmd_refresh` report it like any other extraction failure and write no `data.json`.
   - Extend `_PROMPT_TEMPLATE` to require plain decoded text: no HTML entities, no markup.
6. **Docs.** An allowlist docs block in `artifact_templates.py` covering: which dashboard keys are verbatim and why; the two annotations; that markup-spanning templatized regions render as escaped text and templatized URL regions are uncovered until ENH-3554; that `ll-artifact render` input is trusted; that LLM-written HTML loops (`vega-viz`, `rlhf-svg-generate`, `html-anything`) sit outside any Python render boundary; the same holds for `artifact_mode: template` promotion (FEAT-3318, `fsm/persistence.py:947-950`), where the loop's LLM writes both the template body and `data.json`, so escaping the data adds nothing and a later `ll-artifact render` of that `data.json` is trusted input. The same escape-as-text caveat goes in the `refresh` subcommand's help text and in `docs/reference/CLI.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/artifact_templates.py` — `escape_data`, `schema_annotation_paths`, `strip_schema_annotations`; the two keys in `_SCHEMA_ALLOWED_KEYS` and `_validate_schema_shape()`; allowlist docs.
- `scripts/little_loops/cli/artifact/dashboard.py` — `build_dashboard_html`: `DASHBOARD_MARKUP_KEYS` and one `escape_data` call replacing the per-key `html.escape`.
- `scripts/little_loops/cli/artifact/extract.py` — `extract_data`: annotation stripping, validate-then-escape, `_PROMPT_TEMPLATE` change.
- `scripts/little_loops/cli/artifact/` argparse wiring for `refresh` — help-text caveat.
- `docs/reference/CLI.md` — `ll-artifact extract` / `refresh` / `render` behavior (entity-encoded `data.json`, escape-as-text regions, `render` input trusted).

### Dependent Files (Callers/Importers)
- `render_template` callers stay unchanged: `cli/artifact/render.py` (`render_to_disk`, used by `cmd_render` and `cmd_refresh`), `dashboard.py` (`build_dashboard_html`), `templatize.py` (`_render_tmp_dir`, the round-trip oracle; `escape_data` must never run here), `fsm/persistence.py` (render check only).
- `cli/artifact/serve.py` re-serves `build_dashboard_html()` output; inherits the fix.
- ENH-3554 (blocked on this issue) extends `x-ll-context` and `escape_data` with context dispatch.

### Similar Patterns
- The per-key `html.escape` calls at `dashboard.py:314-320` are the direct precedent `escape_data` generalizes.
- The only `autoescape=True` env is the SSE partials env in `render_live_fragment()` (`dashboard.py:374-377`); pin it, don't change it.

### Tests
- `scripts/tests/test_feat3036_artifact_templates.py` — `escape_data` unit tests (idempotence, path allowlist, URL rule); annotation keys accepted and unknown `x-ll-context` values rejected by manifest validation.
- `scripts/tests/test_feat3310_artifact_extract.py` — hostile model output with the host call stubbed; annotations absent from prompt and `json_schema`; nested payload escaping; `refresh` escapes a markup value.
- `scripts/tests/test_feat3304_artifact_dashboard.py` — hostile-payload tests for dashboard shareable and `--local` and for `render_live_fragment` (uses `_build_history_db()` and decodes the base64 blob).
- `scripts/tests/test_artifact_templatize.py` — must pass unchanged (`test_end_to_end_round_trip`, `test_non_ascii_round_trips`, `test_repeat_group_n5_round_trips`, and the rest).

### Documentation
- Allowlist docs in `artifact_templates.py`; `docs/reference/CLI.md`; `refresh` help text.
- CHANGELOG (release prep): `extract`/`refresh` `data.json` now holds entity-encoded text; markup-spanning regions render as escaped text on `refresh`.

### Configuration
- N/A

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `dashboard.py` per-key `html.escape` calls | Escape `filter_tables`, `filter_since`, `source_schema_version`, `schema_version_warning`, `serve_events_url` | PRESERVED (broadened) | `escape_data` now also escapes every other string key not in `DASHBOARD_MARKUP_KEYS`. Output differs from today only for values that contain `&`, `<`, `>`, quotes, or entity text. Existing dashboard tests must pass unchanged. |
| `dashboard.py` literal `"all history"` fallback for `filter_since` | Stamped unescaped | PRESERVED | Escaping a plain ASCII constant is a no-op. |
| `extract.py` `data.json` | Stores raw model output | CHANGED | Stores escaped byte form (the FEAT-3308 contract). Noted as a breaking change. |
| `render_template` | Stamps data verbatim under `autoescape=False` | PRESERVED | Not modified. |

## Program Design

### Types
- `DASHBOARD_MARKUP_KEYS: frozenset[str]` — new, in `dashboard.py`. The six verbatim dashboard keys listed in Proposed Solution §4.
- `DataPath = tuple[str, ...]` — new type alias, in `artifact_templates.py`. A data path as a tuple of segments.
- `ARRAY_ITEM: str` — new sentinel segment, in `artifact_templates.py`, standing for "any array index". Chosen so it cannot be produced by a JSON object key lookup at the same position (array positions never yield key segments).

### Signatures
- `escape_data(data: dict[str, Any], markup_keys: frozenset[str | DataPath], url_keys: frozenset[str | DataPath] = frozenset()) -> dict[str, Any]` — new, in `artifact_templates.py`. A `str` entry means the one-segment path `(name,)`. Escapes each `str` leaf, and each string mapping key, whose path is not in `markup_keys` by the escape rule below. Leaves whose path is in `url_keys` are checked against the URL rule first and raise `ValueError` naming the path on a disallowed scheme. Array indices collapse to `ARRAY_ITEM`.
- `schema_annotation_paths(schema: dict[str, Any]) -> tuple[frozenset[DataPath], frozenset[DataPath]]` — new, in `artifact_templates.py`. Returns `(trusted_paths, url_paths)` from `x-ll-trusted` / `x-ll-context: url`.
- `strip_schema_annotations(schema: dict[str, Any]) -> dict[str, Any]` — new, in `artifact_templates.py`. Returns a deep copy with every `x-ll-*` key removed at every depth.
- `extract_data(template: ArtifactTemplate, source_path: Path, config: Any, *, model: str | None, timeout: int) -> tuple[dict[str, Any], bytes]` — existing, in `extract.py`. Sends the stripped schema to the host; validates, then escapes, the model output.
- `render_template(template: ArtifactTemplate, data: dict[str, Any], config: object) -> str` — existing, in `artifact_templates.py`. Unchanged.

### Call Path
`cmd_dashboard` -> `build_dashboard_html` -> `escape_data` -> `render_template` (unchanged)
`cmd_refresh` -> `extract_data` -> `strip_schema_annotations` / `escape_data` -> `render_to_disk` -> `render_template` (unchanged)
`cmd_templatize` -> `verify_round_trip` -> `render_template` (unchanged; no `escape_data`)

### Decision Rules
- Escape rule: a `str` leaf becomes `html.escape(_decode_terminated_refs(value), quote=True)` unless its path is allowlisted. `_decode_terminated_refs` decodes **only `;`-terminated** character references — `&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);`, each match passed through `html.unescape` — and leaves every other `&` alone. **Never** apply bare `html.unescape` to the whole value here: its HTML5 legacy rules decode `&not`, `&copy`, `&amp`, `&lt` without a `;` (`a=1&not=2` → `a=1¬=2`). Idempotent means stable under re-escaping, not byte-preserving: a bare `"` becomes `&quot;` and `'` becomes `&#x27;`.
- Allowlist sources: code-built dicts pass `markup_keys` explicitly; `extract_data` derives it from `x-ll-trusted: true`.
- URL rule: for a path in `url_keys`, in this order: (1) decode with full `html.unescape` (the permissive decoder is correct here: decoding more only makes the check stricter, and it catches `javascript&#58;`, `javascript&colon;`, `java&#9;script:`); (2) remove all ASCII whitespace and control characters (U+0000–U+0020, U+007F) anywhere in the result; (3) lowercase; (4) take the scheme (text before the first `:` that precedes any `/`, `?`, or `#`). Allowed: `http`, `https`, `mailto`, no scheme (relative), or a value starting with `#`. Anything else raises. The decoded form is used only for the check; the stored value is the original escaped by the escape rule above.
- Annotation rule: `x-ll-context` and `x-ll-trusted` are stripped from a deep copy of `data_schema` before it is formatted into `_PROMPT_TEMPLATE` or passed as `json_schema`.
- Order rule: validate against the schema, then escape — in both `extract_data` and `build_dashboard_html`.
- Error rule: in `extract_data`, a URL-rule `ValueError` becomes `ExtractError`; no `data.json` is written. In `build_dashboard_html`, it propagates as `ValueError` (callers already map it).
- Annotation placement rule: `x-ll-context: url` and `x-ll-trusted` are valid only on `type: string` nodes; `x-ll-trusted` must be a bool; `x-ll-trusted: true` + `x-ll-context: url` on one node is rejected.
- Never run `escape_data` on the templatize round-trip path.

## Implementation Steps

1. Re-run `/ll:explore-api jinja2-byte-exact-round-trip` (stale since 2026-08-24) to confirm the round-trip baseline before touching the data layer.
2. Add `escape_data`, `schema_annotation_paths`, `strip_schema_annotations`, and the two schema keys, with unit tests.
3. Switch `build_dashboard_html` to `escape_data` with `DASHBOARD_MARKUP_KEYS` and `serve_events_url` as a URL key.
4. Wire `extract_data`: stripped schema to prompt and host, validate-then-escape, prompt change.
5. Add the allowlist docs, `refresh` help text, and `docs/reference/CLI.md` updates.
6. Hostile-payload tests (below). Then run `test_feat3036_artifact_templates.py`, `test_feat3304_artifact_dashboard.py`, `test_feat3310_artifact_extract.py`, `test_artifact_templatize.py`, plus `mypy` and `ruff check`.

## Impact

- **Priority**: P1 — `refresh` turns a hostile source document into stored XSS against whoever opens the artifact.
- **Effort**: Medium — three helpers, two schema keys, two call sites, prompt change, docs, four test files.
- **Risk**: Medium — a wrong boundary breaks FEAT-3308 round trips; mitigated by never touching `render_template` and running `test_artifact_templatize.py` unchanged.
- **Breaking Change**: Minor, behavioral. `extract`/`refresh` `data.json` holds entity-encoded text (already the FEAT-3308 byte-form contract, but direct readers of `data.json` see `&amp;`). Markup-spanning regions on `refresh` render as escaped text.

## Scope Boundaries

- **In scope**: `escape_data` with path allowlist and URL rule; `x-ll-context` (`text`, `url`) and `x-ll-trusted`; annotation stripping; validate-then-escape in `extract_data`; `_PROMPT_TEMPLATE` change; dashboard switch to `escape_data`; allowlist docs; hostile-payload tests for dashboard (shareable and `--local`), SSE fragments, and `extract`/`refresh`.
- **Out of scope**: `script_json` and policy-builder splices (ENH-3557); write paths (ENH-3559); builder DOM sinks (ENH-3560); region-context classification and the other `x-ll-context` values (ENH-3554); changing `render_template` / `build_environment()`; hand-written `data.json` given to `ll-artifact render` (documented trusted); LLM-written HTML loops (documented only).

## Acceptance Criteria

- [ ] Dashboard data values are escaped by `escape_data` unless in `DASHBOARD_MARKUP_KEYS`; the per-key `html.escape` calls are gone; existing dashboard tests pass.
- [ ] Ingest escaping is idempotent: model values `Tom &amp; Jerry` and `Tom & Jerry` both land in `data.json` as `Tom &amp; Jerry`. `_PROMPT_TEMPLATE` asks for decoded plain text.
- [ ] Unterminated references are not decoded: `a=1&not=2` → `a=1&amp;not=2`, `a&copy=1` → `a&amp;copy=1`, `&notes` → `&amp;notes` (no `¬` or `©` in the output).
- [ ] `escape_data` matches allowlist entries by tuple path: a nested extract payload (group → array of objects) escapes non-allowlisted nested leaves and leaves an `x-ll-trusted` nested path verbatim.
- [ ] An undeclared key in model output is escaped, and an undeclared top-level key literally named `"items[].body"` (or any string spelling of a trusted nested path) does **not** inherit that path's trust.
- [ ] A string mapping key containing markup (e.g. `{"<b>k</b>": "v"}` at a non-trusted path) is escaped in the output.
- [ ] For declared URL keys, `escape_data` raises on `javascript:alert(1)`, ` JavaScript:alert(1)`, `java\tscript:alert(1)`, `java&#9;script:alert(1)`, `javascript&#58;alert(1)`, `javascript&colon;alert(1)`, `data:text/html,x`, and `vbscript:x`, and accepts `https://x`, `https://x/?a=1&not=2` (stored as `https://x/?a=1&amp;not=2`), `mailto:a@b`, `/rel/path`, and `#frag`. The dashboard's `serve_events_url` passes.
- [ ] A disallowed URL in extract output makes `extract`/`refresh` exit 1 with an `ExtractError` naming the path, and leaves `data.json` unwritten.
- [ ] Manifest validation accepts `x-ll-context: text|url` and `x-ll-trusted: true|false`, and rejects: any other `x-ll-context` value; `x-ll-context: url` or `x-ll-trusted` on a non-`string` node; a non-boolean `x-ll-trusted`; and `x-ll-trusted: true` combined with `x-ll-context: url`.
- [ ] Neither annotation appears in the prompt text or the `json_schema` passed to `build_blocking_json` (host call stubbed).
- [ ] An `enum` value containing `&` still validates (validation runs before escaping).
- [ ] `refresh` on a template whose value contains markup emits the markup as escaped text, not live tags.
- [ ] Hostile-payload tests cover dashboard shareable and `--local` (payloads in `loop_name`, `state`, `branch`, `model`, and transcript text; no unescaped payload outside the base64 blob), `render_live_fragment`, and `extract`/`refresh` (host stubbed), in the default `python -m pytest scripts/tests/` tier.
- [ ] `test_artifact_templatize.py` round-trip tests pass unchanged.
- [ ] The allowlist docs in `artifact_templates.py`, the `refresh` help text, and `docs/reference/CLI.md` state the escape-as-text default, that templatized URL regions are uncovered until ENH-3554, and that `render` input is trusted.

## Related

- EPIC-3556 (parent); ENH-3540 (cancelled, original spec and Option A decision)
- ENH-3557 (blocker: `script_json` for the allowlisted `_js` keys)
- ENH-3554 (follow-up: extends `x-ll-context` with region-context classification)
- FEAT-3308 (byte-exact round-trip contract)

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Verified against code 2026-09-24: `_SCHEMA_ALLOWED_KEYS` (`artifact_templates.py:33`), `autoescape=False` (`:278`), the five per-key `html.escape` calls (`dashboard.py:314,315,318,320,337`), `_PROMPT_TEMPLATE` (`extract.py:51`), `extract_data` (`:102`), `data.json` writes (`:227,289`), and the `render_live_fragment` `autoescape=True` env (`dashboard.py:376`) all match.
- Corrected: schema-to-host line refs were `extract.py:154`/`:162`; actual `:150-152` (prompt) and `:163` (`json_schema`).
- Evidence-quote check (`ll-verify-evidence`): clean. Decisions log: no active required rules.
- Graph provider `codegraph` was `stale`; not used for any verdict (Grep only).

## Status

**Open** | Created: 2026-09-24 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-24T19:44:39 - `a13ea329-0bac-4e0c-ae19-52c2a57cea17.jsonl`
- `/ll:verify-issues` - 2026-09-24T19:13:35 - `27bdfde5-d1ef-4e98-b8ff-2728ac43d651.jsonl`
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - pre-implementation review: replaced bare `html.unescape` in the escape rule with `;`-terminated-only decoding (legacy-entity corruption verified); tuple paths with `ARRAY_ITEM` sentinel (dotted-string trust collision via undeclared keys); annotation placement rules; URL-rule step order and `ExtractError` wrapping; mapping-key escaping; validate-then-escape in the dashboard; `artifact_mode: template` added to the outside-boundary docs; refreshed `dashboard.py` line refs after ENH-3557 (done, `c6972b69d`)
- Manual review - 2026-09-24 - ported ENH-3540 Scope §2/§3, Option A decision, and ACs into this child; decided the annotation keys (`x-ll-context` + separate `x-ll-trusted`) and path derivation; added validate-then-escape ordering and `blocked_by: ENH-3557`
