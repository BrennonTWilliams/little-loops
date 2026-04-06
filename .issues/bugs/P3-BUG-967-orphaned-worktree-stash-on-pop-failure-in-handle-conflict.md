---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# BUG-967: Orphaned worktree stash when `git stash pop` fails in `_handle_conflict`

## Summary

In `MergeCoordinator._handle_conflict`, after a successful rebase the code attempts to pop the worktree stash (if changes were stashed). If `git stash pop` returns a non-zero exit code, the function calls `_handle_failure` and returns early. The worktree's stash entry is never cleaned up — it is orphaned. The worktree is subsequently destroyed by `_cleanup_worktree`, silently discarding the stashed changes with no user-actionable warning.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 1019–1034 (at scan commit: 96d74cda)
- **Anchor**: `in function MergeCoordinator._handle_conflict`, rebase success + stash pop block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/parallel/merge_coordinator.py#L1019-L1034)
- **Code**:
```python
if rebase_result.returncode == 0:
    if worktree_has_changes:
        pop_result = subprocess.run(
            ["git", "stash", "pop"],
            cwd=result.worktree_path,
            ...
        )
        if pop_result.returncode != 0:
            self.logger.error(...)
            self._handle_failure(request, "Stash pop conflict after rebase")
            return   # ← worktree stash entry left on stack; worktree later destroyed
    self._queue.put(request)
```

## Current Behavior

When `git stash pop` fails (e.g., due to a conflict between stashed worktree changes and the rebased HEAD), the error is logged and `_handle_failure` is called. The function returns without popping or dropping the stash entry. The worktree is eventually removed by `_cleanup_worktree`, which force-deletes the directory, leaving the stashed changes unrecoverable with no user warning beyond a single error log line.

## Expected Behavior

When `git stash pop` fails in this path, the code should either:
1. Attempt `git stash drop` to cleanly discard the unreachable stash entry before cleanup, OR
2. Log a warning that includes the stash content (`git stash show -p`) so the user can recover it manually before the worktree is removed

## Motivation

Worktree changes that were stashed represent real work in-progress. Silent data loss when the worktree is destroyed — even for what appears to be a transient conflict — is a hard-to-diagnose reliability problem. Users have no way to recover the changes after the worktree directory is removed.

## Steps to Reproduce

1. Set up a merge scenario where the worktree has local changes that get stashed before rebase.
2. Arrange for the rebase to succeed but for `git stash pop` to conflict with the rebased HEAD.
3. Observe: `_handle_failure` is called, the worktree is destroyed, and the stashed changes are gone with only an error log entry.

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in function MergeCoordinator._handle_conflict`
- **Cause**: The early-return path after `pop_result.returncode != 0` exits `_handle_conflict` without issuing a `git stash drop` on the worktree stash. The `_process_merge` `finally` block only handles the **main-repo** stash (`_pop_stash`), not the worktree stash managed inside `_handle_conflict`.

## Proposed Solution

Before calling `_handle_failure` and returning, attempt to drop the worktree stash:

```python
if pop_result.returncode != 0:
    self.logger.error("Stash pop conflict after rebase in worktree %s", result.worktree_path)
    # Drop the stash to prevent orphan; log the diff first for diagnostics
    show_result = subprocess.run(["git", "stash", "show", "-p"], cwd=result.worktree_path, capture_output=True, text=True)
    if show_result.returncode == 0:
        self.logger.warning("Dropping unrecoverable worktree stash content:\n%s", show_result.stdout[:2000])
    subprocess.run(["git", "stash", "drop"], cwd=result.worktree_path, capture_output=True)
    self._handle_failure(request, "Stash pop conflict after rebase")
    return
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — `_handle_conflict` stash pop failure path

### Dependent Files (Callers/Importers)
- `MergeCoordinator._process_merge` — calls `_handle_conflict`

### Similar Patterns
- Main-repo stash cleanup in `_process_merge` `finally` block — reference for stash drop pattern

### Tests
- `scripts/tests/test_merge_coordinator.py` — add test for stash pop failure path asserting `git stash drop` is called

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `git stash show -p` + `git stash drop` before the `_handle_failure` call in the pop-failure branch
2. Add a warning log with the stash diff content (truncated) so users have a chance to recover
3. Add a unit test asserting that stash drop is attempted on pop failure

## Impact

- **Priority**: P3 — Data loss scenario; uncommon but silent when it occurs
- **Effort**: Small — A few lines of subprocess calls in one code path
- **Risk**: Low — Only affects the failure path; no change to the success path
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `parallel`, `data-loss`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P3
