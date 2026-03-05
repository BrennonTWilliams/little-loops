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

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Anchor**: `in run_claude_command()`
- **Cause**: `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` is set in the env passed to `subprocess.Popen`, but the env var may not propagate to all subshells Claude spawns internally, or Claude may resolve absolute paths that bypass CWD enforcement. A duplicate env var set also exists in `worker_pool.py` `_detect_worktree_model_via_api()`.
- **Effect chain**: Changes land in main repo → worktree has no diff → `_get_changed_files(worktree_path)` returns `[]` → `_verify_work_was_done()` returns False → worker fails with "No files were changed during implementation"
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
- `worker_pool.py:910` — `_detect_main_repo_leaks()` detects UNSTAGED leaks but not committed leaks

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` with a multi-issue parallel wave
2. After the sprint, run `git log --oneline -5` and `git status`
3. Observe commits made directly to main during worker execution, and unstaged file modifications in the main repo

## Actual Behavior

- Commits created on `main` by parallel workers
- Unstaged/staged modifications in main repo after sprint
- `_verify_work_was_done` fails → workers fall to sequential retry

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`: primary env var set location; investigate if additional CWD enforcement is needed
- `scripts/little_loops/parallel/worker_pool.py` — `_run_claude_command()`: wrapper that calls `_run_claude_base`; investigate `--project-dir` flag support
- `scripts/little_loops/parallel/worker_pool.py` — `_detect_main_repo_leaks()`: currently detects unstaged leaks only; extend to detect committed leaks (compare `git log` against worktree branch)
- `scripts/little_loops/parallel/worker_pool.py` — `_setup_worktree()`: add post-setup validation step

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — wraps `run_claude_command` from subprocess_utils; any fix must be compatible
- `scripts/little_loops/parallel/worker_pool.py` — primary caller of `run_claude_command` for parallel workers

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:574` — duplicate env var set in `_detect_worktree_model_via_api()`: keep in sync

### Tests
- `scripts/tests/test_worker_pool.py` — add test for commit-leak detection in `_detect_main_repo_leaks()`
- `scripts/tests/test_subprocess_utils.py` — verify `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` is always set
- `scripts/tests/test_subprocess_mocks.py` — may need mock updates for new validation behavior

### Documentation
- N/A — internal infrastructure change

### Configuration
- N/A — no config file changes

## Implementation Steps

1. Investigate if Claude CLI supports `--project-dir <path>` flag; if so, pass it from `_run_claude_command()` in addition to `cwd`
2. Extend `_detect_main_repo_leaks()` to detect committed leaks: compare `git log --oneline main` before and after worker execution
3. Add post-worker main-repo validation in the worker execution loop (Step 8 area in `worker_pool.py`) — log warning if unexpected commits appear on main
4. Optionally add a write-lock or advisory lock on the main repo index during parallel runs to detect unintended writes early
5. Add regression test reproducing the leak scenario (mock Claude subprocess that writes to main repo path)

## Impact

- **Priority**: P2 — Regression of fixed bug BUG-007; corrupts main repo state during parallel sprints, requiring manual cleanup; blocks reliable sprint automation
- **Effort**: Medium — Root cause is unclear (env var vs absolute path vs Claude CLI behavior); investigation needed before fix; `_detect_main_repo_leaks()` extension is well-bounded
- **Risk**: Medium — Changes touch core parallel execution path; risk of breaking worktree isolation in the other direction; needs careful testing
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `worktree`, `regression`

## Resolution

**Status**: Fixed | Resolved: 2026-03-05

### Changes Made

**`scripts/little_loops/parallel/worker_pool.py`**:
- Added `_get_main_head_sha()` — captures the current HEAD SHA of the main repo via `git rev-parse HEAD` using the git lock
- Added `_detect_committed_leaks(baseline_head_sha)` — compares main's HEAD after worker execution against the baseline SHA captured before; if HEAD advanced, retrieves leaked commit SHAs via `git log --format=%H baseline..HEAD`
- Added `_recover_committed_leaks(leaked_commits, worktree_path, baseline_head_sha, issue_id)` — cherry-picks leaked commits (oldest-first) onto the worktree branch, then resets main to baseline if main hasn't advanced further
- Modified `_process_issue()`: captures `baseline_head_sha` before the try block; reorders steps so detection (8) and committed-leak recovery (8b) happen before work verification (7), giving recovery a chance to populate `changed_files` before the "No files were changed" check

**`scripts/tests/test_worker_pool.py`**:
- `test_get_main_head_sha_returns_sha` — verifies SHA is extracted from git output
- `test_get_main_head_sha_returns_empty_on_failure` — verifies graceful fallback
- `test_detect_committed_leaks_no_leaks_same_sha` — no-op when HEAD is unchanged
- `test_detect_committed_leaks_empty_baseline` — no-op when baseline is empty string
- `test_detect_committed_leaks_finds_new_commits` — detects commits added to main
- `test_recover_committed_leaks_cherry_pick_success` — cherry-picks in chronological order and resets main
- `test_recover_committed_leaks_cherry_pick_fails` — returns False on cherry-pick conflict
- `test_recover_committed_leaks_skips_reset_when_main_advanced` — skips reset if main has diverged
- `test_process_issue_recovers_committed_leaks` — integration test for the full recovery flow

### Root Cause Confirmed
`_detect_main_repo_leaks()` only checks `git status --porcelain` (unstaged changes). When Claude commits directly to `main` (as happened with ENH-535 commit `3b2e206`), committed changes are "clean" in git status and invisible to the existing detection. `_get_changed_files(worktree_path)` then returned `[]` because the worktree branch had no new commits, causing `_verify_work_was_done` to fail.

### Note on Prevention
`--project-dir` does not exist in the Claude CLI (confirmed). The existing `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` + `.claude/` copy approach (BUG-007 fix) remains the prevention layer. This fix adds detection and recovery for when prevention fails.

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a470e022-6e78-4989-a376-3d78b8dd783e.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7c88523-a3c9-4dde-9eb7-a055993ac4ef.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe19332-ebe5-498a-8fd2-9f987738f4b9.jsonl`
- `/ll:manage-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/700c60f0-215c-43c7-af34-5e23b90ff029.jsonl`

---
## Status
**Fixed** | Resolved: 2026-03-05
