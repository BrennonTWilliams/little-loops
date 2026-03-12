---
title: Add /ll:review-loop to COMMANDS.md reference
type: ENH
priority: P3
effort: Low
impact: Low
risk: Low
---

## Summary

The `/ll:review-loop` skill is missing from `docs/reference/COMMANDS.md` — both the detailed "Automation Loops" section and the Quick Reference table need entries added.

## Current Behavior

`/ll:review-loop` exists as a skill (`skills/review-loop/SKILL.md`) and is documented in `README.md` and `docs/guides/LOOPS_GUIDE.md`, but `COMMANDS.md` has no mention of it.

## Proposed Solution

Add a detailed section under "## Automation Loops" in `docs/reference/COMMANDS.md`:

```markdown
### `/ll:review-loop`
Review an existing FSM loop configuration for quality, correctness, consistency, and potential improvements.

**Arguments:**
- `loop_name` (optional): Name or path of the loop to review

**Output:** Findings grouped by severity (Error/Warning/Suggestion) with proposed fixes.
```

Add an entry to the Quick Reference table:

```markdown
| `review-loop` | Review and improve existing FSM loop configurations |
```

## Affected Files

- `docs/reference/COMMANDS.md`

## Implementation Steps

1. Read `skills/review-loop/SKILL.md` for accurate description, arguments, and behavior
2. Add detailed section under Automation Loops (after `/ll:create-loop`)
3. Add row to Quick Reference table (alphabetical position near `resume`)
