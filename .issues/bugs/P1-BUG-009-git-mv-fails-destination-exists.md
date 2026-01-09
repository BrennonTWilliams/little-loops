---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-009: Issue lifecycle: git mv fails when destination already exists

## Summary

When completing issue lifecycle (moving issue file to `completed/`), the `git mv` command fails because the destination file already exists. This indicates a race condition or state synchronization issue where the file has already been moved or created in the destination.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 3
**Affected External Issues**: ENH-550, ENH-557, ENH-547

### Sample Log Output

```
[16:27:20] Completing lifecycle for ENH-550 (merged but file not moved)
[16:27:20] Git status output: ?? .issues/completed/P1-ENH-550-geometric-reasoning-vertex-multiplication-calculation.md
[16:27:20] git mv failed for ENH-550: fatal: destination exists, source=.issues/enhancements/P1-ENH-550-geometric-reasoning-vertex-multiplication-calculation.md, destination=.issues/completed/P1-ENH-550-geometric-reasoning-vertex-multiplication-calculation.md

[16:27:21] git mv failed for ENH-557: fatal: destination exists, source=.issues/enhancements/P1-ENH-557-convert-string-criteria-to-measurable-objects.md, destination=.issues/completed/P1-ENH-557-convert-string-criteria-to-measurable-objects.md

[16:27:21] Git status output: ?? .issues/completed/ENH-547-specfile-criteria-verification-validation.md
[16:27:21] git mv failed for ENH-547: fatal: destination exists, source=.issues/enhancements/ENH-547-specfile-criteria-verification-validation.md, destination=.issues/completed/ENH-547-specfile-criteria-verification-validation.md
```

## Current Behavior

1. Issue is marked for lifecycle completion
2. System attempts `git mv source destination`
3. Destination file already exists (shown as `??` in git status - untracked)
4. `git mv` fails with "destination exists"
5. Lifecycle completes anyway (commit is made), but file state is inconsistent

## Expected Behavior

Before attempting `git mv`:
1. Check if destination already exists
2. If destination exists and is identical, simply remove source
3. If destination exists and differs, log error and handle gracefully
4. Ensure consistent state between worktrees and main repo

## Root Cause Analysis

The `??` status suggests the destination file exists as an untracked file. This could happen if:
- Claude's work created the file in completed/ directly
- A previous merge/sync operation copied the file
- File was created by another worktree and appeared via the leak issue (see BUG-007)

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/merge_coordinator.py` (lifecycle completion logic)

## Proposed Investigation

1. Review lifecycle completion logic in merge_coordinator.py
2. Check if the issue files are being created/moved by Claude's work
3. Understand the relationship with the "leaked files" issue (BUG-007)
4. Add pre-check before git mv to handle existing destination

## Impact

- **Severity**: High (P1) - 3 occurrences, leaves inconsistent state
- **Frequency**: 3 occurrences in single run (affects ~18% of completed issues)
- **Data Risk**: Medium - issue files may be in inconsistent state

---

## Status
**Open** | Created: 2026-01-09 | Priority: P1
