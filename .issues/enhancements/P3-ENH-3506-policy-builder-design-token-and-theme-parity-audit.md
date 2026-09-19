---
id: ENH-3506
type: ENH
title: Policy builder design-token and theme parity audit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-18'
captured_at: '2026-09-18T23:50:20Z'
relates_to:
- ENH-3500
- ENH-3491
- EPIC-3493
program_design_not_applicable: true
---

# ENH-3506: Policy builder design-token and theme parity audit

## Summary

Verify that the policy-router builder's shipped authoring modes consume design tokens correctly under both `light` and `dark` themes, by diffing the rendered CSS custom-property blocks against the active token profile and flagging hardcoded values that bypass a token. Split from ENH-3500 (Scope §1) on 2026-09-18 so it can run now: ENH-3500's remaining holistic UX audit is blocked on FEAT-3505, and nothing here depends on it. Deliverable is audit findings filed as follow-up issues, not fixes.

## Current Behavior

Design-token and dark/light usage in the builder is unverified against real rendering: `test_policy_builder_renders_byte_identically_to_golden_fixture` only catches byte-level drift from a golden fixture, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees as a stopgap so that test doesn't false-fail on a missing token file — it does not verify the templates consume tokens correctly. `ll-verify-design-tokens`' `lint_profile()` checks theme-JSON completeness only and never reads the templates.

## Expected Behavior

Design-token and dark/light theme usage in the shipped builder template is confirmed correct (not just passing the golden-fixture byte-match), with each confirmed drift filed as a follow-up ENH carrying the file/selector and expected vs. actual value. The findings also state whether the `worktree_utils.py` stopgap is still needed and whether `ll-doctor`'s design-token check needs a template-aware companion.

## Motivation

There is a concrete signal that token usage is fragile: ENH-3491's notes flagged that `test_policy_builder_renders_byte_identically_to_golden_fixture` false-fails on degraded design tokens, and `worktree_utils.py:687-713` exists specifically as a stopgap for that. That is a workaround for a symptom, not a check on actual token usage in the builder templates. The audit is boundable today and independent of the connected-page work, so it should not sit behind ENH-3500's FEAT-3505 blocker.

## Proposed Solution

