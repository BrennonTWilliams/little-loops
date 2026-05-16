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

## Expected Behavior

`/ll:review-loop` should have a detailed entry in `docs/reference/COMMANDS.md` under the "Automation Loops" section and a row in the Quick Reference table, consistent with other loop-related skills.

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

## Scope Boundaries

- Only add documentation entries to `COMMANDS.md` — no code changes
- Do not modify the skill itself or other documentation files
- Follow existing formatting conventions in `COMMANDS.md`

## Affected Files

- `docs/reference/COMMANDS.md`

## Implementation Steps

1. Read `skills/review-loop/SKILL.md` for accurate description, arguments, and behavior
2. Add detailed section under Automation Loops (after `/ll:create-loop`)
3. Add row to Quick Reference table (alphabetical position near `resume`)

## Impact

- **Priority**: P3 - Documentation gap, not blocking functionality
- **Effort**: Low - Single file edit with clear template to follow
- **Risk**: Low - Documentation-only change, no code impact
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `low-effort`

## Resolution

- **Status**: Completed
- **Date**: 2026-03-12
- **Changes**:
  - Added detailed `/ll:review-loop` section under "Automation Loops" in `docs/reference/COMMANDS.md` with arguments, flags, and see-also links
  - Added `review-loop` row to Quick Reference table in alphabetical position

## Session Log
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d52031f4-3086-4912-9d38-46e53a5c63fb.jsonl`
- `/ll:manage-issue` - 2026-03-12 - ENH-680 implementation

---

**Completed** | Created: 2026-03-12 | Resolved: 2026-03-12 | Priority: P3
