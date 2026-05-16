---
discovered_commit: 841d8e8
discovered_date: 2026-01-24
discovered_source: argobots-ll-parallel-debug.log
discovered_external_repo: <external-repo>
---

# BUG-140: Race condition between worktree creation and merge operations

## Summary

Worktree creation and merge processing can run concurrently, causing transient merge conflicts. When a worker completes and queues a merge, the orchestrator can immediately dispatch the next issue, creating a new worktree while the merge coordinator is still processing.

## Evidence from Log

**Log File**: `argobots-ll-parallel-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
**Affected External Issues**: ENH-1002

### Timeline

```
18:14:42  ENH-1002 completes, queue_merge() called
18:14:42  Git status shows: D .claude/ll-context-state.json, M .gitignore
18:14:42  FEAT-1000 dispatched to worker pool (concurrent with merge)
18:14:42  Stashed local changes before merge
18:14:42  FEAT-1000 worktree creation: "Copied .claude/ directory to worktree"
18:14:43  Git status output: ?? .worktrees/
18:14:43  Merge conflict for ENH-1002, attempting rebase (retry 1/2)
```

### Root Cause

The `_on_worker_complete` callback in `orchestrator.py:652` calls `queue_merge(result)` at line 697, which is asynchronous (runs in the merge coordinator's background thread). Control returns immediately to the orchestrator, allowing the main loop to dispatch new workers.

Meanwhile, worktree creation:
1. Copies `.claude/` directory to the new worktree
2. Creates files/directories in `.worktrees/`
3. Runs git operations on the main repo

These operations overlap with the merge coordinator's:
1. `git status --porcelain` checks
2. Stash operations
3. Merge attempts

The concurrent file operations cause git to see inconsistent state, triggering spurious conflicts.

## Current Behavior

1. Worker completes → `queue_merge()` called (asynchronous)
2. Orchestrator immediately dispatches next worker
3. Worktree creation runs concurrently with merge processing
4. Git sees unstable repository state → reports conflict
5. Merge coordinator retries, eventually succeeds after worktree creation completes

## Expected Behavior

Worktree creation and merge operations should not overlap. Options:
1. Use `GitLock` during worktree creation (in `WorkerPool`)
2. Wait for merge completion before dispatching next worker
3. Serialize worktree creation with merge operations via a shared lock

## Affected Components

- **Tool**: ll-parallel
- **Module**: `scripts/little_loops/parallel/orchestrator.py` (dispatch timing)
- **Module**: `scripts/little_loops/parallel/worker_pool.py` (worktree creation)
- **Module**: `scripts/little_loops/parallel/merge_coordinator.py` (merge processing)
- **Related**: `GitLock` coordination

## Possible Fix

In `worker_pool.py`, wrap worktree creation in `GitLock` to serialize with merge coordinator operations:

```python
with self._git_lock:
    self._create_worktree(issue)
```

Or in `orchestrator.py`, ensure merge completes before dispatching:

```python
self.merge_coordinator.queue_merge(result)
self.merge_coordinator.wait_for_completion(timeout=60)  # Add this
# Then allow dispatch of next worker
```

## Impact

- **Severity**: Medium (P2)
- **Frequency**: Medium (occurs when workers complete close together)
- **Data Risk**: Low - conflicts auto-resolve on retry, no work is lost

---

## Labels
- component:parallel
- type:bug

## Status
**Completed** | Created: 2026-01-24 | Completed: 2026-01-24 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/orchestrator.py`: Added `wait_for_completion(timeout=120)` call after `queue_merge()` in `_on_worker_complete()` callback. This ensures merges complete before the callback returns, preventing new worker dispatch while merge is in progress.

### Verification Results
- Tests: PASS (1845 passed, 1 pre-existing unrelated failure)
- Lint: PASS
- Types: PASS

### Implementation Notes
The fix implements option 2 from the issue: waiting for merge completion before dispatching the next worker. This is cleaner than wrapping worktree creation in `GitLock` because:
1. It doesn't hold the git lock for extended periods (file copies, model detection)
2. It matches the existing pattern used for P0 sequential processing
3. It's a minimal change with clear semantics

The 120-second timeout matches the existing timeout used in `_wait_for_completion()` for final merge processing.
