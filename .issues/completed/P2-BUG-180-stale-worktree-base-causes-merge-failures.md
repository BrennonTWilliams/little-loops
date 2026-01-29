---
discovered_date: 2026-01-28
discovered_by: capture_issue
---

# BUG-180: Stale worktree base commits cause merge failures in ll-sprint

## Summary

When `ll-sprint` creates worktrees, they are based on the current `main` HEAD. By the time workers complete and attempt to merge, `git pull --rebase origin main` advances `main` beyond the worktrees' base commit. This causes merge/rebase failures with "skipped previously applied commit" warnings and conflicts on commits that appear to have content "already upstream."

## Context

Identified from investigating `ll-sprint run sprint-improvements` failure where all 4 parallel workers (ENH-175, ENH-176, ENH-177, ENH-178) failed to merge despite being the first in their wave.

**Error output:**
```
[20:05:46] Merge conflict for ENH-176, attempting rebase (retry 1/2)
[20:05:46] Merge failed for ENH-176: Rebase failed after merge conflict: warning: skipped previously applied commit daae513
warning: skipped previously applied commit abda4a1
...
hint: use --reapply-cherry-picks to include skipped commits
Rebasing (1/2)
dropping d15981039cb529d2f2bf44f60a147002e876ed7a refactor(create-sprint): reorganize validation flow for optional name argument -- patch contents already upstream
Rebasing (2/2)
error: could not apply 27c0e3c... feat(sprint): reduce default max_workers from 4 to 2
```

## Current Behavior

1. Worktrees created from `main` at time T₀ (all based on same commit)
2. Workers run in parallel, making commits on their branches
3. Meanwhile, `main` may advance (commits pushed to origin)
4. When first worker completes and merge begins:
   - `git checkout main` in main repo
   - `git pull --rebase origin main` advances main to T₁
   - `git merge worker-branch --no-ff` fails (worker branch based on T₀)
5. Conflict handler attempts `git rebase main` in worktree
6. Rebase sees commits from T₀→T₁ as "already upstream" and drops them
7. Real work commits then conflict with the advanced main
8. All workers fail despite no actual conflicting changes

**Key insight:** The first merge (ENH-176) failed immediately, not due to other workers' changes but due to main advancing during the pull.

## Expected Behavior

Worktree branches should merge successfully when:
1. Their changes don't actually conflict with main
2. The only "conflict" is that main advanced since worktree creation

## Root Cause

The merge coordinator's flow has a timing vulnerability:

```
_process_merge():
  git checkout main                    # Switch to main
  git pull --rebase origin main        # ← ADVANCES MAIN (T₀ → T₁)
  git merge worker-branch --no-ff      # ← CONFLICTS (branch based on T₀)
```

When the pull advances main, worker branches become stale. The subsequent rebase in `_handle_conflict()` tries to replay commits onto the new main, but:
- Some commits are detected as duplicates ("already upstream")
- Other commits conflict with changes made between T₀ and T₁

## Proposed Solution

Combine pre-flight sync with worker-side base updates for comprehensive coverage:

### Part 1: Pre-flight pull before worktree creation
Ensure `main` is fully synced with origin BEFORE creating any worktrees:

```python
def _setup_worktrees(self):
    # Sync main with origin first
    self._git_lock.run(["pull", "--rebase", "origin", "main"], cwd=self.repo_path)
    # Then create worktrees from up-to-date main
    for issue in issues:
        self._setup_worktree(...)
```

### Part 2: Worker base update before merge
Have each worker fetch and rebase onto latest main BEFORE queuing for merge (not during conflict retry):

```python
def _process_issue(self, issue):
    # ... work done ...
    # Before returning result, update branch base
    subprocess.run(["git", "fetch", "origin", "main"], cwd=worktree_path)
    subprocess.run(["git", "rebase", "origin/main"], cwd=worktree_path)
    # Now queue for merge with current base
```

### Why both parts?

- **Part 1** ensures a clean starting state (good hygiene)
- **Part 2** handles main advancing during sprint execution (the actual failure mode)

Part 2 is essential because it directly addresses the observed failure: "first merge failed immediately, not due to other workers' changes but due to main advancing during the pull." It also fails early in the worker context rather than during merge coordination.

## Affected Components

- **Tool**: ll-sprint, ll-parallel
- **Module**: `scripts/little_loops/parallel/merge_coordinator.py` (line 779-860)
- **Module**: `scripts/little_loops/parallel/worker_pool.py` (worktree creation)
- **Module**: `scripts/little_loops/parallel/orchestrator.py` (workflow coordination)

## Impact

- **Priority**: P2 (causes complete sprint failures)
- **Effort**: Medium
- **Risk**: Low (additive fix)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Parallel processing design |

## Related Issues

- **ENH-143**: Detect overlapping file modifications (related but different scope)
- **BUG-157**: Post-merge rebase (completed - different failure mode)

## Labels

`bug`, `ll-sprint`, `ll-parallel`, `merge-coordinator`, `git`

---

## Status

**Completed** | Created: 2026-01-28 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-28
- **Status**: Completed

### Changes Made

1. **worker_pool.py**: Added `_update_branch_base()` method that fetches `origin/main` and rebases the worker branch onto it before returning from `_process_issue()`. This ensures worker branches are based on latest main before entering the merge queue.

2. **worker_pool.py**: Integrated the base update call as Step 9 in `_process_issue()`, after work verification passes but before returning success. If the rebase fails (genuine conflict), worker fails early with a clear error.

3. **merge_coordinator.py**: Updated `_handle_conflict()` to fetch `origin/main` and rebase onto it (instead of just `main`) when retrying after merge conflict. Falls back to `main` if no remote is configured.

4. **test_worker_pool.py**: Updated 3 tests to mock the new `_update_branch_base()` method.

### Verification Results
- Tests: PASS (123/123)
- Lint: PASS
- Types: PASS
