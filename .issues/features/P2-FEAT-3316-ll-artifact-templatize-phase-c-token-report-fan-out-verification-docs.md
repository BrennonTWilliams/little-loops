---
id: FEAT-3316
title: '`ll-artifact templatize` Phase C: token report, fan-out verification, docs'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: FEAT-3308
depends_on:
- FEAT-3314
relates_to:
- FEAT-3308
- FEAT-3309
- ENH-3035
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
testable: true
---

# FEAT-3316: `ll-artifact templatize` Phase C: token report, fan-out verification, docs

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md).
Adds the design-token unlifted-literal report, verifies the produced template
renders correctly against a second, different source document (the fan-out
use case the epic exists for), and lands the documentation updates.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Depends On

FEAT-3314 (Phase A) — this phase reports against and fan-out-tests the
template directory Phase A's `build_manifest`/`verify_round_trip` flow
produces. Independent of FEAT-3315 (Phase B); can proceed in parallel with
it once Phase A lands.

## Current Behavior

Phase A produces a working, byte-exact template but gives no signal about
design-token coverage: baked literal hex values in the artifact's CSS that
match the resolved token map go unreported, so a template can ship
permanently un-themeable with no warning. Nor is there any verification
that a produced template actually generalizes to a second source document —
Phase A's round trip only proves it reproduces the *original* artifact.

## Expected Behavior

After a successful `templatize` promote, an `unlifted-tokens.json` report is
written alongside the template listing every baked literal that matches the
resolved token map (with all candidate token names when a value is
ambiguous), plus a non-silent `logger.warn` naming the count. Separately, a
fixture proves the produced template renders correctly against a *second*,
different source document using a hand-authored `data.json` for that
document, matching a checked-in expected output. `docs/reference/CLI.md`,
`docs/reference/CONFIGURATION.md`, and `docs/ARCHITECTURE.md` reflect the
completed subcommand.

## Use Case

A user has run Phase A/B `templatize` successfully and has a working
template. Before adopting it for fan-out across many source documents, they
want to know two things without inspecting the output by hand: whether the
template is still carrying hard-coded colors that won't pick up a theme
change, and whether it actually generalizes past the one document it was
extracted from — both of which this phase answers automatically.

## Proposed Solution

### Round trip vs. token lifting

Byte-exact round trip and design-token lifting are **mutually exclusive by
construction**: a lifted stamp point renders `ll.theme_css` (a CSS
custom-property block), which is by definition not the literal hex the
original artifact contains. Resolution for v1:

- The round-trip gate (Phase A) runs against the **unlifted** template —
  that stays byte-exact with no tolerance, and this phase does not touch it.
- Token lifting is **report-only** in v1: `templatize` scans the artifact's
  CSS for values matching the resolved token map and writes an
  `unlifted-tokens.json` report plus a non-silent `logger.warn` naming the
  count and the token names. It does not rewrite them, and the emitted
  manifest does **not** set `theme: design-tokens`.
- Actually performing the lift (and the normalized-diff gate it would
  require) is deferred to a follow-up (see § Deferred below).

### Design-token stamp points

The HTML loops receive design tokens as **prompt text** —
`cli/loop/_helpers.py:1416-1424` seeds `context["design_tokens_context"]` via
`render_as_prompt_context`. A generated artifact therefore has token values
baked in as literal hex. The template kit (ENH-3035) stamps tokens **at
render time** as CSS variables via `render_as_css_vars_themed`
(`design_tokens.py:688`).

`templatize` must reconcile the two by recognizing baked literal token
values in the artifact's CSS and reporting them. Building that report needs
a `value -> token-name` inversion of `DesignTokens.resolved`
(`design_tokens.py:35`), which does not exist in the codebase — every
renderer iterates it forward-only. The inversion is **not injective** — two
tokens can resolve to the same hex — so a matched literal maps to a *list*
of candidate names and the report must say so rather than pick one.

### Fan-out verification

The resulting template must render correctly against a *second, different*
source document of the same kind. **Oracle:** the fixture ships a
hand-authored `data.json` for the second document and the test asserts the
render matches a checked-in expected output. (Deriving that `data.json`
automatically is `ll-artifact extract`, i.e. FEAT-3309, and is explicitly
not in scope here — this phase asserts the template *works* for fan-out, not
that extraction is automated.)

