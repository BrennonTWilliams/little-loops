---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, ENH-1176]
decision_needed: false
confidence_score: 85
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
size: Very Large
---

# ENH-1197: Harden Worktree Cleanup Against SIGKILL Mid-Teardown

## Summary

Parallel states in worktree mode create per-worker git worktrees and tear them down in a `try/finally` block (per ENH-1176). If the parent process is SIGKILLed *during* cleanup — e.g., between "worktree removed from disk" and "`git worktree prune` committed" — the repo ends up with a ghost worktree reference and a leaked directory. Add out-of-band recovery so stale worktrees from SIGKILL'd prior runs are detected and reclaimed on the next `ll-parallel` / `ll-loop` invocation.

## Current Behavior

`ENH-1176` adds a `try/finally` cleanup audit — but `finally` does not run on SIGKILL. Existing `ll:cleanup-worktrees` skill/command cleans *orphaned* worktrees from interrupted runs, but it's manually invoked. There is no automatic recovery on the next parallel-mode launch.

Failure modes observed / expected:

1. **Ghost ref**: worktree dir deleted before `git worktree prune` ran. `.git/worktrees/<name>/` survives. Next `git worktree add` of the same path fails with "already exists".
2. **Orphaned dir**: branch metadata cleaned up before the worktree directory was removed. Disk fills up over many kills.
3. **Lock file stranded**: `.git/worktrees/<name>/locked` stays, preventing future cleanup without manual `git worktree unlock`.

## Expected Behavior

1. **Startup scan**: on `ll-parallel` / parallel-state loop start, scan `.git/worktrees/` for entries matching the LL naming convention (`ll-parallel-<run-id>-worker-<i>`). For each:
   - If the matching run-id is not an active process (check by PID file or process lookup), classify as stale and reclaim.
   - Reclaim = `git worktree remove --force <path>` then `git worktree prune` then `rm -rf <dir>` if still present.
2. **Cleanup idempotency**: the in-band `finally` cleanup must tolerate being partially applied from a prior SIGKILL'd run. Specifically: `git worktree remove` on a path that's already half-gone should not raise.
3. **PID file per worker**: each worker writes a PID file inside its worktree at start; the startup scan uses this to distinguish "actively running worker from another ll-parallel invocation" from "dead worker from a SIGKILL'd run". Don't reclaim worktrees belonging to a live sibling process.
4. **Reclamation log**: when stale worktrees are reclaimed at startup, emit an INFO-level log line naming each reclaimed worktree and its age. Operators should be able to see "we cleaned up 4 leaked worktrees from a prior run killed 2h ago".

## Use Case

**Who**: Operator running `ll-parallel` in a constrained CI env where job runners can get OOM-killed or SIGKILL'd on resource exhaustion.

**Context**: Job runner OOMs mid-fan-out with 4 worktrees open. Worktrees and branch refs leak. Next CI job fails on `git worktree add` because the path already exists.

**Outcome**: Next invocation's startup scan reclaims the leaks cleanly; CI job succeeds.

## Proposed Solution

1. Add a `reclaim_stale_worktrees()` function that runs at `ll-parallel` / parallel-state start.
2. Define a naming convention for LL-managed worktrees: `.git/worktrees/ll-parallel-<run-id>-worker-<N>/`.
3. PID-file-based liveness: each worker writes `<worktree>/.ll-worker.pid`; scanner reads PID and checks `os.kill(pid, 0)`.
4. Wrap `git worktree remove` calls in tolerant error handling — "already gone" is not an error.
5. Ensure the existing `ll:cleanup-worktrees` skill uses the same reclamation path so behavior is consistent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**What already exists (do NOT re-implement):**
- `orchestrator.py:234-309` — `_cleanup_orphaned_worktrees()` already runs at startup: scans `.worktrees/worker-*` dirs, reads `.ll-session-<pid>` markers, calls `os.kill(pid, 0)` with `ProcessLookupError`/`PermissionError` handling, then runs `git worktree remove --force` + `shutil.rmtree(ignore_errors=True)` + `git worktree prune`. Covers the orphaned-dir case.
- `worktree_utils.py:96-99` — `.ll-session-<pid>` session marker already written per worker by `setup_worktree()`; the orchestrator already reads it at `orchestrator.py:249-265`.
- `worktree_utils.cleanup_worktree()` at `worktree_utils.py:102-142` — already idempotent: returns early if path is gone, uses `shutil.rmtree(ignore_errors=True)` as fallback after `git worktree remove --force`.
- Actual naming convention in use: `worker-<issue-id-lower>-<YYYYMMDD-HHMMSS>` (from `worker_pool.py:239-249`), not `ll-parallel-<run-id>-worker-<N>`.

