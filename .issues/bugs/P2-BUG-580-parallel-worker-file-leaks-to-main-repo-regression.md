---
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# BUG-580: Parallel Worker File Leaks to Main Repo — Regression of BUG-007

## Summary

Despite `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` being set for all parallel worker Claude subprocesses, Claude's git writes are escaping the worktree and landing in the main repo working tree. Observed in the 2026-03-04 sprint run: ENH-535's `manage-issue` Claude committed directly to `main` (commit `3b2e206`) instead of the worktree branch, and BUG-528/BUG-529's changes appeared as unstaged modifications in the main repo.

## Context

From `ll-sprint-run-debug.txt` analysis:

**Confirmed leak**: Commit `3b2e206 feat(ll-loop): surface validation warnings in cmd_validate output` was created at 18:13:41 during ENH-535's parallel worker execution. The commit was on `main`, not on the parallel worktree branch. The worktree itself had no staged changes, causing `_verify_work_was_done` to fail with "No files were changed during implementation."

**Git status evidence** (post-sprint, main repo working tree):
```
 M scripts/little_loops/cli/loop/_helpers.py       ← BUG-528 fix, leaked to main
 M scripts/little_loops/cli/loop/lifecycle.py      ← BUG-529 fix, leaked to main
 M scripts/tests/test_cli_loop_background.py       ← leaked to main
 D .issues/bugs/P3-BUG-528-...md                  ← issue file moved in main (not worktree)
 D .issues/bugs/P3-BUG-529-...md
```

## Current Behavior

`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` does not reliably prevent Claude from operating on the main repo. When Claude writes files or runs `git commit`, these operations can target the main repo rather than the worktree checkout, leaving the worktree branch empty and causing work verification failures.

## Root Cause

- **Env var**: `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` is passed to `subprocess.Popen` in `subprocess_utils.py:93`
- **Failure mode**: The env var may not propagate to all subshells Claude spawns, or Claude may use absolute paths that bypass CWD enforcement
- **Effect chain**: Changes in main repo → worktree has no diff → `_get_changed_files(worktree_path)` returns `[]` → `_verify_work_was_done` returns False → worker fails with "No files were changed during implementation"
- **Secondary effect**: Leaked commits and unstaged changes in main repo need manual cleanup after sprint

## Expected Behavior

All file writes and git operations performed by a parallel worker's Claude session should be confined to that worker's worktree. The main repo should remain clean during parallel processing.

## Proposed Solution

1. **Stronger CWD enforcement**: Before each Claude subprocess call, verify the worktree exists and consider passing `--project-dir <worktree_path>` (if the Claude CLI supports it)
2. **Post-worker validation**: After each Claude subprocess exits, check the main repo for unexpected changes (`git status --porcelain` in main repo) and log warnings before proceeding
3. **Lock the main repo index**: During parallel processing, hold a write lock on the main repo to detect unintended writes early
4. **Verify worktree before manage-issue**: Call `git diff --name-only HEAD <worktree-branch>` from the main repo to confirm changes were committed to the worktree branch, not main

## Similar Patterns

- `BUG-007` (completed): original worktree file leak bug — fix was `_setup_worktree` copies `.claude/` and sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`
- `BUG-038` (completed): leaked files causing cascading merge failures
- `worker_pool.py:392` — `_detect_main_repo_leaks()` detects UNSTAGED leaks but not committed leaks

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` with a multi-issue parallel wave
2. After the sprint, run `git log --oneline -5` and `git status`
3. Observe commits made directly to main during worker execution, and unstaged file modifications in the main repo

## Actual Behavior

- Commits created on `main` by parallel workers
- Unstaged/staged modifications in main repo after sprint
- `_verify_work_was_done` fails → workers fall to sequential retry

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a470e022-6e78-4989-a376-3d78b8dd783e.jsonl`

---
## Status
**Open** | Priority: P2
