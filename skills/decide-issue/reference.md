# decide-issue reference

Extracted from `SKILL.md` (ENH-494 500-line budget). Referenced from Phase 4, Phase 6, and Phase 9.

## Phase 6 Decision Rationale Subsection Template

```markdown
### Decision Rationale

Decided by `/ll:decide-issue` on YYYY-MM-DD.

**Selected**: [option title]

**Reasoning**: [2-3 sentence explanation citing specific codebase evidence]

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| [Option A] | N/3 | N/3 | N/3 | N/3 | N/12 |
| [Option B] | N/3 | N/3 | N/3 | N/3 | N/12 |

**Key evidence**:
- [Option A]: [1-2 sentence evidence summary]
- [Option B]: [1-2 sentence evidence summary]
```

## Phase 4 Agent Prompt Template

For each option, the agent prompt template is:

```
Use Agent tool with subagent_type="ll:codebase-pattern-finder"

Prompt:
Find codebase evidence for or against this implementation option for {{ISSUE_ID}}.

Issue: {{ISSUE_ID}} — {{issue title}}

Option being evaluated: "{{option_title}}"
Option description: {{option_description}}

Find:
1. Existing patterns that use this approach — similar implementations already in the codebase
2. Call site count — how many places currently use a similar pattern
3. Existing utilities, helpers, or modules that this option could reuse
4. Patterns that conflict with or differ from this approach (evidence against)
5. Test patterns for this type of implementation

Return:
- Evidence FOR: existing patterns, utilities, call sites (with file:line references)
- Evidence AGAINST: conflicting patterns or missing utilities that would require new infrastructure
- Reuse score: 0 (builds from scratch) to 3 (reuses existing utilities directly)
- Summary: 1-2 sentence assessment of codebase fit
```

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
