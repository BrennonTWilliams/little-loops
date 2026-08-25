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
body, to a `var(--...)` reference at the literal's own byte span, and the
template gains the token block that defines those vars
(`manifest["theme"] = "design-tokens"` plus a `/*__THEMED_CSS_VARS__*/`
stamp point, so `artifact_template_kit.themed_css_vars`/`stamp_page_shell`
and `ll.theme_css` supply the declarations). With the flag off, behavior is
exactly today's: report-only, fail-open, byte-exact round trip.

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
(`artifact_templates.py:311-345`) that resolves `var(--surface-primary)`
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
- `scripts/little_loops/artifact_template_kit.py` — `themed_css_vars`/`stamp_page_shell` (`:18`, `:52`) fire only against a hardcoded `/*__THEMED_CSS_VARS__*/` placeholder and `data-theme="light"` attribute, and are a silent no-op on a body carrying neither. The lift pass injects that placeholder into the templatize-produced body and sets `manifest["theme"] = "design-tokens"`, so the existing stamping path starts firing instead of no-opping. The kit itself already does exactly what is needed — **no edit**.
- `scripts/little_loops/design_tokens.py` — `tokens.resolved` is the shared source of both the literal-matching inversion in `report_token_literals` and the `--name-with-dashes: value;` declarations `render_as_css_vars_themed` (`:688-707`) emits, so the `var(--...)` naming convention the lift emits already exists on this path. **No edit.**
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
- `scripts/little_loops/cli/artifact/policy_builder.py:61,68,91` — the one existing consumer of `themed_css_vars`/`stamp_page_shell`, for reference on how the stamp point is currently invoked; its no-op-on-missing-placeholder contract constrains how a new templatize call site must be shaped to actually fire.

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
- `scripts/tests/test_enh3035_artifact_template_kit.py` — covers `themed_css_vars`/`stamp_page_shell`.
- `scripts/tests/test_design_tokens.py` — covers `DesignTokens`/`.resolved`.

_Wiring pass added by `/ll:wire-issue` — revised for the default-off flag and the sibling-function split:_

**Existing tests that must keep passing unchanged** (the default-off flag is what buys this — if any of these needs editing, the flag gating is wrong):
- `scripts/tests/test_artifact_templatize.py::TestReportTokenLiterals` (`:995-1054`) — full dict equality against the three-key `UnliftedToken` shape. Preserved by adding `find_token_literals` as a **sibling** rather than a span field on `UnliftedToken`.
- `scripts/tests/test_artifact_templatize.py::TestCmdTemplatizeTokenReport` (`:1057-1212`), including `test_containment_forced_failure_still_promotes_exit_0` (`:1182-1212`) — the fail-open contract stays exactly as-is on the default (`--lift-tokens` off) path. The exit-code-2 behavior is additive, tested separately under the flag, not a bifurcation of this class.
- `scripts/tests/test_artifact_templatize.py::TestCmdTemplatizeEndToEnd.test_end_to_end_round_trip` (`:403-440`) and `TestApplyRegions` (`:208-325`) — byte-exact round trip is still the contract with the flag off.
- `scripts/tests/test_feat3036_artifact_templates.py`, `test_feat3310_artifact_extract.py`, `test_fsm_persistence.py`, `test_artifact_discover.py` — no render-engine change, so no edits expected.

**Existing test that changes by design:**
- `scripts/tests/test_enh3035_artifact_template_kit.py::TestKitAcceptsTemplatizedBody.test_templatized_body_with_baked_in_token_literal_stamps_without_error` (`:82-132`) — asserts `assert "#fdfbf6" in body` (`:124`) and `assert stamped == body` (`:132`), documenting that the literal "survived templatize unchanged." Keep this test as the **flag-off** case (it stays true) and add a flag-on sibling asserting the `var(--surface-primary)` form plus a non-no-op `stamp_page_shell`.