**What is NOT yet implemented (actual work for this issue):**
1. **Ghost ref scan** — `_cleanup_orphaned_worktrees()` only scans `.worktrees/worker-*` directories. If a directory was deleted but `.git/worktrees/<name>/` metadata remains (the ghost ref scenario), it is invisible to the startup scan. Need to also scan `.git/worktrees/` for entries whose worktree path no longer exists and run `git worktree prune` to clear them.
2. **Stranded lock file** — Current code calls `git worktree remove --force` but does not call `git worktree unlock` first. Older git versions may not honor `--force` on locked worktrees; adding `git worktree unlock <path>` before remove is defensive hardening.
3. **`ll-loop --worktree` coverage** — Loop worktrees use naming pattern `<timestamp>-<safe-name>` (no `worker-` prefix, see `run.py:211-214`). Neither the orchestrator scan (`startswith("worker-")` at `orchestrator.py:248`) nor the `cleanup-worktrees` command (`-name "worker-*"`) catches them.
4. **`cleanup-worktrees` liveness gap** — `commands/cleanup-worktrees.md` is a shell-only command with no PID/liveness check (lines 54-73). It blindly removes all `worker-*` dirs, risking nuking live worker worktrees from a sibling `ll-parallel` run.

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — call reclaim-stale at runner init
- `scripts/little_loops/git/worktrees.py` (or wherever worktree mgmt lives) — `reclaim_stale_worktrees()`, PID-file write, tolerant remove
- `skills/cleanup-loops/` or `ll:cleanup-worktrees` (locate exact path) — factor shared reclaim function
- `scripts/tests/test_worktree_reclaim.py` — simulate ghost refs, orphaned dirs, stranded locks

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected file paths from codebase analysis:_

