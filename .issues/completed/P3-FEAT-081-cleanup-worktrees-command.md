---
discovered_date: 2026-01-17
discovered_by: capture_issue
---

# FEAT-081: Add /ll:cleanup-worktrees command

## Summary

Create a `/ll:cleanup-worktrees` command to manually clean orphaned git worktrees that may remain after interrupted or failed `ll-parallel` runs.

## Context

User description: "A /ll:cleanup-worktrees command to manually clean orphaned worktrees"

The `ll-parallel` tool creates temporary git worktrees for parallel issue processing. When runs are interrupted, fail unexpectedly, or encounter errors during cleanup, orphaned worktrees can remain in the filesystem. Currently, users must manually identify and remove these using git commands.

## Current Behavior

- No user-facing command exists to clean orphaned worktrees
- Users must manually run `git worktree list` and `git worktree remove` commands
- Orphaned worktrees consume disk space and may cause confusion

## Expected Behavior

A `/ll:cleanup-worktrees` command that:
1. Lists all git worktrees in the repository
2. Identifies which are orphaned (no active ll-parallel process using them)
3. Safely removes orphaned worktrees
4. Reports what was cleaned and disk space recovered

## Proposed Solution

Create `commands/cleanup_worktrees.md` with:

1. **Discovery phase**: Run `git worktree list` to enumerate worktrees
2. **Identification**: Filter to ll-parallel worktrees (pattern: `worker-*` in `.worktrees/` directory)
3. **Validation**: Check if any are actively in use (lock files, running processes)
4. **Cleanup**: Remove orphaned worktrees with `git worktree remove --force` if needed
5. **Reporting**: Show summary of cleaned worktrees

### Optional enhancements:
- `--dry-run` flag to preview what would be cleaned
- `--force` flag to skip confirmation
- `--all` flag to clean non-ll-parallel worktrees too

## Impact

- **Priority**: P3 (useful utility, not blocking)
- **Effort**: Low - straightforward command implementation
- **Risk**: Low - uses standard git worktree commands

## Labels

`feature`, `command`, `captured`, `ll-parallel`

---

## Status

**Completed** | Created: 2026-01-17 | Completed: 2026-01-17 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-17
- **Status**: Completed

### Changes Made
- `commands/cleanup_worktrees.md`: Created new command with `run` and `dry-run` modes
- `thoughts/shared/plans/2026-01-17-FEAT-081-management.md`: Implementation plan

### Implementation Details
The command uses bash/git directly (no Python dependencies) following the pattern from `hooks/scripts/session-cleanup.sh`. Supports:
- Default `run` mode: Removes all `worker-*` directories and `parallel/*` branches
- `dry-run` mode: Preview what would be cleaned without making changes
- Automatic git worktree prune after cleanup
- Fallback to `rm -rf` if `git worktree remove` fails

### Verification Results
- File exists: PASS
- Lint: PASS (no new issues)
- Types: PASS
