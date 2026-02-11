---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-333: create_loop template wizard shows use-cases instead of paradigms

## Summary

When running `/ll:create_loop` and selecting "Start from template (Recommended)", the wizard presents use-case specific templates (e.g., codebase-scan, pre-pr-checks) rather than the loop paradigm options. The template path should instead present the five loop paradigms with descriptions, since paradigms are the fundamental building blocks that users should choose from.

## Current Behavior

The "Start from template" option in the create_loop wizard lists existing use-case templates (e.g., `codebase-scan.yaml`, `quality-gate.yaml`) rather than paradigm choices.

## Expected Behavior

When the user selects "Start from template", the wizard should present the five loop paradigms as options with short descriptions:

- **goal** - Define an end state and let the loop work toward it
- **convergence** - Repeatedly measure a metric until it stabilizes or reaches a target
- **invariants** - Define conditions that must always hold; loop runs checks and fixes violations
- **imperative** - Execute an ordered list of steps sequentially
- **FSM** - Define explicit states and transitions (all other paradigms compile to this)

## Motivation

Paradigms are the core abstraction of the loop system. Presenting use-case templates at this stage conflates template selection with paradigm selection, making it harder for users to understand the loop model. Users should first pick a paradigm, then optionally customize from there.

## Proposed Solution

Update the create_loop skill's template selection step to present paradigm options instead of use-case templates. Each option should include the paradigm name and a brief explanation of when to use it.

## Implementation Steps

1. Locate the template selection logic in the create_loop skill
2. Replace use-case template list with paradigm list and descriptions
3. Wire selected paradigm into the subsequent wizard steps

## Impact

- **Priority**: P3 - UX improvement for loop creation workflow
- **Effort**: Small - wizard prompt changes only
- **Risk**: Low - only affects the create_loop wizard flow
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop system and paradigm definitions |

## Labels

`bug`, `loops`, `ux`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
