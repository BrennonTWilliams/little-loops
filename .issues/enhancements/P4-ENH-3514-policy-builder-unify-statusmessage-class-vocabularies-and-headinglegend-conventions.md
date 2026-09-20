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
- BUG-3516
blocked_by:
- ENH-3510
- BUG-3512
parent: EPIC-3493
epic: EPIC-3493
---

# ENH-3514: Policy builder: unify status/message class vocabularies and heading/legend conventions

## Summary

Found by ENH-3500 audit. Two class vocabularies coexist: is-error/is-warning/is-success (connected status) vs msg-error/msg-warn/msg-ok plus msg-info (Result diagnostics, scenarios, lifecycle). 'Try it' is the legend of two fieldsets; the h2s ('Result', 'Submit to host') use inline font-size:1rem while left column uses legends; dark theme 'Otherwise ->' fallback row renders as a saturated green block with italic label unlike other rows. Expected: one status vocabulary and consistent heading treatment. Evidence: auth-populated-decision_table-dark-w1280-offline.png, conn-accepted-warnings-*.

## Current Behavior

Two status class vocabularies coexist: `is-error`/`is-warning`/`is-success` (connected status) and `msg-error`/`msg-warn`/`msg-ok` plus `msg-info` (Result diagnostics, scenarios, lifecycle). 'Try it' is the legend of two fieldsets; the 'Result' and 'Submit to host' h2s use inline `font-size:1rem` while the left column uses legends. In dark theme the 'Otherwise ->' fallback row renders as a saturated green block with an italic label unlike other rows.

## Expected Behavior

One status class vocabulary (`msg-*`) is used throughout and the two right-column `h2`s are styled by a CSS rule instead of inline styles. The dark-theme fallback-row finding is split out to BUG-3516.

## Motivation

This enhancement would:
- Duplicate vocabularies double the CSS and invite drift between connected and offline views.
- Inconsistent headings and the dark-theme fallback row look unintentional.
- ENH-3500 audit evidence: `auth-populated-decision_table-dark-w1280-offline.png`, `conn-accepted-warnings-*`.

## Scope Boundaries

- **In scope**: migrating `is-*` onto `msg-*` (decided — see Design Decisions); replacing the two inline `h2` styles with one CSS rule.
- **Out of scope**: design-token changes (ENH-3506); new status states; message text changes.
- **Split out → BUG-3516**: the "saturated green fallback row". Checked against `auth-populated-decision_table-dark-w1280-offline.png`: it is the `.rule-winner` Try-it highlight landing on `#fallback-row` because all Try-it inputs are blank (`evaluateModel(model, {})` → fallback), painted only behind the label since the `<select>` has its own background. That is a behavior defect in `updateTryIt`, not a vocabulary/heading matter.
- **Dropped**: the duplicate 'Try it' legend. The two fieldsets are mutually exclusive via `applyModeVisibility` (:1867-1868), so the text is never visible twice — not a defect.
- **Dropped**: converting `h2`s to legends (or vice versa). The right column is `section`/`h2` content, the left is form `fieldset`/`legend`; both are semantically correct. Only the inline styling is inconsistent.

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

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `.loops/probes/enh-3500-audit-probes.mjs` (:88, class census `^(msg-|is-)`) and `.loops/probes/enh-3506-theme-probes.mjs` (:71, `li.className = "msg-" + k`) — update both if class names change; `.loops/verify-enh-3506-theme.yaml` drives the latter [Agent 1 finding]
- `scripts/tests/test_enh3506_policy_builder_theme_parity.py` — reusing existing `--color-status-*` tokens keeps it green; any new CSS variable must be declared in both stamped theme blocks [Agent 3 finding]

