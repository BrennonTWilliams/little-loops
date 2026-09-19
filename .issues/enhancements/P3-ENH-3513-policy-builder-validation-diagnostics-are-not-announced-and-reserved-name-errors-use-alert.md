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
- `/ll:format-issue` - 2026-09-19T20:40:37 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
