---
discovered_date: "2026-04-22"
discovered_by: issue-size-review

depends_on: [FEAT-1075, ENH-1176]
decision_needed: false
size: Very Large
confidence_score: 93
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
parent: ENH-1197
status: done
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1247: Stranded Lock File Hardening + Breaking Test Updates

## Summary

When `git worktree remove --force` is called on a locked worktree, older git versions may not honor `--force`. Adding `git worktree unlock <path>` before `remove --force` in `worktree_utils.cleanup_worktree()` and `merge_coordinator.py` prevents this failure mode. This change is a net-new command in existing git call sequences, which breaks call-order assertions in four existing test files — these must be updated as part of this issue.

## Parent Issue

Decomposed from ENH-1197: Harden Worktree Cleanup Against SIGKILL Mid-Teardown

## Current Behavior

`worktree_utils.cleanup_worktree()` at line 131 calls `git worktree remove --force` without a preceding `git worktree unlock`. If a SIGKILL stranded the lock file (`.git/worktrees/<name>/locked`), the remove may fail on older git. `merge_coordinator.py:1205` has its own `git worktree remove --force` with the same gap and does not delegate to `worktree_utils.cleanup_worktree()`.

## Expected Behavior

1. `worktree_utils.cleanup_worktree()` calls `git worktree unlock <path>` (suppressing errors if not locked) before `git worktree remove --force`.
2. `merge_coordinator.py:1205` either adds the same unlock call or is refactored to delegate to `worktree_utils.cleanup_worktree()` so the fix lives in one place.
3. All four affected test files have updated call-order/call-count assertions to account for the new `unlock` call.

## Proposed Solution

### worktree_utils.py

At `cleanup_worktree()` line 131, before the existing `GitLock.run(["worktree", "remove", "--force", path])` call, add:

```python
try:
    GitLock.run(["worktree", "unlock", str(path)], cwd=repo_path)
except subprocess.CalledProcessError:
    pass  # not locked; ignore
```

### merge_coordinator.py

At line 1205, either:
- (Preferred) refactor to call `worktree_utils.cleanup_worktree()` so the unlock is inherited, OR
- Add the same `unlock` call inline before the existing `remove --force`

### Breaking Test Updates

The unlock call is a new entry in the git command sequence. Update:

- `scripts/tests/test_cli_loop_worktree.py:281-306` — `git_lock.run` patch; `unlock` is captured before `remove`; fix call-order assertions
- `scripts/tests/test_cli_loop_worktree.py:409-450` — `WorkerPool._cleanup_worktree()` backward-compat tests; check call-count assertions
- `scripts/tests/test_worker_pool.py:722-778` — `TestSetupAndCleanupWorktree`; check `len()` and list-filter assumptions
- `scripts/tests/test_orchestrator.py:350-444` — `TestCleanupOrphanedWorktrees` mock call counts

Also check `test_orchestrator.py:414-444` — if implementation delegates to `_process_alive` from `fsm/concurrency.py`, patch path changes to `little_loops.parallel.orchestrator._process_alive`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Error handling correction**: `GitLock.run()` (`scripts/little_loops/parallel/git_lock.py:81-108`) uses `subprocess.run` **without** `check=True` — it returns a `CompletedProcess` and **never raises `CalledProcessError`**. The proposed `try/except subprocess.CalledProcessError` will never fire. The correct approach:

```python
# Minimal: discard return value (non-zero = not locked, safe to ignore)
# This matches how all other git_lock.run() callers already handle errors
git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)

# OR follow orchestrator.py:272-302 pattern if wrapping the paired unlock+remove together:
try:
    git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)
    git_lock.run(["worktree", "remove", "--force", str(worktree_path)], cwd=repo_path, timeout=30)
except Exception:
    pass  # only fires on TimeoutExpired or RuntimeError (retries exhausted), not on non-zero returncode
```

**Third implementation site (not in Files to Modify)**: `orchestrator._cleanup_orphaned_worktrees()` at `scripts/little_loops/parallel/orchestrator.py:275-279` has its own inline `git worktree remove --force`, already wrapped in `except Exception as e: self.logger.warning(...)` at line 301. Insert the `unlock` call before line 275 — the existing broad `except Exception` provides the error suppression.

**Test assertion analysis**: All four test files use list-filter patterns (`"remove" in args`, `args[:2] == ["worktree", "remove"]`) to select the remove call. An `unlock` call produces `args[:2] == ["worktree", "unlock"]`, which does **not** match these filters. Based on code analysis, existing assertions may pass without modification. Run the full regression suite first; update only tests that actually fail.

## Files to Modify