- `scripts/little_loops/parallel/orchestrator.py` — extend `_cleanup_orphaned_worktrees()` at line 234; add `.git/worktrees/` ghost ref scan after the existing `.worktrees/worker-*` scan
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` at line 20, `cleanup_worktree()` at line 102; add `git worktree unlock` call before `remove --force` at line 131
- `commands/cleanup-worktrees.md` — shell-only command (lines 54-73 detection, 109-144 cleanup); add `.ll-session-*` PID probe before removing each directory
- `scripts/little_loops/cli/loop/run.py` — worktree setup at line 199, atexit cleanup at line 240; assess whether loop worktrees need separate scan coverage
- ~~`scripts/little_loops/fsm/parallel_runner.py`~~ — does not exist; parallel logic lives in `orchestrator.py` + `worker_pool.py`
- ~~`scripts/little_loops/git/worktrees.py`~~ — does not exist; worktree management is in `scripts/little_loops/worktree_utils.py`
- ~~`skills/cleanup-loops/`~~ — `cleanup-worktrees` is `commands/cleanup-worktrees.md` (shell command, no Python module)
- New test file: `scripts/tests/test_worktree_reclaim.py` — extend patterns from `scripts/tests/test_orchestrator.py:389-474`; use real-git `temp_git_repo` fixture from `scripts/tests/test_merge_coordinator.py:20-54`

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_cleanup_orphaned_worktrees()` at line 234 (extend to also scan `.git/worktrees/` for ghost refs where directory is gone but git metadata remains)
- `scripts/little_loops/worktree_utils.py` — `cleanup_worktree()` at line 102 (add `git worktree unlock` before `remove --force` at line 131 as stranded-lock hardening)
- `commands/cleanup-worktrees.md` — add `.ll-session-<pid>` PID liveness check (lines 109-144) mirroring `orchestrator.py:249-265` to prevent nuking live worker trees

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/merge_coordinator.py:1205` — has its own `git worktree remove --force` that does NOT delegate to `worktree_utils.cleanup_worktree()`; the `git worktree unlock` fix must be applied here separately, or this method refactored to delegate [Agent 2]
- `scripts/little_loops/parallel/orchestrator.py:385` — `_check_pending_worktrees()` also uses `startswith("worker-")` filter; update if loop worktree scan coverage is extended [Agent 1/2]
- `scripts/little_loops/parallel/worker_pool.py:1316` — `cleanup_all_worktrees()` uses `startswith("worker-")` filter; same loop-worktree gap as `_check_pending_worktrees` [Agent 1/2]
- `scripts/little_loops/loops/worktree-health.yaml:14` — grep pattern `ll-worktree` matches no actual worktree name (neither `worker-*` nor `<timestamp>-<safe-name>`); built-in loop always reports 0 orphaned worktrees [Agent 2]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py:601-636` — `_cleanup_worktree()` delegates to `worktree_utils.cleanup_worktree()`; `cleanup_all_worktrees()` at line 1309 calls `_cleanup_worktree()`
- `scripts/little_loops/parallel/merge_coordinator.py:1194-1221` — `_cleanup_worktree()` also delegates to `worktree_utils.cleanup_worktree()`
- `scripts/little_loops/cli/loop/run.py:219-226` — calls `worktree_utils.setup_worktree()`; atexit cleanup at line 240 calls `worktree_utils.cleanup_worktree()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py:404-411` — creates `ParallelOrchestrator`; startup scan (`_cleanup_orphaned_worktrees`) runs on every `ll-sprint` multi-issue wave, making ghost-ref scan an indirect change for sprint users [Agent 1]

### Similar Patterns to Follow
- `orchestrator.py:249-265` — PID liveness pattern (`os.kill(pid, 0)`, `ProcessLookupError`, `PermissionError`) — reuse exactly this in the ghost ref scan extension
- `worktree_utils.py:102-142` — idempotent cleanup pattern (early return if path gone, `shutil.rmtree(ignore_errors=True)` fallback)
- `fsm/concurrency.py:26-38` — `_process_alive()` using `os.kill(pid, 0)` — factored form of same liveness check; consider extracting to shared utility

### Tests
- `scripts/tests/test_orchestrator.py:389-474` — existing PID liveness tests (`test_skips_worktree_owned_by_live_process`, `test_removes_worktree_with_dead_process_marker`) to extend for ghost ref + lock scenarios
- `scripts/tests/test_cli_loop_worktree.py` — unit tests for `setup_worktree`/`cleanup_worktree` with marker assertions
- New: `scripts/tests/test_worktree_reclaim.py` — simulate: (a) ghost ref (`.git/worktrees/<name>/` present, directory gone), (b) stranded lock file, (c) live-sibling skip via mocked `os.kill`, (d) orphaned directory; use real-git `temp_git_repo` fixture from `test_merge_coordinator.py:20-54`

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests to update — will break when `git worktree unlock` is inserted before `remove --force`:**
- `scripts/tests/test_cli_loop_worktree.py:281-306` — patches `git_lock.run`; `unlock` call adds a new capture entry before `remove`; review call-order assertions [Agent 3]
- `scripts/tests/test_cli_loop_worktree.py:409-450` — `WorkerPool._cleanup_worktree()` backward-compat tests; patched `git_lock.run` receives additional `unlock` call; check call-count assertions [Agent 3]
- `scripts/tests/test_worker_pool.py:722-778` — `TestSetupAndCleanupWorktree` captures all `git_lock` commands; `unlock` call also contains `"worktree"` — check list-length and filter assumptions [Agent 3]
- `scripts/tests/test_orchestrator.py:350-444` — `TestCleanupOrphanedWorktrees` mocks `_git_lock.run`; mock call count increases with each unlock call; check any `len()` or `call_count` assertions [Agent 3]
- `scripts/tests/test_orchestrator.py:414-444` — patches `os.kill` directly with `ProcessLookupError`; if implementation delegates to `_process_alive` from `fsm/concurrency.py`, patch path must change to `little_loops.parallel.orchestrator._process_alive` [Agent 3]

