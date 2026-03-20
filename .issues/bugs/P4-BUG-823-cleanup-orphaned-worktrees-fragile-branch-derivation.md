---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
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


## Verification Notes

**Verified**: 2026-03-19 | **Verdict**: NEEDS_UPDATE

**Core bug is VALID and still present** (orchestrator.py:273):
```python
branch_name = worktree_path.name.replace("worker-", "parallel/")
```
`GitLock.run()` (git_lock.py:81) returns `CompletedProcess` without raising on non-zero exit codes, so the `branch -D` failure at lines 274-278 is silently swallowed — confirming the silent-failure claim.

**Incorrect reference**: The issue states "Compare with `_cleanup_worktree` (line 679)" implying this is in `orchestrator.py`. Line 679 in `orchestrator.py` is `issue = queued.issue_info` — unrelated. The correct comparison is `scripts/little_loops/parallel/worker_pool.py`, `_cleanup_worktree` at line 641, which reads the actual branch via `git rev-parse --abbrev-ref HEAD` at line 660.

**Update needed**: Change the `## Current Behavior` comparison reference from `(line 679)` to `worker_pool.py:_cleanup_worktree (line 641)`.

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:49:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
