---
discovered_date: 2026-01-17
discovered_by: capture_issue
---

# ENH-082: Report pending merges on ll-parallel startup

## Summary

On startup, `ll-parallel` should check for and report any pending merges from a previous interrupted run. This provides visibility into incomplete work that may need attention before starting a new run.

## Context

User description: "`ll-parallel` Merge status reporting - On startup, report if there are pending merges from a previous interrupted run"

When `ll-parallel` is interrupted (Ctrl+C, crash, system shutdown), some workers may have completed their issue processing but not yet had their changes merged back to main. Currently, there's no way to know if such pending merges exist when starting a new run.

## Current Behavior

- `ll-parallel` starts fresh without checking for remnants of previous runs
- Orphaned worktrees may exist with completed work that was never merged
- Users have no visibility into this state without manual investigation
- Related: FEAT-081 proposes cleanup of orphaned worktrees, but this issue focuses on reporting status

## Expected Behavior

On startup, `ll-parallel` should:
1. Check for existing worktrees from previous runs
2. Identify any that contain completed work not yet merged
3. Report this information to the user before proceeding
4. Optionally offer to resume/merge pending work or clean up

Example output:
```
[ll-parallel] Checking for pending work from previous runs...
[ll-parallel] Found 2 worktrees with potential pending merges:
  - worker-1: BUG-045 (branch: issue/BUG-045, status: completed, not merged)
  - worker-3: ENH-067 (branch: issue/ENH-067, status: in-progress)

Options:
  1. Attempt to merge pending work before continuing
  2. Clean up and start fresh
  3. Continue without action (worktrees will be reused)
```

## Proposed Solution

1. **Detection**: On startup, enumerate existing ll-parallel worktrees
2. **Status Check**: For each worktree:
   - Check if it has a branch that's ahead of main
   - Check for lifecycle/state files indicating completion status
   - Check for uncommitted changes
3. **Reporting**: Display summary of pending work
4. **User Choice**: Present options via prompt or CLI flags:
   - `--resume-pending`: Attempt to merge pending work
   - `--clean-start`: Remove worktrees and start fresh
   - Default: Report and ask user

## Impact

- **Priority**: P3 (quality of life improvement)
- **Effort**: Medium - requires startup checks and optional merge/cleanup logic
- **Risk**: Low - additive feature, doesn't change core workflow

## Related Issues

- **FEAT-081**: Cleanup worktrees command - complements this by providing manual cleanup
- **BUG-079**: Post-merge rebase handling - related to merge workflow (completed)

## Labels

`enhancement`, `ll-parallel`, `captured`, `ux`

---

## Status

**Completed** | Created: 2026-01-17 | Priority: P3

---

## Resolution

- **Action**: add
- **Completed**: 2026-01-17
- **Status**: Completed

### Changes Made

- `scripts/little_loops/parallel/types.py`: Added `PendingWorktreeInfo` dataclass and new config flags (`merge_pending`, `clean_start`, `ignore_pending`) to `ParallelConfig`
- `scripts/little_loops/parallel/orchestrator.py`: Added `_inspect_worktree()`, `_check_pending_worktrees()`, and `_merge_pending_worktrees()` methods; updated `run()` to check for pending work on startup
- `scripts/little_loops/cli.py`: Added `--merge-pending`, `--clean-start`, and `--ignore-pending` CLI flags
- `scripts/little_loops/config.py`: Updated `create_parallel_config()` to accept new parameters
- `scripts/tests/test_orchestrator.py`: Added `TestCheckPendingWorktrees`, `TestInspectWorktree`, and `TestMergePendingWorktrees` test classes

### Verification Results
- Tests: PASS (1345 tests)
- Lint: PASS
- Types: PASS
