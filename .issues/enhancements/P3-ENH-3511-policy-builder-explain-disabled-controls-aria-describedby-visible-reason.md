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
- `/ll:format-issue` - 2026-09-19T20:40:32 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
