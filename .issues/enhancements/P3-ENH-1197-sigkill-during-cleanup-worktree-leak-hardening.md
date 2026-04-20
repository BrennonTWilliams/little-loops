---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1075, ENH-1176]
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

## Files to Modify

- `scripts/little_loops/fsm/parallel_runner.py` — call reclaim-stale at runner init
- `scripts/little_loops/git/worktrees.py` (or wherever worktree mgmt lives) — `reclaim_stale_worktrees()`, PID-file write, tolerant remove
- `skills/cleanup-loops/` or `ll:cleanup-worktrees` (locate exact path) — factor shared reclaim function
- `scripts/tests/test_worktree_reclaim.py` — simulate ghost refs, orphaned dirs, stranded locks

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

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as follow-up from parallel-family review. SIGKILL-during-cleanup is the one failure mode `try/finally` cannot cover; needs out-of-band recovery.

---

**Open** | Created: 2026-04-20 | Priority: P3
