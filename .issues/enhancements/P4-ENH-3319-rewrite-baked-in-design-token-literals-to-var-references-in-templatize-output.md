---
id: ENH-3319
type: ENH
title: Rewrite baked-in design-token literals to var() references in templatize output
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:04:10Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- templatize
confidence_score: 100
outcome_confidence: 85
score_complexity: 16
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# ENH-3319: Rewrite baked-in design-token literals to var() references in templatize output

## Summary

`ll-artifact templatize`'s `_report_unlifted_tokens` (`templatize.py:717-740`)
only *reports* baked-in color literals matching known design tokens
(`unlifted-tokens.json`) — it never rewrites the spliced template body to
reference `var(--...)` / the artifact template kit's stamping unit
(`artifact_template_kit.themed_css_vars`, ENH-3035). File real
literal→`var(--...)` rewriting as its own feature.

## Current Behavior

`ll-artifact templatize` produces a spliced `.j2` template body via
`apply_regions` (`scripts/little_loops/cli/artifact/templatize.py:474`),
writes it to disk, and verifies it round-trips byte-for-byte against the
original artifact via `verify_round_trip` (`templatize.py:545`). Only after
that verification succeeds does `cmd_templatize` call
`_report_unlifted_tokens` (`templatize.py:717`, invoked at `templatize.py:923`),
which decodes the already-final `spliced` bytes and calls
`report_token_literals` (`templatize.py:662`) to scan for `#`-hex /
`rgb()`/`rgba()`/`hsl()`/`hsla()` literals whose normalized value matches a
resolved design token (`DesignTokens.resolved`). Matches are written to
`unlifted-tokens.json` as `{"literal", "candidate_names", "occurrences"}`
entries — no byte offsets are captured; the regex match spans are read for
`.group(0)` only and discarded — and logged as a warning. The template body
on disk is never modified. `_report_unlifted_tokens`'s entire body is wrapped
in a bare `except Exception` (`templatize.py:717-740`) specifically so
nothing in this step can affect `cmd_templatize`'s exit code or block
`promote()`.

## Expected Behavior

Under an opt-in `--lift-tokens` flag (default off), a baked-in color literal
matching a resolved design token gets rewritten, in the spliced template
body, to a `var(--color-surface-primary)`-style reference at the literal's
own byte span, and the template gains the token block that defines those
vars (`manifest["theme"] = "design-tokens"` plus an injected
`[[= ll.theme_css =]]` expression inside a `<style>` element, so
`build_ll_namespace`'s existing `ll.theme_css` hook supplies the
declarations at render time). With the flag off, behavior is exactly
today's: report-only, fail-open, byte-exact round trip.

**Not `/*__THEMED_CSS_VARS__*/`.** An earlier revision specified that
placeholder. `render_template` never calls
`artifact_template_kit.stamp_page_shell` — its only caller is
`cli/artifact/policy_builder.py:91`, a build-time HTML-assembly path, and
the render path (`artifact_templates.py:311-345`) exposes `ll.theme_css`
and nothing else. A literal `/*__THEMED_CSS_VARS__*/` comment injected into
a templatize-produced body is therefore inert: it survives verbatim into the
rendered artifact, no `:root {}` block is ever emitted, and every lifted
`var()` resolves to nothing. The Jinja delimiters are frozen at
`artifact_templates.py:268-273` (`[[=` / `=]]`), so the stamp point the lift
injects is the expression `[[= ll.theme_css =]]`, wrapped in a `<style>`
element in `<head>`.

**Byte-exact round trip and real token lifting are mutually exclusive.** A
lifted template renders to `var(--...)` references plus a `:root {}` block —
deliberately *not* the original bytes. So `verify_round_trip`
(`templatize.py:545`), which diffs `render_template`'s output against the
original pre-splice artifact bytes, cannot be the check for a lifted
template. See Program Design § Decision Rules for the two-stage verification
that replaces it. Notably this requires **no change to
`ArtifactTemplate`/`render_template`** — see the rejected alternative below.

## Motivation

ENH-3035's Decisions (2026-08-25) explicitly rejected doing this as part of
the template-kit extraction: setting `manifest["theme"] = "design-tokens"`
whenever `_report_unlifted_tokens` finds matching literals would stamp
`theme_css` vars into a body that still carries the literals — unreferenced
vars *and* unlifted literals, not token lifting. Real lifting requires
locating each literal's span in the template body and splicing in a
`var(--...)` reference (or an `[[= ll.theme_css =]]`-style stamp point),
which is new feature work, not the extraction ENH-3035 scoped.

ENH-3035 was right that stamping `theme_css` *alone* is dead weight. This
issue supplies the other half: the stamp point and the literal rewrite land
**together**, or not at all. A body with `var(--...)` refs and no `:root {}`
block renders colorless; a body with a `:root {}` block and no refs is the
unreferenced-vars dead weight ENH-3035 rejected.

### Rejected alternative: a render-time un-lift hook

An earlier revision of this issue proposed adding a design-token-aware
substitution hook to `render_template`/`build_ll_namespace`
(`artifact_templates.py:311-345`) that resolves `var(--color-surface-primary)`
back to `#fdfbf6` at render time, so `verify_round_trip` keeps passing
byte-exact. **Rejected**: if that hook works, the rendered artifact is
byte-identical to today's, i.e. nothing is lifted at render time — the hook's
entire job is to undo the feature. It would also change the shared render
engine for every `.llat` consumer (`extract.py`, `render.py`,
`fsm/persistence.py::promote_run_artifact`, `dashboard.py`) to buy nothing,
and a textual `var()`→literal substitution would corrupt hand-authored
templates that legitimately emit `var(--name, fallback)` in their output CSS
(`templates/policy-router-builder.html.tmpl:18,27`). The two-stage
verification in Program Design § Decision Rules gets the same safety with
zero render-engine blast radius.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- `little_loops/artifact_templates.py` — `render_template()` (`:321-345`) has no general "resolve a reference back to a literal" mechanism at render time; the only existing design-token-aware render hook is `build_ll_namespace()`'s `ll.theme_css` (`:311-318`), an unconditional whole-token-set CSS blob gated by `manifest["theme"] == "design-tokens"` — not a per-occurrence literal→var lookup.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` (hand-authored, not `templatize`-produced) already uses the CSS-native `var(--name, <fallback-literal>)` two-argument form throughout (e.g. `:18`, `:27`) — a precedent for pairing a token reference with an inline literal fallback, though unrelated to `templatize`'s byte-exact round-trip mechanism.
- Contested convention: this codebase has two different span-splicing models, not one. `apply_regions` (`templatize.py:474-511`) is byte-oriented, forward-cursor, and hard-fails (`SpliceError`) on overlap/out-of-bounds. `_sweep_file` (`issues/anchor_sweep.py:59`) is str-oriented, collects `(start, end, replacement)` and applies them in **reverse order** with no explicit overlap check. Both exist in this codebase; the Conventions-in-Force claim above that a literal-rewrite span "must compose into apply_regions's model" is one option among two established patterns, not the only one.

