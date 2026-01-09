---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-008: Merge coordination: stash pop failure loses local changes

## Summary

During merge coordination, after merging a completed branch, the stash pop operation can fail due to conflicts. When this happens, the user's local changes are left in the stash and may be lost or forgotten.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
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

## Status
**Open** | Created: 2026-01-09 | Priority: P2
