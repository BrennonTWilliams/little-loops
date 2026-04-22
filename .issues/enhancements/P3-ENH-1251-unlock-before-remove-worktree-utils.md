---
id: ENH-1251
priority: P3
parent_issue: ENH-1247
discovered_date: "2026-04-22"
discovered_by: issue-size-review
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1251: Unlock Before Remove in worktree_utils.cleanup_worktree

## Summary

Add `git worktree unlock` before `git worktree remove --force` in `worktree_utils.cleanup_worktree()` to prevent cleanup failures when a SIGKILL stranded a lock file. Update and add tests for this code path.

## Parent Issue

Decomposed from ENH-1247: Stranded Lock File Hardening + Breaking Test Updates

## Current Behavior

`worktree_utils.cleanup_worktree()` at line 131 calls `git worktree remove --force` without a preceding `git worktree unlock`. On older git versions, `--force` may not override a lock file, causing cleanup to fail.

## Expected Behavior

1. `worktree_utils.cleanup_worktree()` calls `git worktree unlock <path>` (silently ignoring non-zero return) before `git worktree remove --force`.
2. `worker_pool._cleanup_worktree()` and `cli/loop/run.py` atexit handler inherit the fix automatically via delegation.
3. All affected test assertions pass; new ordering and error-suppression tests exist.

## Proposed Solution

### worktree_utils.py

At `cleanup_worktree()` line 131, before the existing `GitLock.run(["worktree", "remove", "--force", path])` call, add:

```python
git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)
```

Discard return value — `GitLock.run()` uses `subprocess.run` without `check=True` and never raises `CalledProcessError`. Non-zero return (worktree not locked) is silently ignored, consistent with all other `git_lock.run()` callers.

### Test Updates

Run the test suite first and update only tests that actually fail:

- `scripts/tests/test_cli_loop_worktree.py:281-306` — `git_lock.run` patch with `"remove" in args` filter; `unlock` args don't match this filter, so assertions likely pass unchanged
- `scripts/tests/test_cli_loop_worktree.py:409-450` — `WorkerPool._cleanup_worktree()` backward-compat tests; check call-count assertions
- `scripts/tests/test_worker_pool.py:722-778` — `TestSetupAndCleanupWorktree`; filters on `"remove" in c` and `"branch" in c and "-D" in c`; unlock call doesn't match

### New Tests to Write

1. **Ordering test** in `test_cli_loop_worktree.py` — capture all `git_lock.run` call args in order; assert `["worktree", "unlock", path]` appears before `["worktree", "remove", "--force", path]`; follow `_mock_run` pattern at lines 287-306.
2. **Error-suppression test** in `test_cli_loop_worktree.py` or `test_worker_pool.py` — verify that when `git_lock.run(["worktree", "unlock", ...])` returns non-zero, `remove --force` still proceeds; follow `test_cleanup_worktree_handles_nonexistent` pattern at `test_worker_pool.py:780-789`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Function signature confirmed** (`worktree_utils.py:102-108`):
```python
def cleanup_worktree(
    worktree_path: Path,
    repo_path: Path,
    logger: Logger,
    git_lock: GitLock,
    delete_branch: bool = True,
) -> None:
```
Variable passed to git commands: `str(worktree_path)` — use the same form for the unlock call.

**Existing `remove --force` call** (`worktree_utils.py:131-135`):
```python
git_lock.run(["worktree", "remove", "--force", str(worktree_path)], cwd=repo_path, timeout=30)
```
Insert `git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)` immediately before line 131.

**Test helpers available at `test_cli_loop_worktree.py:24-38`**:
```python
def _make_git_lock(logger: MagicMock | None = None) -> GitLock:
    return GitLock(logger=logger)

def _ok(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, "", "")
```

**Ordering test — use `call_order: list[str]` append pattern** (from `test_orchestrator.py:1369-1388`):
```python
def test_unlock_called_before_remove(self, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    git_lock = _make_git_lock()
    call_order: list[str] = []

    def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["worktree", "unlock"]:
            call_order.append("unlock")
        elif args[:2] == ["worktree", "remove"]:
            call_order.append("remove")
        return _ok()

    with patch.object(git_lock, "run", side_effect=_mock_run):
        with patch("subprocess.run", return_value=_ok()):
            cleanup_worktree(worktree_path=wt, repo_path=repo,
                             logger=MagicMock(), git_lock=git_lock, delete_branch=False)

    assert call_order.index("unlock") < call_order.index("remove")
```