### Files to Modify

**`scripts/little_loops/cli/artifact/templatize.py`** — the only source file this issue edits.
- *Current*: `report_token_literals` (`:662`) scans the spliced body and discards each regex match's `.start()`/`.end()`, returning only aggregate `UnliftedToken` counts (`:616`); `cmd_templatize` has no lifting flag; `_write_unlifted_tokens_report` (`:698`) emits an `unlifted`-only payload whose `_comment` asserts "Report-only — not rewritten."
- *New*: a sibling `find_token_literals(template_text, tokens) -> list[TokenLiteralMatch]` exposes per-match spans and applies the CSS-value-position guard, with `report_token_literals` reimplemented as a thin aggregation over it — signature and return shape unchanged, so every subtest in `TestReportTokenLiterals` (`test_artifact_templatize.py:995-1054`), which asserts full dict equality against today's three-key shape, passes untouched. `add_templatize_parser` gains `--lift-tokens` (default off); `cmd_templatize` gains a post-`verify_round_trip` lift pass plus a reversibility check; the report payload gains a `lifted` list and a rewritten `_comment`.

**`scripts/little_loops/cli/artifact/__init__.py`** — *current*: dispatches `templatize` subcommand args as-is (`:47,35`). *New*: threads the `--lift-tokens` flag through. No other behavior change.

