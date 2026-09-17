---
id: ENH-3500
type: ENH
title: Policy builder cross-mode design and UX audit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T19:57:23Z'
blocked_by: [FEAT-3498, FEAT-3488]
relates_to: [EPIC-3493, ENH-3491]
program_design_not_applicable: true
reconcile_attempted: true
---

# ENH-3500: Policy builder cross-mode design and UX audit

## Summary

Holistic visual/UX audit of the policy-router builder across all authoring modes (lifecycle, decision-table, and whatever FEAT-3498's connected-execution surface adds): design-token/theme parity (dark/light), information hierarchy, empty/error states, and cross-mode consistency. None of EPIC-3493's 8 children own this — ENH-3491 (done) covered lifecycle-mode layout, responsive CSS, and keyboard/label basics only, scoped to that one mode.

## Current Behavior

Each policy-builder authoring mode (lifecycle, decision-table) was designed, reviewed, and shipped independently, and no issue has ever checked them against each other. ENH-3491 audited lifecycle-mode layout, responsive CSS, and keyboard/label basics in isolation. Design-token and dark/light usage is unverified against real rendering: `test_policy_builder_renders_byte_identically_to_golden_fixture` only catches byte-level drift from a golden fixture, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees as a stopgap so that test doesn't false-fail on a missing token file — it does not verify the templates consume tokens correctly. There is no audit covering information hierarchy, empty/error states, or visual consistency across modes.

## Expected Behavior

Design-token and dark/light theme usage in the already-shipped lifecycle and decision-table modes is confirmed correct (not just passing the golden-fixture byte-match), with any drift filed as follow-up issues. Once FEAT-3498 and FEAT-3488 land, a second audit pass reviews information hierarchy, empty/error states, and cross-mode visual consistency across every authoring mode, producing filed follow-up issues for any inconsistency found — this issue's own deliverable is the audit findings, not the fixes themselves.

## Motivation

The builder now spans multiple modes shipped independently (lifecycle, decision-table, plus connected-execution and scenario-suite surfaces still landing via FEAT-3498/FEAT-3488). Each mode was designed and reviewed in isolation; nothing has checked them together for a consistent look, consistent empty/error handling, or correct dark/light design-token usage. There's already a concrete signal that token usage is fragile: ENH-3491's notes flagged that `test_policy_builder_renders_byte_identically_to_golden_fixture` false-fails on degraded design tokens, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees specifically as a stopgap for that. That's a workaround for a symptom, not a check on the actual token usage in the builder templates.

## Proposed Solution

Two-phase audit (see Scope), not a code change in itself:

1. **Token/theme audit (now)**: for each design token referenced by `scripts/little_loops/templates/policy_builder_core.mjs` and its per-mode templates, render lifecycle mode and decision-table mode under both `dark` and `light` themes (`ll-config.json` → `design_tokens.active_theme`) and diff the rendered CSS custom-property values against `.ll/design-tokens/<theme>.json`. Flag any hardcoded color/spacing value that bypasses a token, and any token referenced in one mode's template but not the other where the two should match. File one follow-up ENH per confirmed drift.
2. **Holistic UX audit (after FEAT-3498/FEAT-3488 land)**: walk every authoring mode side by side against a shared checklist — information hierarchy (heading levels, primary/secondary action placement), empty states (no rules/no decisions yet), error states (validation failure presentation), and terminology/iconography consistency. File one follow-up issue per inconsistency found, tagged `relates_to: [ENH-3500]`.

No emitted-YAML or runtime-behavior change is in scope for this issue (see Out of Scope) — only presentation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- A single `ll-artifact policy-builder` render already embeds both themes' resolved CSS in one output file (`:root{...}` for light, `[data-theme=dark]{...}` for dark) — `themed_css_vars()`/`render_as_css_vars_themed()` (`scripts/little_loops/artifact_template_kit.py:18-49`, `scripts/little_loops/design_tokens.py:773-792`) resolve and stamp both theme's values unconditionally, regardless of `config.design_tokens.active_theme`. No `--theme` CLI flag exists (`scripts/little_loops/cli/artifact/__init__.py:138-148` defines only `-o/--output`), and none is needed for token-value comparison: one rendered file already contains both blocks to parse and diff against `.ll/design-tokens/profiles/<active-profile>/themes/{light,dark}.json` (merged over `semantic.json`/`typography.json`/`spacing.json`/`primitives.json` per `_load_profile_from_root`, `design_tokens.py:363-402`).
- No existing tool checks template-vs-token consumption (`scripts/little_loops/cli/verify_design_tokens.py::lint_profile()` only checks theme-JSON-to-theme-JSON key completeness, never reading the `.html.tmpl`/`.mjs` files), and no existing test renders the template under both light and dark and diffs the two — this audit's Phase 1 has no reusable checker or snapshot precedent to extend, only the single-render byte-identical golden fixture.
- Convention for filing follow-up issues from an audit varies across existing audit skills: `commands/audit-architecture.md`/`skills/audit-docs/SKILL.md` hand-`Write` a fixed issue-file template (one issue per finding row); the current post-FEAT-2947 convention (`skills/capture-issue/SKILL.md:266-275`) instead calls `ll-issues create` directly. ENH-3491 (the prior lifecycle-only audit this issue's Scope §2 extends) filed no follow-up issues at all — its findings were implemented directly in that same issue, so it is not a precedent for this issue's "file one follow-up per finding" mechanism.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the single shared HTML template whose inline `<style>` block consumes design tokens via `var(--token-name, <fallback>)` (lines 18-27, 65, 111-113); primary target for token/theme audit
- `scripts/little_loops/templates/policy_builder_core.mjs` — the single shared, DOM-free JS module implementing all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`) via client-side `<select id="mode-switch">`; has zero token/CSS-variable references and only toggles the `data-theme` attribute, so it is out of scope for the token audit itself (future FEAT-3498/FEAT-3488 additions are expected to extend these same two shared files rather than adding per-mode fragments)
- No source files are expected to change for the audit itself; any drift found is filed as a follow-up ENH rather than fixed inline here

### Dependent Files (Callers/Importers)
- `scripts/little_loops/worktree_utils.py:687-713` — copies `.ll/design-tokens` into epic-verify worktrees as a stopgap for the golden-fixture test's token dependency; this issue determines whether that stopgap is still needed once token usage is verified correct
- `.ll/design-tokens/profiles/<active-profile>/{primitives.json, semantic.json, typography.json, spacing.json, themes/{light,dark}.json}` — the token source of truth the audit diffs rendered output against (theme-independent `semantic`/`typography`/`spacing` layers merged with the theme-specific `themes/<theme>.json` override, resolved against `primitives.json`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/artifact_templates.py:315-317` — `build_ll_namespace()` calls `themed_css_vars()` when a template manifest declares `theme: design-tokens`; generic artifact-templating path (not policy-builder-specific — policy-builder calls `themed_css_vars` directly via `policy_builder.py:68`), but a future fix to `themed_css_vars()` itself would ripple here too [Agent 1 finding]
- `scripts/little_loops/cli/artifact/templatize.py:945-949` — `_themed_css_vars()`, a "thin patchable wrapper" over `themed_css_vars()` used by `ll-artifact templatize`'s lift tooling; same generic-consumer caveat as above [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:1095-1105` — `_full_design_tokens_check()` (`@register_full_check`) is a live `ll-doctor` gate calling `lint_profiles_dir()` (built on `lint_profile()`, the same theme-JSON-completeness checker that never reads `.html.tmpl`/`.mjs`); it surfaces "half-flipped themes" as an error-severity check, separate from the epic-verify golden-fixture gate already listed above — audit findings should note whether this doctor check also needs a template-aware companion [Agent 1 + Agent 2 finding]

### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; this issue's Scope §2 explicitly extends that pattern across modes rather than re-litigating it

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

## Implementation Steps

1. Enumerate the design tokens `policy-router-builder.html.tmpl`'s inline `<style>` block references via `var(--token-name, <fallback>)`; confirm each resolves through `.ll/design-tokens/profiles/<active-profile>/` (merged `semantic.json`/`typography.json`/`spacing.json` + `themes/<theme>.json`, resolved against `primitives.json`) rather than relying on the hardcoded fallback.
2. Run a single `ll-artifact policy-builder` render (mode switching is client-side, so one render covers all three authoring modes); parse the output's two embedded CSS blocks (`:root{...}` for light, `[data-theme=dark]{...}` for dark, stamped in by `stamp_page_shell()`) and diff each block's resolved values against the corresponding theme's expected token values.
3. File one follow-up ENH per confirmed token/theme drift, with the specific file/selector and expected vs. actual value.
4. Once FEAT-3498 and FEAT-3488 land, repeat the process for information hierarchy, empty/error states, and cross-mode consistency, using ENH-3491's shipped lifecycle-mode output as the baseline.
5. File one follow-up issue per inconsistency found; close this issue once both audit passes are complete and findings are filed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Diff against `.ll/design-tokens/profiles/<config.design_tokens.active>/` — the `active` profile key, not `active_theme` (which only sets the default `data-theme` attribute, not which values render)
- Special-case `design_tokens.source == "design_md"` in the diff logic — `themed_css_vars()` short-circuits so the dark block equals the light block by design in that mode; do not flag it as drift
- Note `scripts/little_loops/cli/doctor.py::_full_design_tokens_check()` as a related-but-insufficient gate (theme-JSON completeness only, same as `lint_profile()`) — audit findings should state whether it needs a template-aware companion alongside the golden-fixture gate
- If drift is confirmed, also flag `docs/reference/CLI.md` `#### ll-artifact policy-builder` and `docs/guides/POLICY_ROUTER_GUIDE.md` for correction in the filed follow-up issue — both currently assert the theming behavior works correctly

## Impact

- **Priority**: P3 - polish/consistency work, not blocking any shipped functionality; the token-drift stopgap in `worktree_utils.py` already masks the symptom the token half of this audit targets
- **Effort**: Medium - Scope §1 (token/theme audit) is boundable now; Scope §2 (holistic audit) can't be sized until FEAT-3498/FEAT-3488 land and define the full set of modes
- **Risk**: Low - audit-only, no source changes in this issue itself; any risk lives in the follow-up issues it files
- **Breaking Change**: No

## Scope

Two halves with different timing — do not block the whole issue on the later one:

1. **Token/theme parity (can start now, independent of FEAT-3498/FEAT-3488)**: audit current design-token and dark/light usage in the already-shipped lifecycle and decision-table modes against ENH-3491's shipped output. Confirm the builder templates consume tokens correctly rather than relying on the golden-fixture stopgap masking drift.
2. **Holistic hierarchy / empty-state / error-state / cross-mode consistency review**: wait until FEAT-3498 (connected execution) and FEAT-3488 (scenario suites) land, so the audit sees every mode once instead of auditing a surface that's about to change again.

## Scope Boundaries

- **In scope**: token/theme parity audit of shipped modes (now); holistic hierarchy/empty-state/error-state/cross-mode audit once FEAT-3498/FEAT-3488 land (see Scope above for the two-phase breakdown)
- **Out of scope**: see Out of Scope below

## Out of Scope

- Re-litigating ENH-3491's lifecycle-mode layout, presets, or execution-summary decisions (already shipped).
- Any change to emitted YAML or runtime behavior — this is presentation/UX only.
- Being made a child of EPIC-3493 — kept separate so it doesn't stall that epic's closure.

## Dependencies

`blocked_by: [FEAT-3498, FEAT-3488]` applies to the holistic half only (Scope §2). The token/theme parity sub-item (Scope §1) can be picked up early or in parallel without waiting on either.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-17T20:36:27 - `09ec3a0b-aab2-4bb6-8cae-e9097652c9fa.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T20:19:51 - `6b0d1a07-f3de-4f1f-94c3-b6d1cbb4cbbf.jsonl`
- `/ll:refine-issue` - 2026-09-17T20:12:08 - `661efed9-f2d1-44cc-aba2-5fe939c77557.jsonl`
- `/ll:format-issue` - 2026-09-17T20:03:20 - `7d2e95ae-d922-4199-a105-d094d1bfae74.jsonl`
- `/ll:capture-issue` - 2026-09-17T19:57:56 - `1bf1a777-2967-438b-a3cf-45a0eb0f285a.jsonl`
