---
id: ENH-3511
type: ENH
title: 'Policy builder: explain disabled controls (aria-describedby / visible reason)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
---

# ENH-3511: Policy builder: explain disabled controls (aria-describedby / visible reason)

## Summary

Found by ENH-3500 audit. ~13 bare .disabled sites and zero aria-disabled/aria-describedby; only #conn-unavailable gives a reason. Disabled Submit before review, delete-outcome-in-use, rule up/down at ends, and Copy/Download on invalid models give no reason (title only on some). Repro: any mode with invalid model -> Copy/Download disabled with no explanation next to them; connected panel before review -> Submit disabled. Expected: visible/associated reason. Native disabled semantics may stay. Evidence: auth-invalid-model-*, conn-issue-selected-*, conn-review-none-*.

## Current Behavior

About 13 sites set `.disabled` with no `aria-disabled`/`aria-describedby` anywhere; only `#conn-unavailable` explains a disabled state. Submit before review, delete-outcome-in-use, rule up/down at list ends, and Copy/Download on an invalid model give no reason (a `title` on some only).

## Expected Behavior

Each disabled control has a visible or programmatically associated reason (`aria-describedby` pointing at a hint element). Native `disabled` semantics may stay.

## Motivation

This enhancement would:
- Users, and assistive-tech users especially, cannot tell why an action is unavailable or how to enable it.
- ENH-3500 audit evidence: `auth-invalid-model-*`, `conn-issue-selected-*`, `conn-review-none-*`.

## Scope Boundaries

- **In scope**: reason text/association for Copy/Download (invalid model), connected Submit (before review), delete-outcome-in-use, and rule up/down at list ends.
- **Out of scope**: replacing native `disabled` with `aria-disabled`; undo/redo buttons; announcing validation diagnostics (ENH-3513).

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `updatePreview` (:1778), `renderConnected` (:2217), `renderOutcomes` (:776), `renderRules` (:1029). None of `aria-describedby`, `aria-disabled`, `aria-invalid`, `role="alert"` appears anywhere in the template; only `aria-label` and two `role="status" aria-live="polite"` regions exist.
- Complete `.disabled` inventory (14 assignments; issue says ~13): undo/redo (:517-518, out of scope); `delOc` in `renderOutcomes` (:789, `inUse = state.fallback === oc.name || state.rules.some(r => r.target === oc.name)`, already sets a dynamic `title` at :790-792 — the only disabled control with any reason); rule value input `valInput` for `==true`/`==false` ops (:1077); rule up/down at ends (:1154 `i === 0`, :1159 `i === state.rules.length-1`, titles are static and do not explain the disabled state); scenario `idxInput` when `expectedFallback` (:1542); Copy/Download (:1797-1798, `hasError`); connected `#conn-issue` (:2241), review (:2250), submit (:2251), refresh (:2256); static `disabled` on `#conn-submit-btn` markup (:344).
- Submit's disabled condition (:2251) is a disjunction: `!av.ok || rv.status !== "ready" || st.busy || outcome_unknown` — a single static reason cannot describe it; a reason must be derived from whichever clause holds. Review (:2250) has no title/reason at all.
- The one existing reason element: `#conn-unavailable` (:333), `<p class="hint" hidden>` toggled in `renderConnected` (:2220-2221); it carries no role/aria. It is the only precedent for "visible reason next to a disabled connected control".
- The issue's scope lists `valInput`, `idxInput`, and the `#conn-issue`/review/refresh sites as neither in nor out of scope; the Scope Boundaries only name Copy/Download, connected Submit, delete-outcome-in-use, and rule up/down. Those unlisted sites (:1077, :1542, :2241, :2250, :2256) need an explicit in/out decision so the "~13 sites" claim can be checked.
- `updatePreview` runs on every render (via `renderAll`), so any reason element for Copy/Download must be updated there, and cleared when the model is valid (the AC's "absent when enabled").

### Conventions in Force
- Hint elements are `<p class="hint">`/`small.help` filled through `.textContent` (:165, :168); JS assigns classes via `el.className = …`.
- Interaction with ENH-3513 / BUG-3512: an `aria-describedby` target that is also a live region would double-announce; ENH-3513 explicitly owns diagnostics announcements and BUG-3512 (open, P2) owns `#conn-status`/`#conn-notices`/`#conn-review-info` live regions, both editing `renderConnected`.
- Golden byte-comparison (`test_enh3035_artifact_template_kit.py:93-103`) and `test_policy_builder_emit.py` string-greps constrain how tests are written; there is no rendered-DOM pytest harness — assertions about "present while disabled, absent when enabled" are only checkable via the on-demand ENH-3500 probe (`.loops/probes/enh-3500-audit-probes.mjs`, which already records `aria-describedby`/`aria-disabled` per element at :75-77) or a vm-sandbox test in the style of `policy_validator.test.mjs:1574` (`_newBug3502Sandbox`).

**Tests (research)**
- `scripts/tests/test_policy_builder_emit.py` (static markup only); golden `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` must be regenerated; probe cases `auth-invalid-model-*`, `conn-issue-selected-*`, `conn-review-none-*` to rerun via `CASE_ONLY`.

## Program Design

### Types

- `StatusClass: str` — CSS class name strings only; no new persisted shapes.

### Signatures

- `updatePreview() -> void`
- `renderConnected(st) -> void`
- `renderOutcomes() -> void`
- `renderRules() -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `updatePreview` / `renderConnected` -> new `aria-describedby` reason element

## Implementation Steps

1. Enumerate the bare `.disabled` sites and the reason each should give.
2. Add hint elements and wire `aria-describedby`, cleared when the control is enabled.
3. Add template tests asserting the reason is present while disabled and absent when enabled.

## Impact

- **Priority**: P3 - accessibility polish
- **Effort**: Small-Medium - ~13 sites, mostly hint wiring
- **Risk**: Low - additive attributes and text
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-19T20:57:40 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:32 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
