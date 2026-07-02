# decide-issue reference

Extracted from `SKILL.md` (ENH-494 500-line budget). Referenced from Phase 9.

## Phase 9 Output Report Template

```
================================================================================
DECIDE ISSUE: {{ISSUE_ID}}
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH|EPIC]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]
- decision_needed was: [true | false | absent]

## OPTIONS FOUND (N total)
- Option A: [title] — [one-line description]
- Option B: [title] — [one-line description]
...

## SCORING

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [A]    | N/3         | N/3        | N/3         | N/3  | N/12  |
| [B]    | N/3         | N/3        | N/3         | N/3  | N/12  |

## DECISION
✓ Selected: [option title] (score: N/12)

Reasoning: [2-3 sentences]

## CHANGES APPLIED
- [Annotated issue with > **Selected:** callout | Skipped (idempotent)]
- [Appended ### Decision Rationale section | Skipped (idempotent)]
- decision_needed: [set to false | already false — no change]

## DRY RUN PREVIEW  ← only shown when --dry-run
---
[Full annotation content that would be written]
---

## FILE STATUS
- [Modified | Not modified (--dry-run | nothing to change)]

## NEXT STEPS
- Run `/ll:wire-issue {{ISSUE_ID}}` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue {{ISSUE_ID}}` to validate the issue is ready to implement
- Run `/ll:manage-issue feature implement {{ISSUE_ID}}` to implement

================================================================================
```
