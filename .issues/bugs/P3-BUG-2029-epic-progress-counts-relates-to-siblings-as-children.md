---
id: BUG-2029
title: epic-progress counts relates_to siblings as children
type: BUG
priority: P3
status: open
captured_at: "2026-06-08T23:16:56Z"
discovered_date: "2026-06-08"
discovered_by: capture-issue
labels: [epic-progress, issue-management, relates_to]
---

# BUG-2029: epic-progress counts relates_to siblings as children

## Summary

`compute_epic_progress` builds its child set as the union of `relates_to:` (forward) and `parent:` (backward). When an EPIC uses `relates_to:` for sibling/context cross-references rather than children, those sibling issues are counted as children, inflating progress totals and oldest-open displays.

**Observed**: EPIC-2027 (`relates_to: [EPIC-1707, EPIC-1918, ENH-1911]`) reports `0/3 done` with oldest-open `EPIC-1707 (13 days)`, even though only ENH-1911 has `parent: EPIC-2027`. The real child count is 1.

## Current Behavior

`compute_epic_progress` builds its child set as the union of `relates_to:` (forward) and `parent:` (backward) edges. Any issue referenced in an EPIC's `relates_to:` field is counted as a child, inflating progress totals and oldest-open displays regardless of whether those issues are true children or sibling/context cross-references.

## Root Cause

`scripts/little_loops/issue_progress.py:85` — `compute_epic_progress`:

```python
forward_ids: set[str] = set(epic_info.relates_to)   # ← treats ALL relates_to as children
backward_ids: set[str] = {i.issue_id for i in all_issues if i.parent == epic_id}
child_ids = forward_ids | backward_ids
```

`relates_to:` is a general cross-reference field (siblings, dependencies, context). It is not a parent→child edge. Only `parent:` (on the child side) is a reliable child indicator.

## Steps to Reproduce

1. Create an EPIC with `relates_to: [EPIC-X, EPIC-Y, ENH-Z]` where EPIC-X and EPIC-Y are siblings, not children.
2. Run `ll-issues epic-progress <epic-id>` — reports 3 children instead of 1.
3. Also visible in `ll-issues list` progress column.

## Expected Behavior

`epic-progress` child set = issues where `parent: <EPIC-ID>` only. The `relates_to:` field should not contribute to the child set.

## Proposed Solution

Remove the `forward_ids` union from `compute_epic_progress`. Use only `backward_ids` (the `parent:` reverse edge):

```python
child_ids: set[str] = {i.issue_id for i in all_issues if i.parent == epic_id}
```

If forward-declared children are still desired, introduce a separate `children:` frontmatter field (distinct from `relates_to:`) and update the resolver to use that field instead.

## Implementation Steps

1. Edit `scripts/little_loops/issue_progress.py` — remove `forward_ids` from `compute_epic_progress`, use only the `parent:` backward edge.
2. Update the docstring to remove the `relates_to: (forward)` claim.
3. Verify `ll-issues epic-progress EPIC-2027` now reports `0/1`.
4. Check `ll-issues list` progress column for the same EPIC.
5. Run existing tests: `python -m pytest scripts/tests/ -k epic`.

## Impact

- **Priority**: P3 — epic progress counts are inaccurate when EPICs use `relates_to:` for sibling/context cross-references; misleading but not blocking
- **Effort**: Small — single-function change in `compute_epic_progress`; remove the `forward_ids` union and update the docstring
- **Risk**: Low — removes an incorrect code path; EPICs that rely solely on `parent:` back-links are unaffected
- **Breaking Change**: No

## Acceptance Criteria

- `ll-issues epic-progress EPIC-2027` reports `0/1 done` (ENH-1911 only).
- EPIC-1707 and EPIC-1918 no longer appear as children of EPIC-2027.
- `ll-issues list` progress column matches the corrected count.
- No regression: EPICs that rely solely on `parent:` back-links continue to work correctly.

## Session Log
- `/ll:format-issue` - 2026-06-08T23:29:42 - `ebb63dbd-49fa-42fb-81b2-2bb56096c150.jsonl`
- `/ll:capture-issue` - 2026-06-08T23:16:56Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8518210d-a8fb-472f-a76d-946f02b2ae27.jsonl`