Audit, not a code change in itself. Render once with `ll-artifact policy-builder` (mode switching is client-side, and one render embeds both themes' CSS blocks), parse the `:root{...}` (light) and `[data-theme=dark]{...}` (dark) blocks, and diff each against `.ll/design-tokens/profiles/<active-profile>/` resolved values. Flag any hardcoded color/spacing value in the template's inline `<style>` that bypasses a token, and any `var(--token, <fallback>)` whose token never resolves (silently relying on the fallback). File one follow-up ENH per confirmed drift, tagged `relates_to: [ENH-3506, ENH-3500]`.

No emitted-YAML or runtime-behavior change is in scope — only presentation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- A single `ll-artifact policy-builder` render already embeds both themes' resolved CSS in one output file (`:root{...}` for light, `[data-theme=dark]{...}` for dark) — `themed_css_vars()`/`render_as_css_vars_themed()` (`scripts/little_loops/artifact_template_kit.py:18-49`, `scripts/little_loops/design_tokens.py:773-792`) resolve and stamp both theme's values unconditionally, regardless of `config.design_tokens.active_theme`. No `--theme` CLI flag exists (`scripts/little_loops/cli/artifact/__init__.py:138-148` defines only `-o/--output`), and none is needed for token-value comparison: one rendered file already contains both blocks to parse and diff against `.ll/design-tokens/profiles/<active-profile>/themes/{light,dark}.json` (merged over `semantic.json`/`typography.json`/`spacing.json`/`primitives.json` per `_load_profile_from_root`, `design_tokens.py:363-402`).
- No existing tool checks template-vs-token consumption (`scripts/little_loops/cli/verify_design_tokens.py::lint_profile()` only checks theme-JSON-to-theme-JSON key completeness, never reading the `.html.tmpl`/`.mjs` files), and no existing test renders the template under both light and dark and diffs the two — this audit's Phase 1 has no reusable checker or snapshot precedent to extend, only the single-render byte-identical golden fixture.

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Conventions in force: template tokens are consumed only via `var(--name, fallback)` with one generation-time stamp point (`stamp_page_shell`); the only other template doing this is `templates/dashboard.llat/template.html.j2`, which uses a *different* token vocabulary (`--color-background`, `--color-text`, `--font-family-sans`) and dark-valued fallbacks — two contested vocabularies, so "expected token name" must be defined against the resolver's output, not against either template.
- Follow-up filing goes through `ll-issues create --type ENH --title … --body-file - --json` (`skills/capture-issue/SKILL.md` §4); `create` has no `--relates-to`, so `relates_to: [ENH-3506, ENH-3500]` is set afterward with `ll-issues link <ID> --relates-to …` (`cli/issues/link.py`). Given the pre-check above, the 15 unresolved names likely share one root cause; the audit should decide whether to file per-name or grouped drift issues.
- Any permanent regression coverage would extend the existing real-profile precedent (`test_themed_css_vars_is_separately_callable`), and must isolate config (`monkeypatch.chdir(tmp_path)` style, as `TestKitAcceptsTemplatizedBody` does) rather than reading ambient `.ll/`.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the single shared HTML template whose inline `<style>` block consumes design tokens via `var(--token-name, <fallback>)` (lines 18-27, 65, 111-113); primary target for token/theme audit
- `scripts/little_loops/templates/policy_builder_core.mjs` — the single shared, DOM-free JS module implementing all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`) via client-side `<select id="mode-switch">`; has zero token/CSS-variable references and only toggles the `data-theme` attribute, so it is out of scope for the token audit itself (FEAT-3488's additions extended, and FEAT-3505's are expected to extend, these same two shared files rather than adding per-mode fragments)
- No source files are expected to change for the audit itself; any drift found is filed as a follow-up ENH rather than fixed inline here

### Dependent Files (Callers/Importers)
- `scripts/little_loops/worktree_utils.py:687-713` — copies `.ll/design-tokens` into epic-verify worktrees as a stopgap for the golden-fixture test's token dependency; this issue determines whether that stopgap is still needed once token usage is verified correct
- `.ll/design-tokens/profiles/<active-profile>/{primitives.json, semantic.json, typography.json, spacing.json, themes/{light,dark}.json}` — the token source of truth the audit diffs rendered output against (theme-independent `semantic`/`typography`/`spacing` layers merged with the theme-specific `themes/<theme>.json` override, resolved against `primitives.json`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/artifact_templates.py:315-317` — `build_ll_namespace()` calls `themed_css_vars()` when a template manifest declares `theme: design-tokens`; generic artifact-templating path (not policy-builder-specific — policy-builder calls `themed_css_vars` directly via `policy_builder.py:68`), but a future fix to `themed_css_vars()` itself would ripple here too [Agent 1 finding]
- `scripts/little_loops/cli/artifact/templatize.py:945-949` — `_themed_css_vars()`, a "thin patchable wrapper" over `themed_css_vars()` used by `ll-artifact templatize`'s lift tooling; same generic-consumer caveat as above [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:1095-1105` — `_full_design_tokens_check()` (`@register_full_check`) is a live `ll-doctor` gate calling `lint_profiles_dir()` (built on `lint_profile()`, the same theme-JSON-completeness checker that never reads `.html.tmpl`/`.mjs`); it surfaces "half-flipped themes" as an error-severity check, separate from the epic-verify golden-fixture gate already listed above — audit findings should note whether this doctor check also needs a template-aware companion [Agent 1 + Agent 2 finding]


### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; it fixed findings inline rather than filing follow-ups, so it is a scope baseline, not a filing precedent
- Follow-up filing convention: call `ll-issues create` directly (post-FEAT-2947 convention, `skills/capture-issue/SKILL.md:266-275`)

### Tests
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — the existing golden-fixture guard this audit's findings should either confirm covers real token usage or supplement
- `scripts/tests/test_policy_builder_corpus.py`, `scripts/tests/test_policy_builder_emit.py` — existing coverage for builder-emitted output; no changes expected unless the audit finds drift requiring a new regression test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py::TestRenderAsCssVarsThemed` (lines 635-687) — unit tests of `render_as_css_vars_themed()` against synthetic tmp-dir tokens; pins the exact CSS block delimiters (`:root {`, `[data-theme=dark] {`) the audit's parser needs, but never renders the real template or diffs against the real active profile — partial precedent only [Agent 3 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_themed_css_vars_is_separately_callable` (lines 31-40) — the one existing test that calls the themed-CSS path against this repo's real active profile (`warm-paper` + `dark`), but asserts only block presence, not value-level parity with source JSON — closest existing precedent to extend if Phase 1 becomes permanent regression coverage [Agent 3 finding]
- `scripts/tests/test_verify_design_tokens.py::TestLintProfile` (lines 80-133) — confirms `lint_profile()` checks theme-JSON-to-theme-JSON completeness only and never reads `.html.tmpl`/`.mjs`, substantiating the issue's own gap claim [Agent 3 finding]

### Documentation
- N/A — this issue produces an audit report and follow-up issues, not doc changes

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `#### ll-artifact policy-builder` — prose claims the page "honors the project's configured `active_theme`" via `load_design_tokens`/`render_as_css_vars_themed`; if the audit confirms token/theme drift, this section's claim needs checking and correcting as part of the filed follow-up issue, not this one [Agent 2 finding]
- `docs/guides/POLICY_ROUTER_GUIDE.md` (section preceding "### Issue Lifecycle Mode") — same "stamped from this project... honors active_theme" claim; same follow-up-issue caveat [Agent 2 finding]

### Configuration
- N/A or list config files

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1974-1983` — `design_tokens.active` (profile selector, default `"default"`) is the key the audit must diff against (`.ll/design-tokens/profiles/<active>/`), distinct from `design_tokens.active_theme` (default `"dark"`), which only sets the initial `data-theme` attribute and does not gate which theme's values get rendered — both light and dark CSS blocks are always rendered from the one active profile [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1989-1994` — `design_tokens.source` (`"profile"` vs `"design_md"`): when `"design_md"`, `themed_css_vars()` short-circuits so the dark block equals the light block by design — the audit's diff logic must not flag this degenerate case as drift [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- No per-mode template fragment files exist. `scripts/little_loops/templates/policy-router-builder.html.tmpl` (one shared HTML template) plus `scripts/little_loops/templates/policy_builder_core.mjs` (one shared, DOM-free JS module) implement all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`); mode switching happens client-side via `<select id="mode-switch">` inside the single template, not via separate per-mode files. `policy_builder_core.mjs` has zero token/CSS-variable references (confirmed by grep for `--color`/`--space`/`--radius`/`--typography`/`--font`/`getComputedStyle`/`setProperty`) — it only toggles the `data-theme` attribute string.
- Token consumption mechanism: the template's inline `<style>` block references tokens exclusively via CSS `var(--token-name, <hardcoded-fallback>)` (e.g. `policy-router-builder.html.tmpl:18-27,65,111-113`). The placeholder `/*__THEMED_CSS_VARS__*/` (line 9) is where resolved CSS is stamped in once, at generation time, by `stamp_page_shell()` (`scripts/little_loops/artifact_template_kit.py:52-71`) — there is no runtime fetch or browser-side token lookup.
- Render entry point: `cmd_policy_builder()` in `scripts/little_loops/cli/artifact/policy_builder.py` (invoked via `ll-artifact policy-builder`, subparser at `scripts/little_loops/cli/artifact/__init__.py:138-148`, which defines only `-o/--output` — no theme-selecting flag exists anywhere in the codebase).
- A single render already embeds BOTH themes' resolved CSS in one output file: `themed_css_vars(config)` (`artifact_template_kit.py:18-49`) loads `theme="light"` and `theme="dark"` token sets independently and `render_as_css_vars_themed()` (`scripts/little_loops/design_tokens.py:773-792`) emits one `:root{...}` block (light) and one `[data-theme=dark]{...}` block (dark) into the same file. `config.design_tokens.active_theme` only selects which block the default (attribute-less) `<html>` state matches; it does not gate which theme's tokens get rendered.
- Actual token file layout differs from a literal `.ll/design-tokens/<theme>.json` per theme: it is `.ll/design-tokens/profiles/<active-profile>/{primitives.json, semantic.json, typography.json, spacing.json, themes/<theme>.json}` (config-schema.json:1945-1994; `_load_profile_from_root`, `design_tokens.py:363-402`). `themes/<theme>.json` supplies only the theme-specific override layer, merged over the theme-independent `semantic`/`typography`/`spacing` files and resolved against `primitives.json`.
- No existing tool checks template-vs-token consumption. `scripts/little_loops/cli/verify_design_tokens.py::lint_profile()` checks theme-JSON-to-theme-JSON completeness (`semantic.json` keys vs `themes/*.json` keys) only — it never reads `policy_builder_core.mjs` or `policy-router-builder.html.tmpl`. No headless-browser/DOM rendering harness (playwright/puppeteer/jsdom) exists in the repo; the only JS test (`scripts/tests/js/policy_validator.test.mjs`) runs `policy_builder_core.mjs` under plain `node --test` as a DOM-free module.
- No existing test renders the template twice (once per theme) and diffs; the golden-fixture test (`test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`) calls `cmd_policy_builder()` exactly once, under whichever `active_theme` the ambient project config resolves to, and does not override `Path.cwd()` — it always reads whatever `.ll/design-tokens/` and `.ll/ll-config.json` sit at the process cwd.

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Pre-check on the real active profile (`warm-paper`, this checkout) finds substantial drift already.** Calling `themed_css_vars(BRConfig(Path.cwd()))` yields 85 declared custom properties; `policy-router-builder.html.tmpl` references 18 distinct `var(--…)` names, of which only 3 resolve (`--color-action-primary`, `--color-surface-raised`, `--color-text-primary`). The other 15 never resolve and always fall back to their hardcoded literal: `--color-surface-base`, `--color-surface-sunken`, `--color-text-on-sunken`, `--color-border-default`, `--color-action-primary-text`, `--color-status-{success,warning,error,info}-{bg,text}`, `--typography-font-family-{base,mono}`. Because the template carries no `[data-theme=dark]` override of its own, an unresolved name renders its light-valued fallback in **both** themes — the golden-fixture test cannot see this because it only byte-compares one render.
- Naming rule (evidence: `design_tokens.py::render_as_css_vars_themed`, `_flatten`): CSS name = `--` + dotted token key with `.`→`-`. The profiles emit `color.surface.{primary,secondary,raised}`, `color.text.*`, `color.border.{subtle,strong}`, `color.action.{primary,…}`, and `font.family.*` (→ `--font-family-*`, not `--typography-font-family-*`). There is no `color.status.*` group in `.ll/design-tokens/profiles/warm-paper` or the packaged profiles (grep under `scripts/little_loops/templates/design-tokens` returns 0). Whether the fix is renaming template refs or adding tokens to the profiles is a decision for the follow-up issues, not this audit.
- `themed_css_vars()` emits sorted, fully-resolved declarations, two-space indented, as `:root {` … `}` then `[data-theme=dark] {` … `}` (dark scope unquoted); keys starting with `_` are skipped; both blocks are full sets, not deltas. Returns the literal empty-block pair when `load_design_tokens()` is `None`; when `light.source == "design_md"`, dark is the same object as light.
- Reusable, already-scriptable pieces (no new render harness needed): `render_policy_builder_html(config)` (`cli/artifact/policy_builder.py`) returns the HTML string without writing a file; `load_design_tokens(config, theme=)` exposes `DesignTokens.resolved` (`dict[str, str]`); `templatize.py` (`_check_lift_preconditions`, `verify_lift_renders`) already does set-difference of emitted vs. declared var names, but on a templatize-time set, not on a parsed template.
- Correction to earlier citation: `render_policy_builder_html` is where `themed_css_vars` is called (`policy_builder.py:79` per code graph), not `:68`. The `stamp_page_shell` call is at `:114`.
- Template hardcodes outside `var()`: radii (8/6/4px), `1px`/`2px` borders, rem paddings/gaps, font-weights, `opacity`, `max-height`. Fallbacks themselves are literals and are internally inconsistent — the same token falls back to different values (`--color-surface-base`: `#ffffff` vs `#fff`; `--color-border-default`: `#d0d0d0` vs `#ccc`). Spacing/radius have no token references at all, so "spacing bypasses a token" needs a decision on whether the profile's `space.*`/`radius.*` groups are in audit scope.
- `.ll/design-tokens/` is gitignored, and ENH-3441 (done) made `load_design_tokens` fall back to packaged profiles when it is absent (`_resolve_packaged_profile_root`). That weakens the original rationale for the `worktree_utils.py:687-713` copy (comment there calls it a BUG-3370 "stopgap"); the audit should decide whether it is now redundant. Note the golden test still reads ambient cwd config (no `chdir`), so the fixture is machine-config-dependent.
- Stale comment: `design_tokens.py` refers to `artifact_template_kit._cached_themed_tokens`, which does not exist.

## Implementation Steps

1. Enumerate the design tokens `policy-router-builder.html.tmpl`'s inline `<style>` block references via `var(--token-name, <fallback>)`; confirm each resolves through `.ll/design-tokens/profiles/<active-profile>/` (merged `semantic.json`/`typography.json`/`spacing.json` + `themes/<theme>.json`, resolved against `primitives.json`) rather than relying on the hardcoded fallback.
2. Run a single `ll-artifact policy-builder` render (mode switching is client-side, so one render covers all three authoring modes); parse the output's two embedded CSS blocks (`:root{...}` for light, `[data-theme=dark]{...}` for dark, stamped in by `stamp_page_shell()`) and diff each block's resolved values against the corresponding theme's expected token values.
3. File one follow-up ENH per confirmed token/theme drift, with the specific file/selector and expected vs. actual value.
4. State in the findings whether the `worktree_utils.py:687-713` stopgap is still needed and whether `_full_design_tokens_check()` needs a template-aware companion; close this issue once findings are filed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Diff against `.ll/design-tokens/profiles/<config.design_tokens.active>/` — the `active` profile key, not `active_theme` (which only sets the default `data-theme` attribute, not which values render)
- Special-case `design_tokens.source == "design_md"` in the diff logic — `themed_css_vars()` short-circuits so the dark block equals the light block by design in that mode; do not flag it as drift
- Note `scripts/little_loops/cli/doctor.py::_full_design_tokens_check()` as a related-but-insufficient gate (theme-JSON completeness only, same as `lint_profile()`) — audit findings should state whether it needs a template-aware companion alongside the golden-fixture gate
- If drift is confirmed, also flag `docs/reference/CLI.md` `#### ll-artifact policy-builder` and `docs/guides/POLICY_ROUTER_GUIDE.md` for correction in the filed follow-up issue — both currently assert the theming behavior works correctly

## Impact

- **Priority**: P3 - polish/consistency work; the token-drift stopgap in `worktree_utils.py` already masks the symptom this audit targets
- **Effort**: Small-Medium - one render, two CSS blocks, one template's `<style>` block; fully boundable now
- **Risk**: Low - audit-only, no source changes in this issue itself
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: token/theme parity audit of the shipped builder template under `light` and `dark`; filing follow-ups for drift
- **Out of scope**: information hierarchy, empty/error states, and cross-mode consistency (ENH-3500); FEAT-3505's connected-page surface (audited under ENH-3500 once it lands — if it introduces new token references, ENH-3500's pass covers them); fixing any drift found; any change to emitted YAML or runtime behavior

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-18 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-19T00:47:41 - `304eba96-751f-4059-9328-1fc1b29cacd2.jsonl`
