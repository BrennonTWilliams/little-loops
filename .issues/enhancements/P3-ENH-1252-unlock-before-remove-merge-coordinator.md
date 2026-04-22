---
id: ENH-1252
priority: P3
parent_issue: ENH-1247
discovered_date: "2026-04-22"
discovered_by: issue-size-review
size: Small
decision_needed: false
confidence_score: 98
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1252: Unlock Before Remove in merge_coordinator._cleanup_worktree

## Summary

Add `git worktree unlock` before `git worktree remove --force` in `merge_coordinator.MergeCoordinator._cleanup_worktree()` (line 1205), which does not delegate to `worktree_utils.cleanup_worktree()` and therefore does not inherit the fix from ENH-1251. Add a new sequence-level test covering this code path.

## Parent Issue

Decomposed from ENH-1247: Stranded Lock File Hardening + Breaking Test Updates

## Current Behavior

`merge_coordinator.py:1194-1221` (`_cleanup_worktree()`) has its own `git worktree remove --force` (the call is inside that range) without a preceding `git worktree unlock`. It is called by `_finalize_merge()` at line 1174 (the issue previously referred to this method as `_handle_success()`; the actual name is `_finalize_merge()`). It does not delegate to `worktree_utils`, so it will not pick up the fix from ENH-1251.

## Expected Behavior

`MergeCoordinator._cleanup_worktree()` calls `git worktree unlock` before `git worktree remove --force`, with unlock errors silently suppressed.

## Proposed Solution

**Decision: inline unlock** (delegation to `worktree_utils.cleanup_worktree()` was considered and rejected — see Decision Notes below).

At `merge_coordinator.py:1194-1221` (`_cleanup_worktree()`), insert before line 1205:

```python
self._git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=self.repo_path, timeout=10)
```

Discard return value — `GitLock.run()` never raises `CalledProcessError` (uses `subprocess.run` without `check=True`).

### Decision Notes

Delegation to `worktree_utils.cleanup_worktree()` was rejected for two reasons:

1. **Safety regression**: The utility lacks the `parallel/` branch guard present in `MergeCoordinator._cleanup_worktree()`, which could cause non-`parallel/` branches to be deleted.
2. **Silent branch-deletion failure**: The utility derives branch name via `git rev-parse --abbrev-ref HEAD` inside the worktree. If the worktree directory is already gone when branch deletion runs, `rev-parse` fails and the branch is silently skipped — unlike the current approach which passes `branch_name` as a parameter. This is a real race condition in cleanup paths.

The goal is narrowly to add unlock before remove; delegation would change behavior in two ways unrelated to the fix.

### New Test to Write

In `test_merge_coordinator.py` — add test in `TestCleanupWorktreeFallback` at line 2762 (class currently has only one test at line 2762 covering the early-return path for non-existent worktrees) that:
- Creates a worktree path where `.exists()` returns `True` (use `tmp_path / "test-worktree"` and `mkdir()` it)
- Patches `coordinator._git_lock.run` using `patch.object(coordinator._git_lock, "run", side_effect=mock_git_run)` (established pattern from `test_merge_coordinator.py:2936-2975`)
- Records all `cmd` args passed to `mock_git_run` into a `git_commands_run: list[list[str]] = []`
- Asserts strict ordering with `enumerate()` + index comparison:

```python
calls = git_commands_run
unlock_idx = next(i for i, c in enumerate(calls) if c[:3] == ["worktree", "unlock", str(worktree_path)])
remove_idx = next(i for i, c in enumerate(calls) if c[:2] == ["worktree", "remove"])
assert unlock_idx < remove_idx
```

This path currently has zero sequence-level test coverage.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `test_merge_coordinator.py:2762` — `TestCleanupWorktreeFallback` class; single existing test uses non-existent worktree path (early-return branch), so `_git_lock.run` is never reached there
- `test_merge_coordinator.py:2936-2975` — `TestPopStashConflictCleanup` — the canonical pattern for recording all `cmd` lists and asserting membership; extend with `enumerate()` index comparison for strict ordering
- `test_orchestrator.py:427-444` — orchestrator cleanup test that directly assigns `_git_lock.run` instead of using `patch.object`; the `test_merge_coordinator` convention uses `patch.object` — follow that form here

## Files to Modify

