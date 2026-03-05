---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 94
outcome_confidence: 79
---

# BUG-579: `_cleanup_orphaned_worktrees()` Ignores Worker Pool's `_active_worktrees` Guard

## Summary

`ParallelOrchestrator._cleanup_orphaned_worktrees()` (orchestrator.py:217) removes **all** `worker-*` directories in the worktree base without consulting `WorkerPool._active_worktrees`. This means the BUG-142 fix (which added the `_active_worktrees` set to `_cleanup_worktree` in the worker pool) does **not** protect against the orchestrator's own orphan cleanup path.

## Context

Discovered during analysis of `ll-sprint-run-debug.txt`. The worker pool's `_cleanup_worktree()` correctly guards against deleting active worktrees, but `_cleanup_orphaned_worktrees()` in the orchestrator is a separate code path that bypasses this guard entirely:

```python
# orchestrator.py:217 — no check against _active_worktrees
def _cleanup_orphaned_worktrees(self) -> None:
    for item in worktree_base.iterdir():
        if item.is_dir() and item.name.startswith("worker-"):
            orphaned.append(item)  # ALL worker dirs, no guard

    for worktree_path in orphaned:
        self._git_lock.run(["worktree", "remove", "--force", str(worktree_path)], ...)
```

Currently this runs at the **start** of `orchestrator.run()` (before any workers start), so it is safe in the normal flow. However, the lack of guard creates a latent bug:

- If a sprint creates a second orchestrator while the first is still processing (bug, restart, or race condition)
- If `_cleanup_orphaned_worktrees` is called at an unexpected point due to refactoring
- If two `ll-parallel` invocations run concurrently

## Current Behavior

`_cleanup_orphaned_worktrees()` removes ALL directories matching `worker-*` pattern with no session ID, timestamp check, or `_active_worktrees` coordination.

## Root Cause

- **File**: `scripts/little_loops/parallel/orchestrator.py:217`
- **Issue**: The orchestrator doesn't have a reference to the worker pool's `_active_worktrees` set when cleanup runs. There is no cross-component coordination for worktree liveness.
- **Risk**: Latent bug that would cause data loss if cleanup timing ever shifts.

## Expected Behavior

`_cleanup_orphaned_worktrees()` should only remove worktrees that are genuinely from a **previous** session (e.g., different timestamp, no corresponding running process, or confirmed stale via lockfile).

## Acceptance Criteria

- [x] A second `ll-parallel` invocation running concurrently does **not** remove worktrees owned by the first (active session's worktrees are preserved)
- [x] Worktrees from a previous interrupted session are still removed by `_cleanup_orphaned_worktrees()` (no regression in orphan cleanup behavior)

## Proposed Solution

Add session-based worktree naming or a per-session lock file:

1. **Option A** (chosen): Write a `.ll-session-<pid>` marker file (contents: `str(os.getpid())`) into each worktree on creation. `_cleanup_orphaned_worktrees()` reads the marker and skips any worktree whose PID matches `os.getpid()` (i.e., belongs to the current process).

2. **Option B**: Pass `worker_pool._active_worktrees` reference to `_cleanup_orphaned_worktrees()` so it can skip active ones.

3. **Option C**: Use `git worktree list --porcelain` to check whether a worktree is registered and recently accessed before removing it.

## Implementation Steps

1. In `worker_pool.py:_setup_worktree()`, after creating the worktree directory, write a `.ll-session-<pid>` marker file with contents `str(os.getpid())`
2. In `orchestrator.py:_cleanup_orphaned_worktrees()`, read the marker file from each `worker-*` directory and skip those whose PID matches `os.getpid()`; worktrees with no marker are still cleaned up (no regression)
3. Add test to `scripts/tests/test_orchestrator.py:TestOrphanedWorktreeCleanup` covering the concurrent-orchestrator scenario (worktree with matching PID marker is skipped; worktree with foreign PID marker is removed)
4. Run existing parallel tests to confirm no regression in orphan cleanup for worktrees without a marker

## Similar Patterns

- `worker_pool.py:620` — `_cleanup_worktree()` has `_active_worktrees` guard (BUG-142 fix), but this is only called from within the worker pool
- `orchestrator.py:145` — calls `_cleanup_orphaned_worktrees()` at startup, before workers start

## Steps to Reproduce

1. Start `ll-parallel` with 4 workers
2. While workers are running, create a second `ParallelOrchestrator` instance (or run `ll-parallel` in a second terminal)
3. The second orchestrator's `_cleanup_orphaned_worktrees()` will destroy the first orchestrator's active worktrees

## Impact
- **Priority**: P2 - Latent bug that causes data loss (active worktrees deleted) when two concurrent `ll-parallel` sessions run simultaneously; currently safe but one refactor away from data loss
- **Effort**: Small - Session marker file approach is self-contained; ~3 files to modify
- **Risk**: Low - Change is additive (adds marker check); existing orphan cleanup for un-marked worktrees is preserved
- **Breaking Change**: No

## Labels
`bug`, `parallel`, `worktrees`, `data-safety`

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_cleanup_orphaned_worktrees()` at line 217 (add session marker check)
- `scripts/little_loops/parallel/worker_pool.py` — `_create_worktree()` or worktree setup path (write `.ll-session-<id>` marker)

### Dependent Files (Callers/Importers)
- `orchestrator.py:145` — calls `_cleanup_orphaned_worktrees()` at startup; no call-site changes needed

### Similar Patterns
- `worker_pool.py:620` — `_cleanup_worktree()` BUG-142 guard (reference implementation for active-worktree protection)

### Tests
- `scripts/tests/test_parallel_types.py` — add concurrent-orchestrator test case

### Documentation
- N/A

### Configuration
- N/A

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a470e022-6e78-4989-a376-3d78b8dd783e.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7c88523-a3c9-4dde-9eb7-a055993ac4ef.jsonl`
- `/ll:ready-issue` - 2026-03-04T21:49:18Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1b61e9b-5498-4fe4-9f8c-9e3d2dd5ded4.jsonl`
- `/ll:confidence-check` - 2026-03-04T22:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f17b114-2f56-460a-ad29-5184e3ad148f.jsonl`
- `/ll:ready-issue` - 2026-03-04T22:15:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:manage-issue` - 2026-03-04T22:30:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---
## Resolution

**Fixed** via session marker approach (Option A from proposed solution).

### Changes
- `scripts/little_loops/parallel/orchestrator.py`: Added `import os`; modified `_cleanup_orphaned_worktrees()` to scan each `worker-*` dir for `.ll-session-<pid>` marker files and skip any worktree whose owning process is still alive (`os.kill(pid, 0)`)
- `scripts/little_loops/parallel/worker_pool.py`: `_setup_worktree()` writes a `.ll-session-<pid>` marker file into each worktree after creation
- `scripts/tests/test_orchestrator.py`: Added 2 tests to `TestOrphanedWorktreeCleanup` — one asserting a live-PID-marked worktree is skipped, one asserting a dead-PID-marked worktree is removed

## Status
**Completed** | Priority: P2