**Existing test files covering affected code (not yet listed):**
- `scripts/tests/test_worker_pool.py:722-815` — `TestWorkerPoolWorktreeManagement`; direct tests of `_cleanup_worktree` with git_lock mock [Agent 1/3]
- `scripts/tests/test_subprocess_mocks.py:496-603` — `TestWorkerPoolSetupWorktree`; tests command sequences via subprocess capture [Agent 1/3]
- `scripts/tests/test_concurrency.py` — indirect coverage of `_process_alive` via `LockManager`; review if orchestrator is refactored to use `_process_alive` [Agent 1/3]

**New test gap identified:**
- `scripts/little_loops/cli/loop/run.py:201-243` — entire `args.worktree=True` path through `cmd_run` is untested; no test calls `cmd_run` with `worktree=True`; add to `test_cli_loop_worktree.py` [Agent 3]

### Documentation
- `docs/development/TROUBLESHOOTING.md` — may need a section on ghost ref recovery if `git worktree add` fails with "already exists"

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:409-414` — documents `/ll:cleanup-worktrees`; line 410-411 description omits liveness check behavior; update if PID probe is notable enough to document [Agent 2]
- `docs/reference/CLI.md:317` — documents `--worktree` branch naming as `TIMESTAMP-LOOP-NAME`; update if loop worktrees are explicitly added to the orphan scan [Agent 2]
- `docs/ARCHITECTURE.md:820-826` — worktree layout diagram shows only `worker-N` naming; `ll-loop --worktree` format (`<timestamp>-<loop-name>`) is absent from the diagram [Agent 2]

## Dependencies

- **Hard blockers**: FEAT-1075 (runner), ENH-1176 (in-band cleanup audit)
- **Soft**: ENH-1073 (worktree-mode fan-out)

## Acceptance Criteria

- Startup scan detects and reclaims: (a) ghost `.git/worktrees/<name>/` ref, (b) orphaned worktree dir, (c) stranded lock file
- Live-sibling protection: reclaim skips worktrees whose PID file points to a live process
- In-band `finally` cleanup is idempotent against half-applied prior cleanup
- INFO log enumerates each reclaimed worktree at startup
- Test suite simulates all three failure modes + live-sibling case; real git repo fixture
- No regression in `ll:cleanup-worktrees` manual invocation

## Implementation Steps

1. **Audit existing `_cleanup_orphaned_worktrees()`** (`orchestrator.py:234-309`) — confirm it covers the orphaned-dir case end-to-end before adding anything new
2. **Extend ghost ref scan** — after the `.worktrees/worker-*` scan, also iterate `.git/worktrees/` for entries whose worktree path no longer exists on disk; run `git worktree prune` via `GitLock.run(["worktree", "prune"], cwd=repo_path)` following pattern at `orchestrator.py:304-309`
3. **Add stranded lock handling** — in `worktree_utils.cleanup_worktree()` (line 131), add `git worktree unlock <path>` via `GitLock.run()` before `git worktree remove --force`; suppress errors if not locked
4. **Add liveness check to `cleanup-worktrees` command** — in `commands/cleanup-worktrees.md` (lines 109-144), add `.ll-session-*` glob + `kill -0 <pid>` probe for each `worker-*` directory before removing; skip if process alive
5. **Assess loop worktree gap** — decide whether `ll-loop --worktree` worktrees (naming: `<timestamp>-<safe-name>` at `run.py:211-214`) should be added to orphan scans; if yes, unify naming or add a second scan pattern
6. **Write tests** in `scripts/tests/test_worktree_reclaim.py` — use `temp_git_repo` fixture from `test_merge_coordinator.py:20-54`; extend existing tests in `test_orchestrator.py:389-474`; cover all three failure modes + live-sibling protection
7. **Verify no regression** — `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_cli_loop_worktree.py scripts/tests/test_worker_pool.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/parallel/merge_coordinator.py:1205` — add `git worktree unlock <path>` before `git worktree remove --force`, or refactor to delegate to `worktree_utils.cleanup_worktree()` so the unlock fix isn't applied in two places
9. Update `scripts/little_loops/parallel/orchestrator.py:385` (`_check_pending_worktrees()`) and `worker_pool.py:1316` (`cleanup_all_worktrees()`) — if loop worktrees are added to orphan scan, extend `startswith("worker-")` filter in both methods; consider a shared name-predicate utility
10. Fix `scripts/little_loops/loops/worktree-health.yaml:14` — grep pattern `ll-worktree` never matches actual worktrees; update to match real naming (`worker-*` for parallel, `<timestamp>-` for loop) or use `git worktree list --porcelain` without a broken grep
11. Update breaking tests before step 7 regression run — `test_cli_loop_worktree.py:281-450`, `test_worker_pool.py:722-778`, `test_orchestrator.py:350-444`, `test_orchestrator.py:414-444` (see Tests section for details on each)
12. Add `cmd_run` with `worktree=True` integration test in `scripts/tests/test_cli_loop_worktree.py` — covers the `run.py:201-243` path currently uncovered by any test

## Impact

- **Priority**: P3 — Real operational hazard for users running `ll-parallel` in any env that can OOM-kill or SIGKILL the parent. Not strictly required for v1 parallel ship (workaround is manual `ll:cleanup-worktrees`), but v1 adoption in CI will surface this quickly.
- **Effort**: Medium — real-git test fixtures, multiple failure modes
- **Risk**: Medium — `git worktree remove --force` is destructive; the live-sibling check is the main safety gate. Getting it wrong could nuke an actively-running worker's worktree.
- **Breaking Change**: No — additive recovery path

## Labels

`fsm`, `parallel`, `worktree`, `reliability`, `cleanup`

## Related / See Also

- **ENH-1176** — in-band cleanup audit (this issue handles out-of-band recovery)
- **ll:cleanup-worktrees** — manual skill; should share the reclaim function
- **ENH-1073** — worktree-mode fan-out

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-22_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 56/100 → LOW

### Concerns
- Stale dependency declarations: FEAT-1075 and ENH-1176 are both deferred; ENH-1176 is actually "resource limits" not the "in-band cleanup audit" the issue describes — verify and reclassify before starting
- Open design decision in step 5: loop worktree scan scope (`<timestamp>-<safe-name>` naming) must be decided before steps 9-10; highest scope-expansion risk
- merge_coordinator.py step 8 has an unresolved or-choice (in-place unlock vs. refactor to delegate to worktree_utils)

### Outcome Risk Factors
- Test breakage cascade: `git worktree unlock` insertion changes call-order in four existing test files — update breaking tests before the step-7 regression run
- `run.py:201-243` loop worktree path has zero test coverage; write the stub test early
- worktree-health.yaml grep fix changes the loop's count from always-0 to non-zero, which may trigger unexpected cleanup runs in CI envs running the loop

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-22T15:30:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf1f3140-90a5-4ebf-a752-46183ce079dc.jsonl`
- `/ll:wire-issue` - 2026-04-22T15:22:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/940f0219-3108-4f89-84ef-2983c9cc5d04.jsonl`
- `/ll:refine-issue` - 2026-04-22T15:13:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3c3e12d-0001-4c04-8f00-c22acb75421d.jsonl`
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as follow-up from parallel-family review. SIGKILL-during-cleanup is the one failure mode `try/finally` cannot cover; needs out-of-band recovery.
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-22
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1246: Ghost Ref Scan Extension in Startup Cleanup
- ENH-1247: Stranded Lock File Hardening + Breaking Test Updates
- ENH-1248: ll-loop Worktree Orphan Scan Coverage + worktree-health.yaml Fix
- ENH-1249: Add PID Liveness Check to cleanup-worktrees Command

---

**Decomposed** | Created: 2026-04-20 | Priority: P3