### Wiring: Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate by hand after reviewing the diff (byte-compared in `test_enh3035_artifact_template_kit.py`) [Agent 3 finding] (golden is pinned to the dark theme, so the fallback-row change shows there)
- `scripts/tests/test_policy_builder_emit.py` — add a regex test that only one status vocabulary remains in the rendered HTML [Agent 3 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` reference the template but no status class names — no doc change needed [Agent 2 finding]

## Program Design

### Types

- `StatusClass: str` — CSS class name strings only; no new persisted shapes.

### Signatures

- `renderConnected(st) -> void`
- `_renderConnectedStatus(st, box) -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderConnected` -> `_renderConnectedStatus` -> `msg-*` class on the `.conn-status` child of `#conn-status`

## Design Decisions

> **Context refresh (2026-09-19)**: BUG-3512 is **done** (2f5bdb89a). `:NNNN` line references in this issue predate it — roughly +4 up to `updatePreview` (now :1782) and +75 in the connected code (`renderConnected` now :2292). Function-name anchors remain correct; resolve by name, not line.
- Post-BUG-3512 the single `is-*` JS site lives in `_renderConnectedStatus(st, box)` (:2360, called from `renderConnected`), and the `.conn-status.is-*` CSS is at :173-175. Verified: `.msg-*` colour rules (:161-164) are unscoped; the only two `<h2>`s are in the right-column `.panel` sections (:313, :334), so `.panel h2` is safe.

- **Canonical vocabulary: `msg-*`** (`msg-error` / `msg-warn` / `msg-ok` / `msg-info`). It has ~8 JS sites plus the ENH-3506 theme probe (`li.className = "msg-" + k`); `is-*` has exactly one JS site (:2275) and three CSS rules (:171-173). Mapping: `is-error`→`msg-error`, `is-warning`→`msg-warn`, `is-success`→`msg-ok`. Delete the three `.conn-status.is-*` rules, but move the shared `.msg-*` color rules after the `.conn-status` base rule. Both selectors have equal specificity; retaining the current order would make the later base info colors override every renamed severity class. The base keeps its info fallback colors, and the later shared severity rules override them without duplicating declarations. ENH-3510/3511/3513 land first and already use `msg-*` for anything new.
- **Headings**: add `.panel h2` (or the nearest existing right-column scope) `{ margin-top: 0; font-size: 1rem; }` and remove the inline `style` from :311 and :332. No new CSS variables, so `test_enh3506_policy_builder_theme_parity.py` is unaffected.

## Acceptance Criteria

- [ ] Rendered HTML matches none of `is-error|is-warning|is-success` (pytest regex in `test_policy_builder_emit.py`).
- [ ] No `<h2` in the rendered HTML carries a `style=` attribute; an `h2` CSS rule exists (pytest).
- [ ] Browser assertions check computed foreground and background colors for connected accepted, accepted-with-warnings, rejected, and outcome-unknown states in both light and dark themes. Accepted states retain success colors, rejected retains error colors, and outcome-unknown retains warning colors. These checks must catch base info colors overriding severity colors; token-parity checks and golden/string assertions alone do not establish this behavior.
- [ ] `.loops/probes/enh-3500-audit-probes.mjs` class census (:88) updated to expect no `is-*`.
- [ ] Theme-parity test passes; golden regenerated after reviewing the diff; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Replace the class expression in `_renderConnectedStatus` (:2360) with the `msg-*` mapping; delete `.conn-status.is-*` CSS and move shared severity rules after the base `.conn-status` rule.
2. Add the `h2` rule; remove the two inline styles.
3. Add the two pytest checks; update the ENH-3500 probe census and add the four-state, two-theme computed-color assertions; rerun the browser and theme probes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Fallback-row defect is **settled and split out** to BUG-3516 (winner highlight on blank Try-it inputs)
- Sequenced via `blocked_by`: BUG-3512 → ENH-3513 → ENH-3511 → ENH-3510 → **ENH-3514** → BUG-3516 (shared template + byte-compared golden — never run in parallel)
- Update the ENH-3500 probe's class census (the ENH-3506 theme probe already uses `msg-*` and needs no change) and rerun `.loops/verify-enh-3506-theme.yaml` plus ENH-3500 cases `auth-populated-decision_table-dark-*`, `conn-accepted-warnings-*`
- Regenerate the golden after reviewing the diff

## Impact

- **Priority**: P4 - cosmetic consistency
- **Effort**: Small - one JS site, three CSS rules, one `h2` rule
- **Risk**: Low - no pytest asserts class names; only the ENH-3500 probe census changes
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:34 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:05:53 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:52 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:43 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): BUG-3512 also edits the `.conn-status` block in `renderConnected` (live-region/alert semantics, state class stays on the inner child). **Re-checked (BUG-3512 landed)**: the state class is on the inner `.conn-status` child built in `_renderConnectedStatus`; the outer `#conn-status` is a `role="group"` focus target and carries no state class — migrate the inner child only. BUG-3516 owns the saturated-green fallback row; regenerate the golden fixture in coordination.
