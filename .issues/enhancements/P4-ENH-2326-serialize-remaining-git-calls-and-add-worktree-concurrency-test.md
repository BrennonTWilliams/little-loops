---
id: ENH-2326
title: Route remaining bare git calls through GitLock and add a worktree concurrency
  regression test
type: ENH
status: done
priority: P4
captured_at: '2026-06-26T22:26:49Z'
completed_at: '2026-06-30T04:53:35Z'
discovered_date: '2026-06-26'
discovered_by: audit
labels:
- worktree
- parallel
- testing
- tech-debt
relates_to:
- BUG-140
- BUG-142
- BUG-579
depends_on:
- ENH-2329
decision_needed: false
confidence_score: 96
outcome_confidence: 83
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 20
---

# ENH-2326: Route remaining bare git calls through GitLock and add a worktree concurrency regression test

## Summary

Two parts, both low-risk hardening of the worktree subsystem:
1. A couple of git invocations in `worktree_utils.py` use bare `subprocess.run` and bypass
   `GitLock`, inconsistent with the serialization discipline used everywhere else.
2. The race-condition fixes (BUG-140 create/merge race, BUG-142 active-worktree delete,
   BUG-579 orphan-vs-live) are each unit-tested in isolation, but **no test exercises
   concurrent workers** — a regression of any of those fixes would pass CI.

## Motivation

The race fixes are the highest-value robustness work in this subsystem, yet nothing guards
them against regression under actual concurrency; a future refactor (e.g. EPIC-1867's
orchestrator decomposition) could silently reintroduce a race. Routing the stray calls through
`GitLock` is cheap consistency that removes a "why is this one different?" trap for future
maintainers. Neither part changes behavior; both reduce the chance of a silent regression.

## Current Behavior

Bare `subprocess.run` git calls bypassing `GitLock` in
`scripts/little_loops/worktree_utils.py`:
- `:78` — git-identity copy in `setup_worktree()` (note `:76` reads via `git_lock.run`, then
  `:78` writes via bare `subprocess.run`).
- `:141` — branch detection in `cleanup_worktree()` (note `:149`/`:160` in the same function
  use `git_lock.run`).

These are read-only/identity ops, so the practical risk is low — but the inconsistency is real.

For tests: `test_worker_pool.py`, `test_orchestrator.py`, and `test_merge_coordinator.py`
cover create/cleanup, active-worktree guards, orphan liveness, and ghost-ref prune as
**isolated unit tests**. None spin up N concurrent workers against a real scratch repo.

## Expected Behavior

- All git operations on the repo route through `GitLock` (or a documented exemption comment
  explains why a given call is deliberately lock-free).
- A concurrency regression test creates several worktrees/branches in parallel against a
  temporary git repo and asserts no leaked worktrees, no `index.lock` failures, correct
  branch/worktree teardown, and that an active worktree is never removed mid-run.

## Proposed Solution

1. Convert the `:78` and `:141` calls to `git_lock.run([...], cwd=...)`. Where a call is in a
   path that may run without a `GitLock` instance, either thread the lock through or add a
   short comment documenting the intentional exemption.
2. Add `scripts/tests/test_worktree_concurrency.py` (or a `@pytest.mark.integration` class in
   an existing file): initialize a tmp git repo, launch K threads each calling
   `setup_worktree` + `cleanup_worktree` (and/or drive a small `ProcessWorkerPool` run), and
   assert post-conditions (no orphaned `.worktrees/` dirs, no dangling `parallel/*` branches,
   no `index.lock` errors surfaced). Reference the scenarios from BUG-140/142/579.

## Implementation Steps

1. Convert `worktree_utils.py:78` (git-identity copy in `setup_worktree()`) from bare `subprocess.run` to `git_lock.run(["config", config_key, value], cwd=worktree_path)`.
2. Convert `worktree_utils.py:141` (`cleanup_worktree()` branch detection) to `git_lock.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, timeout=10)`. ENH-2325 is done and targeted `orchestrator.py._inspect_worktree` only — no lock-free mandate applies to this call (see updated Scope Boundary note).
3. Update `test_cli_loop_worktree.py` — move branch-name injection from `patch("subprocess.run")` to `patch.object(git_lock, "run", side_effect=...)` for the three hard-breaking tests (`test_deletes_branch_when_delete_branch_true` line 406, `test_parallel_branch_is_deleted` line 563, `test_main_branch_not_deleted` line 609).
4. Update `test_worker_pool.py` — move branch-name injection from `mock_subprocess.return_value` to `patch.object(worker_pool._git_lock, "run", side_effect=...)` for lines 723 and 751.
5. Add `scripts/tests/test_worktree_concurrency.py` using `ThreadPoolExecutor(max_workers=K)` against a real tmp git repo (copy `temp_git_repo` fixture from `test_merge_coordinator.py`); assert post-conditions: no orphaned `.worktrees/` dirs, no dangling `parallel/*` branches, no `index.lock` errors.
6. Run `python -m pytest scripts/tests/` to verify no regressions.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (git-identity copy bypasses lock) and `cleanup_worktree()` (branch-detection call bypasses lock).

