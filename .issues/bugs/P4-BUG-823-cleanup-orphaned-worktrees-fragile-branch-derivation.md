---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# BUG-823: `_cleanup_orphaned_worktrees` fragile branch name derivation

## Summary

`ParallelOrchestrator._cleanup_orphaned_worktrees` derives the branch name from the worktree directory name using `str.replace("worker-", "parallel/")`. This is fragile — if the naming convention changes in one place but not the other, orphan cleanup silently fails to delete the branch because the `branch -D` return code is not checked.

## Location

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Line(s)**: 271-278 (at scan commit: 8c6cf90)
- **Anchor**: `in method ParallelOrchestrator._cleanup_orphaned_worktrees`
- **Code**:
```python
branch_name = worktree_path.name.replace("worker-", "parallel/")
self._git_lock.run(
    ["branch", "-D", branch_name],
    ...
)
```

## Current Behavior

Branch name is derived from directory name via string replacement. If the derived name doesn't match the actual branch, `branch -D` silently fails (return code not checked). Compare with `_cleanup_worktree` (line 679) which reads the actual branch name via `git rev-parse --abbrev-ref HEAD`.

## Expected Behavior

Either read the actual branch name from the worktree (using `git rev-parse`) or check the return code of `branch -D` and log a warning on failure.

## Steps to Reproduce

1. Interrupt `ll-parallel` during a run to create orphaned worktrees
2. On the next run, observe that orphaned branches may not be deleted if the naming convention has any inconsistency

## Proposed Solution

Use `git -C <worktree_path> rev-parse --abbrev-ref HEAD` to read the actual branch name before deletion, matching the pattern in `_cleanup_worktree`. Alternatively, check the return code of `branch -D` and log a warning.

## Impact

- **Priority**: P4 - Orphaned branches accumulate but don't cause functional issues
- **Effort**: Small - Mirror existing pattern from `_cleanup_worktree`
- **Risk**: Low - Additive improvement
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `cleanup`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Session Log
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
