---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-479: `_handle_conflict` doesn't verify stash pop success before re-queue

## Summary

In `MergeCoordinator._handle_conflict`, after a successful rebase, `git stash pop` is called but its return code is not checked. If the stash pop fails (e.g., due to conflicts with rebased content), the worktree is left in a dirty state and the merge request is re-queued, leading to confusing subsequent failures.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 1003-1012 (at scan commit: 95d4139)
- **Anchor**: `in method MergeCoordinator._handle_conflict`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/parallel/merge_coordinator.py#L1003-L1012)
- **Code**:
```python
if rebase_result.returncode == 0:
    if worktree_has_changes:
        subprocess.run(
            ["git", "stash", "pop"],
            cwd=result.worktree_path,
            capture_output=True,
            timeout=30,
        )                    # return code not checked
    self._queue.put(request)
```

## Current Behavior

The `subprocess.run(["git", "stash", "pop"])` return code is not checked. If stash pop fails with conflicts, the worktree has unresolved merge conflicts, and the merge request is immediately re-queued. The subsequent merge attempt encounters a dirty worktree with no indication that stash pop was the root cause.

## Expected Behavior

The stash pop return code should be checked. On failure, the merge should be marked as failed with an appropriate error message rather than silently re-queued.

## Steps to Reproduce

1. Trigger a merge conflict retry where the worktree had uncommitted changes
2. The rebase succeeds but introduces conflicts with the stashed changes
3. Stash pop fails silently
4. Re-queued merge hits a different error with no indication of root cause

## Proposed Solution

Check the return code and handle failure:

```python
if worktree_has_changes:
    pop_result = subprocess.run(
        ["git", "stash", "pop"],
        cwd=result.worktree_path,
        capture_output=True,
        timeout=30,
    )
    if pop_result.returncode != 0:
        self.logger.error(
            f"Stash pop failed for {request.issue_id} after rebase: "
            f"{pop_result.stderr.decode()}"
        )
        self._mark_failed(request, "Stash pop conflict after rebase")
        return
self._queue.put(request)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — check stash pop return code in `_handle_conflict`

### Dependent Files (Callers/Importers)
- N/A — internal merge handling

### Similar Patterns
- Other `subprocess.run` calls in the same file check return codes

### Tests
- `scripts/tests/` — add test for stash pop failure during conflict handling

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Confusing failure mode during parallel merge conflicts
- **Effort**: Small — Add return code check and error handling
- **Risk**: Low — Defensive improvement to existing error path
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `merge`, `error-handling`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
