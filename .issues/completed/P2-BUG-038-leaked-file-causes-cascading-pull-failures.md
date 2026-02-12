---
discovered_commit: d2f420d
discovered_date: 2026-01-13
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-038: Leaked file cleanup fails silently for gitignored paths

## Summary

When a file leaks to a gitignored path (e.g., `issues/` without dot prefix), the cleanup logic fails silently because `git status --porcelain -- <gitignored_path>` returns empty output. The leaked file persists and causes cascading pull failures when the merge coordinator's stash logic skips completed directory files.

**Root cause**: `_cleanup_leaked_files` in worker_pool.py relies solely on git status to categorize files. When git returns nothing (gitignored paths), no cleanup occurs and no warning is logged.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
**Occurrences**: 11 pull failures after initial leak
**Trigger Issue**: ENH-706 (leaked to `issues/enhancements/` then moved to `issues/completed/`)

### Sample Log Output

```
[16:42:17] ENH-706 leaked 1 file(s) to main repo: ['issues/enhancements/P1-ENH-706-add-verification-pattern-for-guide-height-criterion.md']
...
[16:54:28] Git status output:  M .issues/completed/P1-ENH-706-add-verification-pattern-for-guide-height-criterion.md
[16:54:28] Skipping completed directory file from stash: .issues/completed/P1-ENH-706-add-verification-pattern-for-guide-height-criterion.md
[16:54:29] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
...
[17:03:35] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:08:04] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:17:23] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:19:51] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:28:58] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:31:55] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:37:06] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:41:49] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
[17:45:18] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
```

## Current Behavior

1. A file leaks from a worktree to the main repo (BUG-007 recurrence)
2. During processing, the issue file is moved to `completed/` directory
3. The leaked file path in main repo now points to completed directory
4. Merge coordinator detects the modified file but **intentionally skips** stashing completed directory files
5. The unstaged change persists, causing every subsequent `git pull --rebase` to fail
6. The tool recovers by skipping the pull, but this creates:
   - Unnecessary git operations (repeated re-stash attempts)
   - Potential for stale branches (no pull means no remote updates)
   - Log noise that obscures real issues

## Expected Behavior

When a leaked file is detected in the completed directory:
1. It should be either stashed (not skipped) OR
2. Cleaned up entirely (since it shouldn't exist in main repo anyway) OR
3. At minimum, a warning should be logged that ongoing pull operations will be affected

## Affected Components

- **Tool**: ll-parallel
- **Primary Module**: `scripts/little_loops/parallel/merge_coordinator.py` (stash logic)
- **Related Module**: `scripts/little_loops/parallel/worker_pool.py` (leak cleanup logic)

## Root Cause Analysis

There are **two distinct paths** in the log output that reveal the actual root cause:

1. **Leaked file**: `issues/enhancements/P1-ENH-706...md` (WITHOUT dot prefix)
2. **Tracked file**: `.issues/completed/P1-ENH-706...md` (WITH dot prefix)

These are **different files in different directories**. The cleanup failed for the `issues/` path (without dot), leaving it to cause downstream issues.

### Why `issues/` (without dot) wasn't cleaned up

The cleanup logic in `worker_pool.py:771-840` has a **silent failure mode**:

1. Detection finds leaked file at `issues/enhancements/...` via `git status --porcelain`
2. Cleanup runs `git status --porcelain -- issues/enhancements/...` to categorize as tracked/untracked
3. **Git returns empty output** because `issues/` (without dot) is likely gitignored in blender-agents
4. Neither `tracked_files` nor `untracked_files` gets populated (lines 800-811)
5. Nothing gets cleaned, no warning logged

```python
# worker_pool.py:800-811 - silent failure when git status returns empty
for line in status_result.stdout.splitlines():
    if not line or len(line) < 3:
        continue
    # If git returns nothing, this loop never executes
    # and both tracked_files and untracked_files remain empty
```

### Secondary issue: stash skip logic

The stash logic in merge_coordinator.py has special handling to skip completed directory files:
```
Skipping completed directory file from stash: .issues/completed/...
```

This was added to avoid stashing legitimately completed issue files. However, when combined with the cleanup failure above, it allows the `.issues/completed/` file (which is a tracked file that was modified) to persist and block all subsequent pulls.

## Proposed Fix

**Primary fix (cleanup gap)**: Add fallback filesystem deletion for files not reported by git status.

In `_cleanup_leaked_files`, after processing git status output:

```python
# Track which files were handled by git status
accounted_files = set(tracked_files + untracked_files)

# Fallback: directly delete files not reported by git (may be gitignored)
for file_path in leaked_files:
    if file_path not in accounted_files:
        full_path = self.repo_path / file_path
        if full_path.exists():
            try:
                full_path.unlink()
                cleaned += 1
                self.logger.info(f"Deleted gitignored leaked file: {file_path}")
            except OSError as e:
                self.logger.warning(f"Failed to delete gitignored leaked file {file_path}: {e}")
        else:
            self.logger.debug(f"Leaked file not found (may have been moved): {file_path}")
```

**Secondary fix (stash logic)**: Track whether completed directory files existed in baseline vs appeared during processing. Only skip stashing if the file existed before processing started.

## Reproduction Steps

1. Run ll-parallel on a repository that has `issues/` (without dot) gitignored
2. Have Claude Code write a file to the wrong path: `issues/enhancements/...` instead of `.issues/enhancements/...`
3. Detection will find the leaked file
4. Cleanup will run `git status --porcelain -- issues/...` which returns empty (gitignored)
5. File persists, causing cascading pull failures on subsequent merges

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 11 occurrences in single run (every merge after the initial leak)
- **Data Risk**: Low - tool recovers by skipping pull, but branches may become stale
- **User Impact**: Log noise, potential confusion, risk of merge conflicts due to stale branches

---

## Labels
- component:parallel
- type:bug
- related:BUG-007

## Status
**Completed** | Created: 2026-01-13 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/worker_pool.py`: Added fallback cleanup logic for gitignored files not reported by git status. After processing tracked/untracked files, the method now iterates over leaked files not accounted for by git status and deletes them directly via filesystem operations.
- `scripts/tests/test_worker_pool.py`: Added test case `test_cleanup_leaked_files_gitignored` to verify gitignored file cleanup behavior.

### Verification Results
- Tests: PASS (55 tests in test_worker_pool.py)
- Lint: PASS
- Types: PASS
