---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# BUG-931: Commit Leak Recovery Skips Main Reset When Main Has Advanced

## Summary

`_recover_committed_leaks()` bails silently when another worker has merged between the leak and the recovery attempt. Leaked commits become permanent on `main` outside any proper merge commit, corrupting git history. The fix is a surgical `git rebase --onto` to excise only the leaked commits.

## Context

Observed during `ll-sprint run tech-debt-04-26` with ENH-825: Claude committed 2 commits (`1a2b08fa`, `033f731c`) directly to `main`. BUG-580 detection fired and `_recover_committed_leaks()` ran, but ENH-497 had already merged on top of the leaked commits, so `current_main_sha != most_recent_leaked`. Recovery was skipped; `033f731c` is now permanently on `main` outside any merge commit.

Related to completed BUG-580 (which added detection+recovery). This is a sub-bug in the recovery path itself.

## Steps to Reproduce

1. Run an `ll-sprint` parallel run with 2+ workers
2. Have a worker commit directly to `main` (simulating a commit leak; triggers BUG-580 detection)
3. Have a second worker merge a separate issue on top of the leaked commits before `_recover_committed_leaks()` runs
4. Observe that `_recover_committed_leaks()` logs a warning and returns without removing the leaked commits
5. Inspect `git log --oneline main`: leaked commits are present outside any merge commit

## Root Cause

- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `_recover_committed_leaks()`, lines 1255–1276
- **Cause**: The `else` branch when `current_main_sha != most_recent_leaked` logs a warning and returns, leaving leaked commits permanently on `main`. No attempt is made to surgically remove them.

```python
if current_main_sha == most_recent_leaked:
    # reset main ✓
else:
    self.logger.warning("...skipping main reset, manual cleanup may be needed")
    # leaked commits stay on main permanently ✗
```

## Current Behavior

When another worker merges after a commit leak but before recovery runs, `_recover_committed_leaks()` skips the reset entirely. The leaked commits persist on `main` as orphaned non-merge commits.

## Expected Behavior

Recovery should attempt a surgical `git rebase --onto` to excise only the leaked commits, even when `main` has advanced.

## Proposed Solution

In the `else` branch at line ~1272, replace the warning-and-return with a rebase attempt:

```python
else:
    # main has advanced past the leaked commits — attempt surgical rebase
    rebase_result = self._git_lock.run(
        ["rebase", "--onto", baseline_head_sha, most_recent_leaked, "HEAD"],
        cwd=self.repo_path,
        timeout=60,
    )
    if rebase_result.returncode == 0:
        self.logger.info(f"[{issue_id}] Surgically removed leaked commits via rebase")
    else:
        self._git_lock.run(["rebase", "--abort"], cwd=self.repo_path, timeout=10)
        self.logger.warning(f"[{issue_id}] Surgical rebase failed — manual cleanup required")
```

Where `baseline_head_sha` is the SHA of `main` before any of the leaked commits (the parent of the first leaked commit).

## Implementation Steps

1. Open `scripts/little_loops/parallel/worker_pool.py`
2. Locate `_recover_committed_leaks()` (~line 1255)
3. Identify the variables already computed: `current_main_sha`, `most_recent_leaked`, and the baseline SHA (first leaked commit's parent)
4. In the `else` branch, add the `rebase --onto` attempt with `rebase --abort` fallback
5. Ensure `_git_lock.run()` is used (not bare subprocess) to respect the git lock
6. Add integration test: simulate leaked commits + concurrent merge, verify rebase path fires

## Verification

- Simulate a commit leak manually (commit directly to main during a sprint run), let recovery run — confirm the rebase path fires and main is cleaned up
- Inspect git history after a parallel run to confirm no stray commits outside merge commits
- Existing tests: `python -m pytest scripts/tests/ -v -k "sprint or parallel or worktree or merge"`

## Motivation

Commit leaks that survive recovery corrupt `main`'s git history with non-merge commits, making it impossible to trace which code came from which issue. This undermines the core guarantee of `ll-sprint`'s parallel merge strategy and requires manual `git` cleanup. This is a sub-bug of the completed BUG-580 recovery mechanism — detection fires but cleanup fails in a common concurrent scenario.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` — `_recover_committed_leaks()` else branch (~line 1272)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — `_git_lock.run()` used for all git operations; must be used here too

### Similar Patterns
- `scripts/little_loops/parallel/orchestrator.py` — `_merge_sequential()` and `_on_worker_complete()` for existing merge/rebase patterns

### Tests
- `python -m pytest scripts/tests/ -v -k "sprint or parallel or worktree or merge"`
- Add integration test: simulate leaked commits + concurrent merge; verify rebase path fires and cleans up

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Corrupts `main` git history with stray non-merge commits; requires manual cleanup when triggered
- **Effort**: Small-Medium — Add `rebase --onto` logic with `rebase --abort` fallback; must correctly identify `baseline_head_sha` (parent of first leaked commit) and use `_git_lock.run()`
- **Risk**: Medium — Git rebase on a shared branch is destructive if misapplied; requires careful handling to avoid data loss
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `git`, `recovery`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P2

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- `scripts/little_loops/parallel/worker_pool.py` `_recover_committed_leaks()` at lines 1255–1276 confirmed ✓
- `current_main_sha != most_recent_leaked` else branch (line 1271–1276): logs warning and returns without attempting rebase ✓
- `_git_lock` is used throughout the method for all other git operations ✓
- No `rebase --onto` logic exists in recovery path ✓
- Bug accurately describes the leaked commit persistence issue

## Session Log
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/677939b4-0616-4d61-b3ac-9611ab44a683.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
