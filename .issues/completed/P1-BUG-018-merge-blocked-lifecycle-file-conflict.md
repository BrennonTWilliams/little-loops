---
discovered_commit: 8279174
discovered_date: 2026-01-12
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-018: Merge blocked by local changes despite stash exclusions

## Summary

During merge coordination, a merge can fail because "local changes would be overwritten" even though the stash exclusion logic was specifically designed to prevent this. The issue occurs when an earlier issue's lifecycle file move (to completed/) conflicts with a later merge.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
**Occurrences**: 1
**Affected External Issues**: ENH-643 (failed), ENH-625 (lifecycle file causing conflict)

### Sample Log Output

```
[13:01:46] Completing lifecycle for ENH-625 (merged but file not moved)
[13:01:47] Git status output: RM .issues/enhancements/P1-ENH-625-validate-acceptance-criteria-at-phase-level.md -> .issues/completed/P1-ENH-625-validate-acceptance-criteria-at-phase-level.md

[13:01:47] Merge blocked by local changes despite stash: error: Your local changes to the following files would be overwritten by merge:
  .issues/completed/P1-ENH-625-validate-acceptance-criteria-at-phase-level.md
Merge with strategy ort failed.

[13:01:47] Merge failed for ENH-643: Merge failed due to local changes: error: Your local changes to the following files would be overwritten by merge:
  .issues/completed/P1-ENH-625-validate-acceptance-criteria-at-phase-level.md
Merge with strategy ort failed.
```

## Current Behavior

1. ENH-625 is merged successfully, but lifecycle file move is deferred
2. Later, orchestrator completes lifecycle for ENH-625, moving issue file to `completed/`
3. This creates a rename entry in git status (`RM old -> new`)
4. When ENH-643 tries to merge, git complains that local changes would be overwritten
5. The stash exclusion logic (from BUG-008 fix) skips lifecycle file moves, so nothing is stashed
6. Merge fails because the local rename conflicts with the merge

## Expected Behavior

