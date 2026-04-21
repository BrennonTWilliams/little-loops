---
captured_at: "2026-04-21T21:48:57Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
---

# ENH-1242: Improve issue-size-review decomposition to use "independently shippable" principle

## Summary

The `/ll:issue-size-review` skill's Phase 4 decomposition guidance is too vague, allowing splits along artifact type lines (code | tests | docs) instead of capability lines. This causes child issues like "tests and documentation for X" that have no standalone value and can't ship independently. The fix is to add a concrete "independently shippable" test as the governing decomposition principle and a hard constraint against splitting tests/docs from the code they cover.

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

## Acceptance Criteria

- Phase 4 child issue criteria uses "independently shippable" language and includes the artifact-type constraint
- "Avoid" list explicitly names tests/docs child issues for newly-introduced behavior as an antipattern
- "Good Decomposition" replaces "independently implementable" with "independently shippable"
- The exception case (retroactive test/doc issues for already-shipped code) is documented

## Implementation Steps

1. Edit Phase 4 criteria: replace "independently implemented" with "independently shippable" and add the artifact-type constraint bullet
2. Edit Good Decomposition: replace "independently implementable" with "independently shippable — each can produce a PR with tests for its own changes"
3. Edit Avoid list: add the tests/docs child antipattern

## Impact

- **Priority**: P3
- **Effort**: Small — three targeted text edits to one file
- **Risk**: Low — documentation/guidance only; no behavioral changes to Python pipeline

## Related Key Documentation

_No documents linked._

## Labels

`enhancement`, `skill`, `decomposition`, `issue-management`

## Session Log
- `/ll:capture-issue` - 2026-04-21T21:48:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5c6e7c1-6ecf-4c7a-8c50-e42175af1abf.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
