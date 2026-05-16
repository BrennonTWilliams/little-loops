---
id: ENH-981
discovered_date: 2026-04-07
discovered_by: capture-issue
testable: false
---

# ENH-981: Add /ll:wire-issue as first Next Steps item in refine-issue

## Summary

The `Next Steps` section in `/ll:refine-issue` currently recommends `/ll:ready-issue` then `/ll:manage-issue`, but omits `/ll:wire-issue` — the integration wiring pass that should run after research refinement and before readiness validation. Adding it first in the list completes the recommended workflow.

## Current Behavior

The `Next Steps` section in `commands/refine-issue.md` (lines ~444–446) reads:

```
- Run `/ll:ready-issue [ID]` to validate the enriched issue
- Run `/ll:manage-issue` to implement
- If `/ll:ready-issue` continues to score NOT_READY after 2+ refinement passes, run `/ll:issue-size-review [ID]`...
```

`/ll:wire-issue` is not mentioned in this section.

## Expected Behavior

The `Next Steps` section leads with `/ll:wire-issue`, then the existing two items:

```
- Run `/ll:wire-issue [ID]` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue [ID]` to validate the enriched issue
- Run `/ll:manage-issue` to implement
- If `/ll:ready-issue` continues to score NOT_READY after 2+ refinement passes, run `/ll:issue-size-review [ID]`...
```

## Motivation

`/ll:wire-issue` fills in integration points — callers, entry points, test hooks — that `refine-issue` doesn't cover. Running it before readiness validation means `ready-issue` has complete wiring to evaluate, reducing NOT_READY verdicts caused by missing integration context rather than poor research.

## Proposed Solution

Edit `commands/refine-issue.md`: locate the `Next Steps` bullet list and prepend a bullet for `/ll:wire-issue [ID]` before the `/ll:ready-issue` bullet.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — `Next Steps` bullet list (~line 444)

### Dependent Files (Callers/Importers)
- N/A (documentation-only change)

### Similar Patterns
- `skills/capture-issue/SKILL.md` — its Integration section also lists next steps commands; check for consistency if desired

### Tests
- N/A

### Documentation
- `commands/refine-issue.md` is the only file requiring change

### Configuration
- N/A

## Implementation Steps

1. Open `commands/refine-issue.md`
2. Find the `Next Steps` section bullet list (around line 444)
3. Insert `- Run \`/ll:wire-issue [ID]\` to add integration wiring (callers, entry points, test hooks)` as the first bullet, before the `/ll:ready-issue` bullet
4. Verify the section reads in order: wire-issue → ready-issue → manage-issue

## Scope Boundaries

- Only `commands/refine-issue.md` Next Steps section is in scope
- No changes to `skills/capture-issue/SKILL.md` or other workflow diagrams (those are separate issues if desired)
- No changes to the workflow flow diagrams or integration tables in refine-issue.md

## Impact

- **Priority**: P3 - Low-friction doc fix that improves workflow discoverability
- **Effort**: Small - single-file, single-section edit
- **Risk**: Low - documentation-only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked._

## Resolution

Added `/ll:wire-issue [ID]` as the first bullet in the `## NEXT STEPS` section of `commands/refine-issue.md` (line 444), before the existing `/ll:ready-issue` bullet. The section now reads: wire-issue → ready-issue → manage-issue.

## Labels

`enhancement`, `completed`

## Status

**Completed** | Created: 2026-04-07 | Completed: 2026-04-07 | Priority: P3

---

## Session Log
- `/ll:ready-issue` - 2026-04-07T18:36:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aff59e17-bf42-492e-855a-73322684e41f.jsonl`
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a14635ac-d01b-4670-8032-74bc9a150bc1.jsonl`
