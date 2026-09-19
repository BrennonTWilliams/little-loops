---
id: ENH-3513
type: ENH
title: 'Policy builder: validation diagnostics are not announced and reserved-name
  errors use alert()'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
- BUG-3512
---

# ENH-3513: Policy builder: validation diagnostics are not announced and reserved-name errors use alert()

## Summary

Found by ENH-3500 audit. #messages (Result diagnostics) is not a live region; after an edit or Open project produces msg-error diagnostics, copy/download are disabled but only #live-status ('Project opened.') is announced. #import-diagnostics is polite even for errors. add-outcome/add-dim reserved or duplicate names use blocking alert() instead of inline messages. Repro: open a project with a bogus dimension type; try adding outcome 'done' in decision_table. Expected: errors announced (assertive or status) and inline. Evidence: auth-invalid-model-*, live-import-error-offline.

## Current Behavior

`#messages` (Result diagnostics) is not a live region: after an edit or Open project yields `msg-error` diagnostics, Copy/Download disable but only `#live-status` ('Project opened.') is announced. `#import-diagnostics` is `aria-live="polite"` even for errors. The `#add-outcome`/`#add-dim` handlers report reserved or duplicate names with blocking `alert()`.

## Expected Behavior

Validation errors are announced (assertive or status role, chosen by severity) and shown inline. Reserved/duplicate-name errors appear as inline messages instead of `alert()`.

## Motivation

This enhancement would:
- Screen-reader users get no notice that the model became invalid and export was disabled.
- Blocking `alert()` interrupts flow and is inconsistent with the inline diagnostics elsewhere.
- ENH-3500 audit evidence: `auth-invalid-model-*`, `live-import-error-offline`.

## Scope Boundaries

- **In scope**: live-region semantics for `#messages` and `#import-diagnostics`; replacing `alert()` in the `add-dim`/`add-outcome` handlers with inline messages.
- **Out of scope**: rewording diagnostic text; explaining disabled controls (ENH-3511); unifying message class names (ENH-3514).

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `renderMessages(model, diagnostics)` (:1296, called only from `updatePreview` :1800) and `showLiveStatus(text)` (:430, plain `textContent` overwrite, 12 callers, no clear/queue).
- Live-region inventory: exactly two — `#import-diagnostics` (:283, `role="status" aria-live="polite"`, hidden outside lifecycle mode by `applyModeVisibility` :1871, written directly at :1711-1746 without `showLiveStatus`) and `#live-status` (:323, same attrs). `#messages` (:315, `<ul class="messages">`), `#transition-graph`, `#conn-notices` (:350), `#conn-status` (:351) have no role/aria. No `role="alert"` or `aria-live="assertive"` exists anywhere.
- `renderMessages` rebuilds `#messages` via `innerHTML = ""` on every `updatePreview()` (every edit), so making `#messages` a live region announces the entire list on each keystroke-level commit unless the announcement is restricted to changes (e.g. error set becoming non-empty). This is the double-announcement / chatter risk; it also interacts with `#live-status` texts written on Open/Save ("Project opened.").
- Severity mapping is `d.severity === "error" ? "msg-error" : "msg-warn"` (:1302); unreachable-outcome warnings (:1309, decision_table only), unknown-skill errors (:1317, template-side only — they do NOT disable Copy/Download since gating uses `validateBuilderModel` diagnostics only, :1795-1798), and `msg-ok` "No issues detected." (:1320) are also written there.
- `alert(` inventory (exactly four, all in click handlers, each followed by `return` before `renderAll()`/`commit()`): #add-dim :1997 (name contains ":" or "|"), :2002 (duplicate field); #add-outcome :2017 (reserved name via `isReservedOutcomeToken`), :2021 (duplicate). add-outcome is skipped early in `issue_lifecycle` (:2011). The issue text says "four `alert()` sites" — confirmed. Any inline replacement needs a message element near `#add-dim`/`#add-outcome`, cleared on the next successful add or edit.
- BUG-3512 (open, P2) covers `#conn-status`/`#conn-notices`/`#conn-review-info` live regions and connected-panel focus, and edits `renderConnected` too; ENH-3513 scope is `#messages`/`#import-diagnostics`/`alert()` only. `renderConnected` regions must stay out of this issue.

### Conventions in Force
- `#import-diagnostics` is `<p>` with `textContent`; `#messages` uses `<li class=msg-*>`; polite regions are assigned by static markup attributes, not by JS. `test_policy_builder_emit.py:317-318` asserts `'id="live-status"' in html` and `'aria-live="polite"' in html` — that assertion must keep passing (it is satisfied by either region).
- No test currently asserts `alert(` absence; a string-grep test over the add-dim/add-outcome handler region is feasible via the template-slicing approach in `policy_validator.test.mjs:1514-1572` (literal-marker slice; throws "template source moved" if markers shift), otherwise the whole-file `"alert(" not in html` check must account for any legitimate remaining `alert(` (none found).
- ENH-3500 probe installs MutationObservers on `live-status`, `import-diagnostics`, `conn-*` (`.loops/probes/enh-3500-audit-probes.mjs:235-237`); evidence cases `auth-invalid-model-*`, `live-import-error-offline` rerun via `CASE_ONLY`.

**Tests (research)**
- `scripts/tests/test_policy_builder_emit.py`; golden `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` must be regenerated; probe cases above.

## Program Design

### Types

- `StatusClass: str` — CSS class name strings only; no new persisted shapes.

### Signatures

- `renderMessages(model, diagnostics) -> void`
- `showLiveStatus(text) -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderMessages`; `add-dim`/`add-outcome` click handlers -> inline message replacing `alert()`

## Implementation Steps

1. Give `#messages` an appropriate live-region role and make `#import-diagnostics` severity-aware.
2. Replace the `alert()` calls in `add-dim`/`add-outcome` with an inline message element.
3. Add template tests for role/aria-live attributes and absence of `alert(` in those handlers.

## Impact

- **Priority**: P3 - accessibility and UX consistency
- **Effort**: Small - two live-region changes and four `alert()` sites
- **Risk**: Low - watch for double announcement with `#live-status`
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-19T20:57:46 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:37 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
