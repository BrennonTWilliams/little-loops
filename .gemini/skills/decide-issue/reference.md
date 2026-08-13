# decide-issue reference

Extracted from `SKILL.md` (ENH-494 500-line budget). Referenced from Phase 3b, Phase 4, Phase 6,
Phase 9, and Integration.

## Phase 3b Pattern E — full rationale and worked example (ENH-2936)

Pattern E exists to close a specific remedy-chain gap (ENH-2866): an issue can name 2+ concrete
alternatives plus an explicit imperative to decide ("stamp it or move it to Out of scope with a
stated reason — do not leave it unaddressed") but state no preference. Pattern D requires a
stated preference to materialize inline alternatives, so this shape fell through every
extraction pattern and `decide-issue` exited `NO_ACTIONABLE_DECISIONS`, leaving
`decision_needed: true` unresolved indefinitely — nothing else in the pipeline can clear a
`decision_needed` flag it did not earn.

The imperative marker is what distinguishes this from the settled-informal-list case that Phase
3's auto-mode conservatism protects against elsewhere (automation must not re-litigate a list
the author already settled). Here the issue text explicitly *asks* for a decision, so scoring it
re-litigates nothing.

Worked example (from ENH-2866's `## Scope Boundaries`):
> "stamp it or move it to Out of scope with a stated reason — do not leave it unaddressed"

This matches Pattern E: two alternatives ("stamp it" / "move it to Out of scope") within 3 lines
of an imperative marker ("do not leave it unaddressed"), no stated preference between them. It
is materialized as `**Option A**: stamp it` / `**Option B**: move it to Out of scope` and routed
to Phase 4 scoring.

## When to Use vs. Related Commands

| Skill | Purpose |
|-------|---------|
| `refine-issue` | Fills knowledge gaps; may deposit competing options |
| `decide-issue` | Selects the best option from competing alternatives using codebase evidence |
| `wire-issue` | Traces all wiring touchpoints for the selected implementation |
| `confidence-check` | Evaluates implementation readiness score |

`decide-issue` is specifically for the "refine-issue deposited multiple options but hasn't
selected one" problem. It consumes `decision_needed: true` and produces a clear, annotated
winner so the pipeline can continue.

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
