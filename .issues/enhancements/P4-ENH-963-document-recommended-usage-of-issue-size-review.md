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

## Current Behavior

No documentation exists on the recommended trigger point for `/ll:issue-size-review`. The skill's `SKILL.md`, the `issue-workflow` guide, and the output templates for `ready-issue` and `confidence-check` make no mention of escalating to `issue-size-review` when an issue repeatedly fails readiness or confidence checks.

## Expected Behavior

Documentation in the following locations explicitly guides users to run `/ll:issue-size-review` when readiness/confidence checks continue to fail after two or more refinement passes:
- `skills/issue-size-review/SKILL.md` — "When to Activate" section lists the persistent-readiness-failure trigger
- `skills/issue-workflow/SKILL.md` — Refinement Phase includes a branch directing to `issue-size-review` on repeated NOT_READY
- `commands/ready-issue.md` — NEXT_STEPS output template suggests `issue-size-review` when issues have been refined 2+ times
- `skills/confidence-check/SKILL.md` — Escalation block under "Gaps to Address" points to `issue-size-review`
- `skills/wire-issue/SKILL.md` — Phase 10 NEXT STEPS includes a conditional note for persistent failures
- `commands/refine-issue.md` — NEXT STEPS includes an escalation branch
- `docs/guides/LOOPS_GUIDE.md` — Refine-limit guard description includes a "See also" pointer to `issue-size-review`

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

## Scope Boundaries

- **In scope**: Adding documentation text (prose, bullet points, blockquotes) to existing SKILL.md and command files at the locations identified in Implementation Steps
- **Out of scope**: Changing how `/ll:issue-size-review` works, modifying FSM loop behavior, adding new commands or skills, changing scoring thresholds, or any code changes

## Implementation Steps

1. Locate `skills/issue-size-review/SKILL.md` and add a "When to Use" section near the top
2. Update `/ll:issue-workflow` command or skill to include a decision branch: "still failing readiness after 2+ refinement passes → run issue-size-review"
3. Optionally update the "Next Steps" output of `/ll:ready-issue` and `/ll:confidence-check` to suggest `issue-size-review` when scores are persistently low

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `skills/wire-issue/SKILL.md:449-451` — append a conditional note to the Phase 10 NEXT STEPS block: when `confidence-check` or `ready-issue` continue to fail after this wiring pass, suggest running `/ll:issue-size-review [ID]`
5. Update `commands/refine-issue.md:443-444` — add a conditional line to the NEXT STEPS output template: "If `/ll:ready-issue` continues to score NOT_READY after 2+ refinement passes, run `/ll:issue-size-review [ID]`"
6. Update `docs/guides/LOOPS_GUIDE.md:261-263` — after the sentence describing the `failed` route when the refine cap is reached, add a "See also" note pointing to `/ll:issue-size-review` as the recommended next action

## Integration Map

### Files Modified
- `skills/issue-size-review/SKILL.md` — new bullet in `## When to Activate` for the persistent-readiness-failure trigger
- `skills/issue-workflow/SKILL.md` — blockquote note after Refinement Phase command list directing to `issue-size-review` on repeated NOT_READY
- `commands/ready-issue.md` — new conditional line in `## NEXT_STEPS` output template for 2+ refinement pass NOT_READY
- `skills/confidence-check/SKILL.md` — new `### Escalation` block in output template under `### Gaps to Address`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/SKILL.md:449-451` — Phase 10 NEXT STEPS routes users to `confidence-check → ready-issue` with no escalation note; directly upstream of the commands being changed, so its exit text leaves a gap in the guidance chain [Agent 1 finding]
- `commands/refine-issue.md:443-444,472` — NEXT STEPS shows `ready-issue → manage-issue` chain with no escalation branch; pipeline diagram at line 472 also omits escalation; the most-repeated command in the refinement loop [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:261-263` — `refine-to-ready-issue` loop failure description routes to `failed` state with no pointer to `issue-size-review` as the recommended next action [Agent 2 finding]

### Related Key Documentation
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:341-353` — "Size Review & Decomposition" section (no changes needed; describes flags)
- `docs/reference/COMMANDS.md:212-217` — `issue-size-review` command entry (no changes needed)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- No existing tests cover the content of these SKILL.md or command files; no tests will break from this pure-documentation change [Agent 3 finding]
- If content-locking tests are desired, follow the pattern in `scripts/tests/test_update_skill.py` and `scripts/tests/test_improve_claude_md_skill.py` — `Path.read_text()` + substring assertion, placed in `scripts/tests/test_issue_size_review_skill.py` [Agent 3 finding]

## Impact

- **Priority**: P4 - Low; workflow guidance gap, not a blocking deficiency
- **Effort**: Small - pure documentation additions across 7 files, no code changes
- **Risk**: Low - additive-only changes to markdown files; no logic altered
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `ux`, `captured`

---

## Session Log
- `/ll:manage-issue` - 2026-04-06T05:24:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/355e833e-00ff-4c02-b74a-e32eb7c366c6.jsonl`
- `/ll:ready-issue` - 2026-04-06T05:23:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52e725d0-991c-4e1a-9a0a-48fea1976285.jsonl`
- `/ll:wire-issue` - 2026-04-06T04:55:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29393bcc-663e-4c28-a557-5e66cac854a2.jsonl`
- `/ll:refine-issue` - 2026-04-06T04:49:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c769f1ff-fff7-4e6f-9950-bab87fe646ba.jsonl`
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f81b809e-fe37-4e61-92be-ecdf125880d9.jsonl`

---

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-04-06
- **Fix Commit**: TBD

### Changes Made
- `skills/issue-size-review/SKILL.md` — added persistent-readiness-failure trigger bullet to `## When to Activate`
- `skills/issue-workflow/SKILL.md` — added "Stuck on readiness?" blockquote after Refinement Phase command list
- `commands/ready-issue.md` — added conditional `issue-size-review` line to `## NEXT_STEPS` output template
- `skills/confidence-check/SKILL.md` — added `### Escalation` block under `### Gaps to Address`
- `skills/wire-issue/SKILL.md` — added conditional note to Phase 10 NEXT STEPS block
- `commands/refine-issue.md` — added escalation branch to NEXT STEPS output template
- `docs/guides/LOOPS_GUIDE.md` — added "See also" note after refine cap description

## Status

**Completed** | Created: 2026-04-05 | Completed: 2026-04-06 | Priority: P4