### Files to Add
- `scripts/tests/test_worktree_concurrency.py` — new concurrency regression test.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — calls `setup_worktree` / `cleanup_worktree`
- `scripts/little_loops/parallel/orchestrator.py` — calls `setup_worktree` / `cleanup_worktree`
- `scripts/little_loops/cli/loop/run.py` — calls worktree lifecycle functions
- `scripts/little_loops/parallel/worker_pool.py` — in addition to calling `setup_worktree` / `cleanup_worktree`, has its **own bare `subprocess.run` at line 719** for branch detection in `_cleanup_worktree()` (same pattern as `worktree_utils.py:141`). Out-of-scope for this issue (it's in WorkerPool's private method, not the shared util), but closely related; worth addressing in the same PR or a follow-on. [Wiring pass finding]
- `scripts/little_loops/parallel/merge_coordinator.py` — has its own private `_cleanup_worktree()` method (line 1061; does not call `worktree_utils`) and **additionally contains ~10 bare `subprocess.run` git calls** (lines 850, 863, 877, 887, 898, 910, 922, 933, 940) that bypass `self._git_lock`. Scope: these bypass calls are **out-of-scope** for this issue (they are in a different subsystem) but are closely related; worth a follow-on or a scope discussion. [Wiring pass finding]

### Similar Patterns
- `scripts/little_loops/parallel/git_lock.py` — `GitLock.run()` with `index.lock` retry/backoff; the pattern the converted calls should follow.

### Tests
- `scripts/tests/test_worktree_concurrency.py` — new (to add); covers N-concurrent-worker scenarios.
- `scripts/tests/conftest.py` — existing tmp-project scaffolding fixtures; **has no real git repo fixture** (no `git init`); `temp_project_dir` and `temp_project` fixtures do not create a commit history.
- `scripts/tests/test_merge_coordinator.py` — `temp_git_repo` fixture (function scope) is the canonical real-git-repo scaffold to copy into the new test file.
- `scripts/tests/test_worker_pool.py` — existing isolation-unit tests; shows `threading.Event`/`time.sleep` concurrency patterns. **Update required**: All `TestWorkerPoolWorktreeManagement.*` tests use `patch("subprocess.run")` to catch the line-78 `git config` and line-141 `rev-parse` calls; after conversion these patches become no-ops. Hard-breaking tests: `test_cleanup_worktree_removes_worktree` (line 723) and `test_cleanup_worktree_deletes_parallel_branch` (line 751) inject branch names via `mock_subprocess.return_value` — after conversion the branch name will come from `patch.object(worker_pool._git_lock, "run", side_effect=...)` instead; those tests must be updated to set the branch return value via the git_lock mock.
- `scripts/tests/test_orchestrator.py`, `scripts/tests/test_merge_coordinator.py` — existing isolation-unit tests for BUG-140/142/579 scenarios; no direct `worktree_utils` subprocess mock coupling; no update needed.
- `scripts/tests/test_cli_loop_worktree.py` — shows `patch.object(git_lock, "run", ...)` + separate `patch("subprocess.run", ...)` stub pattern. **Update required**: All `TestSetupWorktree.*` tests (lines 50–264) patch `subprocess.run` to catch the line-78 `git config` call; these patches become no-ops after conversion. Hard-breaking tests: `TestCleanupWorktree.test_deletes_branch_when_delete_branch_true` (line 406), `TestWorkerPoolCleanupBranchGuard.test_parallel_branch_is_deleted` (line 563), and `test_main_branch_not_deleted` (line 609; formerly `test_non_parallel_branch_not_deleted`) inject branch names via `patch("subprocess.run")` for the line-141 `rev-parse` call; after conversion they must inject the branch name via `patch.object(git_lock, "run", side_effect=...)` for `args == ["rev-parse", "--abbrev-ref", "HEAD"]`.
- `scripts/tests/test_git_lock.py` — GitLock unit tests; reference for retry/backoff assertion patterns.
- `scripts/tests/test_subprocess_mocks.py` — uses a **global** `patch("subprocess.run", side_effect=mock_run)` (not a split `patch.object(git_lock, "run")` pattern). After conversion, the moved calls still route through `GitLock._run_with_retry → subprocess.run`, so the global patch intercepts them transitively with the same `["git", ...]` argv. **No update required.** [Wiring pass finding — corrected by Agent 2 analysis]

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**GitLock conversion recipe** — `git_lock.run()` prepends `"git"` internally (`_run_with_retry()` in `git_lock.py`); both stray calls have `git_lock` available as a parameter in their enclosing functions.

