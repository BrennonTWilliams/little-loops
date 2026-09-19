---
id: ENH-3506
type: ENH
title: Policy builder design-token and theme parity audit and fix
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-18'
captured_at: '2026-09-18T23:50:20Z'
blocks:
- FEAT-3505
relates_to:
- ENH-3500
- ENH-3491
- EPIC-3493
program_design_not_applicable: true
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3506: Policy builder design-token and theme parity audit and fix

## Summary

Verify that the policy-router builder's shipped authoring modes consume design tokens correctly under both `light` and `dark` themes, by diffing the rendered CSS custom-property blocks against the active token profile and flagging hardcoded values that bypass a token. Split from ENH-3500 (Scope §1) on 2026-09-18 so it can run now: ENH-3500's remaining holistic UX audit is blocked on FEAT-3505, and nothing here depends on it. Rescoped 2026-09-19 from audit-only to audit **and fix**: the refine pre-check below already established the unresolved-token defect (15 of the template's 18 `var(--…)` names never resolve, re-verified 2026-09-19), so filing up to 15 follow-ups would cost more than fixing. Deliverables are the corrected template and profiles, compatibility behavior for existing token sources, permanent parity/readability regression coverage, an isolated golden fixture, and the two verdicts (worktree stopgap, `ll-doctor` companion). Sequenced **before FEAT-3505** so its new connected UI is built on resolving token names and the golden fixture is regenerated serially, not concurrently.

## Current Behavior

Design-token and dark/light usage in the builder is unverified against real rendering: `test_policy_builder_renders_byte_identically_to_golden_fixture` only catches byte-level drift from a golden fixture, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees as a stopgap so that test doesn't false-fail on a missing token file — it does not verify the templates consume tokens correctly. `ll-verify-design-tokens`' `lint_profile()` checks theme-JSON completeness only and never reads the templates.

## Expected Behavior

Design-token and dark/light theme usage in the shipped builder template is correct (not just passing the golden-fixture byte-match): for each complete packaged profile, every template `var(--name, …)` reference is declared in both rendered theme blocks with the expected resolved value. Foreground/background pairs remain readable; existing mirrors and partial/disabled sources have defined, tested compatibility behavior. Regression tests enforce these requirements. The findings also state whether the `worktree_utils.py` stopgap is still needed and whether `ll-doctor`'s design-token check needs a template-aware companion.

## Motivation

There is a concrete signal that token usage is fragile: ENH-3491's notes flagged that `test_policy_builder_renders_byte_identically_to_golden_fixture` false-fails on degraded design tokens, and `worktree_utils.py:687-713` exists specifically as a stopgap for that. That is a workaround for a symptom, not a check on actual token usage in the builder templates. The audit is boundable today and independent of the connected-page work, so it should not sit behind ENH-3500's FEAT-3505 blocker.

## Proposed Solution

### Fix (rescoped 2026-09-19)

1. **Rename template refs to existing semantic tokens** (CSS name = `--` + dotted key with `.`→`-`): `--color-surface-base` → `--color-surface-primary`; `--color-surface-sunken` → `--color-surface-secondary`; `--color-text-on-sunken` → `--color-text-secondary`; `--color-border-default` → the appropriate `--color-border-{subtle,strong}` for the component; `--typography-font-family-base` → `--font-family-body`; `--typography-font-family-mono` → `--font-family-mono`. Choose borders by their role, not incidental fallback spelling. Normalize equivalent fallback literals while preserving readable foreground/background pairs.
2. **Add paired action and status colors** to `semantic.json` plus `themes/{light,dark}.json` in every packaged profile (`default`, `editorial-mono`, `warm-paper`) and this checkout's `.ll/design-tokens/` mirror. Keep `--color-action-primary-text` and introduce `color.action.primary-text`, explicitly paired with `color.action.primary`; do not alias it blindly to `color.text.inverse`. Review measured that proposed inverse mapping at 2.38:1 in editorial-mono dark and 4.17:1 in warm-paper dark. Add `color.status.{success,warning,error,info}.{bg,text}` and keep the template's corresponding names. Require at least 4.5:1 contrast for normal text on primary buttons, status messages, YAML output, and winning-rule highlights across all six profile/theme combinations. Check the actual inherited foreground on `.rule-winner`, not just the status token pair. `test_ambient_mirror_matches_packaged_profiles` and `lint_profile()` theme completeness must stay green.
3. **Define compatibility for existing consumers before changing tokens.** Local mirrors take precedence and are not merged with newly packaged keys. Implement either a non-destructive migration or theme-aware fallback behavior for missing action/status tokens; record the selected approach and any required upgrade command in Findings and user documentation. Preserve existing custom values. Test a pre-change mirror missing the new keys, plus partial `DESIGN.md` and disabled-token configurations. Scope full declaration parity to complete packaged profiles; fallback configurations must remain readable without pretending to supply a complete token set.
4. **Make native controls follow the selected theme.** Set `color-scheme` explicitly for light and dark `data-theme` states instead of leaving `light dark` to the OS preference. Verify initial configured theme and toggling with an opposing OS preference, preserving the existing stored-toggle → configured-theme → OS precedence.
5. **Permanent regression coverage:** extract template `var(--x` references, assert each is declared in both rendered theme blocks for every packaged profile, and compare emitted values with `load_design_tokens(config, theme=...).resolved`. Isolate config (`monkeypatch.chdir(tmp_path)` + a local config helper) and exercise both packaged fallback and freshly materialized mirrors. Do not require every light/dark value to differ: fonts and other shared values legitimately match. Test degraded sources separately; branch on the returned `DesignTokens.source`, since `source: auto` can resolve to `design_md`, whose two blocks intentionally match. Add contrast checks for the paired colors and rendered-style/visual checks for inherited colors and native controls.
6. **Isolate the golden test before regenerating its fixture.** Pin profile, active theme, token source, and other environment-dependent render inputs (including catalog resolution/config) in the test; use the same setup for regeneration. Verify the intended changes before overwriting (BUG-2303 advisory), then regenerate once. Demonstrate that ambient config/mirror changes do not affect the golden comparison. Correct documentation of the resulting theme and fallback behavior.
7. **Record the two verdicts.** Assess worktree-copy necessity with mirror-present and mirror-absent verification after golden isolation; token-name correctness alone does not establish that the copy is redundant. Record whether `ll-doctor` needs a template-aware companion, but implement any new doctor companion separately. Spacing/radius tokenization remains out of scope.

### Verification method

Render through `render_policy_builder_html(config)` (shared by CLI and served output). One render embeds both themes; parse the stamped `:root` and `[data-theme=dark]` custom-property blocks and compare against independently loaded resolved values for the selected profile/theme. Exercise the three authoring modes visually in both themes, including buttons, status messages, winning-rule highlights, YAML output, and native controls. The unresolved-name pre-check is complete; value, contrast, compatibility, and browser verification remain implementation deliverables.

Fix in-scope drift here. File follow-ups only for excluded work, tagged `relates_to: [ENH-3506, ENH-3500]`. No emitted-YAML or policy execution behavior change is in scope; theme presentation and compatibility behavior are explicitly included.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- A single `ll-artifact policy-builder` render already embeds both themes' resolved CSS in one output file (`:root{...}` for light, `[data-theme=dark]{...}` for dark) — `themed_css_vars()`/`render_as_css_vars_themed()` (`scripts/little_loops/artifact_template_kit.py:18-49`, `scripts/little_loops/design_tokens.py:773-792`) resolve and stamp both theme's values unconditionally, regardless of `config.design_tokens.active_theme`. No `--theme` CLI flag exists (`scripts/little_loops/cli/artifact/__init__.py:138-148` defines only `-o/--output`), and none is needed for token-value comparison: one rendered file already contains both blocks to parse and diff against `.ll/design-tokens/profiles/<active-profile>/themes/{light,dark}.json` (merged over `semantic.json`/`typography.json`/`spacing.json`/`primitives.json` per `_load_profile_from_root`, `design_tokens.py:363-402`).
- No existing tool checks template-vs-token consumption (`scripts/little_loops/cli/verify_design_tokens.py::lint_profile()` only checks theme-JSON-to-theme-JSON key completeness, never reading the `.html.tmpl`/`.mjs` files), and no existing test renders the template under both light and dark and diffs the two — this audit's Phase 1 has no reusable checker or snapshot precedent to extend, only the single-render byte-identical golden fixture.

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Conventions in force: template tokens are consumed only via `var(--name, fallback)` with one generation-time stamp point (`stamp_page_shell`); the only other template doing this is `templates/dashboard.llat/template.html.j2`, which uses a *different* token vocabulary (`--color-background`, `--color-text`, `--font-family-sans`) and dark-valued fallbacks — two contested vocabularies, so "expected token name" must be defined against the resolver's output, not against either template.
- Follow-up filing goes through `ll-issues create --type ENH --title … --body-file - --json` (`skills/capture-issue/SKILL.md` §4); `create` has no `--relates-to`, so `relates_to: [ENH-3506, ENH-3500]` is set afterward with `ll-issues link <ID> --relates-to …` (`cli/issues/link.py`). The unresolved references are fixed together here; use follow-ups only for excluded work.
- Permanent regression coverage extends the existing real-profile precedent (`test_themed_css_vars_is_separately_callable`), and must isolate config (`monkeypatch.chdir(tmp_path)` style, as `TestKitAcceptsTemplatizedBody` does) rather than reading ambient `.ll/`.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the single shared HTML template whose inline `<style>` block consumes design tokens via `var(--token-name, <fallback>)` (lines 18-27, 65, 111-113); primary target for token/theme audit
- `scripts/little_loops/templates/policy_builder_core.mjs` — the single shared, DOM-free JS module implementing all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`) via client-side `<select id="mode-switch">`; has zero token/CSS-variable references; theme initialization/toggling lives in the HTML template, so it is out of scope for the token audit itself (FEAT-3488's additions extended, and FEAT-3505's are expected to extend, these same two shared files rather than adding per-mode fragments)
- `scripts/little_loops/templates/design-tokens/profiles/{default,editorial-mono,warm-paper}/{semantic.json,themes/light.json,themes/dark.json}` (+ the gitignored `.ll/design-tokens/` mirror) — add `color.status.*` and the paired `color.action.primary-text` token
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate once
- `scripts/tests/test_enh3035_artifact_template_kit.py` — isolate golden rendering inputs before regeneration
- New pytest coverage alongside that module — declaration/value parity, contrast, old-mirror and partial/disabled-source compatibility
- Compatibility implementation in the template/rendering path, or migration tooling if selected — choose the narrowest approach preserving custom tokens and document it in Findings

### Dependent Files (Callers/Importers)
- `scripts/little_loops/worktree_utils.py:687-713` — copies `.ll/design-tokens` into epic-verify worktrees as a stopgap for the golden-fixture test's token dependency; this issue determines whether that stopgap is still needed once token usage is verified correct
- `.ll/design-tokens/profiles/<active-profile>/{primitives.json, semantic.json, typography.json, spacing.json, themes/{light,dark}.json}` — the token source of truth the audit diffs rendered output against (theme-independent `semantic`/`typography`/`spacing` layers merged with the theme-specific `themes/<theme>.json` override, resolved against `primitives.json`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/artifact_templates.py:315-317` — `build_ll_namespace()` calls `themed_css_vars()` when a template manifest declares `theme: design-tokens`; generic artifact-templating path (not policy-builder-specific — policy-builder calls `themed_css_vars` directly via `policy_builder.py:79`), but a future fix to `themed_css_vars()` itself would ripple here too [Agent 1 finding]
- `scripts/little_loops/cli/artifact/templatize.py:945-949` — `_themed_css_vars()`, a "thin patchable wrapper" over `themed_css_vars()` used by `ll-artifact templatize`'s lift tooling; same generic-consumer caveat as above [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:1095-1105` — `_full_design_tokens_check()` (`@register_full_check`) is a live `ll-doctor` gate calling `lint_profiles_dir()` (built on `lint_profile()`, the same theme-JSON-completeness checker that never reads `.html.tmpl`/`.mjs`); it surfaces "half-flipped themes" as an error-severity check, separate from the epic-verify golden-fixture gate already listed above — audit findings should note whether this doctor check also needs a template-aware companion [Agent 1 + Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/serve.py:218,226` — `render_policy_builder_html(config, workspace_id=...)` is a second consumer of the rendered page (FEAT-3504 connected/served path); the audit's render should go through `render_policy_builder_html` so the served page and `ll-artifact policy-builder` output are the same token surface [Agent 1 finding]
- `scripts/little_loops/cli/artifact/templatize.py:987-994` — `_lift_precondition 5` calls `_themed_css_vars(config)` and fails the lift if required declarations are missing; a fix to `themed_css_vars()` output ripples into `ll-artifact templatize` [Agent 1 + Agent 2 finding]
- `.loops/verify-feat-3488-browser-persistence.yaml:54` — shell state runs `ll-artifact policy-builder -o "${context.run_dir}/html"` and feeds `.loops/probes/feat-3488-browser-probes.mjs`; the only loop rendering the builder, probes localStorage keys only (no token/theme check). Precedent (per `reference_playwright_browser_probe_loop`) if runtime computed-style verification is wanted later [Agent 2 finding]
- `scripts/little_loops/design_tokens.py:418-430,448,584,632` — ENH-3441 packaged-profile fallback: with no `.ll/design-tokens/` mirror the render uses the packaged profile with a fallback notice, so a missing mirror is invisible in rendered output; likewise `_find_profiles_dir` (used by `verify_design_tokens.py` and `doctor.py:1095`) reports "not found" (exit 1) although artifacts still render [Agent 2 finding]
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — the golden fixture itself; the template/profile fixes in this issue require regenerating it after test isolation [Agent 3 finding]

### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; it fixed findings inline rather than filing follow-ups, so it is a scope baseline, not a filing precedent
- Follow-up filing convention: call `ll-issues create` directly (post-FEAT-2947 convention, `skills/capture-issue/SKILL.md:266-275`)

### Tests
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — isolate this byte-level guard and supplement it with value/readability coverage
- `scripts/tests/test_policy_builder_corpus.py`, `scripts/tests/test_policy_builder_emit.py` — existing coverage for builder-emitted output; no changes expected unless the audit finds drift requiring a new regression test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py::TestRenderAsCssVarsThemed` (lines 635-687) — unit tests of `render_as_css_vars_themed()` against synthetic tmp-dir tokens; pins the exact CSS block delimiters (`:root {`, `[data-theme=dark] {`) the audit's parser needs, but never renders the real template or diffs against the real active profile — partial precedent only [Agent 3 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_themed_css_vars_is_separately_callable` (lines 31-40) — the one existing test that calls the themed-CSS path against this repo's real active profile (`warm-paper` + `dark`), but asserts only block presence, not value-level parity with source JSON — closest existing precedent to extend for the required permanent regression coverage [Agent 3 finding]
- `scripts/tests/test_verify_design_tokens.py::TestLintProfile` (lines 80-133) — confirms `lint_profile()` checks theme-JSON-to-theme-JSON completeness only and never reads `.html.tmpl`/`.mjs`, substantiating the issue's own gap claim [Agent 3 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3441_packaged_profile_fallback.py::test_ambient_mirror_matches_packaged_profiles` (and `_make_config`/`_write_mirror_profile` helpers) — existing packaged-vs-mirror parity check; closest precedent for a permanent parity test and the config-isolation helper to reuse [Agent 3 finding]
- `scripts/tests/test_worktree_utils.py::test_gitignored_design_tokens_dir_materialized_in_worktree` — docstring calls the copy a stopgap and names the durable fix as pinning the golden test to a checked-in fixture; will need removal/update if the audit concludes the stopgap is redundant [Agent 3 finding]
- `scripts/tests/test_artifact_templatize.py::TestVerifyLiftRenders` (lines 1618-1650), `::TestLiftTokenLiterals::test_var_name_matches_render_as_css_vars_themed_mangling` — existing declared-vs-referenced var-set checks and name-mangling precedent for a template-ref-vs-declared test [Agent 3 finding]
- `scripts/tests/test_feat3504_policy_builder_serve.py::_make_config` / `_bridge_for` — only test calling `render_policy_builder_html`; `_make_config` is the model for an isolated new test [Agent 3 finding]
- `scripts/tests/test_cli_doctor_full.py::test_design_tokens_reports_informational_when_missing` — covers `_full_design_tokens_data()`; reference for the verdict; implementing a new companion is out of scope [Agent 3 finding]
- **Gap (required new coverage):** none extracts template `var(--x)` refs and checks them against rendered `:root`/`[data-theme=dark]` declarations, and none unit-tests `render_policy_builder_html` theme blocks [Agent 3 finding]

### Documentation
- Update existing theme/fallback documentation as needed to match this fix and its compatibility behavior.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `#### ll-artifact policy-builder` — prose claims the page "honors the project's configured `active_theme`" via `load_design_tokens`/`render_as_css_vars_themed`; if the audit confirms token/theme drift, this section's claim needs checking and correcting within this issue [Agent 2 finding]
- `docs/guides/POLICY_ROUTER_GUIDE.md` (section preceding "### Issue Lifecycle Mode") — same "stamped from this project... honors active_theme" claim; update within this issue as needed [Agent 2 finding]

_Second wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `### ll-verify-design-tokens` (lines 4724-4746) — documents a structural lint only, no rendered-artifact parity; relevant to the "template-aware companion" finding [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:874` — states an explicit `theme=` is passed only by `artifact_template_kit.themed_css_vars`; closest parity-adjacent claim, verify against audit results [Agent 1 + Agent 2 finding]
- `docs/ARCHITECTURE.md:1066,1070` and `docs/reference/CLI.md:493,5327` — long lines matching the theming symbols; likely further "honors active_theme" claims, read directly before making any necessary documentation corrections here [Agent 1 + Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1974-1983` — `design_tokens.active` (profile selector, default `"default"`) is the key the audit must diff against (`.ll/design-tokens/profiles/<active>/`), distinct from `design_tokens.active_theme` (default `"dark"`), which only sets the initial `data-theme` attribute and does not gate which theme's values get rendered — both light and dark CSS blocks are always rendered from the one active profile [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1989-1994` — `design_tokens.source` (`"auto"`, `"profile"`, or `"design_md"`): when the resolved `DesignTokens.source` is `"design_md"`, `themed_css_vars()` short-circuits so the dark block equals the light block by design — the audit's diff logic must not flag this degenerate case as drift [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- No per-mode template fragment files exist. `scripts/little_loops/templates/policy-router-builder.html.tmpl` (one shared HTML template) plus `scripts/little_loops/templates/policy_builder_core.mjs` (one shared, DOM-free JS module) implement all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`); mode switching happens client-side via `<select id="mode-switch">` inside the single template, not via separate per-mode files. `policy_builder_core.mjs` has zero token/CSS-variable references (confirmed by grep for `--color`/`--space`/`--radius`/`--typography`/`--font`/`getComputedStyle`/`setProperty`) — theme initialization and toggling are in the HTML template, not this core module.
- Token consumption mechanism: the template's inline `<style>` block references tokens exclusively via CSS `var(--token-name, <hardcoded-fallback>)` (e.g. `policy-router-builder.html.tmpl:18-27,65,111-113`). The placeholder `/*__THEMED_CSS_VARS__*/` (line 9) is where resolved CSS is stamped in once, at generation time, by `stamp_page_shell()` (`scripts/little_loops/artifact_template_kit.py:52-71`) — there is no runtime fetch or browser-side token lookup.
- Render entry point: `cmd_policy_builder()` in `scripts/little_loops/cli/artifact/policy_builder.py` (invoked via `ll-artifact policy-builder`, subparser at `scripts/little_loops/cli/artifact/__init__.py:138-148`, which defines only `-o/--output` — no theme-selecting flag exists anywhere in the codebase).
- A single render already embeds BOTH themes' resolved CSS in one output file: `themed_css_vars(config)` (`artifact_template_kit.py:18-49`) loads `theme="light"` and `theme="dark"` token sets independently and `render_as_css_vars_themed()` (`scripts/little_loops/design_tokens.py:773-792`) emits one `:root{...}` block (light) and one `[data-theme=dark]{...}` block (dark) into the same file. `config.design_tokens.active_theme` stamps the initial `<html data-theme="...">` attribute; it does not gate which theme's tokens get rendered.
- Actual token file layout differs from a literal `.ll/design-tokens/<theme>.json` per theme: it is `.ll/design-tokens/profiles/<active-profile>/{primitives.json, semantic.json, typography.json, spacing.json, themes/<theme>.json}` (config-schema.json:1945-1994; `_load_profile_from_root`, `design_tokens.py:363-402`). `themes/<theme>.json` supplies only the theme-specific override layer, merged over the theme-independent `semantic`/`typography`/`spacing` files and resolved against `primitives.json`.
- No existing tool checks template-vs-token consumption. `scripts/little_loops/cli/verify_design_tokens.py::lint_profile()` checks theme-JSON-to-theme-JSON completeness (`semantic.json` keys vs `themes/*.json` keys) only — it never reads `policy_builder_core.mjs` or `policy-router-builder.html.tmpl`. No headless-browser/DOM rendering harness (playwright/puppeteer/jsdom) exists in the repo; the only JS test (`scripts/tests/js/policy_validator.test.mjs`) runs `policy_builder_core.mjs` under plain `node --test` as a DOM-free module.
- No existing test renders the template twice (once per theme) and diffs; the golden-fixture test (`test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`) calls `cmd_policy_builder()` exactly once, under whichever `active_theme` the ambient project config resolves to, and does not override `Path.cwd()` — it always reads whatever `.ll/design-tokens/` and `.ll/ll-config.json` sit at the process cwd.

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Pre-check on the real active profile (`warm-paper`, this checkout) finds substantial drift already.** Calling `themed_css_vars(BRConfig(Path.cwd()))` yields 85 declared custom properties; `policy-router-builder.html.tmpl` references 18 distinct `var(--…)` names, of which only 3 resolve (`--color-action-primary`, `--color-surface-raised`, `--color-text-primary`). The other 15 never resolve and always fall back to their hardcoded literal: `--color-surface-base`, `--color-surface-sunken`, `--color-text-on-sunken`, `--color-border-default`, `--color-action-primary-text`, `--color-status-{success,warning,error,info}-{bg,text}`, `--typography-font-family-{base,mono}`. Because the template carries no `[data-theme=dark]` override of its own, an unresolved name renders the same hardcoded fallback in **both** themes — the golden-fixture test cannot see this because it only byte-compares one render.
- Naming rule (evidence: `design_tokens.py::render_as_css_vars_themed`, `_flatten`): CSS name = `--` + dotted token key with `.`→`-`. The profiles emit `color.surface.{primary,secondary,raised}`, `color.text.*`, `color.border.{subtle,strong}`, `color.action.{primary,…}`, and `font.family.*` (→ `--font-family-*`, not `--typography-font-family-*`). There is no `color.status.*` group in `.ll/design-tokens/profiles/warm-paper` or the packaged profiles (grep under `scripts/little_loops/templates/design-tokens` returns 0). The Fix section now selects ref renames plus new paired action/status tokens in this issue.
- `themed_css_vars()` emits sorted, fully-resolved declarations, two-space indented, as `:root {` … `}` then `[data-theme=dark] {` … `}` (dark scope unquoted); keys starting with `_` are skipped; both blocks are full sets, not deltas. Returns the literal empty-block pair when `load_design_tokens()` is `None`; when `light.source == "design_md"`, dark is the same object as light.
- Reusable, already-scriptable pieces (no new render harness needed): `render_policy_builder_html(config)` (`cli/artifact/policy_builder.py`) returns the HTML string without writing a file; `load_design_tokens(config, theme=)` exposes `DesignTokens.resolved` (`dict[str, str]`); `templatize.py` (`_check_lift_preconditions`, `verify_lift_renders`) already does set-difference of emitted vs. declared var names, but on a templatize-time set, not on a parsed template.
- Correction to earlier citation: `render_policy_builder_html` is where `themed_css_vars` is called (`policy_builder.py:79` per code graph), not `:68`. The `stamp_page_shell` call is at `:114`.
- Template hardcodes outside `var()`: radii (8/6/4px), `1px`/`2px` borders, rem paddings/gaps, font-weights, `opacity`, `max-height`. Fallbacks themselves are literals and are internally inconsistent — the same token falls back to different values (`--color-surface-base`: `#ffffff` vs `#fff`; `--color-border-default`: `#d0d0d0` vs `#ccc`). Spacing/radius have no token references at all, so "spacing bypasses a token" is excluded from implementation scope; tokenization may be a separate follow-up.
- `.ll/design-tokens/` is gitignored, and ENH-3441 (done) made `load_design_tokens` fall back to packaged profiles when it is absent (`_resolve_packaged_profile_root`). That weakens the original rationale for the `worktree_utils.py:687-713` copy (comment there calls it a BUG-3370 "stopgap"); the audit should decide whether it is now redundant. Note the golden test still reads ambient cwd config (no `chdir`), so the fixture is machine-config-dependent.
- Stale comment: `design_tokens.py` refers to `artifact_template_kit._cached_themed_tokens`, which does not exist.

## Implementation Steps

1. Establish isolated render fixtures for all packaged profiles and both themes; capture a pre-change mirror lacking the new tokens. Choose and record the non-destructive compatibility approach.
2. Write failing declaration/value parity and paired-color contrast tests; add separate old-mirror, partial `DESIGN.md` (explicit and `auto`), and disabled-token cases with their expected behavior.
3. Apply the token renames, paired action/status tokens, compatibility behavior, and explicit per-theme `color-scheme`. Refresh this checkout's mirror without overwriting unrelated customizations.
4. Verify all three authoring modes visually in both themes, including an OS preference opposite to the selected theme. Check buttons, all status types, winning-rule highlights (including inherited text), native controls, and YAML output.
5. Isolate all environment-dependent golden render inputs, verify the diff, and regenerate the fixture once using that setup. Check independence from ambient config/mirrors and update user documentation.
6. Run targeted parity, contrast, fallback, lint/mirror, golden, and existing builder-output checks, then the required local suite (`python -m pytest scripts/tests/`). Record the worktree-stopgap and doctor-companion verdicts in `## Findings`; remove the copy only if verification establishes it is redundant and update its test accordingly.

## Acceptance Criteria

- [ ] Every template CSS variable reference is declared in both theme blocks for each of `default`, `editorial-mono`, and `warm-paper`; emitted values match the selected profile's resolved values. Identical shared values across themes are allowed.
- [ ] `color.action.primary-text` is explicitly paired with the primary action background, and all four status types have paired background/text tokens in every packaged profile/theme. Normal text on primary buttons, status messages, winning-rule highlights, and YAML output has contrast of at least 4.5:1 across all six combinations.
- [ ] A pre-change mirror missing new keys follows the documented migration/fallback behavior without losing custom values. Partial `DESIGN.md` (explicit and `auto`) and disabled-token configurations have separate passing fallback tests; full-profile parity requirements are not incorrectly applied to them.
- [ ] Native controls follow the selected `data-theme` even when OS preference differs. Initial theme and toggling retain existing theme precedence; visual verification covers all three modes and the listed text surfaces in both themes.
- [ ] The golden test pins environment-dependent inputs and passes independently of ambient config/mirrors. The fixture is regenerated only after reviewing the intended render changes, using the same isolated setup.
- [ ] Profile lint and mirror parity, new regressions, existing builder-output checks, and the required local pytest suite pass. Emitted YAML and policy execution behavior are unchanged.
- [ ] Documentation describes the resulting theme/compatibility behavior. Findings record both verdicts; any worktree-copy removal is supported by mirror-present/absent verification, and a new doctor companion is left to separate work.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Diff against `.ll/design-tokens/profiles/<config.design_tokens.active>/` — the `active` profile key, not `active_theme` (which only sets the default `data-theme` attribute, not which values render)
- Special-case the resolved `DesignTokens.source == "design_md"` (including selection through `source: auto`) in the diff logic — `themed_css_vars()` short-circuits so the dark block equals the light block by design in that mode; do not flag it as drift
- Note `scripts/little_loops/cli/doctor.py::_full_design_tokens_check()` as a related-but-insufficient gate (theme-JSON completeness only, same as `lint_profile()`) — audit findings should state whether it needs a template-aware companion alongside the golden-fixture gate
- If drift is confirmed, also flag `docs/reference/CLI.md` `#### ll-artifact policy-builder` and `docs/guides/POLICY_ROUTER_GUIDE.md` for correction in this issue's fix (rescoped 2026-09-19) — both currently assert the theming behavior works correctly

- Render via `render_policy_builder_html(config)` (returns the string, no file) rather than shelling to the CLI; it is the same path `serve.py:226` uses, so the audit covers the served page too
- Isolate config (`monkeypatch.chdir(tmp_path)` + `_make_config`, per `test_enh3441_packaged_profile_fallback.py`) in all new regression tests, and account for the ENH-3441 packaged-profile fallback: a missing `.ll/design-tokens/` mirror renders from packaged profiles with a fallback notice, so the stopgap-still-needed verdict must test both mirror-present and mirror-absent renders
- When judging `_full_design_tokens_check()` / `ll-verify-design-tokens`, note both go through `_find_profiles_dir` and report "not found" (exit 1) for a no-mirror project that still renders fine — a second reason they are not a rendered-output gate

## Impact

- **Priority**: P3 - presentation correctness and readability; the worktree copy only addresses ambient-token availability, not unresolved names or contrast
- **Effort**: Medium - template mappings, paired action/status tokens across three profiles, compatibility behavior, parity/contrast/fallback coverage, browser verification, and golden-test isolation/regeneration
- **Risk**: Low-Medium - presentation-only, but visibly changes dark-theme rendering and touches every packaged profile; guarded by the new parity test and existing mirror/lint tests
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: template token/value parity; paired action/status colors and readability; native-control theme selection; compatibility for existing mirrors and partial/disabled sources; regression coverage; golden-test isolation/regeneration; documentation and the two verdicts
- **Out of scope**: information hierarchy, empty/error states, and cross-mode consistency (ENH-3500); FEAT-3505's connected-page surface (audited under ENH-3500 once it lands — if it introduces new token references, ENH-3500's pass covers them); spacing/radius tokenization; implementing a new doctor companion; changes to emitted YAML or policy execution behavior

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-18 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-19T01:36:47 - `953ae6f1-8990-4402-a96c-e167c77869ae.jsonl`
- `/ll:verify-issues` - 2026-09-19T01:29:27 - `95a86361-ae5f-4af5-841b-d063cb74486b.jsonl`
- `/ll:confidence-check` - 2026-09-19T01:27:25 - `7a2a69d3-d8fa-43ea-8e40-15186213e21f.jsonl`
- `/ll:confidence-check` - 2026-09-19T00:55:44 - `089757cd-fbfa-425b-82b6-90c870def4c8.jsonl`
- `/ll:wire-issue` - 2026-09-19T00:54:28 - `e2df2c7e-086d-407f-878d-d3c3d7221a4c.jsonl`
- `/ll:refine-issue` - 2026-09-19T00:47:41 - `304eba96-751f-4059-9328-1fc1b29cacd2.jsonl`
