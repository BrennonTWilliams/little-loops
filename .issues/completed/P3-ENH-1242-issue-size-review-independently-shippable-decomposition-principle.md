---
captured_at: "2026-04-21T21:48:57Z"
completed_at: "2026-04-21T22:50:17Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1242: Improve issue-size-review decomposition to use "independently shippable" principle

## Summary

The `/ll:issue-size-review` skill's Phase 4 decomposition guidance is too vague, allowing splits along artifact type lines (code | tests | docs) instead of capability lines. This causes child issues like "tests and documentation for X" that have no standalone value and can't ship independently. The fix is to add a concrete "independently shippable" test as the governing decomposition principle and a hard constraint against splitting tests/docs from the code they cover.

## Current Behavior

The skill's Phase 4 decomposition guidance allows splits along artifact type lines (code | tests | docs) instead of capability lines. The governing criterion "can be implemented independently" is vague enough that it permits child issues like "tests and documentation for X" that have no standalone value and cannot produce a meaningful PR on their own.

## Motivation

When decomposing FEAT-1236, the skill produced FEAT-1240 ("Tests and documentation for decide-issue") as a child separate from FEAT-1239 ("Wire decide-issue into Python pipeline"). FEAT-1240 cannot produce a meaningful PR on its own — its tests cover code from FEAT-1239, so FEAT-1239 can be "done" but temporarily untested until 1240 ships. This is a test/implementation coupling antipattern that the skill should actively prevent.

The root cause: the current criterion "can be implemented independently" is too vague. It doesn't distinguish between splitting along *capability* seams (good) vs. splitting along *artifact type* seams (bad).

## Expected Behavior

The skill's Phase 4 guidance enforces:
1. **"Independently shippable" as the governing test**: each child issue should be able to produce its own PR that includes tests for whatever new behavior it introduces
2. **Hard constraint against artifact-type splits**: tests and docs for behavior introduced by child A belong in child A — never in a dedicated tests/docs child
3. **Clear exception**: a test-only or doc-only issue is valid only when retroactively covering already-shipped code

The "Avoid" list in Best Practices reflects the same constraint.

## Proposed Solution

Three targeted edits to `skills/issue-size-review/SKILL.md`:

### 1. Phase 4 — child issue criteria (line ~187)

Replace:
> Can be implemented independently

With:
> Is "independently shippable" — could produce its own PR with tests for whatever it introduces

Add a new bullet constraint below the criteria list:
> **Never split by artifact type**: tests and docs for a child's new behavior belong in that child, not in a dedicated tests/docs child. The only exception: a test-only or doc-only issue for *already-shipped* code.

### 2. Best Practices — "Avoid" section (line ~402)

Add:
> - Splitting tests or documentation into a dedicated child issue for newly-introduced behavior (they belong with the implementation)

### 3. Best Practices — "Good Decomposition" section (line ~395)

Replace:
> Children are **independently implementable** (no blocking dependencies between them)

With:
> Children are **independently shippable** — each can produce a PR with tests for its own changes

## Files to Modify

- `skills/issue-size-review/SKILL.md` — three targeted edits (Phase 4 criteria, Avoid list, Good Decomposition)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact locations confirmed via codebase analysis:_

### Files to Modify
- `skills/issue-size-review/SKILL.md:187` — exact current text: `- Can be implemented independently`
- `skills/issue-size-review/SKILL.md:396` — exact current text: `- Children are **independently implementable** (no blocking dependencies between them)`
- `skills/issue-size-review/SKILL.md:401-406` — 4-item "Avoid" section; none of the existing bullets covers artifact-type splits

### Dependent Files (no changes needed)
- `skills/confidence-check/SKILL.md:563-565` — escalation callout to `/ll:issue-size-review`
- `skills/wire-issue/SKILL.md:441-443` — next-steps callout to `/ll:issue-size-review`
- `skills/issue-workflow/SKILL.md:81-82` — cross-reference callout

### Optional Consistency Update
- `docs/reference/COMMANDS.md:249` — mentions "independent scopes" for child issues; could align with new "independently shippable" language (not required for this issue)

### Tests
- No test file exists for this skill; guidance-only change, no new tests needed

## Acceptance Criteria

- Phase 4 child issue criteria uses "independently shippable" language and includes the artifact-type constraint
- "Avoid" list explicitly names tests/docs child issues for newly-introduced behavior as an antipattern
- "Good Decomposition" replaces "independently implementable" with "independently shippable"
- The exception case (retroactive test/doc issues for already-shipped code) is documented

## Implementation Steps

1. Edit Phase 4 criteria: replace "independently implemented" with "independently shippable" and add the artifact-type constraint bullet
2. Edit Good Decomposition: replace "independently implementable" with "independently shippable — each can produce a PR with tests for its own changes"
3. Edit Avoid list: add the tests/docs child antipattern

## Scope Boundaries

- **In scope**: Three targeted text edits to `skills/issue-size-review/SKILL.md` — Phase 4 criteria, Good Decomposition, and Avoid sections
- **Out of scope**: Changes to Python pipeline or automation scripts; behavioral changes to issue processing logic
- **Out of scope**: Updates to dependent skills (`confidence-check`, `wire-issue`, `issue-workflow`) — their callouts are read-only references that remain accurate after this change
- **Out of scope**: The optional consistency update to `docs/reference/COMMANDS.md:249` (flagged in Integration Map but not required for this issue)

## Impact

- **Priority**: P3
- **Effort**: Small — three targeted text edits to one file
- **Risk**: Low — documentation/guidance only; no behavioral changes to Python pipeline

## Related Key Documentation

_No documents linked._

## Labels

`enhancement`, `skill`, `decomposition`, `issue-management`

## Resolution

Three targeted edits to `skills/issue-size-review/SKILL.md`:
1. Phase 4 criteria: replaced "Can be implemented independently" with "independently shippable" and added artifact-type split constraint
2. Good Decomposition: replaced "independently implementable" with "independently shippable"
3. Avoid list: added antipattern for tests/docs child issues for newly-introduced behavior

## Session Log
- `/ll:ready-issue` - 2026-04-21T22:49:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/703b1905-bd69-4468-8591-1bb37d335db4.jsonl`
- `/ll:confidence-check` - 2026-04-21T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff12b2b-2ed2-40bc-9248-ba889878465e.jsonl`
- `/ll:refine-issue` - 2026-04-21T21:53:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4eb56bac-9901-4808-9ce3-1ce85ecc5f08.jsonl`
- `/ll:capture-issue` - 2026-04-21T21:48:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5c6e7c1-6ecf-4c7a-8c50-e42175af1abf.jsonl`
- `/ll:manage-issue` - 2026-04-21T22:50:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/703b1905-bd69-4468-8591-1bb37d335db4.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