### Deferred to a follow-up

Actually **rewriting** baked token literals into `ll.theme_css` stamp points
(and emitting `theme: design-tokens`) is out of scope. It cannot coexist
with the byte-exact round-trip gate, so it needs its own normalized-diff
fitness function — a separate design decision, not a step here.
`report_token_literals` exists so the follow-up has an inventory to work
from and so a lossy template is never silently accepted in the meantime.

## Program Design

### Types

- `UnliftedToken: {literal: str, candidate_names: list[str], occurrences: int}` — the inversion is not injective, hence a name *list*

### Signatures

- `report_token_literals(css: str, tokens: DesignTokens) -> list[UnliftedToken]` — report-only in v1

### Call Path

`cmd_templatize` (Phase A) -> [after successful promote] -> `report_token_literals`

`build_ll_namespace`/`_themed_css_vars`/`render_as_css_vars_themed` are
**not** on this path in v1, because the emitted manifest omits `theme`.
`report_token_literals` needs a resolved `DesignTokens` via
`load_design_tokens`, obtained the same way `_themed_css_vars`
(`cli/artifact/policy_builder.py:56-87`) obtains it.

### Codebase Research Findings

- **`DesignTokens.resolved` (`design_tokens.py:35`) is forward-only.** Every
  renderer (`render_as_css_vars` `:678`, `render_as_css_vars_themed` `:688`,
  `render_as_prompt_context` `:572`) iterates it name -> value. No value ->
  name index exists anywhere; `report_token_literals` builds the inversion
  from scratch and must handle the non-injective case.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` — add
  `report_token_literals` call after successful promote
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — complete the
  subcommand section
- `docs/reference/CONFIGURATION.md` § `artifacts` (`:910-924`) — the prose at
  `:912` ("Currently backs the `policy-builder` subcommand...") stops being
  accurate once `templatize` reads *and writes* `templates_dir`; update it
- `docs/ARCHITECTURE.md` — document the templatize flow

### Similar Patterns
- `hitl-md.yaml:256-263`, `vega-viz.yaml:505-513` — hand-written loop states
  that already copy `${run_dir}/index.html` out; prior art for wanting
  artifacts to outlive a run

### Tests
- Extend `scripts/tests/test_artifact_templatize.py`:
  - Token report test: fixture with baked design-token hex literals, assert
    the report is non-empty and that a literal matching two token names
    reports both candidates.
  - Fan-out test: second, different source document with a hand-authored
    `data.json`, assert the render matches a checked-in expected output.
  - Assert the generating FSM loop is never invoked by `templatize` or
    subsequent renders (no `host_runner`/loop-execution call in this path).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Existing `.llat` fixture layout to extend for the fan-out fixture**: `scripts/tests/fixtures/artifact_templates/{simple,delimiters,theme}.llat/` (each with `manifest.yaml`, `template.html.j2`, `data.json`) is the existing checked-in template-fixture shape; a fan-out fixture (second source document + hand-authored `data.json` + checked-in expected render output) extends this layout.
- **No CSS-parsing dependency exists anywhere in `scripts/pyproject.toml`** (no `tinycss2`, `cssutils`, `cssselect`, etc. — the only markup-parsing dependency, `BeautifulSoup`, is used solely by the unrelated `doc_scraper.py`). `report_token_literals` must do its own from-scratch value-matching (regex/substring scan of the CSS text against `tokens.resolved`'s values) — there is no existing CSS-aware helper to reuse.
- **Precise mechanism for why literal token values get baked into generated artifacts**: `inject_design_context()` in `cli/loop/_helpers.py:1397-1430` (a more exact anchor than the issue's own `:1416-1424` citation) is guarded by `context.get("use_design_tokens", True)` with string-to-bool coercion at `:1419-1420` (`""`/`"0"`/`"false"`/`"no"`/`"off"` all disable it); when enabled it sets `context["design_tokens_context"] = render_as_prompt_context(_tokens)` (`:1423`), which emits `name: value` lines with literal resolved values (hex codes, sizes) — not CSS custom-property references. This confirms the exact seed point of the "baked literal" problem this phase reports on.
- **Two divergent, unreconciled report/warning conventions exist in this codebase** — the implementer must pick one for `cmd_templatize`'s token-report warning, since precedent alone does not settle it:
  - (a) `cli/verify_design_tokens.py`'s `lint_profile()`/`lint_profiles_dir()` (`:92-133`) build a `ThemeViolation` list, formatted via `_format_json_report()`/`_format_text_report()` (plain `json.dumps(..., indent=2)`) — but this convention *gates* (nonzero exit on any violation), which contradicts this phase's stated report-only, non-blocking requirement.
  - (b) `design_tokens.py`/`cli/artifact/design_md.py`'s `cmd_design_md_export` (`:111-122`) computes `notes` via a pure function (`_design_md_dropped_groups`, `design_tokens.py:862-888`) and emits exactly one `sys.stderr.write(f"[little-loops] Warning: ...")` line while the command still succeeds — the closer behavioral match to "report-only ... plus a non-silent warning naming the count," but note this uses raw `sys.stderr.write` with a hand-built `[little-loops] Warning:` prefix, **not** `Logger.warning()` — which is what `cmd_policy_builder`/`cmd_design_md_export` otherwise use for everything else, since FEAT-3314's Program Design has `cmd_templatize` receive a `Logger` argument matching that error-handling shape. Which convention the new warning line follows is an open implementation choice, not a settled one.
- **Existing JSON-report-to-disk write idiom**: `cli/verify_private_refs.py:461-474` (`write_baseline`) and `cli/verify_evidence.py:1234-1302` (`write_verdict_cache`/`write_baseline`) both use `path.parent.mkdir(parents=True, exist_ok=True)` then `path.write_text(json.dumps(payload, indent=2, ...) + "\n", encoding="utf-8")` — the closest existing write-idiom precedent for `unlifted-tokens.json`, though both existing examples exist for baseline/gating rather than pure reporting.
- **Fan-out / cross-fixture test convention to model after**: `test_streaming_cache_parity.py` and `test_benchmark_fragment.py::TestHarborFixtures` both hardcode fixture IDs (not globbed, so a missing fixture fails at collection time rather than silently generating zero test cases) and pair a `TestXFixtures` structural sanity-check class with a parametrized assertion test. This is the established N-input/N-expected-output pattern the fan-out test should follow.
- **`docs/reference/CLI.md`'s `### ll-artifact` section structure**: a subcommand table (`:4461-4465`) plus one `#### ll-artifact <subcommand>` subsection per subcommand (prose → Flags table → Examples → Exit codes → optional `> **Note:**` phase-status callout, e.g. `:4531` for `render`). `templatize` needs both a new table row and its own subsection in this shape.
- **`docs/ARCHITECTURE.md` has no artifact-templates section yet** (confirmed via grep — zero hits for `.llat`, "artifact template", `FEAT-3036`, `manifest.yaml`). The nearest analog is the "Project-enriched artifacts" paragraph (`:1027-1029`), which folds new artifact-generator examples into existing prose rather than adding a new heading. Whether `templatize` gets its own `####` section or a clause added to this existing paragraph is not settled by precedent — both shapes exist elsewhere in the file for other subsystems.

