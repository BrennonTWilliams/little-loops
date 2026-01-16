---
discovered_commit: ef0f5a7
discovered_date: 2026-01-16
discovered_source: git-error-analysis-blender-agents-ll-parallel.md
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-079: Post-merge rebase causes unnecessary merge failures

## Summary

After the merge coordinator successfully handles a merge conflict by switching from rebase to merge strategy, it still attempts a subsequent rebase which causes a new conflict and marks the merge as failed. This causes valid merges to fail unnecessarily.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Affected External Issues**: ENH-828

### Sample Log Output

```
[16:01:47] Merge conflict for ENH-828, attempting rebase (retry 1/2)
[16:01:47] Merge failed for ENH-828: Rebase failed after merge conflict
[16:01:47] error: could not apply 79c12c55... feat(primitives): add rotation parameter to all primitive creation operations
```

### Timeline

1. Initial pull --rebase fails with conflict (commit ae3b85ec superseded)
2. System correctly detects conflict and switches to merge strategy
3. `git pull --no-rebase` succeeds
4. **Bug:** Rebase is still attempted on ENH-828's branch
5. Rebase fails with conflict on commit 79c12c55
6. ENH-828 merge marked as failed despite successful merge

## Current Behavior

When a merge conflict occurs:
1. System tries `git pull --rebase` → fails
2. System switches to `git pull --no-rebase` → succeeds
3. System still attempts rebase for the branch → fails
4. Overall merge marked as failed

## Expected Behavior

After successfully resolving a conflict with merge strategy:
1. Do NOT attempt a subsequent rebase
2. Continue with the merge workflow
3. Mark the merge as successful

## Affected Components

- **Tool**: ll-parallel
- **Module**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Related**: Conflict recovery logic, rebase fallback handling

## Root Cause Hypothesis

The merge coordinator has separate logic paths for:
1. Pulling changes from remote (where rebase-to-merge fallback works)
2. Rebasing the feature branch onto updated main

When path #1 switches to merge strategy, path #2 is not informed and still attempts a rebase. The rebase attempt should be skipped when merge strategy was used.

## Possible Investigation Areas

1. Check `merge_coordinator.py` for the retry/rebase logic after merge
2. Look for state tracking of which strategy was used
3. Verify if there's a flag to skip rebase after merge fallback
4. Check if the retry counter (1/2) indicates a rebase retry vs merge retry

## Impact

- **Severity**: Medium (P2)
- **Frequency**: Low (specific to branches with complex conflict scenarios)
- **Data Risk**: Low - work is not lost, just requires manual merge or rerun

---

## Labels
- component:parallel
- type:bug

## Status
**Completed** | Created: 2026-01-16 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-16
- **Status**: Completed

### Root Cause
The `_handle_conflict()` method in `merge_coordinator.py` was attempting a rebase retry unconditionally after a merge conflict, without checking whether merge strategy had been used during the pull phase. When merge strategy was used (because rebase would have failed on the same commits), the rebase retry would fail on the exact same conflicts.

### Changes Made
- `scripts/little_loops/parallel/merge_coordinator.py`: Added `used_merge_strategy` local variable tracking in `_process_merge()` to track when `git pull --no-rebase` is used
- `scripts/little_loops/parallel/merge_coordinator.py`: Modified `_handle_conflict()` to accept `used_merge_strategy` parameter and skip rebase retry when merge strategy was used
- `scripts/tests/test_merge_coordinator.py`: Added `TestMergeStrategySkipsRebaseRetry` test class with 2 tests
- `scripts/tests/test_merge_coordinator.py`: Fixed existing test mock to match new `_handle_conflict()` signature

### Verification Results
- Tests: PASS (1335 tests)
- Lint: PASS
- Types: PASS
