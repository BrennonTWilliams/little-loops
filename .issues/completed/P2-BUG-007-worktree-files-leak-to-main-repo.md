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
- **Likely Module**: `scripts/little_loops/parallel/worker_pool.py` (contains workaround code)
- **Related**: `scripts/little_loops/parallel/merge_coordinator.py` (handles merge conflicts from leaks)

## Root Cause

This is a known issue with Claude Code's project root detection when working in git worktrees (referenced in worker_pool.py as GitHub #8771). Claude Code may incorrectly identify the main repository as the project root instead of the worktree, causing file writes to go to the wrong location.

## Current Workaround

The codebase already has detection and cleanup logic in `worker_pool.py`:
- `_get_main_repo_baseline()` (line 817): Captures git status before worker starts
- `_detect_main_repo_leaks()` (line 682): Compares status after worker completes to detect new files
- `_cleanup_leaked_files()` (line 746): Removes leaked files from main repo

## Fix Implemented

**Root Cause Analysis**: Claude Code's project root detection prioritizes `.claude/` directory, then `.git/`, then cwd. In git worktrees, the `.git` is a file pointing to main repo. Without a `.claude/` directory in the worktree, Claude Code detects the main repo as project root.

**Solution (2 changes)**:

1. **Copy `.claude/` directory to worktrees** (`worker_pool.py:405-416`)
   - Copies entire `.claude/` directory during worktree setup
   - Establishes project root anchor for Claude Code
   - Existing `worktree_copy_files` config entries for `.claude/*` are skipped (already copied)

2. **Set environment variable** (`subprocess_utils.py:84-88`)
   - Sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` when launching Claude CLI
   - Keeps Claude in the project working directory after bash commands

**Safety Net Retained**: Existing leak detection/cleanup logic (`_detect_main_repo_leaks`, `_cleanup_leaked_files`) is retained as defense-in-depth.

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 2 occurrences in single run
- **Data Risk**: Medium - uncommitted changes in wrong location could cause merge conflicts

---

## Labels
- component:parallel
- type:bug
- root-cause:external-dependency

## Status
**Reopened** | Created: 2026-01-09 | Priority: P2 | Fixed: 2026-01-09 | Reopened: 2026-01-12

---

## Reopened

- **Date**: 2026-01-12
- **By**: /analyze_log
- **Reason**: Issue recurred despite `.claude/` copy fix and environment variable setting

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: BUG-636

```
[12:31:27] Found 2 file(s) changed: ['src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py', 'tests/unit/test_ooda_prompt.py']
[12:31:27] BUG-636 leaked 1 file(s) to main repo: ['issues/bugs/P1-BUG-636-generic-mesh-references-in-manifold-checks.md']
[12:31:27] BUG-636 completed in 5.5 minutes
```

### Analysis

The previous fix copied `.claude/` directory to worktrees and set `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`. However, a leak still occurred:

**Observations**:
1. The leaked file is an issue file (`issues/bugs/P1-BUG-636-...`), not a source file
2. This suggests Claude Code may have created/modified this issue file and written it to the wrong location
3. The fix may not be effective for all file write scenarios, or there's a race condition

**Possible causes**:
1. Issue file creation uses a different path resolution than source files
2. The `.claude/` copy may not be complete or may be overwritten
3. Claude Code may cache the project root before `.claude/` is copied
4. The environment variable may not be respected in all scenarios

### Next Steps

1. Investigate the timing of `.claude/` copy vs Claude Code launch
2. Verify the environment variable is being passed correctly
3. Check if issue file creation uses a special path resolution
4. Consider additional anchoring strategies (symlinks, explicit project root config)

---

## Resolution (Second Fix)

- **Action**: fix
- **Completed**: 2026-01-12
- **Status**: Completed

### Root Cause Identified

The `_detect_worktree_model_via_api()` function in `worker_pool.py` invoked Claude CLI without
the `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` environment variable that was added to
`subprocess_utils.py` as part of the original BUG-007 fix.

**Key discovery**: This function uses `subprocess.run()` directly instead of the shared
`run_claude_command()` function, bypassing the environment variable setup. When `--show-model`
is enabled, this becomes the FIRST Claude CLI invocation in each worktree, potentially
establishing a cached project root before subsequent invocations with the proper environment.

### Changes Made

**File**: `scripts/little_loops/parallel/worker_pool.py`
- Added `os` import
- Added environment variable setup to `_detect_worktree_model_via_api()` function (lines 453-457)
- Environment variable `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` now set for model detection API call
- Ensures first Claude CLI invocation has same project root behavior as subsequent calls

### Verification Results
- Tests: PASS (491 tests)
- Lint: PASS
- Types: PASS