## Acceptance Criteria

- [ ] Baked design-token literals are reported as unlifted in `unlifted-tokens.json` and a non-silent log line; a test asserts the report is non-empty for a fixture with baked tokens and that a literal matching two token names reports both candidates.
- [ ] The resulting template renders correctly against a *second, different* source document of the same kind — the fan-out case. **Oracle:** the fixture ships a hand-authored `data.json` for the second document and the test asserts the render matches a checked-in expected output.
- [ ] The generating FSM loop is not invoked at any point in `templatize` or in subsequent renders.
- [ ] `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, and `docs/ARCHITECTURE.md` reflect the completed `templatize` subcommand.

## Impact

- **Priority**: P2 — the fan-out verification is the epic's stated
  user-facing payoff; the token report prevents a permanently un-themeable
  template from shipping silently.
- **Effort**: Medium — the token inversion and fan-out fixture are new but
  bounded; no round-trip transaction work (that's Phase A).
- **Risk**: Low — report-only, no rewrite; failure mode is an incomplete
  report, not a corrupted template.
- **Breaking Change**: No.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md` — dependency (Phase A)
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-24T18:58:03 - `ffa41e96-ab11-4f72-8513-f6153385423a.jsonl`
- `/ll:format-issue` - 2026-08-24T18:48:19 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
