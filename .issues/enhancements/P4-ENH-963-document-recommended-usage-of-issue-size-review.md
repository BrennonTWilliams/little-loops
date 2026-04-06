---
discovered_date: 2026-04-05
discovered_by: capture-issue
testable: false
---

# ENH-963: Document Recommended Usage of issue-size-review

## Summary

Add documentation clarifying when to invoke `/ll:issue-size-review` — specifically, that it should be used as a follow-up on issues that fail readiness or outcome confidence checks after multiple refinement passes, rather than as a first-pass tool.

## Context

**Direct mode**: User description: "Document recommended usage of /ll:issue-size-review - Use on an Issue that does not pass readiness and outcome confidence scores after multiple refinement passes"

This guidance surfaced from observed workflow patterns: users sometimes run `/ll:issue-size-review` prematurely or skip it when it would be most valuable. The correct trigger is when an issue repeatedly fails `/ll:ready-issue` or `/ll:confidence-check` — meaning refinement alone isn't resolving the readiness gap, and the issue may be too large or poorly scoped.

## Motivation

Without clear guidance on when to invoke `/ll:issue-size-review`, users either:
1. Never use it — missing cases where decomposition would unlock a stuck issue
2. Use it too early — before refinement has had a chance to fill gaps that size-review can't address

Documenting the recommended trigger point (post-refinement, readiness/confidence still failing) closes this guidance gap and makes the issue workflow more actionable.

## Proposed Change

Document the recommended usage pattern in one or more of the following locations:
- The `issue-size-review` skill's `SKILL.md` under a "When to Use" or "Recommended Trigger" section
- The issue workflow guide (`/ll:issue-workflow`) as a branching decision after failed readiness checks
- `CLAUDE.md` or the issue lifecycle notes in `docs/`

The guidance should state:
> After two or more refinement passes (via `/ll:refine-issue` or `/ll:wire-issue`), if `/ll:ready-issue [ID]` still scores low on readiness or `/ll:confidence-check` still flags outcome uncertainty, run `/ll:issue-size-review [ID]`. A persistent readiness gap often signals the issue is too large or poorly decomposed rather than just under-researched.

## Implementation Steps

1. Locate `skills/issue-size-review/SKILL.md` and add a "When to Use" section near the top
2. Update `/ll:issue-workflow` command or skill to include a decision branch: "still failing readiness after 2+ refinement passes → run issue-size-review"
3. Optionally update the "Next Steps" output of `/ll:ready-issue` and `/ll:confidence-check` to suggest `issue-size-review` when scores are persistently low

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `documentation`, `ux`, `captured`

---

## Session Log
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f81b809e-fe37-4e61-92be-ecdf125880d9.jsonl`

---

## Status

**Open** | Created: 2026-04-05 | Priority: P4
