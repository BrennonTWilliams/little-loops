---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-007: Worktree isolation: files leak to main repo during parallel processing

## Summary

During parallel issue processing, files created or modified in worker worktrees are sometimes appearing in the main repository. This breaks the isolation that worktrees are supposed to provide and can cause merge conflicts or uncommitted changes in the wrong location.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 2
**Affected External Issues**: BUG-553, BUG-552

### Sample Log Output

```
[15:19:53] Found 2 file(s) changed: ['src/blender_agents/ai/specfile_generator.py', 'tests/unit/ai/test_enh_515_presentation_phases.py']
[15:19:53] BUG-553 leaked 1 file(s) to main repo: ['tests/unit/ai/test_enh_515_presentation_phases.py']
[15:19:53] Cleaned up 1 leaked file(s) from main repo

[16:04:14] BUG-552 leaked 1 file(s) to main repo: ['issues/bugs/P2-BUG-552-stall-detection-skips-criteria-validation-no-scene-snapshot.md']
```

## Current Behavior

When a worker completes work in its worktree, some files unexpectedly appear in the main repository directory. The tool currently detects and cleans up these leaked files, but the root cause is not addressed.

## Expected Behavior

Files created or modified in worker worktrees should remain isolated to those worktrees until explicitly merged. No files should appear in the main repo until the merge coordinator performs a controlled merge.

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/worker.py` or `scripts/little_loops/parallel/merge_coordinator.py`

## Proposed Investigation

1. Review how worktrees are created and whether they're properly isolated
2. Check if any file operations (like `git add` or `shutil` operations) accidentally target the main repo path
3. Examine if the leaked files have a pattern (e.g., test files, issue files)
4. Check if this correlates with specific Claude operations or tool uses

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 2 occurrences in single run
- **Data Risk**: Medium - uncommitted changes in wrong location could cause merge conflicts

---

## Status
**Open** | Created: 2026-01-09 | Priority: P2