**New tests needed:**
- Two-stage verification (Decision Rules): pre-lift byte-exact round trip passes, then the inverse map applied to the lifted body reproduces the verified pre-lift body byte-for-byte.
- Unreversible lift → `rejected_dir` / exit code 2, under `--lift-tokens` only. Follow `TestApplyRegions`'s `pytest.raises(SpliceError, match=...)` pattern composed with `TestCmdTemplatizeEndToEnd`'s CLI-level `code == 2` assertions.
- **CSS-context guard (highest-value new coverage)**: an artifact carrying `href="#dedede"`, an id selector `#face {`, and `"#c0ffee"` inside a `<script>` string, where those values are also resolved token values — assert none are rewritten and all are still reported. Today these are harmless warning lines; after the rewrite an unguarded match is silent artifact corruption, and the two-stage verification will *not* catch it (the inverse map restores it cleanly).
- Ambiguous literal-to-token-name resolution (AC #5): >1 candidate ⇒ not rewritten, still reported. `test_non_injective_reports_all_candidate_names` (`:1005-1011`) covers only today's report-all behavior.
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
- Testing convention beyond `TestCmdTemplatizeEndToEnd`: a full-loop byte-identical assertion pattern also exists — run `templatize` to produce a `.llat/`, then run `render` against it, then compare `read_bytes()` of the rendered output to `read_bytes()` of the original artifact (not just `verify_round_trip(...) is None`) — `test_artifact_templatize.py:403-440`, `:1277-1292`.

### Types
- `UnliftedToken` (TypedDict, `templatize.py:616`): `{"literal": str, "candidate_names": list[str], "occurrences": int}` — carries no byte-offset/span data. **Leave this shape alone.** Add a new `TokenLiteralMatch` (`{"start": int, "end": int, "literal": str, "candidate_names": list[str]}`) returned by the new sibling function; `report_token_literals` aggregates matches into today's `UnliftedToken` shape unchanged.
- Report payload: `unlifted-tokens.json` keeps its filename and grows a sibling `"lifted"` list next to `"unlifted"` (rather than being renamed), so existing readers keyed on `"unlifted"` — including `TestCmdTemplatizeTokenReport` — keep working. The hardcoded `_comment` string (`templatize.py:701-709`), which currently states "Report-only — not rewritten, and the manifest does not set theme: design-tokens", must be rewritten to describe both modes.

### Signatures
- `report_token_literals(template_text: str, tokens: DesignTokens) -> list[UnliftedToken]` (`templatize.py:662`) — signature and return shape **unchanged**; reimplemented as an aggregation over the new sibling.
- New: `find_token_literals(template_text: str, tokens: DesignTokens) -> list[TokenLiteralMatch]` — the span-returning primitive (regex matches already carry `.start()`/`.end()`; today they are read for `.group(0)` only and discarded). This is also where the CSS-context guard lives (see Decision Rules).
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` (`templatize.py:474`) — the only span-splicing entry point in this module; consumes `Region`/`RegionGroup` spans, not literal-match spans.
- `themed_css_vars(config: object) -> str` (`artifact_template_kit.py:18`); `stamp_page_shell(template_text: str, *, active_theme: str, css_vars: str) -> str` (`artifact_template_kit.py:52`) — stamps only against a hardcoded `/*__THEMED_CSS_VARS__*/` placeholder and `data-theme="light"` attribute; a no-op on text without them.
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
- **Ambiguous literal-to-token mapping — resolved, fail-closed**: when `value_to_names` yields **more than one** candidate name for a literal, **do not rewrite it**; leave it as a literal and report it in `unlifted` with all candidates, as today. Rationale: no "canonical name" concept exists in `design_tokens.py`, neither established precedent supports a pick-first/alphabetical rule, and `text_utils.classify_file_ref`'s explicit `"ambiguous"` status (`text_utils.py:269-364`) is the closer precedent. Silently picking a candidate risks stamping a semantically wrong token name that renders identically today and diverges the moment the theme is edited — the exact failure this feature exists to prevent.
- **CSS-context guard — mandatory**: `_HEX_LITERAL_RE = r"#[0-9a-fA-F]+"` (`templatize.py:625`) has no word boundary and no context check. It matches `href="#dedede"`, an id selector `#face`, and `"#c0ffee"` in a JS string. Today a false positive is a harmless warning line; **under rewriting it is silent artifact corruption**, and the reversibility check will not catch it because the inverse map restores it cleanly. Rewrites therefore fire **only in CSS-value position** — inside a `<style>` element or a `style="…"` attribute, after a `:` and before a `;`, `}`, `)`, or the attribute's closing quote. A match outside CSS-value position is reported (today's behavior) and never rewritten.
- **Scope**: the rewrite inherits `report_token_literals`'s v1 scope verbatim — **colors only** (`#rgb`/`#rgba`/`#rrggbb`/`#rrggbbaa` plus `rgb()`/`rgba()`/`hsl()`/`hsla()`). `space`, `radius`, `font`, and bare-number token namespaces are out of scope and are neither reported nor rewritten.
- **Reversibility (replaces "round-trip compatibility")**: a lift is valid iff applying the inverse map (`var(--name)` → the token's resolved value for the active theme) to the lifted body reproduces the verified pre-lift body byte-for-byte. This is a self-contained textual check inside `templatize.py` — no render-engine participation, no new hook in `ArtifactTemplate`/`render_template`. The lifted template's *rendered* output is deliberately not byte-identical to the original artifact (it carries `var()` refs plus a `:root {}` block from `ll.theme_css`); that difference is the feature, not a regression.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-25 — based on codebase analysis:_

1. Extract `find_token_literals(template_text, tokens) -> list[TokenLiteralMatch]` from `report_token_literals`'s scan loop, exposing `.start()`/`.end()` per match. Reimplement `report_token_literals` as an aggregation over it — its signature, return shape, and `TestReportTokenLiterals` all stay unchanged.
2. Add the CSS-value-position guard to `find_token_literals` (Decision Rules § CSS-context guard), with the `href="#dedede"` / `#face {` / `"#c0ffee"`-in-`<script>` test first. **Do this before any rewrite code exists** — it is the difference between a false positive being a warning line and being artifact corruption.
3. Add `--lift-tokens` (default off) to `add_templatize_parser`, threaded through `cli/artifact/__init__.py`. Everything below is reachable only under the flag.
4. Implement `lift_token_literals(spliced: bytes, tokens) -> tuple[bytes, list[TokenLiteralMatch], list[TokenLiteralMatch]]` as a post-splice pass applying `(start, end, replacement)` spans in reverse order (`issues/anchor_sweep.py:59` model). Skips ambiguous (>1 candidate) matches per Decision Rules; returns lifted body plus the lifted/unlifted match split.
5. Inject the `/*__THEMED_CSS_VARS__*/` stamp point into the body's `<style>`/`<head>` and set `manifest["theme"] = "design-tokens"`, so the emitted `var(--...)` refs resolve via the existing `build_ll_namespace` `ll.theme_css` path (`artifact_templates.py:311-318`). A body where the stamp point cannot be placed is not lifted.
6. Implement `verify_lift_reversible(lifted, pre_lift)`: apply the inverse map and assert byte equality against the already-`verify_round_trip`-verified pre-lift body; failure routes to `rejected_dir`/exit code 2.
7. Extend `_write_unlifted_tokens_report` with a `"lifted"` list alongside `"unlifted"` and rewrite the hardcoded `_comment` (`templatize.py:701-709`), which currently asserts "Report-only — not rewritten." Leave `_report_unlifted_tokens`'s bare `except Exception` intact.
8. `python -m pytest scripts/tests/test_artifact_templatize.py scripts/tests/test_enh3035_artifact_template_kit.py -v` passes, and the full suite (`python -m pytest scripts/tests/`) is green.

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
- **Effort**: Large — six implementation steps across a CLI flag, a new
  span-splicing pass, a CSS-context guard, a two-stage verification, a report
  schema change, and two doc updates, plus roughly six new tests. Not the
  "expose spans and splice" Small the first revision implied.
- **Risk**: Medium-High — the dominant risk is the unguarded hex regex
  (Decision Rules § CSS-context guard), where a false positive silently
  corrupts a promoted artifact and passes the reversibility check. Mitigated
  by landing the guard before the rewrite (step 2) and by `--lift-tokens`
  defaulting off. Secondary risk: a lifted body whose stamp point lands in
  the wrong place produces a valid-but-colorless artifact.
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
- Injecting the token-declaration block (`/*__THEMED_CSS_VARS__*/` +
  `manifest["theme"] = "design-tokens"`) so the emitted refs resolve — the
  rewrite and the stamp point land together or not at all.
- A fail-closed rule for ambiguous literal→name matches (skip + report).
- Two-stage verification: byte-exact round trip on the pre-lift body, then
  textual reversibility of the lift.

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

1. With `--lift-tokens` **off** (the default), `ll-artifact templatize` is bit-for-bit identical to today: same template body, same byte-exact `verify_round_trip`, same `unlifted-tokens.json` `unlifted` list, same fail-open exit code. Covered by a dedicated regression test; every existing test in `TestReportTokenLiterals`, `TestCmdTemplatizeTokenReport`, and `TestCmdTemplatizeEndToEnd` passes **unmodified**.
2. With `--lift-tokens` **on**, a color literal in CSS-value position matching exactly one resolved design token is rewritten in the spliced body to `var(--<name>)`, and the body gains the `/*__THEMED_CSS_VARS__*/` stamp point with `manifest["theme"] = "design-tokens"`, so rendering emits both the refs and their `:root {}` declarations.
3. A matched literal **outside** CSS-value position — `href="#dedede"`, an id selector `#face {`, `"#c0ffee"` inside `<script>` — is never rewritten and is still reported. Tested explicitly with token values chosen to collide with all three.
4. Verification is two-stage and both stages are tested: (a) `verify_round_trip` passes byte-exact on the pre-lift body, unchanged from today; (b) applying the inverse map to the lifted body reproduces the pre-lift body byte-for-byte. A failure in either routes to `rejected_dir` with exit code 2.
5. An ambiguous match (`value_to_names` yields >1 candidate) is **not rewritten** and is reported in `unlifted` with all candidates — tested, not left to arbitrary selection.
6. `unlifted-tokens.json` keeps its filename and its `unlifted` key, and gains a `lifted` list recording what was rewritten; the `_comment` string no longer claims "Report-only — not rewritten."
7. `scripts/little_loops/artifact_templates.py` and `scripts/little_loops/artifact_template_kit.py` are unmodified by this issue.
8. `docs/reference/CLI.md` (~`:4593`) and `docs/ARCHITECTURE.md:1031` describe both modes; neither still states that token lifting is report-only.
9. `python -m pytest scripts/tests/` exits 0.


## Session Log
- pre-implementation review - 2026-08-25 - rejected the render-time un-lift hook (self-defeating), replaced byte-exact round trip with two-stage verification, added `--lift-tokens` default-off gating, added the mandatory CSS-context guard, resolved the ambiguity rule fail-closed, switched to a sibling span function over an `UnliftedToken` shape change, and filled in Impact.
- `/ll:wire-issue` - 2026-08-25T22:16:50 - `867cfaaa-2edf-4fc6-ad4a-9687e6d51d00.jsonl`
- `/ll:refine-issue` - 2026-08-25T21:45:32 - `b389fbd8-d752-4f90-8c29-d033923443fb.jsonl`
- `/ll:refine-issue` - 2026-08-25T20:20:19 - `c8f2587f-3ca1-4ca9-b1e5-e2886b741049.jsonl`
