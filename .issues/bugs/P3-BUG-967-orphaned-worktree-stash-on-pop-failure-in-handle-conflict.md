---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
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
- `scripts/little_loops/parallel/merge_coordinator.py` — `_handle_conflict` stash pop failure path (lines 1042–1048); also see secondary gap at lines 1058–1064

### Dependent Files (Callers/Importers)
- `MergeCoordinator._process_merge` (calls `_handle_conflict`; its `finally` block at lines 935–943 only covers the main-repo stash via `_pop_stash`, not the worktree stash)
- `orchestrator.py` — `_cleanup_orphaned_worktrees` (line 231) and end-of-run `worktree remove --force` (line 472) both force-delete worktree directories without inspecting stash entries

### Similar Patterns
- `_pop_stash` (lines 230–302) — main-repo stash cleanup pattern, uses `_git_lock.run` and sets `self._stash_active = False`
- `_stash_pop_failures` dict (`__init__` lines 69–76; written in `_pop_stash` at lines 287–292) — established convention for recording stash-related failures by `_current_issue_id` under `self._lock`

### Tests
- `scripts/tests/test_merge_coordinator.py:1780` — `test_stash_pop_failure_after_rebase_marks_failed` (existing test in `TestMergeStrategySkipsRebaseRetry` class at line 1660): already covers pop-failure path marking request as failed; extend or add a sibling test asserting `git stash drop` is called
- `scripts/tests/test_merge_coordinator.py:1844` — `mock_subprocess_run` pattern to follow: uses `cmd[:3]` slices keyed on `["git", "stash", "pop"]`; patch target is `"little_loops.parallel.merge_coordinator.subprocess.run"`
- `scripts/tests/test_merge_coordinator.py:1794` — worktree setup boilerplate (`git worktree add -b parallel/...`) to reuse for new test

### Documentation
- `docs/development/MERGE-COORDINATOR.md` — may need a note about worktree stash cleanup behavior

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed line numbers** (current HEAD): stash pop failure branch is at lines 1042–1048, not 1019–1034 as noted at scan time
- **Secondary gap (Branch C, lines 1058–1064)**: the rebase-failure path runs `git stash pop` on the worktree with no `returncode` check and no `text=True`; if pop silently fails here, the stash entry is also orphaned. This secondary gap is not covered by this issue but should be tracked.
- **No `git stash drop` exists anywhere** in `merge_coordinator.py` or its test file — there is no existing cleanup pattern to reuse, only the equivalent `_pop_stash` pattern using `_git_lock.run` for the main-repo stash
- **`_cleanup_worktree` (lines 1180–1207)** is only called from `_finalize_merge:1160` (success path); `_handle_failure` does NOT call it, so the worktree directory persists after a pop failure. The stash entry is abandoned in that persistent directory until the orchestrator's separate cleanup removes it without inspecting stash entries.

## Implementation Steps

1. In `_handle_conflict` at line 1042 (after `pop_result.returncode != 0` check): add `git stash show -p` (with `capture_output=True, text=True, timeout=30`) and log the diff as a `warning`; then add `git stash drop` (with `capture_output=True, timeout=10`) before the `_handle_failure` call — matching the `subprocess.run` signature pattern used at lines 1035–1041
2. Add a unit test in `TestMergeStrategySkipsRebaseRetry` (`test_merge_coordinator.py:1660`) as a sibling to `test_stash_pop_failure_after_rebase_marks_failed` (line 1780): follow the `mock_subprocess_run` pattern at line 1844, adding a `["git", "stash", "drop"]` branch to the mock and asserting it is called when pop returns non-zero
3. Run `python -m pytest scripts/tests/test_merge_coordinator.py -v -k "stash_pop" --tb=short` to verify

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
- `/ll:ready-issue` - 2026-04-06T18:04:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/21f19bed-97fc-4565-8516-1dab2c921bc1.jsonl`
- `/ll:refine-issue` - 2026-04-06T18:00:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c681f349-9672-4ba6-84ba-7219aa7c4e3a.jsonl`
- `/ll:format-issue` - 2026-04-06T17:57:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55295d1d-bc37-4e4a-994a-bf5011f65b45.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`
- `/ll:confidence-check` - 2026-04-06T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5ada5db-6f30-4aaf-a2f5-bcf633c40d46.jsonl`

## Resolution

**Fixed** in `scripts/little_loops/parallel/merge_coordinator.py` `_handle_conflict`.

Before calling `_handle_failure` on stash pop failure, the code now:
1. Runs `git stash show -p` and logs the diff as a `warning` for diagnostics.
2. Runs `git stash drop` to clean up the orphaned stash entry.

A new test `test_stash_drop_called_on_pop_failure_after_rebase` was added to `TestMergeStrategySkipsRebaseRetry` asserting that `git stash drop` is called when stash pop returns non-zero.

## Status

**Completed** | Created: 2026-04-06 | Resolved: 2026-04-06 | Priority: P3