_Reference only — read during implementation, not edited:_
- `scripts/little_loops/artifact_template_kit.py` — **not involved in this issue's mechanism, and no edit.** `stamp_page_shell` (`:52`) is a *build-time* helper whose only caller is `cli/artifact/policy_builder.py:91`; the `.llat` render path never invokes it. `themed_css_vars` (`:18`) *is* reached, but indirectly — `build_ll_namespace` (`artifact_templates.py:311-318`) calls it to populate `ll.theme_css` when `manifest["theme"] == "design-tokens"`. The lift therefore injects a `[[= ll.theme_css =]]` expression, not the kit's `/*__THEMED_CSS_VARS__*/` placeholder. (An earlier revision claimed "the existing stamping path starts firing instead of no-opping" — that is false; `stamp_page_shell` is never called on this path at all.)
- `scripts/little_loops/design_tokens.py` — `tokens.resolved` is the shared source of both the literal-matching inversion in `report_token_literals` and the `--name-with-dashes: value;` declarations `render_as_css_vars_themed` (`:688-707`) emits. Two properties of that emitter bind the lift (see Decision Rules § Var-name derivation): names are **dotted full paths** (`color.surface.primary`, not `surface.primary`) mangled `.`→`-` at `:703`, and `_`-prefixed metadata keys are **skipped** at `:701-702`. **No edit.**
- `scripts/little_loops/artifact_templates.py` — **no edit.**
  An earlier revision listed it as a file to modify, for a render-time
  per-occurrence substitution hook; see Motivation § Rejected alternative for
  why that approach was dropped. `build_ll_namespace`'s existing
  `ll.theme_css` hook (`:311-318`, gated on
  `manifest["theme"] == "design-tokens"`) is the entire render-side mechanism
  needed. Because the shared render engine is untouched, `extract.py`,
  `render.py`, `fsm/persistence.py::promote_run_artifact`, and `dashboard.py`
  have zero behavior exposure to this issue.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/templatize.py:923` — `cmd_templatize` calls `_report_unlifted_tokens` after `verify_round_trip` succeeds and before `promote()`.
- `scripts/little_loops/cli/artifact/templatize.py:731` — `_report_unlifted_tokens` calls `report_token_literals`.
- `scripts/little_loops/cli/artifact/policy_builder.py:61,68,91` — the **only** consumer of `stamp_page_shell`, and a build-time one. Read it to see why it is *not* the model for this issue: it stamps a hand-authored `.html.tmpl` into finished HTML before writing, whereas templatize output is rendered later through `render_template`, which has no stamping step. Reference only; this issue's stamp point is `[[= ll.theme_css =]]`.
- `scripts/little_loops/artifact_templates.py:311-318` — `build_ll_namespace` populates `ll.theme_css` from `themed_css_vars(config)` when `manifest["theme"] == "design-tokens"`. This is the entire render-side mechanism the lift depends on. **No edit** — the lift supplies the manifest key and the `[[= ll.theme_css =]]` reference; this hook already does the rest.

_Wiring pass added by `/ll:wire-issue` — trimmed after the render-hook rejection:_
- `scripts/little_loops/cli/artifact/__init__.py:47,35` — imports `add_templatize_parser`/`cmd_templatize` from `templatize.py`; CLI subcommand dispatch surface, needs the new `--lift-tokens` flag threaded through.
- `scripts/little_loops/cli/artifact/discover.py:23-25` — imports `DiscoveryResult`, `RegionMapError` from `templatize.py`; unaffected (the rewrite is a separate post-splice pass, not a new `Region` variant — see Decision Rules).
- `scripts/little_loops/fsm/persistence.py:818-882` — `promote_run_artifact()` calls `ArtifactTemplate`/`render_template`/`_templatize_promote` directly. **No exposure**: the render engine is unchanged and `--lift-tokens` defaults off, so this path behaves identically. Listed to record that the default-off flag is what keeps it that way.
- `scripts/little_loops/cli/artifact/extract.py:30,103,210,265`, `scripts/little_loops/cli/artifact/render.py:19,37,124` — instantiate `ArtifactTemplate` on the shared render path. **No exposure**, same reason; a lifted template renders through the existing `ll.theme_css` path these already support.

### Conventions in Force
- This module's one span-splicing pass (`apply_regions`, `templatize.py:474-511`) sorts `(start, end, kind, obj)` tuples and hard-errors via `SpliceError` on overlap/out-of-bounds rather than best-effort merging. **This issue deliberately does not extend that list** — see Decision Rules § Splice placement. A literal-rewrite span composed into `apply_regions` would be computed against pre-splice bytes and would therefore match literals *inside extracted data regions*, whose spans overlap the corresponding `Region` and hard-error with `SpliceError` on ordinary artifacts. The rewrite is a separate pass over the already-spliced body, reusing `anchor_sweep._sweep_file`'s reverse-order model (`issues/anchor_sweep.py:59`), the second established span-splicing convention this codebase already carries.
- Splice/round-trip tests assert exact byte equality and error paths via `pytest.raises(SpliceError, match=...)` — evidence: `test_artifact_templatize.py::TestApplyRegions` (`:208-325`).
- Literal matching in this codebase is regex-based over rendered text plus a normalization step (`_normalize_color_value`/`_normalize_hex`), not AST/CSS parsing — evidence: `templatize.py:622-695`.
- A report-only feature graduating to an active rewrite is **filed** as a separate issue — evidence: ENH-3035's Decisions (2026-08-25) explicitly deferred this rewrite to a new ENH (this issue), rejecting a `manifest["theme"]`-stamping shortcut as "dead weight, not token lifting." Note this convention governs *where the work is filed*, not *whether the runtime gates it*; an earlier revision of this issue read it as an argument against a CLI flag, which is a non-sequitur. Both hold: separate issue **and** default-off `--lift-tokens`.
- A documented output guarantee is not changed unconditionally under an existing flagless invocation — the byte-exact round-trip guarantee is stated in `docs/ARCHITECTURE.md:1031` and `docs/reference/CLI.md:4593`, and `fsm/persistence.py::promote_run_artifact` depends on today's behavior with no way to opt out.

### Tests
- `scripts/tests/test_artifact_templatize.py` — `TestReportTokenLiterals` (`:995`), `TestCmdTemplatizeTokenReport` (`:1057`), `TestApplyRegions` (`:208-325`), and `TestCmdTemplatizeEndToEnd.test_end_to_end_round_trip` (`:403-440`) — the only existing byte-identical round-trip regression test in this codebase.
- `scripts/tests/test_enh3035_artifact_template_kit.py` — covers `themed_css_vars`/`stamp_page_shell`. Note `stamp_page_shell` is **not** on this issue's path; do not add flag-on coverage here (see below).
- `scripts/tests/test_feat3036_artifact_templates.py` — covers `build_ll_namespace`/`render_template`, the hook this issue actually depends on. Read for the render-side assertion pattern; no edits.
- `scripts/tests/test_design_tokens.py` — covers `DesignTokens`/`.resolved`.

_Wiring pass added by `/ll:wire-issue` — revised for the default-off flag and the sibling-function split:_

**Existing tests that must keep passing unchanged** (the default-off flag is what buys this — if any of these needs editing, the flag gating is wrong):
- `scripts/tests/test_artifact_templatize.py::TestReportTokenLiterals` (`:995-1054`) — full dict equality against the three-key `UnliftedToken` shape. Preserved by adding `find_token_literals` as a **sibling** rather than a span field on `UnliftedToken`.
- `scripts/tests/test_artifact_templatize.py::TestCmdTemplatizeTokenReport` (`:1057-1212`), including `test_containment_forced_failure_still_promotes_exit_0` (`:1182-1212`) — the fail-open contract stays exactly as-is on the default (`--lift-tokens` off) path. The exit-code-2 behavior is additive, tested separately under the flag, not a bifurcation of this class.
- `scripts/tests/test_artifact_templatize.py::TestCmdTemplatizeEndToEnd.test_end_to_end_round_trip` (`:403-440`) and `TestApplyRegions` (`:208-325`) — byte-exact round trip is still the contract with the flag off.
- `scripts/tests/test_feat3036_artifact_templates.py`, `test_feat3310_artifact_extract.py`, `test_fsm_persistence.py`, `test_artifact_discover.py` — no render-engine change, so no edits expected.

**Existing test that changes by design:**
- `scripts/tests/test_enh3035_artifact_template_kit.py::TestKitAcceptsTemplatizedBody.test_templatized_body_with_baked_in_token_literal_stamps_without_error` (`:82-132`) — asserts `assert "#fdfbf6" in body` (`:124`) and `assert stamped == body` (`:132`), documenting that the literal "survived templatize unchanged." Keep it **unmodified** as the flag-off case; it stays true. An earlier revision proposed a flag-on sibling here asserting a non-no-op `stamp_page_shell` — **drop that**: `stamp_page_shell` is never called on the render path, so such a test would assert the wrong mechanism. The flag-on render-side assertion belongs in `test_artifact_templatize.py` and goes through `render_template` (see below).

**New tests needed:**
- Two-stage verification (Decision Rules): pre-lift byte-exact round trip passes, then undoing the recorded lift + stamp spans on the lifted body reproduces the verified pre-lift body byte-for-byte.
- **Stamp point actually resolves (guards the highest-impact defect)**: run `templatize --lift-tokens`, then `render_template` the result, and assert the rendered output contains a `:root {` block with the `--color-…` declarations *and* no residual `[[=` / `/*__THEMED_CSS_VARS__*/` text. Without this the feature ships colorless and every other test still passes.
- **Theme fidelity**: with `active_theme: dark`, a dark-authored artifact lifted and re-rendered resolves its `var()` refs to the *dark* values, not the light `:root` palette.
- **Var-name/declaration agreement**: for each lifted token, the emitted `var(--x)` name appears verbatim as a `--x:` declaration in `render_as_css_vars_themed`'s output — catches drift from the `.`→`-` mangling at `design_tokens.py:703`.
- **Textual-inverse false rejection**: a source artifact already containing `var(--color-surface-primary)` lifts successfully (a whole-body textual inverse would reject it with exit code 2).
- **Alias-preference ambiguity**: `#e8dcc4` (one alias, one primitive) lifts to `color.border.subtle`; `#fdfbf6` under the light theme (two aliases) stays unlifted with both candidates reported.
- **Hard preconditions**: a body with no `<head>`/`<style>`, and a body whose `data-theme` disagrees with the active theme, are both left entirely unlifted with an unchanged manifest and exit code.
- Unreversible lift → `rejected_dir` / exit code 2, under `--lift-tokens` only. Follow `TestApplyRegions`'s `pytest.raises(SpliceError, match=...)` pattern composed with `TestCmdTemplatizeEndToEnd`'s CLI-level `code == 2` assertions.
- **CSS-context guard (highest-value new coverage)**: an artifact carrying `href="#dedede"`, an id selector `#face {`, and `"#c0ffee"` inside a `<script>` string, where those values are also resolved token values — assert none are rewritten and all are still reported. Today these are harmless warning lines; after the rewrite an unguarded match is silent artifact corruption, and the two-stage verification will *not* catch it (the inverse map restores it cleanly).
- Ambiguous literal-to-token-name resolution (AC #5): candidates surviving the alias-preference filter, not the raw candidate count, decide (see the alias-preference bullet above). `test_non_injective_reports_all_candidate_names` (`:1005-1011`) covers only today's report-all behavior and stays unmodified.
- Flag-off regression: an artifact full of matching literals produces byte-identical output and an identical `unlifted-tokens.json` to today's.

### Documentation
- `docs/reference/CLI.md` (`## ll-artifact templatize`, ~`:4545`) documents today's report-only `unlifted-tokens.json` behavior; needs updating once rewriting lands.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:1031` — "Turning a generated artifact into a reusable template" section states verbatim that "token lifting is report-only in v1 ... never rewriting them" — this sentence is exactly what this issue makes obsolete and must be rewritten to describe the actual rewrite mechanism once implemented.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

- **Coordinate-space mismatch (new — not yet reflected in Call Path above)**: `report_token_literals` scans `template_text`, which `_report_unlifted_tokens` decodes from `spliced` (`templatize.py:923`) — i.e. the body *after* `apply_regions` has already run. Its match offsets are therefore in post-splice coordinate space. `apply_regions`'s `Region`/`RegionGroup` spans (`start`/`end`) are byte offsets into the **original pre-splice** `artifact` bytes. A literal-rewrite span cannot be added to `apply_regions`'s existing sorted span list as-is — it must either be computed against the pre-splice artifact bytes directly (a literal-detection pass before `apply_regions` runs), or explicitly translated from post-splice to pre-splice offsets.
- `Region`/`RegionGroup` (dataclasses, `templatize.py`): `Region(start: int, end: int, expr: str, group: str | None, anchor_before: str | None, anchor_after: str | None)`; `RegionGroup(id: str, binding: str, array_path: str, start: int, end: int, iterations: list[tuple[int, int]])` — the concrete shapes `apply_regions` sorts and splices; a literal-rewrite span would need an equivalent shape (or reuse `Region` with a synthetic `expr`).
- Ambiguity-resolution precedent (extends Decision Rules below): no "canonical name" concept exists in `design_tokens.py` (zero hits). Two contested precedents apply from elsewhere, and they disagree: (a) `DesignMdColorCollisionError` (`design_tokens.py:747-770`) is a fail-closed collision guard, but in the reverse direction (name→export-name collisions, raised during DESIGN.md export) — not literal→name selection. (b) `text_utils.classify_file_ref`/`suffix_match_candidates` (`text_utils.py:269-364`) returns an explicit `"ambiguous"` status when more than one candidate remains after a documented filter step, rather than picking one. Neither establishes a pick-first/alphabetical priority rule.
_Added by pre-implementation review — 2026-08-25 — measured against this repo's own `warm-paper` profile:_

- **The value→name inversion is ambiguous for roughly half of all colors, and specifically for the semantic ones.** Measured on `.ll/design-tokens/profiles/warm-paper/`: of 22 distinct resolved color values, **11 (light) / 12 (dark) map to more than one token name**. The cause is structural, not incidental — every semantic token is an alias of a primitive (`color.surface.primary: "{color.paper.0}"`), so it always resolves to the same value as the primitive it points at and always collides with it:
  ```
  light  #fdfbf6 → color.paper.0, color.surface.primary, color.text.inverse
  light  #e8dcc4 → color.border.subtle, color.paper.200
  dark   #c84a1c → color.action.primary, color.terracotta.500
  dark   #2e2820 → color.border.subtle, color.paper.800, color.surface.raised
  ```
  A naive fail-closed-on->1-candidate rule therefore refuses to lift almost every color worth lifting. See Decision Rules § Ambiguous literal-to-token mapping for the alias-preference filter that resolves this.
- **Light and dark resolve the same names to different values** (`color.surface.primary` = `#fdfbf6` light / `#0d0b08` dark — `themes/light.json`, `themes/dark.json`). `load_design_tokens(config)` with no `theme=` argument uses `dt_cfg.active_theme` (`design_tokens.py:370`), which is `dark` in this project's config, while `render_as_css_vars_themed` (`:707`) puts **light** in `:root` and dark under `[data-theme=dark]`. A templatize-produced body carries no `data-theme` attribute. See Decision Rules § Theme selection.
- Token names in `resolved` are **dotted full paths** — `color.surface.primary`, never `surface.primary`. Verified by loading the profile. Every `var(--surface-primary)` in earlier revisions of this issue names a custom property that is never declared.
- `_wcag_spot_check` (a nested dict in `semantic.json`) is present in `resolved` and its `str()` form embeds hex literals, but `_normalize_color_value` returns `None` for it (it neither starts with `#` nor matches the functional-color prefix), so it cannot currently enter the inversion. The `_`-prefix exclusion below is defence in depth against a future scalar `_`-prefixed token, and mirrors `render_as_css_vars_themed:701-702`.
- Testing convention beyond `TestCmdTemplatizeEndToEnd`: a full-loop byte-identical assertion pattern also exists — run `templatize` to produce a `.llat/`, then run `render` against it, then compare `read_bytes()` of the rendered output to `read_bytes()` of the original artifact (not just `verify_round_trip(...) is None`) — `test_artifact_templatize.py:403-440`, `:1277-1292`.

### Types
- `UnliftedToken` (TypedDict, `templatize.py:616`): `{"literal": str, "candidate_names": list[str], "occurrences": int}` — carries no byte-offset/span data. **Leave this shape alone.** Add a new `TokenLiteralMatch` (`{"start": int, "end": int, "literal": str, "candidate_names": list[str]}`) returned by the new sibling function; `report_token_literals` aggregates matches into today's `UnliftedToken` shape unchanged.
- Report payload: `unlifted-tokens.json` keeps its filename and grows a sibling `"lifted"` list next to `"unlifted"` (rather than being renamed), so existing readers keyed on `"unlifted"` — including `TestCmdTemplatizeTokenReport` — keep working. The hardcoded `_comment` string (`templatize.py:701-709`), which currently states "Report-only — not rewritten, and the manifest does not set theme: design-tokens", must be rewritten to describe both modes.

### Signatures
- `report_token_literals(template_text: str, tokens: DesignTokens) -> list[UnliftedToken]` (`templatize.py:662`) — signature and return shape **unchanged**; reimplemented as an aggregation over the new sibling.
- New: `find_token_literals(template_text: str, tokens: DesignTokens) -> list[TokenLiteralMatch]` — the span-returning primitive (regex matches already carry `.start()`/`.end()`; today they are read for `.group(0)` only and discarded). This is also where the CSS-context guard lives (see Decision Rules).
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` (`templatize.py:474`) — the only span-splicing entry point in this module; consumes `Region`/`RegionGroup` spans, not literal-match spans.
- `build_ll_namespace(root: Path, manifest: dict, config: object) -> dict` (`artifact_templates.py:311-318`) — sets `namespace["theme_css"] = themed_css_vars(config)` iff `manifest.get("theme") == "design-tokens"`. **The only render-side hook this issue uses.**
- `build_environment() -> SandboxedEnvironment` (`artifact_templates.py:259-279`) — frozen delimiters `[[= … =]]` (expression), `[[% … %]]` (block). The injected stamp point must use these, not Jinja defaults.
- `render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str` (`design_tokens.py:688-707`) — emits `:root { --<dotted.name → dashed>: <light value>; … }` then `[data-theme=dark] { … }`, skipping `_`-prefixed keys. The lift's var-name derivation must match `:703` exactly.
- `stamp_page_shell(...)` / `themed_css_vars(...)` (`artifact_template_kit.py:52`, `:18`) — listed only to record that `stamp_page_shell` is **not on this path**; `themed_css_vars` is reached solely via `build_ll_namespace`.
- `verify_round_trip(template_dir: Path, data: dict[str, Any], original: bytes, config: object) -> str | None` (`templatize.py:545`) — diffs `render_template`'s output against the pre-splice `artifact_bytes`, never against `spliced`.

### Call Path

Flag off (default) — **unchanged from today**:
`cmd_templatize` -> `apply_regions` -> `verify_round_trip` -> `_report_unlifted_tokens` (fail-open) -> `promote`.

Flag on (`--lift-tokens`):
`cmd_templatize` -> `apply_regions` (produces `spliced`) -> `verify_round_trip(spliced)` **byte-exact against the original, exactly as today** -> `lift_token_literals(spliced)` -> `verify_lift_reversible(lifted, spliced)` -> write lifted body + `theme: design-tokens` manifest -> `_report_unlifted_tokens` (now reporting `lifted` + `unlifted`) -> `promote`.

The two verification stages are ordered so the byte-exact guarantee is proven *first*, on the un-lifted body, and the lift is then proven reversible against that already-verified body. A failure in either stage routes through the existing `rejected_dir`/exit-code-2 path.

`_report_unlifted_tokens`'s bare `except Exception` (`templatize.py:717-740`) stays exactly as-is: it remains a pure reporting step in both modes. The steps that *can* fail closed (`lift_token_literals`, `verify_lift_reversible`) are new siblings placed before it, not modifications to it — so the fail-open contract and the fail-closed rewrite coexist rather than conflict, and `test_containment_forced_failure_still_promotes_exit_0` keeps passing untouched.

### Decision Rules
- **Splice placement**: the lift is a **separate pass over the already-spliced body**, not a span added to `apply_regions`'s list. Rationale: (1) a pre-splice literal detection finds literals *inside extracted data regions*, which are not part of the template body at all, and whose spans overlap the corresponding `Region` → `SpliceError` on ordinary artifacts; (2) post-splice detection excludes them for free; (3) it dissolves the coordinate-space mismatch documented above rather than requiring offset translation. Apply collected `(start, end, replacement)` spans in **reverse order**, per `issues/anchor_sweep.py:59`. This supersedes the earlier "must compose into `apply_regions`" convention claim.
- **Var-name derivation**: the emitted reference is `var(--{name.replace(".", "-")})` over the **full dotted token path** — `color.surface.primary` → `var(--color-surface-primary)`. This is the same mangling `render_as_css_vars_themed:703` uses to emit the declaration, and the two must not drift; a test asserts the emitted reference appears verbatim in `render_as_css_vars_themed`'s output for the same token. Names beginning with `_` are excluded from the candidate map entirely, mirroring the metadata skip at `:701-702` — a `var()` referencing a `_`-prefixed name would never be declared. (Earlier revisions of this issue wrote `var(--surface-primary)`; that property does not exist.)
- **Ambiguous literal-to-token mapping — alias-preference filter, then fail-closed**: a naive ">1 candidate ⇒ skip" rule blocks **11 of 22 light and 12 of 22 dark colors** on this repo's own profile, and blocks precisely the semantic tokens the feature exists to lift (see Codebase Research Findings above). The cause is structural: every semantic token is declared as an alias (`"{color.paper.0}"`), so it *always* resolves equal to its primitive and *always* collides with it. Rule:
  1. Filter the candidate list to names whose **raw, pre-resolution** value is an alias reference (`{...}`) — i.e. prefer the semantic name over the primitive it points at. A `var(--color-surface-primary)` is the reference an artifact should carry; `var(--color-paper-0)` is the implementation detail behind it.
  2. If exactly one candidate survives, rewrite to it.
  3. Otherwise (zero aliases, or two-or-more aliases — e.g. light `#fdfbf6` → both `color.surface.primary` and `color.text.inverse`) **do not rewrite**; report in `unlifted` with all candidates, as today.
  Rationale for still failing closed at step 3: no "canonical name" concept exists in `design_tokens.py`, and `text_utils.classify_file_ref`'s explicit `"ambiguous"` status (`text_utils.py:269-364`) is the governing precedent for a genuinely undecidable choice. Step 1 is not a pick-first heuristic — it is a structural fact about the token graph, and it must read the raw layered data (`DesignTokens.semantic`/`.theme`), not `resolved`, which has already erased the alias.
- **Theme selection — mandatory, or the lift inverts the artifact's colors**: `report_token_literals` calls `load_design_tokens(config)` with no `theme=`, which resolves against `dt_cfg.active_theme` (`design_tokens.py:370`) — `dark` in this project. But `themed_css_vars`/`render_as_css_vars_themed` put the **light** values in `:root` and dark under `[data-theme=dark]`, and a templatize-produced body has no `data-theme` attribute. Left alone, a dark-authored artifact would lift its dark literals and then render light. The reversibility check (below) cannot detect this — it applies the same resolved map on both sides, so the substitution round-trips perfectly while the *rendered* artifact flips theme.
  Resolution: the lift pass loads tokens with an **explicit** `theme=`, and the lifted body's root element carries the matching `data-theme` attribute. Concretely: lift against `dt_cfg.active_theme`, and inject `data-theme="<active_theme>"` on `<html>` alongside the `[[= ll.theme_css =]]` stamp. If the body already carries a `data-theme` attribute whose value differs from the active theme, **do not lift** (route to `unlifted` with a reason) rather than rewriting the author's attribute. A test asserts a dark-active lift produces a body whose rendered colors equal the original artifact's, not the light palette.
- **Emit bare `var(--name)`, not the two-argument `var(--name, #literal)` fallback form** — decided, revisitable. The two-arg form (precedent: `templates/policy-router-builder.html.tmpl:18,27`) would make a failed stamp degrade gracefully instead of rendering colorless. Rejected for v1 because it leaves the literal in the body, so a re-run of `templatize` re-reports every already-lifted literal as `unlifted` — the report contradicts itself — and the inverse map must then distinguish "fallback literal I emitted" from "literal I failed to lift". The graceful-degradation need is met instead by the hard preconditions below: no stamp point placeable ⇒ no lift at all, so a colorless render is unreachable.
- **CSS-context guard — mandatory**: `_HEX_LITERAL_RE = r"#[0-9a-fA-F]+"` (`templatize.py:625`) has no word boundary and no context check. It matches `href="#dedede"`, an id selector `#face`, and `"#c0ffee"` in a JS string. Today a false positive is a harmless warning line; **under rewriting it is silent artifact corruption**, and the reversibility check will not catch it because the inverse map restores it cleanly. Rewrites therefore fire **only in CSS-value position** — inside a `<style>` element or a `style="…"` attribute, after a `:` and before a `;`, `}`, `)`, or the attribute's closing quote. A match outside CSS-value position is reported (today's behavior) and never rewritten.
- **Scope**: the rewrite inherits `report_token_literals`'s v1 scope verbatim — **colors only** (`#rgb`/`#rgba`/`#rrggbb`/`#rrggbbaa` plus `rgb()`/`rgba()`/`hsl()`/`hsla()`). `space`, `radius`, `font`, and bare-number token namespaces are out of scope and are neither reported nor rewritten.
- **Reversibility (replaces "round-trip compatibility") — span-tracked, not textual**: a lift is valid iff undoing it reproduces the verified pre-lift body byte-for-byte. The inverse is applied **only at the spans the lift itself recorded**, and additionally removes the injected stamp block (the `<style>[[= ll.theme_css =]]</style>` insertion and the `data-theme` attribute, both recorded as spans at injection time). Two reasons this cannot be a whole-body textual `var()`→literal substitution, as an earlier revision specified:
  1. The lifted body is not the pre-lift body plus var-substitutions — it also gained the stamp block. A var-only inverse can never reproduce the pre-lift bytes, making the check unsatisfiable by construction.
  2. A textual inverse also rewrites `var(--name)` occurrences that were **already present in the source artifact** — hand-authored artifacts legitimately emit `var()` (the `policy-router-builder.html.tmpl:18,27` precedent this issue cites elsewhere) — turning them into literals and diverging from the pre-lift body. That is a spurious exit-code-2 rejection of a perfectly valid lift.
  The check remains self-contained inside `templatize.py` — no render-engine participation, no new hook in `ArtifactTemplate`/`render_template`. What it actually proves is that the span application is correct and total; it deliberately does **not** prove CSS-context correctness (that is the guard's job) or theme correctness (that is the theme rule's job). The lifted template's *rendered* output is deliberately not byte-identical to the original artifact (it carries `var()` refs plus a `:root {}` block from `ll.theme_css`); that difference is the feature, not a regression.
- **Hard preconditions — no partial lift**: the body is lifted only if (a) the `[[= ll.theme_css =]]` stamp point can be placed (a `<head>` or existing `<style>` exists), and (b) the theme rule above is satisfiable. If either fails, nothing is rewritten, the manifest is untouched, everything is reported as `unlifted`, and the exit code is unchanged — a body with `var()` refs and no declarations must never reach `promote()`.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

1. Extract `find_token_literals(template_text, tokens) -> list[TokenLiteralMatch]` from `report_token_literals`'s scan loop, exposing `.start()`/`.end()` per match. Reimplement `report_token_literals` as an aggregation over it — its signature, return shape, and `TestReportTokenLiterals` all stay unchanged.
2. Add the CSS-value-position guard to `find_token_literals` (Decision Rules § CSS-context guard), with the `href="#dedede"` / `#face {` / `"#c0ffee"`-in-`<script>` test first. **Do this before any rewrite code exists** — it is the difference between a false positive being a warning line and being artifact corruption.
3. Add `--lift-tokens` (default off) to `add_templatize_parser`, threaded through `cli/artifact/__init__.py`. Everything below is reachable only under the flag.
4. Build the candidate map: invert `tokens.resolved` (loaded with an **explicit** `theme=dt_cfg.active_theme`, per Decision Rules § Theme selection), excluding `_`-prefixed names, then apply the alias-preference filter (Decision Rules § Ambiguous literal-to-token mapping) using the raw layered token data — not `resolved`, which has already erased the alias. Emit `var(--{name.replace(".", "-")})`. Test the recorded ambiguity cases from Codebase Research Findings directly (`#e8dcc4` lifts to `color.border.subtle`; `#fdfbf6` light stays unlifted with both semantic candidates reported).
5. Implement `lift_token_literals(spliced: bytes, tokens) -> tuple[bytes, list[TokenLiteralMatch], list[TokenLiteralMatch], list[tuple[int, int]]]` as a post-splice pass applying `(start, end, replacement)` spans in reverse order (`issues/anchor_sweep.py:59` model). Returns the lifted body, the lifted/unlifted match split, and the spans it wrote — the last is what step 7's inverse consumes.
6. Inject the stamp point — `<style>[[= ll.theme_css =]]</style>` into `<head>` (or `[[= ll.theme_css =]]` at the top of an existing `<style>`), plus `data-theme="<active_theme>"` on `<html>` — and set `manifest["theme"] = "design-tokens"`, so the refs resolve via `build_ll_namespace`'s `ll.theme_css` hook (`artifact_templates.py:311-318`). **Not `/*__THEMED_CSS_VARS__*/`**: `render_template` never calls `stamp_page_shell`, so that placeholder is inert (see Expected Behavior). Record the injected spans. Per Decision Rules § Hard preconditions, a body where the stamp point cannot be placed, or whose existing `data-theme` disagrees with the active theme, is **not lifted at all**.
7. Implement `verify_lift_reversible(lifted, pre_lift, lift_spans, stamp_spans)`: undo the recorded spans only — never a whole-body textual `var()`→literal substitution — and assert byte equality against the already-`verify_round_trip`-verified pre-lift body; failure routes to `rejected_dir`/exit code 2. Include a regression test where the *source artifact* already contains a `var(--color-surface-primary)`, which a textual inverse would falsely reject.
8. Extend `_write_unlifted_tokens_report` with a `"lifted"` list alongside `"unlifted"` and rewrite the hardcoded `_comment` (`templatize.py:701-709`), which currently asserts "Report-only — not rewritten." Leave `_report_unlifted_tokens`'s bare `except Exception` intact.
9. `python -m pytest scripts/tests/test_artifact_templatize.py scripts/tests/test_enh3035_artifact_template_kit.py -v` passes, and the full suite (`python -m pytest scripts/tests/`) is green.

_Coordinate-space note (resolved by step 4):_ `report_token_literals` scans the already-spliced `template_text` (post-`apply_regions`), whose match offsets do not correspond to `apply_regions`'s pre-splice `Region`/`RegionGroup` offsets. Keeping the lift as a post-splice pass means there is nothing to translate — the earlier "detect against pre-splice bytes or translate offsets" framing applied only to the rejected compose-into-`apply_regions` approach.

### Wiring Phase (revised)

- Update `docs/reference/CLI.md`'s "Design-token report (Phase C / FEAT-3316)" paragraph (~`:4593`) with the `--lift-tokens` flag, the `lifted`/`unlifted` report split, and the exit-code-2 path; note that the byte-exact round-trip guarantee holds with the flag off and is replaced by the two-stage check with it on.
- Update `docs/ARCHITECTURE.md:1031`'s "token lifting is report-only in v1 ... never rewriting them" sentence to describe both modes.
- Add the flag-off regression test asserting today's behavior is bit-for-bit preserved — this is the contract that keeps `fsm/persistence.py::promote_run_artifact`, `extract.py`, `render.py`, and `dashboard.py` out of scope.
- No changes to `scripts/little_loops/artifact_templates.py` or `scripts/little_loops/artifact_template_kit.py` are expected; if the implementation finds it needs one, that is a signal the design has drifted back toward the rejected render-hook approach.

## Impact

- **Priority**: P4 — nothing is blocked on it. `templatize` output is usable
  today; lifting makes it *themeable*, which is a quality improvement over
  the ENH-3035 baseline rather than a gap.
- **Effort**: Large — nine implementation steps across a CLI flag, a new
  span-splicing pass, a CSS-context guard, an alias-preference candidate
  filter, explicit theme handling, a span-tracked two-stage verification, a
  report schema change, and two doc updates, plus roughly a dozen new tests.
  Not the "expose spans and splice" Small the first revision implied.
- **Risk**: Medium-High. Three failure modes, none of which the reversibility
  check can see:
  1. The unguarded hex regex (Decision Rules § CSS-context guard) — a false
     positive silently corrupts a promoted artifact. Mitigated by landing the
     guard before the rewrite (step 2).
  2. Wrong stamp mechanism — an inert placeholder ships a colorless artifact
     while every span-level test still passes. Mitigated by the
     render-through-`render_template` test, which is the only assertion that
     actually exercises the mechanism end to end.
  3. Theme inversion (Decision Rules § Theme selection) — a dark artifact
     rendering with the light palette. Mitigated by the explicit `theme=`
     load plus the `data-theme` injection.
  `--lift-tokens` defaulting off bounds all three.
- **Breaking Change**: No, given `--lift-tokens` defaults off. It would be
  yes without the flag — the byte-exact round-trip guarantee is documented in
  `docs/ARCHITECTURE.md:1031` and `docs/reference/CLI.md:4593`, and
  `fsm/persistence.py::promote_run_artifact` depends on it with no opt-out.

## Scope

**In scope:**
- Colors only, matching `report_token_literals`'s v1 scope
  (`#rgb`/`#rgba`/`#rrggbb`/`#rrggbbaa`, `rgb()`/`rgba()`/`hsl()`/`hsla()`).
- Rewriting matched literals to `var(--...)` in CSS-value position only,
  under an opt-in `--lift-tokens` flag.
- Injecting the token-declaration block (`[[= ll.theme_css =]]` in a
  `<style>`, `data-theme="<active_theme>"` on `<html>`, and
  `manifest["theme"] = "design-tokens"`) so the emitted refs resolve — the
  rewrite and the stamp point land together or not at all.
- An alias-preference filter plus fail-closed remainder for ambiguous
  literal→name matches (Decision Rules).
- Explicit theme selection so a lifted artifact renders in the theme it was
  authored in.
- Two-stage verification: byte-exact round trip on the pre-lift body, then
  span-tracked reversibility of the lift.

## Scope Boundaries

**Out of scope:**
- Any change to `ArtifactTemplate`/`render_template` or the shared `.llat`
  render path (see Motivation § Rejected alternative).
- Non-color token namespaces (`space`, `radius`, `font`, bare numbers).
- Cross-notation color equivalence (`#ff0000` vs `rgb(255,0,0)`) — inherited
  from `_normalize_color_value`'s existing no-component-parsing rule.
- Changing default (flag-off) behavior in any way.

## Status

**Open** | Created: 2026-08-25 | Priority: P4

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

_Revised 2026-08-25 after pre-implementation review — supersedes the four bullets from the refine pass._
_Revised again 2026-08-25 after a second pre-implementation review (AC #2, #4, #5 corrected; #10–#12 added)._

1. With `--lift-tokens` **off** (the default), `ll-artifact templatize` is bit-for-bit identical to today: same template body, same byte-exact `verify_round_trip`, same `unlifted-tokens.json` `unlifted` list, same fail-open exit code. Covered by a dedicated regression test; every existing test in `TestReportTokenLiterals`, `TestCmdTemplatizeTokenReport`, and `TestCmdTemplatizeEndToEnd` passes **unmodified**.
2. With `--lift-tokens` **on**, a color literal in CSS-value position resolving to a single token (after the alias-preference filter) is rewritten in the spliced body to `var(--<dotted.name with . → ->)` — e.g. `var(--color-surface-primary)`, matching `render_as_css_vars_themed:703`'s mangling exactly. The body gains a `[[= ll.theme_css =]]` expression inside a `<style>`, `data-theme="<active_theme>"` on `<html>`, and `manifest["theme"] = "design-tokens"`. **Verified by rendering**: the test runs the lifted template through `render_template` and asserts the output carries the `--color-…` declarations, carries no residual `[[=` or `/*__THEMED_CSS_VARS__*/` text, and resolves each ref to the value the original artifact had.
3. A matched literal **outside** CSS-value position — `href="#dedede"`, an id selector `#face {`, `"#c0ffee"` inside `<script>` — is never rewritten and is still reported. Tested explicitly with token values chosen to collide with all three.
4. Verification is two-stage and both stages are tested: (a) `verify_round_trip` passes byte-exact on the pre-lift body, unchanged from today; (b) undoing the **recorded lift and stamp spans** on the lifted body reproduces the pre-lift body byte-for-byte. The inverse is span-tracked, never a whole-body textual `var()`→literal substitution — proven by a test where the source artifact already contains a `var(--color-surface-primary)` and the lift still succeeds. A failure in either stage routes to `rejected_dir` with exit code 2.
5. Candidate resolution runs the alias-preference filter first (prefer the semantic name whose raw value is an alias reference over the primitive it points at); if exactly one survives it is used, otherwise the literal is **not rewritten** and is reported in `unlifted` with all candidates. Tested against this profile's real collisions — `#e8dcc4` lifts to `color.border.subtle`, light `#fdfbf6` (two semantic aliases) does not lift. A raw candidate count > 1 alone must **not** block the lift; that rule blocks ~half of all colors on this repo's own profile.
6. `unlifted-tokens.json` keeps its filename and its `unlifted` key, and gains a `lifted` list recording what was rewritten; the `_comment` string no longer claims "Report-only — not rewritten."
7. `scripts/little_loops/artifact_templates.py` and `scripts/little_loops/artifact_template_kit.py` are unmodified by this issue.
8. `docs/reference/CLI.md` (~`:4593`) and `docs/ARCHITECTURE.md:1031` describe both modes; neither still states that token lifting is report-only.
9. `python -m pytest scripts/tests/` exits 0.
10. Tokens are loaded with an **explicit** `theme=` and the lifted body carries a matching `data-theme` attribute, so a lifted artifact re-renders in the theme it was authored in. Tested with `active_theme: dark`: the re-rendered artifact resolves to the dark palette, not the light `:root` values. A body whose existing `data-theme` disagrees with the active theme is left unlifted.
11. `_`-prefixed token names are excluded from the candidate map (mirroring `design_tokens.py:701-702`), so no emitted `var()` can reference an undeclared property. A test asserts every emitted `var(--x)` name appears as a `--x:` declaration in `render_as_css_vars_themed`'s output.
12. Lifting is all-or-nothing per body: if the `[[= ll.theme_css =]]` stamp point cannot be placed, or the theme precondition fails, nothing is rewritten, the manifest is untouched, and everything is reported as `unlifted`. No body carrying `var()` refs without their declarations can reach `promote()`.

## Session Log
- pre-implementation review (2nd) - 2026-08-25 - corrected the stamp mechanism (`stamp_page_shell` is not on the render path; use `[[= ll.theme_css =]]`), corrected var names to dotted-path `.`→`-` mangling, replaced the naive fail-closed ambiguity rule with an alias-preference filter after measuring 11/22 light and 12/22 dark values as ambiguous on the `warm-paper` profile, added an explicit theme-selection rule to prevent dark→light color inversion, made the reversibility inverse span-tracked (unsatisfiable and false-rejecting as a textual substitution), decided against the two-arg `var(--x, #lit)` fallback form, and added ACs #10–#12.
- pre-implementation review - 2026-08-25 - rejected the render-time un-lift hook (self-defeating), replaced byte-exact round trip with two-stage verification, added `--lift-tokens` default-off gating, added the mandatory CSS-context guard, resolved the ambiguity rule fail-closed, switched to a sibling span function over an `UnliftedToken` shape change, and filled in Impact.
- `/ll:wire-issue` - 2026-08-25T22:16:50 - `867cfaaa-2edf-4fc6-ad4a-9687e6d51d00.jsonl`
- `/ll:refine-issue` - 2026-08-25T21:45:32 - `b389fbd8-d752-4f90-8c29-d033923443fb.jsonl`
- `/ll:refine-issue` - 2026-08-25T20:20:19 - `c8f2587f-3ca1-4ca9-b1e5-e2886b741049.jsonl`