Line 78–82 in `setup_worktree()` — config write into worktree:
- Before: `subprocess.run(["git", "config", config_key, value_result.stdout.strip()], cwd=worktree_path, capture_output=True)`
- After: `git_lock.run(["config", config_key, value_result.stdout.strip()], cwd=worktree_path)`

Lines 141–147 in `cleanup_worktree()` — branch detection:
- Before: `branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, capture_output=True, text=True)` then `branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else None`
- After: `branch_result = git_lock.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path)` — the `.stdout`/`.returncode` extraction is unchanged.

Both converted calls retain `cwd=worktree_path` (correct — each worktree has its own index; GitLock's `threading.RLock` is cwd-independent).

**Real git repo fixture** — copy `temp_git_repo` from `scripts/tests/test_merge_coordinator.py`: `git init` → `git config user.email/user.name` → write a file + `git add . && git commit` → `yield repo_path`. Define it locally in `test_worktree_concurrency.py` (per-file fixture pattern, same as `temp_repo_with_config` variants in `test_worker_pool.py` and `test_orchestrator.py`).

**Concurrency test structure** — `concurrent.futures.ThreadPoolExecutor(max_workers=K)` (K=3–5) is the right primitive for N-worker fan-out without mid-run inspection; `threading.Event` is needed only when asserting mid-run state (see `test_worker_pool.py:TestWorkerPoolTaskSubmission.test_handle_completion_tracks_pending_callbacks`). Always call `executor.shutdown(wait=True)` (or join all threads) before asserting post-conditions. Post-condition assertions: no remaining `.worktrees/<name>` dirs, no dangling `parallel/*` branches, no leaked `index.lock` files.

### Codebase Research Findings — second pass (verification)

_Added by `/ll:refine-issue --auto` — re-verified against current source: the bare calls are still at lines 78–82 (`setup_worktree`) and 141–146 (`cleanup_worktree`) with no drift; `git_lock: GitLock` is an explicit param of both functions (`:27`, `:124`); `GitLock.run()` prepends `"git"` at `git_lock.py:130` (`cmd = ["git"] + args`); the `temp_git_repo` fixture exists at `test_merge_coordinator.py:20–54` (function scope) exactly as described, and `conftest.py` has no real-git fixture. Additional findings:_

**Caller-list correction (Integration Map → Dependent Files).** The direct callers of the *public* `setup_worktree` / `cleanup_worktree` are:
- `scripts/little_loops/parallel/worker_pool.py:641` (setup) / `:730` (cleanup) — via the `_setup_worktree` (`:629`) / `_cleanup_worktree` (`:701`) wrappers.
- `scripts/little_loops/cli/loop/run.py:388` (setup) / `:401` (cleanup).
- `scripts/little_loops/worktree_utils.py:51` — internal rollback path: `setup_worktree()` calls `cleanup_worktree(..., delete_branch=True)` on failure.

> ⚠ The `orchestrator.py — calls setup_worktree / cleanup_worktree` bullet above is inaccurate. `orchestrator.py:38` imports only `_is_ll_worktree`; its worktree teardown runs through `_cleanup_orphaned_worktrees()` (using `git_lock` directly), not the public lifecycle functions. `merge_coordinator.py` has its *own* private `_cleanup_worktree` method (`:1061`) — a same-name false positive, not a call into `worktree_utils`. Both remain relevant as concurrency context, but neither is a caller of the converted functions.

**Timeout on the converted calls.** The adjacent locked calls pass explicit timeouts (`:149` `worktree unlock` → `timeout=10`; `:150–154` `worktree remove` → `timeout=30`; `:160` `branch -D` → `timeout=10`). To match local convention, convert the `:141` branch-detection call as `git_lock.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, timeout=10)`. The `:78` config write can rely on `GitLock.run()`'s default `timeout=30`.

**Concrete in-repo models for the new concurrency test** (prior findings name `ThreadPoolExecutor` but cite no in-repo example):
- N-worker fan-out (canonical): `scripts/tests/test_git_lock.py::TestThreadSafety::test_concurrent_operations_serialize` (start-all/join-all over N threads, then assert on shared state) and `::test_no_deadlock_with_many_threads` (20 threads, `join(timeout=10)`).
- The one existing `ThreadPoolExecutor(max_workers=n)` + `as_completed` example: `scripts/tests/test_file_utils.py::TestAcquireLock::test_concurrent_writers_via_acquire_lock`.
- **Real-git + real `git worktree add` + filesystem post-conditions (closest model for the new test):** `scripts/tests/test_orchestrator.py::TestOrphanedWorktreeCleanup::test_prunes_ghost_worktree_refs` — creates real worktrees, simulates a crash via `shutil.rmtree`, then asserts `not wt_path.exists()` and that ghost refs are pruned. It inlines the same git-init scaffold as `temp_git_repo`.
- Branch-teardown assertion model: `test_orchestrator.py::TestOrphanedWorktreeCleanup::test_deletes_branch_via_rev_parse` (asserts on a captured `deleted_branches` list).
- "Active worktree never removed mid-run" assertion model: `scripts/tests/test_worker_pool.py::TestActiveWorktreeProtection::test_process_issue_registers_and_unregisters_worktree` (asserts the path is absent from `_active_worktrees` after processing).

**Gap confirmed.** No existing test asserts a multi-worker post-condition ("after N concurrent workers finish, `.worktrees/` is empty / no dangling `parallel/*` branches"). The issue's core motivation holds — the regression surface is genuinely uncovered.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/tests/test_cli_loop_worktree.py` — **hard-breaking** (split-patch pattern): `test_deletes_branch_when_delete_branch_true` (line 406), `test_parallel_branch_is_deleted` (line 563), and `test_main_branch_not_deleted` (line 609; formerly `test_non_parallel_branch_not_deleted`) use `patch.object(git_lock, "run")` + `patch("subprocess.run")` to inject a branch name for the line-141 `rev-parse` call. After conversion, the rev-parse is intercepted by `patch.object(git_lock, "run")` and never reaches `subprocess.run` — the branch-name return value must be moved into the `git_lock.run` mock, keyed on `args == ["rev-parse", "--abbrev-ref", "HEAD"]`. The `patch("subprocess.run")` in `TestSetupWorktree.*` tests becomes unused (benign, but remove for clarity).
2. Update `scripts/tests/test_worker_pool.py` — **hard-breaking** (split-patch pattern): `test_cleanup_worktree_removes_worktree` (line 723) and `test_cleanup_worktree_deletes_parallel_branch` (line 751) inject branch names via `mock_subprocess.return_value`; after conversion these must inject via `patch.object(worker_pool._git_lock, "run", side_effect=...)` for the rev-parse command.
3. After adding `test_worktree_concurrency.py`, `docs/test-quality-audit.md` has a note ("GitLock serialization assumption is never verified with multiple threads running simultaneously") that describes the gap ENH-2326 closes. No change needed as part of this issue, but the note becomes stale — optionally remove it post-merge.
   Note: `scripts/tests/test_subprocess_mocks.py` uses a global `patch("subprocess.run")` (no split `patch.object(git_lock, "run")`); GitLock._run_with_retry calls `subprocess.run` internally so the global patch fires transitively — **no update needed** there.

## Impact

- **Priority**: P4 — consistency + regression insurance; no current defect.
- **Effort**: Medium — the test is the bulk of the work.
- **Risk**: Low.
- **Breaking Change**: No.

_Note: acceptable to split into two issues (GitLock consistency vs. concurrency test) if the
implementer prefers; kept together here as one robustness pass._

## Session Log
- `/ll:ready-issue` - 2026-06-30T04:41:51 - `1bc6ee50-98a7-4976-8691-22aa548a66a9.jsonl`
- `/ll:format-issue` - 2026-06-30T04:33:07 - `493dc49c-a5c6-43bf-b114-97621d8d3dcc.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:56 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:verify-issues` - 2026-06-27T19:13:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T01:23:43 - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:02:41 - `9c00279d-038d-48ea-b8a2-3f7902367e8a.jsonl`
- `/ll:wire-issue` - 2026-06-26T23:01:32 - `64adeb74-858e-4aba-8e05-0d67aa559f7c.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:56:42 - `f58246a8-2511-4fd7-9cc4-ccb76673c11e.jsonl`
- `/ll:format-issue` - 2026-06-26T22:49:54 - `72d2e412-ebe3-4dd9-98d5-4e6aebd0e9c8.jsonl`
- `/ll:format-issue` - 2026-06-26T22:42:47 - `3ae3140c-819c-420a-ab85-bf3d642198e7.jsonl`
- audit (branch & worktree management) - 2026-06-26 - `thoughts/audits/2026-06-26-branch-worktree-management-audit.md`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`; **updated by `/ll:ready-issue`**: ENH-2325 is now `done`): ENH-2325's scope was `orchestrator.py._inspect_worktree` (branch-name derivation via string manipulation), not `worktree_utils.py:141`. It did not mandate that `cleanup_worktree()`'s `rev-parse` call stay lock-free; `worktree_utils.py:141` remains bare `subprocess.run` after ENH-2325 merged. The coordination concern is resolved — the `:141` conversion decision in this issue stands as written in Implementation Step 2 (convert to `git_lock.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, timeout=10)` per the timeout convention at `:149`). Related issue: ENH-2325 (done).