- `scripts/little_loops/worktree_utils.py` — `cleanup_worktree()` at line 131: add `git worktree unlock` before `remove --force`
- `scripts/little_loops/parallel/merge_coordinator.py` — line 1205: add unlock or delegate to `worktree_utils.cleanup_worktree()`
- `scripts/tests/test_cli_loop_worktree.py` — update call-order assertions at lines 281-306, 409-450
- `scripts/tests/test_worker_pool.py` — update call-count/list assertions at lines 722-778
- `scripts/tests/test_orchestrator.py` — update mock assertions at lines 350-444

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py:131` — `cleanup_worktree()`: add `git worktree unlock` before `remove --force`; discard return value
- `scripts/little_loops/parallel/merge_coordinator.py:1205` — `_cleanup_worktree()`: add unlock or delegate to `worktree_utils.cleanup_worktree()` (requires new import; `branch_name` is already a parameter here, unlike `worktree_utils` which derives it via `rev-parse`)
- `scripts/little_loops/parallel/orchestrator.py:275` — `_cleanup_orphaned_worktrees()`: add unlock before `remove --force` (already inside `except Exception as e: logger.warning(...)` at line 301)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py:628` — `_cleanup_worktree()` delegates to `worktree_utils.cleanup_worktree()` via lazy import; inherits fix automatically
- `scripts/little_loops/cli/loop/run.py:232` — registers `cleanup_worktree()` as `atexit` handler when `--worktree` flag is set; inherits fix automatically
- `scripts/little_loops/worktree_utils.py:46` — `setup_worktree()` calls `cleanup_worktree()` for pre-existing paths; inherits fix automatically
- `scripts/little_loops/parallel/merge_coordinator.py:1174` — `_handle_success()` calls `MergeCoordinator._cleanup_worktree()` (independent, not delegating)
- `scripts/little_loops/parallel/orchestrator.py:162` — orchestrator startup calls `_cleanup_orphaned_worktrees()` before state load

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:163` — calls `pool.cleanup_all_worktrees()` on `WorkerPool` instance, which internally calls `_cleanup_worktree()` for each worktree (line 1317); inherits fix automatically via delegation chain

### Similar Patterns
- `scripts/little_loops/parallel/orchestrator.py:272-302` — broad `try/except Exception` wrapping multiple `git_lock.run()` calls; model for the unlock+remove paired pattern
- `scripts/little_loops/parallel/git_lock.py:81-108` — `GitLock.run()`: never raises `CalledProcessError`; raises only `RuntimeError` or `TimeoutExpired` after retry exhaustion

### Tests
- `scripts/tests/test_cli_loop_worktree.py:281-306` — filters on `"remove" in args`
- `scripts/tests/test_cli_loop_worktree.py:409-450` — `WorkerPool._cleanup_worktree()` backward-compat tests
- `scripts/tests/test_worker_pool.py:722-778` — filters on `"remove" in c` and `"branch" in c and "-D" in c`
- `scripts/tests/test_orchestrator.py:350-444` — filters on `args[:2] == ["worktree", "remove"]`
- `scripts/tests/test_merge_coordinator.py` — check for assertions on `_cleanup_worktree()` git call sequences

_Wiring pass added by `/ll:wire-issue`:_

**Safe tests (mentioned for completeness — confirmed no update needed):**
- `scripts/tests/test_subprocess_mocks.py:560-603` — `TestWorkerPoolGitOperations.test_cleanup_worktree_removes_worktree`; patches `subprocess.run` (not `git_lock.run`), so the new `unlock` call through `git_lock.run` is invisible to it; `"remove" in c` filter still holds — **no changes needed**
- `scripts/tests/test_worker_pool.py:673-700` — `test_setup_worktree_removes_existing`; patches `git_lock.run` with `"remove" in args` filter; `unlock` call doesn't match filter — **no changes needed**
- `scripts/tests/test_worker_pool.py:780-789` — `test_cleanup_worktree_handles_nonexistent`; returns early (path doesn't exist), `git_lock.run` never called — **no changes needed**

**New tests to write (coverage gaps identified by wiring analysis):**
- New test in `test_cli_loop_worktree.py` — verify `["worktree", "unlock", path]` appears in `git_lock.run` calls **before** `["worktree", "remove", "--force", path]`; use `call_args_list` or ordered capture list
- New test in `test_merge_coordinator.py` — verify `MergeCoordinator._cleanup_worktree()` calls unlock→remove sequence for an **existing** worktree path (currently the only test uses a nonexistent path and never reaches `git_lock.run`)
- New test in `test_cli_loop_worktree.py` or `test_worker_pool.py` — verify unlock failure (non-zero returncode from `git_lock.run`) is silently swallowed and `remove --force` still proceeds; follow `test_deletes_branch_when_delete_branch_true` pattern at lines 309-338

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md:174` — manual recovery snippet shows `git worktree remove --force "$w"` without a preceding `git worktree unlock`; after this fix the Python API does this more robustly than the docs suggest — consider adding `git worktree unlock "$w" 2>/dev/null || true` before the remove step
- `commands/cleanup-worktrees.md:116-117` (out of scope) — independent bash implementation with same gap; not modified by this issue but now diverges from Python behavior
- `hooks/scripts/session-cleanup.sh:41` (out of scope) — independent bash implementation at `git worktree remove --force "$w" 2>/dev/null || true`; same divergence, not modified by this issue

