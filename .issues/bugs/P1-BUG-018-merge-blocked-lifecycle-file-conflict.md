---
discovered_commit: 8279174
discovered_date: 2026-01-12
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-018: Merge blocked by local changes despite stash exclusions

## Summary

During merge coordination, a merge can fail because "local changes would be overwritten" even though the stash exclusion logic was specifically designed to prevent this. The issue occurs when an earlier issue's lifecycle file move (to completed/) conflicts with a later merge.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
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

## Status
**Open** | Created: 2026-01-12 | Priority: P1
