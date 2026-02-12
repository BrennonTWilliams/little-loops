---
discovered_date: 2026-01-24
discovered_by: capture_issue
discovered_source: argobots-ll-parallel-debug.log
discovered_external_repo: <external-repo>
---

# BUG-142: Worktree deleted while worker still running

## Summary

A worker's worktree directory is deleted while the worker is still actively processing, causing a `No such file or directory` error. This is distinct from BUG-140 (merge race condition) - the worktree itself disappears, not just merge conflicts.

## Context

Identified from conversation analyzing `argobots-ll-parallel-debug.log`:

**Timeline from log:**
```
19:07:18  Created worktree at .../worker-feat-009-20260124-190718
19:07:18  FEAT-009 begins processing
   ...    (worker actively running)
19:13:11  FEAT-009 failed: [Errno 2] No such file or directory:
          PosixPath('.../worker-feat-009-20260124-190718')
```

The worktree existed for ~6 minutes before disappearing while the worker was still active.

## Current Behavior

1. Worker is dispatched and worktree is created
2. Worker begins processing in the worktree
3. Something deletes the worktree directory while worker is running
4. Worker fails with `No such file or directory`

## Expected Behavior

Worktrees should only be cleaned up after their associated worker has completed (success or failure).

## Possible Root Cause

During the same run:
- `19:09:14-15`: ENH-011's merge failed, triggering retry/abort logic
- `19:09:15`: FEAT-010 was dispatched immediately after

The merge failure handling or worktree cleanup logic may have incorrectly cleaned up FEAT-009's worktree. Potential areas to investigate:

1. **Cleanup after merge failure**: Does `merge_coordinator` clean worktrees on failure?
2. **Worker tracking**: Is there a race where the worker pool loses track of active workers?
3. **Rebase abort cleanup**: Does `git rebase --abort` affect other worktrees?

## Proposed Solution

1. Add explicit tracking of "in-use" worktrees that cleanup cannot touch
2. Verify worktree ownership before any cleanup operation
3. Add assertion/guard in cleanup that checks if associated worker is still running

## Impact

- **Priority**: P2 (causes worker failures, work is lost)
- **Effort**: Medium (needs investigation of cleanup paths)
- **Risk**: Medium (affects parallel processing reliability)

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`bug`, `ll-parallel`, `worktree`, `race-condition`

---

**Priority**: P2 | **Created**: 2026-01-24

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/worker_pool.py`: Added `_active_worktrees: set[Path]` to track worktrees in active use by running workers
- `scripts/little_loops/parallel/worker_pool.py`: Register worktree after creation in `_process_issue()`, unregister in finally block
- `scripts/little_loops/parallel/worker_pool.py`: Added guard in `_cleanup_worktree()` to skip and log warning if worktree is in `_active_worktrees`
- `scripts/tests/test_worker_pool.py`: Added `TestActiveWorktreeProtection` class with 5 tests covering the fix

### Verification Results
- Tests: PASS (70 worker pool tests, 190 parallel module tests)
- Lint: PASS
- Types: PASS
