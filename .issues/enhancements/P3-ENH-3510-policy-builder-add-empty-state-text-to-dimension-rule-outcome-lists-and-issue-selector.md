---
id: ENH-3510
type: ENH
title: 'Policy builder: add empty-state text to dimension, rule, outcome lists and
  issue selector'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:56Z'
relates_to:
- ENH-3500
---

# ENH-3510: Policy builder: add empty-state text to dimension, rule, outcome lists and issue selector

## Summary

Found by ENH-3500 audit. Dimensions, rules and outcomes lists render nothing when empty (children=0, no text) in decision_table/lifecycle; the connected issue selector shows no note when the issue list is empty (conn-issue-note is blank). Only scenarios has 'No scenarios yet.'. Zero-dimension rubric/decision_table also reports 'No issues detected.' with export enabled. Repro: open offline builder, Open project with dimensions=[] (or Start blank in rubric); serve with ./issues returning {issues:[]}. Expected: a consistent empty-state hint per list. Evidence (run .loops/runs/enh-3500-audit-final/evidence): auth-empty-dimensions-*, auth-empty-rules-*, auth-empty-outcomes-*, conn-issues-empty-*.

## Current Behavior

The dimensions, rules and outcomes lists render nothing when empty (0 children, no text) in `decision_table`/`issue_lifecycle`. The connected issue selector leaves `#conn-issue-note` blank when the issue list is empty. Only the scenarios list shows an empty-state ('No scenarios yet.'). Zero-dimension `rubric`/`decision_table` models also report 'No issues detected.' with export enabled.

## Expected Behavior

Each of the dimensions, rules and outcomes lists, and the connected issue selector, shows a consistent empty-state hint (in the style of 'No scenarios yet.') when it has no entries. Whether a zero-dimension model should read 'No issues detected.' is decided in the implementation and recorded in the tests.

## Motivation

This enhancement would:
- Blank lists read as broken or still loading rather than empty; the scenarios list already shows the intended pattern.
- ENH-3500 audit evidence: `auth-empty-dimensions-*`, `auth-empty-rules-*`, `auth-empty-outcomes-*`, `conn-issues-empty-*`.

## Scope Boundaries

- **In scope**: empty-state text for `renderDimensions`, `renderRules`, `renderOutcomes`/`renderLifecycleOutcomes`, and the `#conn-issue-note` empty-issues case.
- **Out of scope**: redesigning the scenarios empty-state; changing validation rules (e.g. requiring at least one dimension); styling beyond reusing the existing `.hint` treatment.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

## Program Design

### Types

- `StatusClass: str` — CSS class name strings only; no new persisted shapes.

### Signatures

- `renderDimensions() -> void`
- `renderRules() -> void`
- `renderOutcomes() -> void`
- `renderLifecycleOutcomes() -> void`
- `renderConnected(st) -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderAll` -> `renderDimensions` / `renderRules` / `renderOutcomes` -> new empty-state branch

## Implementation Steps

1. Define one empty-state helper/class shared with the scenarios 'No scenarios yet.' treatment.
2. Add an empty branch to each render function and the `#conn-issue-note` empty-issues case.
3. Add template tests for each empty state; re-run the ENH-3500 audit probe fixtures.

## Impact

- **Priority**: P3 - polish; no data or correctness impact
- **Effort**: Small - four render branches plus tests
- **Risk**: Low - additive text only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-19T20:40:26 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
