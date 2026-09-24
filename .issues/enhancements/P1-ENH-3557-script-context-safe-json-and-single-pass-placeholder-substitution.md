---
id: ENH-3557
type: ENH
title: Script-context-safe JSON and single-pass placeholder substitution
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
labels:
- security
- artifacts
confidence_score: 100
outcome_confidence: 90
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 23
---

# ENH-3557: Script-context-safe JSON and single-pass placeholder substitution

## Summary

Add a `script_json` helper that escapes `<`, `>`, `&`, U+2028, and U+2029 as JSON unicode escapes, and use it for every `json.dumps` result spliced into HTML in `policy_builder.py` and `dashboard.py`. Replace the chained `html.replace` placeholder splices in `render_policy_builder_html()` with one `re.sub` pass, so spliced content is never rescanned. Pin both with hostile `</script>` and placeholder-token tests.

Carved out of cancelled ENH-3540 (Scope §1, §5); see that file for the full research trail.

## Current Behavior

- **JSON in inline `<script>` is not script-context-safe.** `json.dumps` does not escape `<`, so a string containing `</script>` closes the script block.
  - `scripts/little_loops/cli/artifact/policy_builder.py:88-123` (`render_policy_builder_html`) splices `grammar_json`, `catalog_json`, the generator version, `confidence_gate_json`, and `connected_context_json`. `catalog_json` comes from `_load_skill_catalog(config.project_root)`, whose skill names and descriptions agents can author.
  - `scripts/little_loops/cli/artifact/dashboard.py:343-344` (`build_dashboard_html`) builds `serve_interaction_url_js` and `serve_history_url_js` with `json.dumps`. The dashboard template stamps them into `fetch(...)` calls inside inline `<script>` (`templates/dashboard.llat/template.html.j2:327,393`).
- **Placeholders are re-scanned after each splice.** `render_policy_builder_html()` fills placeholders with a chain of `html.replace` calls (`policy_builder.py:115-123`), and each call rescans the whole page. `catalog_json` is spliced at `:116`. The later replacements (`/*__GENERATOR_VERSION_JSON__*/`, `/*__CONFIDENCE_GATE_JSON__*/`, `/*__BUILDER_CORE_JS__*/`, `/*__CONNECTED_CONTEXT_JSON__*/`) then also match inside the catalog text that was just inserted. A skill description containing `/*__BUILDER_CORE_JS__*/` gets the whole core JS spliced into the middle of a JSON string literal. `script_json` escapes neither `/` nor `*`, so it does not close this hole by itself.

## Expected Behavior

- JSON spliced into an inline `<script>` block is script-context-safe: a `</script>` inside a value cannot close the block, and the spliced text still `json.loads` back to the original value.
- Policy-builder placeholders are substituted in a single pass. Spliced content is never rescanned, so a skill description that contains a placeholder token survives verbatim and the core JS appears exactly once.

## Motivation

The skill catalog is agent-authorable and is embedded in a page that people other than its author open. A `</script>` or placeholder token in a skill description currently rewrites the page's script. This is a stored-XSS route through the policy builder, both offline (`ll-artifact policy-builder`) and in serve mode (`cli/artifact/serve.py` re-serves `render_policy_builder_html()` output verbatim, so it inherits the fix).

## Proposed Solution

1. **`script_json(obj)`** in `scripts/little_loops/artifact_templates.py`: `json.dumps(obj)`, then replace each of the five characters in the Decision Rules table with its six-character JSON unicode escape. Output is valid JSON and valid JS.
2. **Use it at every splice site.** `policy_builder.py`: `grammar_json`, `catalog_json`, the generator version, `confidence_gate_json`, `connected_context_json`. `dashboard.py`: `serve_interaction_url_js`, `serve_history_url_js` (`script_json(None)` is still `null`, so the disabled case needs no special-casing, same as today).
3. **Single-pass substitution.** Replace `policy_builder.py:115-123` with one `re.sub` over the pattern `/\*__([A-Z_]+)__\*/` and a callback that looks the name up in a dict of the six policy-builder values. The callback raises on a name that isn't in the dict. After the pass, also raise if any dict key was never matched, so a renamed template placeholder fails loudly instead of silently shipping an unfilled page. `stamp_page_shell` (which fills `/*__THEMED_CSS_VARS__*/` from config) runs before the pass and is unchanged.
4. `/*__BUILDER_CORE_JS__*/` is raw packaged JS, not JSON. It is spliced verbatim by the same single pass and is out of scope for `script_json`.

