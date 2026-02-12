---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-008: Merge coordination: stash pop failure loses local changes

## Summary

During merge coordination, after merging a completed branch, the stash pop operation can fail due to conflicts. When this happens, the user's local changes are left in the stash and may be lost or forgotten.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
**Occurrences**: 1
**Affected External Issues**: BUG-552 (occurred after merge)

### Sample Log Output

```
[16:04:18] Merged BUG-552 successfully
[16:04:18] Failed to pop stash:
[16:04:18] Cleaned up conflicted stash pop, merge preserved
[16:04:18] Stash could not be restored - your changes are saved in 'git stash list'. Run 'git stash show' to view and 'git stash pop' to retry manually.
```

## Current Behavior

1. Merge coordinator stashes local changes before merging
2. After merge, attempts to pop stash
3. If pop fails due to conflicts, the merge is preserved but stashed changes are abandoned
4. User must manually recover changes from stash

## Expected Behavior

When stash pop fails:
1. Log the failure prominently (potentially as a warning in the final summary)
2. Attempt to provide more context about what changes were stashed
3. Consider alternative recovery strategies
4. Track this as a "requires attention" item in the run summary

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/merge_coordinator.py`

## Proposed Investigation

1. Review the stash/pop logic in merge_coordinator.py
2. Understand what conditions cause pop to fail (likely merge conflicts with stashed files)
3. Consider whether to abort the merge if pop would fail
4. Add better tracking of stash state throughout the run

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in single run
- **Data Risk**: High - user's local changes could be lost if they don't notice the warning

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made

1. **`scripts/little_loops/parallel/merge_coordinator.py`**: Added stash pop failure tracking
   - Added `_stash_pop_failures` dict to track issue IDs with stash recovery failures
   - Added `_current_issue_id` to attribute failures to the correct issue
   - Updated `_pop_stash()` to record failures when they occur
   - Added `stash_pop_failures` property to expose failures for reporting

2. **`scripts/little_loops/parallel/orchestrator.py`**: Added warnings section to final report
   - Modified `_report_results()` to include stash recovery warnings
   - Shows affected issue IDs with recovery guidance
   - Provides explicit instructions for manual recovery via `git stash`

3. **`scripts/tests/test_merge_coordinator.py`**: Added test coverage
   - `TestStashPopFailureTracking` class with 3 tests:
     - `test_tracks_stash_pop_failure`: Verifies failures are tracked with issue ID
     - `test_stash_pop_failures_property_is_thread_safe`: Verifies property returns a copy
     - `test_no_tracking_without_current_issue_id`: Verifies no tracking when issue ID not set

### Verification Results
- Tests: PASS (473 tests, including 3 new tests)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

### How the Fix Works

1. When `_process_merge()` starts, it sets `_current_issue_id` to track which issue is being processed
2. If `_pop_stash()` fails due to conflicts, it now records the failure in `_stash_pop_failures` dict
3. At the end of a run, `_report_results()` checks `merge_coordinator.stash_pop_failures`
4. If any failures exist, a prominent "Stash recovery warnings" section is displayed with:
   - List of affected issue IDs
   - Recovery guidance for each failure
   - Explicit `git stash` commands to recover manually

This ensures users cannot miss the warning about their local changes needing manual recovery.

---

## Reopened

- **Date**: 2026-01-11
- **By**: /analyze_log
- **Reason**: Issue recurred in log analysis

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `<external-repo>`
**Occurrences**: 1 (stash pop) + 1 (pull conflict) + 1 (conflicted stash cleanup)
**Affected External Issues**: ENH-624, ENH-618

```
[22:54:00] Completing lifecycle for ENH-618 (merged but file not moved)
[22:54:00] Pull failed due to local changes, attempting re-stash: error: cannot pull with rebase: You have unstaged changes.
error: additionally, your index contains uncommitted changes.
error: Please commit or stash them.

[22:54:00] Tracked files to stash: ['R  .issues/enhancements/P2-ENH-618-extract-error-enrichment-base.md -> .issues/completed/P2-ENH-618-extract-error-enrichment-base.md']
[22:54:01] Stashed local changes before merge
[22:54:01] Re-stashed local changes after pull conflict
[22:54:01] Merged ENH-624 successfully
[22:54:01] Failed to pop stash:
[22:54:01] Cleaned up conflicted stash pop, merge preserved
[22:54:01] Stash could not be restored - your changes are saved in 'git stash list'. Run 'git stash show' to view and 'git stash pop' to retry manually.
```

### Analysis

The previous fix added **tracking and warnings** for stash pop failures, but the underlying issue persists. The stash/pop mechanism itself still fails when:
1. Local changes include renamed/moved files (`.issues/...` move to `completed/`)
2. Pull conflicts occur due to unstaged changes
3. Re-stash after pull conflict leads to pop conflicts

**Root cause**: The fix addressed visibility (users now see warnings), but didn't prevent the stash conflicts. A more robust solution is needed:
- Consider committing local changes before merge instead of stashing
- Or check for potential conflicts before attempting stash pop
- Or provide automatic conflict resolution for known safe patterns (like issue file moves)

---

## Resolution (Second Fix)

- **Action**: fix
- **Completed**: 2026-01-11
- **Status**: Completed

### Root Cause Analysis

The stash pop failures were caused by orchestrator-managed lifecycle file moves being stashed:
1. When orchestrator completes an issue lifecycle, it moves the issue file to `completed/`
2. This creates a rename entry (`R  old -> new`) in git status
3. The merge coordinator stashes this rename, but the merge changes HEAD
4. Stash pop conflicts because the stash was created against old HEAD

### Solution

Exclude orchestrator-managed lifecycle operations from stashing:
1. **Lifecycle file moves** - issue files being moved to `.issues/completed/`
2. **Files in completed directory** - already completed issue files

These changes are orchestrator-managed and should not be stashed, preventing the stash pop conflicts.

### Changes Made

1. **`scripts/little_loops/parallel/merge_coordinator.py`**:
   - Added `_is_lifecycle_file_move()` method to detect rename entries moving files to completed/
   - Updated `_stash_local_changes()` to skip lifecycle file moves (lines 162-166)
   - Added exclusion for files in `.issues/completed/` directory (lines 172-179)
   - Updated docstring to document all exclusions

2. **`scripts/tests/test_merge_coordinator.py`**:
   - Added `TestLifecycleFileMoveExclusion` class with 6 tests:
     - `test_is_lifecycle_file_move_detects_rename_to_completed`
     - `test_is_lifecycle_file_move_ignores_other_renames`
     - `test_is_lifecycle_file_move_ignores_non_renames`
     - `test_stash_excludes_lifecycle_file_moves`
     - `test_stash_excludes_completed_directory_files`
     - `test_stash_with_only_lifecycle_changes_returns_false`

### Verification Results
- Tests: PASS (486 tests, including 6 new tests)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

### How the Fix Works

1. When `_stash_local_changes()` processes git status output, it now:
   - Calls `_is_lifecycle_file_move()` to detect issue file moves to completed/
   - Skips these entries instead of adding them to the stash
   - Also skips any files already in `.issues/completed/` directory

2. This prevents the stash from containing orchestrator-managed files that would conflict with the merge

3. User's actual local changes (non-orchestrator files) are still stashed and restored normally

---

## Status
**Completed** | Created: 2026-01-09 | Reopened: 2026-01-11 | Fixed: 2026-01-11