The merge coordinator should:
1. Detect that the "local changes" are orchestrator-managed lifecycle operations
2. Either commit the lifecycle file move before merging, OR
3. Temporarily move the file, perform the merge, then restore the file move

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/merge_coordinator.py` (merge logic)
- **Related**: `scripts/little_loops/parallel/orchestrator.py` (lifecycle completion timing)

## Root Cause Analysis

The BUG-008 second fix added stash exclusions for lifecycle file moves to prevent stash pop conflicts. However, this creates a new problem: the lifecycle file move is neither stashed nor committed, so it remains as an uncommitted change that blocks the merge.

The timing issue:
1. ENH-625 is merged successfully at 12:38:43
2. Issue file was not moved at merge time (branch may not have had the move)
3. At 13:01:46, orchestrator detects "merged but file not moved" and performs lifecycle completion
4. At 13:01:47, ENH-643 tries to merge but is blocked by the uncommitted file move

## Proposed Fix

**Option 1 (Recommended)**: Commit lifecycle file moves immediately
- When `_complete_lifecycle()` runs, commit the file move immediately
- This keeps the lifecycle change in the commit history where it belongs
- Prevents blocking subsequent merges

**Option 2**: Defer lifecycle completion until all merges done
- Queue lifecycle completions
- Process them after all workers finish and merges complete
- Less ideal as it delays issue closure

**Option 3**: Force commit before merge
- In `_process_merge()`, check for uncommitted issue file moves
- Auto-commit them before attempting the merge

## Impact

- **Severity**: High (P1) - Causes issue failures and processing incomplete
- **Frequency**: 1 occurrence in single run, but likely affects any run with lifecycle timing edge cases
- **Data Risk**: Low - work is completed, just not merged; can be recovered manually

## Reproduction Steps

1. Run ll-parallel with multiple issues
2. Have an issue complete and merge successfully
3. Have the issue file move to completed/ happen after merge (via lifecycle completion)
4. Have another issue try to merge while the first issue's file move is uncommitted
5. Observe the merge failure

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-12
- **Status**: Completed
- **Solution**: Option 3 (Force commit before merge)

### Changes Made
- `scripts/little_loops/parallel/merge_coordinator.py`: Added `_commit_pending_lifecycle_moves()` method that detects and commits any uncommitted lifecycle file moves before merge operations
- `scripts/little_loops/parallel/merge_coordinator.py`: Call the new method in `_process_merge()` after `_mark_state_file_assume_unchanged()` and before `_stash_local_changes()`
- `scripts/tests/test_merge_coordinator.py`: Added 5 unit tests for the new method

### Verification Results
- Tests: PASS (491 tests, 33 in test_merge_coordinator.py)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

### Technical Details
The fix adds a new method `_commit_pending_lifecycle_moves()` that:
1. Checks `git status --porcelain` for lifecycle file moves (renames to `.issues/completed/`)
2. If found, stages all changes with `git add -A` and commits with a descriptive message
3. Returns True on success (or if no moves exist), False on failure

This method is called at the start of `_process_merge()` before stashing, ensuring any lifecycle file moves from the orchestrator are committed before the merge coordinator attempts to merge the next issue.

### Root Cause
The BUG-008 fix added stash exclusions for lifecycle file moves to prevent stash pop conflicts. However, when the orchestrator completes a lifecycle (moves issue file to completed/) and a commit fails with "nothing to commit", the staged rename persists. The stash exclusion logic then skips it, leaving it as an uncommitted change that blocks subsequent merges.

### Commits
- See git log for implementation commit

---

## Reopened

- **Date**: 2026-01-14
- **By**: /analyze_log
- **Reason**: Issue recurred with merge conflicts in index

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `<external-repo>`
**Occurrences**: 2 merge attempts (both failed)
**Affected External Issues**: ENH-724 (failed)

```
[14:42:42] Merge blocked by unmerged files in index: Auto-merging src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
CONFLICT (content): Merge conflict in src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
Auto-merging src/blender_
[14:42:42] Detected incomplete merge, aborting...
[14:42:42] Aborted incomplete merge
[14:42:42] Recovered from unmerged files, retrying merge
[14:42:42] Processing merge for ENH-724
[14:42:43] Merge blocked by unmerged files in index: Auto-merging src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
CONFLICT (content): Merge conflict in src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
Auto-merging src/blender_
[14:42:43] Merge failed for ENH-724: Merge failed due to unmerged files: Auto-merging src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
CONFLICT (content): Merge conflict in src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py
Auto-merging src/blender_
```

### Analysis

The original BUG-018 was about merge blocked by "local changes would be overwritten" due to lifecycle file moves. This occurrence is different:

**Key differences from original BUG-018**:
1. Original: "local changes would be overwritten" error (lifecycle file moves)
2. This occurrence: "Merge blocked by unmerged files in index" (actual merge conflicts in source code)

**Similarities**:
1. Both involve merge coordinator failing to complete a merge
2. Both involve aborting and retrying
3. Both ultimately fail the issue

**Root cause of this occurrence**:
- ENH-724 modified `src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py`
- The same file had conflicts during merge
- The merge coordinator detected incomplete merge, aborted, and retried
- The retry also failed with the same conflict
- This suggests the conflict resolution didn't properly clean the unmerged state

**Possible causes**:
1. Previous merge attempt left conflicted state in index
2. The abort didn't fully clean the unmerged files
3. The source file has genuine conflicts that need manual resolution
4. The merge retry logic doesn't handle conflicted source files correctly

### Proposed Investigation

1. Check if the merge coordinator properly cleans unmerged state after abort
2. Verify if source file conflicts are being detected before merge attempts
3. Consider adding conflict detection/prevention before merge
4. Evaluate if failed merges should trigger different recovery strategy

---

## Resolution (Reopened Issue)

- **Action**: fix
- **Completed**: 2026-01-14
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/merge_coordinator.py`: Removed confusing retry-after-reset logic for unmerged files errors (lines 816-827). Genuine merge conflicts now route directly to `_handle_conflict()` for rebase retry, instead of attempting a useless reset-and-retry.
- `scripts/tests/test_merge_coordinator.py`: Added 2 new tests for `TestUnmergedFilesHandling` class to verify the fix works correctly.

### Technical Details

**The Problem (Reopened)**:
The original BUG-018 fix (committing pending lifecycle moves) solved the "local changes would be overwritten" issue. However, a different problem was discovered: genuine source code merge conflicts (e.g., in `execution_mixin.py`) were being treated as "unmerged files in index" errors, triggering a confusing retry-after-reset flow that would never succeed.

**The Root Cause**:
The error handling at `merge_coordinator.py:817-827` assumed all "unmerged files" errors were index state corruption that could be fixed by resetting. However, when unmerged files are from **genuine merge conflicts** (the current merge attempt found conflicts), resetting and retrying doesn't help - the same conflicts occur again.

**The Fix**:
Removed the retry-after-reset logic for unmerged files errors. Now:
1. `_check_and_recover_index()` is still called at the **start** of `_process_merge()` (line 688) to clean up any pre-existing index corruption
2. When a merge fails with "unmerged files" error **during** the merge attempt, it's treated as a genuine conflict and routed to `_handle_conflict()` for rebase retry
3. This prevents confusing "Recovered from unmerged files, retrying merge" logs when the conflict is genuine

**Key Changes**:
- Lines 816-827: Removed retry-after-reset block
- Lines 816-822: New unified conflict detection that treats both "unmerged files" and "CONFLICT" as genuine merge conflicts

### Verification Results
- Tests: PASS (1070 tests, 40 in test_merge_coordinator.py)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

### Commits
- See git log for implementation commit

---

## Status

**Completed** | Created: 2026-01-12 | First Completed: 2026-01-12 | Reopened: 2026-01-14 | Final Completed: 2026-01-14 | Priority: P1
