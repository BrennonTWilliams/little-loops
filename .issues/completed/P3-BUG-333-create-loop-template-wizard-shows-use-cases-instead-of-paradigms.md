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

Update the create_loop command's template selection step to present paradigm options instead of use-case templates. Each option should include the paradigm name and a brief explanation of when to use it.

## Implementation Steps

1. Locate the template selection logic in `commands/create_loop.md` (Step 0.1, around lines 47-66)
2. Replace inline use-case template list with paradigm list and descriptions
3. Wire selected paradigm into the subsequent wizard steps

## Steps to Reproduce

1. Run `/ll:create_loop`
2. Select "Start from template (Recommended)"
3. Observe: wizard presents use-case templates (codebase-scan, quality-gate) instead of paradigm options

## Actual Behavior

The template selection step lists existing use-case template files rather than the five loop paradigms.

## Root Cause

- **File**: `commands/create_loop.md`
- **Anchor**: Step 0.1, template selection logic (lines 47-66)
- **Cause**: Template list is hardcoded with use-case templates instead of paradigm definitions

## Integration Map

### Files to Modify
- `commands/create_loop.md` - Replace template list with paradigm options

### Dependent Files (Callers/Importers)
- N/A - standalone command

### Similar Patterns
- N/A

### Tests
- Manual testing of the create_loop wizard flow

### Documentation
- N/A

### Configuration
- N/A

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

**Completed** | Created: 2026-02-11 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-11
- **Verdict**: VALID (updated)
- Template selection logic is in `commands/create_loop.md` (not a skill)
- Templates at Step 0.1 (lines 47-66) are inline use-case definitions, not references to existing YAML files in `loops/`
- Core complaint is valid: paradigms should be presented instead of use-case templates
- Fixed: References corrected from "skill" to "command"

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Replaced Step 0.1 use-case template list with paradigm selection (goal, invariants, convergence, imperative)
- Updated Step 0.2 flow text for consistency with paradigm-first approach

### Verification Results
- Tests: PASS (2686 passed)
- Lint: N/A (markdown-only change)
- Types: N/A
- Integration: PASS
