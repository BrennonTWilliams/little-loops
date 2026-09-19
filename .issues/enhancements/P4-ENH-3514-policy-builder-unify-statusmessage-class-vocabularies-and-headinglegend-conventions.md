---
id: ENH-3514
type: ENH
title: 'Policy builder: unify status/message class vocabularies and heading/legend
  conventions'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# ENH-3514: Policy builder: unify status/message class vocabularies and heading/legend conventions

## Summary

Found by ENH-3500 audit. Two class vocabularies coexist: is-error/is-warning/is-success (connected status) vs msg-error/msg-warn/msg-ok plus msg-info (Result diagnostics, scenarios, lifecycle). 'Try it' is the legend of two fieldsets; the h2s ('Result', 'Submit to host') use inline font-size:1rem while left column uses legends; dark theme 'Otherwise ->' fallback row renders as a saturated green block with italic label unlike other rows. Expected: one status vocabulary and consistent heading treatment. Evidence: auth-populated-decision_table-dark-w1280-offline.png, conn-accepted-warnings-*.

## Current Behavior

Two status class vocabularies coexist: `is-error`/`is-warning`/`is-success` (connected status) and `msg-error`/`msg-warn`/`msg-ok` plus `msg-info` (Result diagnostics, scenarios, lifecycle). 'Try it' is the legend of two fieldsets; the 'Result' and 'Submit to host' h2s use inline `font-size:1rem` while the left column uses legends. In dark theme the 'Otherwise ->' fallback row renders as a saturated green block with an italic label unlike other rows.

## Expected Behavior

One status class vocabulary is used throughout, headings/legends follow one convention, and the fallback row matches other rows in both themes.

## Motivation

This enhancement would:
- Duplicate vocabularies double the CSS and invite drift between connected and offline views.
- Inconsistent headings and the dark-theme fallback row look unintentional.
- ENH-3500 audit evidence: `auth-populated-decision_table-dark-w1280-offline.png`, `conn-accepted-warnings-*`.

## Scope Boundaries

- **In scope**: choosing one class vocabulary and migrating both sets; one heading/legend convention; dark-theme fallback-row styling.
- **Out of scope**: design-token changes (ENH-3506); new status states; message text changes.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `renderMessages` (:1296), `renderConnected` (:2217), `renderFallback` (:743). Message classes are applied in JS at :1302, :1309, :1317, :1320 (`renderMessages`), :1362, :1364, :1372 (`renderTransitionGraph`, also `msg-info`), and :1657 (`_renderSuiteRunResults` scenario verdicts, on `.scenario-verdict.hint`, outside `.messages`). The `is-*` vocabulary has exactly one JS use: :2275 (`"conn-status " + (rejected ? "is-error" : accepted ? "is-success" : "is-warning")`) on `#conn-status`; CSS at :170-173. `msg-*` CSS at :161-164 is scoped by `.messages li` (:160) for sizing.
- Vocabulary asymmetry: `msg-*` has `warn`/`ok`/`info`; `is-*` has `warning`/`success` and relies on base `.conn-status` for info colors. Both draw colors from the same `--color-status-*` variables, so the migration is class-name-only; dark theme is handled by variable overrides in `[data-theme=dark]` (:32-51), not per-class rules.
- The issue's `renderFallback` reference is correct for the function, but the dark-theme fallback-row defect is a CSS matter: `.fallback-row` (:146-147: `font-style: italic; opacity: 0.85`) has no `[data-theme=dark]` rule; the green block comes from `.rule-winner` (:131-134: `outline: 2px solid var(--color-action-primary); background: var(--color-status-success-bg)`), which `_highlightWinner` (:1218-1227) adds to `#fallback-row` when `result.ruleIndex < 0 && result.isFallback`. Callers: `updateTryIt` (:1245), `updateFrontmatterTryIt` (:1271, 1279, 1286). "Renders as a saturated green block" is therefore the *winner highlight* on the fallback row; whether the defect is the highlight itself or its dark-mode saturation must be settled against `auth-populated-decision_table-dark-w1280-offline.png` before changing CSS.
- Headings: `<h2 style="margin-top:0;font-size:1rem;">` at :311 (Result) and :332 (Submit to host); left column uses `<legend>` (Identity, Thresholds, Dimensions, Rules, Try it ×2 at :258 and :264, Scenarios, Budget, Outcomes). The two "Try it" fieldsets are mutually exclusive via `applyModeVisibility` (:1867-1868), so duplicate legend text is never visible together. No `h2` CSS rule exists to absorb the inline style.
- Class-rename blast radius: no pytest/Node test asserts `msg-*`/`is-*` names. The on-demand probes do: `.loops/probes/enh-3500-audit-probes.mjs:88` (class census `^(msg-|is-)`) and `.loops/probes/enh-3506-theme-probes.mjs:71` (`li.className = "msg-" + k` for warn/error/ok/info) — a rename to `is-*` (or `warn`→`warning`) needs that probe updated. The issue's Impact note "tests may assert existing class names" is therefore about probes, not pytest.
- Theme parity guard: `test_enh3506_policy_builder_theme_parity.py` collects every `var(--…)` in the template CSS (from the `"* { box-sizing"` marker to `</style>`) and requires each declared in both stamped theme blocks, plus contrast ≥ 4.5 for the `--color-status-{success,warning,error,info}-{text,bg}` pairs (`PAIRS`, :38-48). Any new CSS variable for the fallback-row fix must be declared in the stamped theme blocks; reusing existing tokens avoids it. ENH-3506 (theme parity) is done and owns token definitions — out of scope here per the issue.

### Conventions in Force
- Colors are token-driven only (`var(--color-status-*, fallback)`); the golden render is pinned to the dark theme (`_pin_golden_render_inputs`, `test_enh3035_artifact_template_kit.py:63-90`), so the golden regeneration will show the dark fallback-row change.
- The `data-theme="light"` literal on line 2 must remain the first occurrence (`stamp_page_shell`, `little_loops/artifact_template_kit.py:52`); placeholders `/*__…__*/` are silent-no-op `str.replace` targets.

**Tests (research)**
- `scripts/tests/test_policy_builder_emit.py` for static structure (a "only one vocabulary remains" check is a string/regex test over the rendered HTML — the golden fixture currently has 20 lines matching `msg-|is-error|is-success|is-warning|No scenarios yet|aria-live`); golden `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` regeneration; probe updates above; ENH-3500 cases `auth-populated-decision_table-dark-*`, `conn-accepted-warnings-*`.

## Program Design

### Types

- `StatusClass: str` — CSS class name strings only; no new persisted shapes.

### Signatures

- `renderMessages(model, diagnostics) -> void`
- `renderConnected(st) -> void`
- `renderFallback() -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderMessages` / `renderConnected` / `renderFallback` -> unified class vocabulary

## Implementation Steps

1. Pick the canonical vocabulary (`msg-*` or `is-*`) and map the other onto it.
2. Migrate CSS rules and JS class assignments; unify headings/legends.
3. Fix the dark-theme fallback row; add a template test that only one vocabulary remains.

## Impact

- **Priority**: P4 - cosmetic consistency
- **Effort**: Small-Medium - CSS and class-name migration
- **Risk**: Low-Medium - tests may assert existing class names
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-09-19T20:57:52 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:43 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
