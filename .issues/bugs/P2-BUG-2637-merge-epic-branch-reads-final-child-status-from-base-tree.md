---
id: BUG-2637
title: merge_epic_branch reads final-child status from base tree, so the completing run can never auto-merge
type: BUG
priority: P2
status: open
labels: [loops, fsm, epic-branches, merge-coordinator]
discovered_date: "2026-07-14"
discovered_by: manual
parent: EPIC-2575
relates_to:
- BUG-2614
---

# BUG-2637: merge_epic_branch reads final-child status from the base tree, so the run that completes an EPIC can never auto-merge

## Summary

The `merge_epic_branch` state in
`scripts/little_loops/loops/auto-refine-and-implement.yaml` decides whether to
merge the epic branch back to base by computing epic progress from issue files
in the **current working tree (base branch)**. When the loop completes the
**final** child of an EPIC, that child's `status: done` was written and
committed **inside the epic-branch worktree** — it does not exist on the base
tree. So the all-children-done gate reads the final child as still `open`,
prints `held_open`, and the auto-merge never fires. No later run can fix it:
nothing brings the `done` status back to base while the merge is held, so the
EPIC deadlocks in `held_open` and requires a manual merge. This is a sibling of
BUG-2614 (which fixed the multi-run "committed but never merged" case) — the
final-child vantage-point gap was left open.

## Current Behavior

On the run that completes the last open child of an EPIC, `merge_epic_branch`
evaluates child status against the checked-out base tree, where the just-
completed child still reads `open`. `all_done` is `False`, verdict is
`held_open`, and the epic branch is left unmerged indefinitely.

Observed in run `auto-refine-and-implement-20260714T103349`
(`--context scope=EPIC-2575`): `summary.json` shows
`"epic_merge_verdict":"held_open"` even though ENH-2578 (the last child) was
verified `done` on the epic branch (commit `158f2181`).

## Expected Behavior

When the loop completes the final child and `merge_to_base_on_complete: true`
with a passing verify gate, the run should resolve `all_done == True` and merge
the epic branch to base (`epic_merge_verdict=merged`). A branch with a genuinely
still-open sibling child should still report `held_open`.

## Steps to Reproduce

1. Configure `parallel.epic_branches.merge_to_base_on_complete: true`.
2. Create an EPIC whose children are all `done` except one still-open child.
3. Run `ll-loop run auto-refine-and-implement --context scope=EPIC-<n>` so the
   loop completes that final child (writing `status: done` on the epic branch).
4. Observe: `summary.json` reports `"epic_merge_verdict":"held_open"` and the
   epic branch is not merged, despite all children being effectively done.
5. Confirm the split:
   `git show <epic-branch>:<child-path> | grep status` → `done`, but
   `grep status <child-path>` (base tree) → `open`.

## Root Cause

- **File**: `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- **Anchor**: `merge_epic_branch` state (~lines 525–546)
- **Cause**: The gate computes progress from the base working tree:
  ```python
  all_issues = find_issues(cfg, status_filter={...})   # reads base tree
  prog = compute_epic_progress(epic_id, all_issues)
  all_done = (total > 0 and done_count == total and blocked_count == 0 and cancelled_count == 0)
  if not all_done:
      print("held_open"); raise SystemExit(0)
  ```
  `find_issues` reads the checked-out (base) tree, but the completing child's
  `done` status lives only on the epic-branch tip — so the deciding status is
  invisible to the very gate that needs it.

## Proposed Solution

Evaluate child status against the **epic branch tip** (where completions land)
rather than the base working tree:

1. Read each child's frontmatter via `git show <epic-branch>:<issue-path>`
   before computing `all_done` (lowest-risk, no worktree checkout).
2. Or union base-tree status with epic-branch-tip status (a child counts as
   `done` if done on either side) so already-merged siblings and the just-
   completed final child both count.

## Impact

- **Priority**: P2 — silently strands verified epic work on an unmerged branch;
  every single-remaining-child EPIC hits it, and it masquerades as a clean
  `success` verdict.
- **Effort**: Small — localized to one FSM state's status computation; reuses
  `git show` + existing `compute_epic_progress`.
- **Risk**: Medium — merge-gate logic; must not introduce false merges when a
  sibling is genuinely open. Covered by the AC regression tests.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] A single `auto-refine-and-implement --context scope=EPIC-<n>` run that
      completes the final child produces `epic_merge_verdict=merged` (not
      `held_open`), given `merge_to_base_on_complete: true` and a passing verify.
- [ ] Regression test (`scripts/tests/test_builtin_loops.py` or merge-coordinator
      test) simulating a final child whose `done` status exists only on the epic
      branch, asserting `all_done == True`.
- [ ] A branch with a genuinely-open sibling child still reports `held_open`.
- [ ] `python -m pytest scripts/tests/` green.

## Notes

Discovered while manually reconciling EPIC-2575. Separately, that epic branch had
gone **stale** (base advanced 17 commits and independently re-implemented the
codequery providers), so its only unique content was the wire-issue Phase 3.6
delta (`158f2181`). The merge coordinator arguably should also surface staleness,
but that is out of scope here.

## Status

**Open** | Created: 2026-07-14 | Priority: P2