- `scripts/little_loops/parallel/merge_coordinator.py:1205` — add unlock or delegate to `worktree_utils.cleanup_worktree()`
- `scripts/tests/test_merge_coordinator.py` — add new sequence test

## Integration Map

### Callers

- `scripts/little_loops/parallel/merge_coordinator.py:1174` — `_finalize_merge()` calls `MergeCoordinator._cleanup_worktree()` (this is the only caller)

### Key References

- `scripts/little_loops/parallel/git_lock.py:81-108` — `GitLock.run()` never raises `CalledProcessError`; returns `CompletedProcess` regardless of exit code; only retries on `index.lock` errors
- `scripts/little_loops/worktree_utils.py:102-142` — `cleanup_worktree(worktree_path, repo_path, logger, git_lock, delete_branch=True)` — fixed in ENH-1251 (sister issue); derives branch name via `git rev-parse --abbrev-ref HEAD` inside the worktree (not from a pre-supplied parameter); lacks the `parallel/` guard present in `_cleanup_worktree`
- `scripts/little_loops/parallel/orchestrator.py:272-302` — `_cleanup_orphaned_worktrees()` — inline implementation of the same three-step pattern (remove → rmtree fallback → branch -D); also lacks unlock (covered by ENH-1253)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/parallel/worker_pool.py` — also has a `_cleanup_worktree()` method but delegates to `worktree_utils.cleanup_worktree()`; contrast with `merge_coordinator._cleanup_worktree()` which is fully inline
- `scripts/tests/test_merge_coordinator.py:2762` — `TestCleanupWorktreeFallback` class; add the new sequence test here
- `scripts/tests/test_merge_coordinator.py:2936-2975` — `TestPopStashConflictCleanup` — established pattern for `_git_lock.run` patching with command recording
- `scripts/tests/test_cli_loop_worktree.py:281-306` — call-ordering tests for `cleanup_worktree()` with unlock; model for ordering assertions
- `scripts/tests/test_orchestrator.py:350-444` — `TestCleanupOrphanedWorktrees`; call-ordering patterns for similar cleanup logic

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_merge_coordinator.py:661` — `TestProcessMergeStashIntegration.test_stash_popped_on_success` — exercises `_cleanup_worktree` on the success path indirectly via `_process_merge` → `_finalize_merge`; no ordering assertions but runs actual git commands against a real temp repo; **verify still passes after implementation** — it will exercise the new unlock call without any mocking of `_git_lock.run`
- `scripts/tests/test_merge_coordinator.py:2775` — `test_cleanup_nonexistent_worktree` — the only direct call to `_cleanup_worktree(path, "parallel/ghost")`; if delegation approach (option a) is chosen and the `branch_name` parameter is removed from the signature, this call site must be updated to match

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/test-quality-audit.md:73,107` — notes `_cleanup_worktree` as lacking test coverage; becomes stale once the new sequence test is added (informational — no content change required, but worth awareness)

## Implementation Steps

1. Open `merge_coordinator.py`, locate `_cleanup_worktree()` around line 1205.
2. Insert `self._git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=self.repo_path, timeout=10)` before the `remove --force` call; discard return value.
3. Write the new sequence test in `test_merge_coordinator.py`.
4. Run `python -m pytest scripts/tests/test_merge_coordinator.py -v`.
5. Confirm `TestProcessMergeStashIntegration.test_stash_popped_on_success` (`test_merge_coordinator.py:661`) still passes — it exercises `_cleanup_worktree` on the real success path with no `_git_lock.run` mocking.
6. Run full regression: `python -m pytest scripts/tests/ -v --tb=short`.

## Acceptance Criteria

- `git worktree unlock` is called before `git worktree remove --force` in `MergeCoordinator._cleanup_worktree()`
- Unlock errors are silently suppressed
- New sequence test passes covering unlock→remove order

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`, `testing`

## Session Log
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a43c1ae8-e64e-4533-a175-4b2b06462f8f.jsonl`
- `/ll:wire-issue` - 2026-04-22T16:21:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dff37768-1fee-4fb7-9e66-0c89101a95df.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:15:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/367ee7a8-400a-4b7b-8f39-2f6e5f8e3e1d.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d28f812d-9c9f-4c1d-9132-8d4f61f6064c.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