## Implementation Steps

1. **`worktree_utils.py:131`** — Insert `git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=repo_path, timeout=10)` immediately before the existing `remove --force` call; discard return value (consistent with all other callers).
2. **`merge_coordinator.py:1205`** — Either (a) add `import little_loops.worktree_utils` and delegate to `worktree_utils.cleanup_worktree()`, adapting the signature since `branch_name` is already a parameter; OR (b) insert the inline `unlock` call before line 1205, discarding return value.
3. **`orchestrator.py:275`** — Insert `self._git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=self.repo_path, timeout=10)` before line 275; the existing `except Exception` block at line 301 provides error suppression.
4. **Run tests before editing assertions**: `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_cli_loop_worktree.py scripts/tests/test_worker_pool.py -v` — list-filter assertions likely pass unchanged; update only tests that actually fail.
5. **Full regression**: `python -m pytest scripts/tests/ -v --tb=short`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Write unlock→remove ordering test** in `test_cli_loop_worktree.py` — new test that captures all `git_lock.run` calls in order and asserts `["worktree", "unlock", ...]` precedes `["worktree", "remove", "--force", ...]`; follow `_mock_run` pattern at lines 287-306
7. **Write MergeCoordinator unlock test** in `test_merge_coordinator.py` — new test in `TestCleanupWorktreeFallback` that creates an actual worktree path (`.exists()` returns `True`), patches `coordinator._git_lock.run`, and asserts the unlock→remove→branch-D sequence; this path has zero sequence-level coverage today
8. **Write unlock error-suppression test** — new test verifying that when `git_lock.run(["worktree", "unlock", ...])` returns non-zero, the `remove --force` call still proceeds; follow `test_cleanup_worktree_handles_nonexistent` pattern at `test_worker_pool.py:780-789` for fixture setup
9. **Update `docs/development/TROUBLESHOOTING.md:174`** (optional, low priority) — add `git worktree unlock "$w" 2>/dev/null || true` before the `remove --force` recovery step in the manual recovery snippet

## Acceptance Criteria

- `git worktree unlock` is called before `git worktree remove --force` in all cleanup paths
- Unlock errors are suppressed (worktree not locked is normal)
- `merge_coordinator.py:1205` uses the same unlock-then-remove sequence as `worktree_utils`
- All previously-passing tests pass after call-order assertion updates
- Regression run: `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_cli_loop_worktree.py scripts/tests/test_worker_pool.py -v`

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`, `testing`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-22_

**Readiness Score**: 93/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- **Dependency metadata may be stale**: `depends_on: [FEAT-1075, ENH-1176]` lists two deferred issues. ENH-1247 modifies existing code that doesn't technically require the new FSM ParallelRunner (FEAT-1075) or resource limits (ENH-1176). Verify no runtime import path pulls in FEAT-1075 module code before starting.
- **merge_coordinator approach not chosen**: Step 2 offers delegation vs. inline unlock with "(Preferred)" noted but not decided. The delegation path requires adapting the `branch_name` parameter difference.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-22T16:01:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d28f812d-9c9f-4c1d-9132-8d4f61f6064c.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/028ea34b-57e7-4d93-b629-3d0ba739f75b.jsonl`
- `/ll:wire-issue` - 2026-04-22T15:54:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/028ea34b-57e7-4d93-b629-3d0ba739f75b.jsonl`
- `/ll:refine-issue` - 2026-04-22T15:48:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04dfc0ce-b9e2-4f0a-a081-7ccda5b93d64.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d28f812d-9c9f-4c1d-9132-8d4f61f6064c.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-22
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1251: Unlock Before Remove in worktree_utils.cleanup_worktree
- ENH-1252: Unlock Before Remove in merge_coordinator._cleanup_worktree
- ENH-1253: Unlock Before Remove in orchestrator._cleanup_orphaned_worktrees

---

**Decomposed** | Created: 2026-04-22 | Priority: P3