**Error-suppression test — return non-zero for unlock, assert remove still fires**:
```python
def test_remove_proceeds_when_unlock_fails(self, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    git_lock = _make_git_lock()
    remove_calls: list[list[str]] = []

    def _mock_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["worktree", "unlock"]:
            return subprocess.CompletedProcess(args, 1, "", "fatal: worktree is not locked")
        if "remove" in args:
            remove_calls.append(args)
        return _ok()

    with patch.object(git_lock, "run", side_effect=_mock_run):
        with patch("subprocess.run", return_value=_ok()):
            cleanup_worktree(worktree_path=wt, repo_path=repo,
                             logger=MagicMock(), git_lock=git_lock, delete_branch=False)

    assert remove_calls, "'git worktree remove' must run even when unlock returns non-zero"
```

**Note for `test_worker_pool.py` equivalents**: `mock_git_run` signature must include `cwd` (`def mock_git_run(args, cwd, **kwargs)`) and patch target is `patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run)` — the attribute is `_git_lock`, not `git_lock`.

## Files to Modify

- `scripts/little_loops/worktree_utils.py:131` — add `git worktree unlock` before `remove --force`; discard return value
- `scripts/tests/test_cli_loop_worktree.py:281-306, 409-450` — update only assertions that fail after the change
- `scripts/tests/test_worker_pool.py:722-778` — update only assertions that fail after the change

## Integration Map

### Callers That Inherit the Fix Automatically

- `scripts/little_loops/parallel/worker_pool.py:628` — `_cleanup_worktree()` delegates to `worktree_utils.cleanup_worktree()` via lazy import
- `scripts/little_loops/cli/loop/run.py:232` — registers `cleanup_worktree()` as atexit handler when `--worktree` flag is set
- `scripts/little_loops/worktree_utils.py:46` — `setup_worktree()` calls `cleanup_worktree()` for pre-existing paths
- `scripts/little_loops/cli/parallel.py:163` — calls `pool.cleanup_all_worktrees()`, which internally calls `_cleanup_worktree()` (delegation chain)
- `scripts/little_loops/parallel/orchestrator.py:1258` — `run()` calls `worker_pool.cleanup_all_worktrees()` at end of execution; fix inherited via delegation chain [wiring pass]

### Safe Tests (Confirmed No Update Needed)

- `scripts/tests/test_subprocess_mocks.py:560-603` — patches `subprocess.run` (not `git_lock.run`); unlock call invisible
- `scripts/tests/test_worker_pool.py:673-700` — patches `git_lock.run` with `"remove" in args` filter; unlock call doesn't match
- `scripts/tests/test_worker_pool.py:780-789` — returns early (path doesn't exist); `git_lock.run` never called
- `scripts/tests/test_orchestrator.py:1810-1829` — mocks the entire `worker_pool` object; no git call visibility; `assert_called_once()` on pool method, not git commands [wiring pass]
- `scripts/tests/test_cli.py:511-516` — mocks the entire pool via `mock_pool`; `cleanup_all_worktrees.assert_called_once()` counts method invocations, not git calls [wiring pass]
- `scripts/tests/test_merge_coordinator.py:2762-2777` — tests `MergeCoordinator._cleanup_worktree()`, a separate standalone implementation that does NOT delegate to `worktree_utils.cleanup_worktree`; unaffected by this change [wiring pass]

### Key Reference

- `scripts/little_loops/parallel/git_lock.py:81-108` — `GitLock.run()` uses `subprocess.run` without `check=True`; raises only `RuntimeError` or `TimeoutExpired` after retry exhaustion (not `CalledProcessError`)

## Implementation Steps

1. Open `worktree_utils.py`, locate `cleanup_worktree()` at line 131.
2. Insert `git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)` immediately before the existing `remove --force` call; discard return value.
3. Run `python -m pytest scripts/tests/test_cli_loop_worktree.py scripts/tests/test_worker_pool.py -v`.
4. Update only assertions that actually fail.
5. Write the two new tests (ordering, error-suppression).
6. Run full regression: `python -m pytest scripts/tests/ -v --tb=short`.

## Acceptance Criteria

- `git worktree unlock` is called before `git worktree remove --force` in `worktree_utils.cleanup_worktree()`
- Non-zero unlock return is silently ignored; `remove --force` still proceeds
- Previously-passing tests pass after any needed assertion updates
- New ordering test and error-suppression test exist and pass

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`, `testing`

## Session Log
- `/ll:wire-issue` - 2026-04-22T16:10:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3f74547-c9d2-42f1-92b3-69f67200920d.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:04:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44820dc9-a5a0-4cb5-b513-13d37140c707.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d28f812d-9c9f-4c1d-9132-8d4f61f6064c.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c75b766d-4937-42d9-a12a-3613998a9d55.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