## Integration Map

### Files to Modify
- `scripts/little_loops/artifact_templates.py` — add `script_json`.
- `scripts/little_loops/cli/artifact/policy_builder.py` — `render_policy_builder_html`: `script_json` for every JSON splice; single-pass placeholder substitution.
- `scripts/little_loops/cli/artifact/dashboard.py` — `build_dashboard_html`: `script_json` for `serve_interaction_url_js` / `serve_history_url_js` (`:343-344`); update the comment at `:339-342`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/serve.py` (`_serve_policy_builder_page`, `_make_page_html_factory`) — re-serves the rendered pages verbatim; inherits the fix, no change.
- ENH-3558 — its markup allowlist exempts the `_js` keys from escaping, which is only safe once they go through `script_json`. ENH-3558 is blocked on this issue.

### Similar Patterns
- The vendoring-time `</script>` guard for trusted assets (`assets/vendor/sql.js/PROVENANCE.md:79-84`, `assets/vendor/htmx/PROVENANCE.md:72-76`) is the only existing `</script>` defense; `script_json` is the runtime equivalent for data.

### Tests
- `scripts/tests/test_policy_builder_emit.py` — hostile skill catalog (monkeypatch `_load_skill_catalog`): `</script><script>alert(1)</script>` and each placeholder token in a description.
- `scripts/tests/test_feat3304_artifact_dashboard.py` — hostile `ServeContext` interaction/history URLs.
- `scripts/tests/test_feat3036_artifact_templates.py` — direct `script_json` unit tests.

### Documentation
- Docstring on `script_json` stating the escape set and why (HTML parser closes `<script>` on `</script>`; U+2028/U+2029 are line terminators in older JS).

### Configuration
- N/A

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `policy_builder.py` `html.replace` chain | Fills the six policy-builder placeholders | PRESERVED | For a catalog with no placeholder tokens and no `<`/`>`/`&`/U+2028/U+2029, the page is byte-identical to today's. Test: render with a clean catalog before and after and compare. |
| `policy_builder.py` `html.replace` chain | Re-scans spliced content for later placeholders | DROPPED | This is the defect. |
| `policy_builder.py` `html.replace` chain | A placeholder missing from the template is silently skipped | CHANGED | Now raises, so a renamed placeholder fails loudly. |
| `dashboard.py` `_json.dumps` for `_js` keys | `None` renders as the JS literal `null` | PRESERVED | `script_json(None) == "null"`. |

## Program Design

### Signatures
- `script_json(obj: Any) -> str` — new, in `artifact_templates.py`. Returns `json.dumps(obj)` with the five characters from the Decision Rules table replaced. The result contains none of those five characters, and `json.loads(result) == obj`.
- `render_policy_builder_html(config: BRConfig, *, workspace_id: str | None = None) -> str` — existing, in `policy_builder.py`. Its JSON splices go through `script_json`; placeholders are filled in one pass.
- `build_dashboard_html(*, db_path: Path, config: BRConfig, tables: list[str], since_iso: str | None, mode: str, serve_context: ServeContext | None = None) -> RenderedDashboard` — existing, in `dashboard.py`. Its two `_js` keys use `script_json`.

### Call Path
`cmd_policy_builder` -> `render_policy_builder_html` -> `script_json` -> single-pass `re.sub` placeholder fill
`build_dashboard_html` -> `script_json` -> `render_template` (unchanged)

### Decision Rules
- Escape set for `script_json`: exactly five replacements, applied to the `json.dumps` output string. Each input character becomes a backslash, a lowercase `u`, and the four hex digits shown (hex digits spelled out in words on purpose; a tool that decodes backslash-u sequences has corrupted this table twice, so do not rewrite it as literal escape sequences):

  | Input character | Hex digits after backslash-u |
  |-----------------|------------------------------|
  | `<` (less-than) | `003c` |
  | `>` (greater-than) | `003e` |
  | `&` (ampersand) | `0026` |
  | U+2028 LINE SEPARATOR | `2028` |
  | U+2029 PARAGRAPH SEPARATOR | `2029` |

  Test oracle: the output contains none of the five input characters, and `json.loads(output) == obj`.
- Placeholder rule: the policy-builder placeholders are substituted in a single pass; spliced content is never rescanned. An unknown placeholder name raises; a dict key that never matched raises.

## Implementation Steps

1. Add `script_json` with unit tests: each of the five characters is absent from the output; `json.loads` round-trips nested dicts/lists/None/non-ASCII.
2. Switch the five policy-builder JSON splices and the two dashboard `_js` keys to `script_json`. Check: `grep -n "json.dumps" scripts/little_loops/cli/artifact/{policy_builder,dashboard}.py` shows no remaining splice sites.
3. Replace the `html.replace` chain with the single-pass `re.sub`; add the unknown/missing-key raises.
4. Hostile-payload tests (below). Then run `test_policy_builder_emit.py`, `test_feat3304_artifact_dashboard.py`, `test_feat3036_artifact_templates.py`, `test_policy_builder_node_gate.py`, plus `mypy` and `ruff check`.

## Impact

- **Priority**: P1 — agent-authored skill descriptions can rewrite the policy builder's script for anyone who opens it.
- **Effort**: Small — one helper, ~7 splice sites, one substitution rewrite, tests.
- **Risk**: Low — output bytes change only where a value contains one of the five characters; the page's JS parses the same values.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: `script_json`; every `json.dumps` spliced into HTML in `policy_builder.py` and `dashboard.py`; single-pass placeholder substitution in `render_policy_builder_html()`; hostile-payload tests for the policy builder and the dashboard's serve URLs.
- **Out of scope**: template-data escaping (`escape_data`, ENH-3558); artifact write paths (ENH-3559); the builder's client-side `innerHTML` sinks (ENH-3560); `render_template` / `build_environment()` (unchanged; FEAT-3308 byte-exact round trips); vendored raw JS (`sql_wasm_js`, `serve_htmax_js`, `/*__BUILDER_CORE_JS__*/`), which is trusted and checked at vendoring time.

## Acceptance Criteria

- [ ] `script_json` exists in `artifact_templates.py`; unit tests show its output contains none of `<`, `>`, `&`, U+2028, U+2029 and `json.loads` returns the input.
- [ ] No `json.dumps` result is spliced into emitted HTML in `policy_builder.py` or `dashboard.py` without `script_json`.
- [ ] A skill description of `</script><script>alert(1)</script>` (via monkeypatched `_load_skill_catalog`) and serve URLs containing the same payload produce a page whose `</script>` count equals a clean-input render's count (derived, not hard-coded), and each spliced JSON blob, extracted from the page, `json.loads` back to the hostile input.
- [ ] `render_policy_builder_html()` substitutes placeholders in one pass. A skill description containing each policy-builder placeholder token (`/*__BUILDER_CORE_JS__*/`, `/*__GRAMMAR_SPEC_JSON__*/`, etc.) round-trips verbatim through the catalog JSON, and the core JS appears exactly once in the page.
- [ ] An unknown placeholder in the template, or a value whose placeholder is missing from the template, raises.
- [ ] Tests run in the default `python -m pytest scripts/tests/` tier (no `integration` marker); `mypy` and `ruff check` pass.

## Related

- EPIC-3556 (parent); ENH-3540 (cancelled, original spec)
- ENH-3558 (blocked on this issue: allowlists the `_js` keys as verbatim)
- FEAT-3308 (byte-exact round-trip contract; `render_template` stays unchanged)

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed)

- Verified against code 2026-09-24: JSON splices at `policy_builder.py:88,91,97,117,120` (`json.dumps`, no escaping); `html.replace` chain at `:114-123` where the later replacements rescan already-spliced catalog and core JS; `dashboard.py:343-344` `_json.dumps` and template `fetch(...)` sites at `dashboard.llat/template.html.j2:327,393`; the six policy-builder placeholders each appear once in the template.
- Evidence-quote check: clean. Decisions log: no active required rules.
- Graph provider `codegraph` was `stale`; not used for any verdict (Grep only).

## Status

**Open** | Created: 2026-09-24 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-24T19:14:49 - `6b43fbf3-9a37-436a-ad6c-0f27aa9fd0d2.jsonl`
- `/ll:verify-issues` - 2026-09-24T19:13:34 - `27bdfde5-d1ef-4e98-b8ff-2728ac43d651.jsonl`
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - ported ENH-3540 Scope §1/§5, Decision Rules, and ACs into this child; added the unmatched-placeholder raise
