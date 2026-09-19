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
- `/ll:format-issue` - 2026-09-19T20:40:43 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
