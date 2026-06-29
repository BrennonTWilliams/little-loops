---
id: BUG-2386
priority: P2
type: BUG
status: open
captured_at: "2026-06-29T01:04:25Z"
discovered_date: 2026-06-28
discovered_by: investigation
relates_to: [BUG-823]
---

# BUG-2386: `ll-loop run --worktree` splits run-tracking across two dirs (invisible/unstoppable) and silently discards the worktree's work

## Summary

`ll-loop run <loop> --worktree` (foreground) writes the run's tracking files to
**two different directories** because `loops_dir` is the relative path `.loops`
and the code `os.chdir()`s into the worktree partway through startup. The
`.pid` and scope `.lock` are written *before* the chdir (→ main repo), while
`.state.json`, `.log`, and `run_dir` are created *after* the chdir (→ inside
the worktree). Consequences observed on a live run
(`rn-implement-20260628T192650`, PID 50194, FEAT-2301):

1. **Invisible:** `ll-loop list --running` from the main repo did not show the
   run — discovery keys on `*.state.json`, which lived in the worktree.
2. **Unstoppable:** `ll-loop stop rn-implement` returned "No state found" /
   no-op — `_find_instances` also keys on `*.state.json`, so it never
   discovered the instance, and the orphaned-lock fallback only iterates
   *discovered* instances.
3. **Work discarded:** on exit the `--worktree` path runs
   `cleanup_worktree(delete_branch=True)` with **no merge/commit/push step**,
   `git worktree remove --force` + `rmtree`-ing the worktree (taking its
   `.state.json`/`.log`/`run_dir` with it) and deleting branch
   `20260628-192650-rn-implement`. Any work the loop produced for FEAT-2301 was
   lost — confirmed no recoverable commits (no dangling 06-28 19:xx commits, no
   reflog entry, no `.git/worktrees` metadata).
4. **Orphaned lock/pid:** cleanup of `.pid` (`atexit`) and `.lock` (`finally`)
   also runs *after* the chdir/`rmtree`, so the relative paths resolve against
   the wrong (now-deleted) cwd and no-op, leaving stale
   `rn-implement-20260628T192650.{lock,pid}` in the main repo's
   `.loops/.running/` (manually removed during diagnosis).

## Impact

**Severity: high (silent data loss + loss of operator control).** Any
`ll-loop run --worktree` (the recommended isolation mode, used by the
autonomous `rn-*` loops) that produces uncommitted work loses it on exit with
no warning, and cannot be monitored or stopped from the main repo while it
runs. The operator's only recourse mid-run is `kill <pid>` by hand or running
`ll-loop` from inside the (ephemeral) worktree. Every such run also leaks a
stale `.lock`/`.pid` into `.loops/.running/`, which then pollutes
`ll-loop list --running` and can block future scope acquisition. Confirmed lost
on `rn-implement-20260628T192650` (FEAT-2301).

## Current Behavior

In `scripts/little_loops/cli/loop/run.py` (`cmd_run`), with `loops_dir =
Path(".loops")` (relative; from `config.loops.loops_dir`, confirmed
`is_absolute() == False`):

| File | Written at | Resolves to |
|------|-----------|-------------|
| `.pid` | `run.py:295-300` — **before** chdir | main repo `.loops/.running/` |
| scope `.lock` | `run.py:308-317` (`LockManager(loops_dir)`) — **before** chdir | main repo `.loops/.running/` |
| `os.chdir(_worktree_path)` | `run.py:417` | — |
| `run_dir` | `run.py:424` — **after** chdir | **worktree** `.loops/runs/` |
| `.state.json` | `PersistentExecutor(loops_dir=loops_dir, …)` `run.py:425-432` — **after** chdir | **worktree** `.loops/.running/` |
| `.log` | `run_foreground(running_dir=running_dir, …)` `run.py:451` — **after** chdir | **worktree** `.loops/.running/` |

Discovery/stop both run from the main repo and only see `*.state.json` there:

- `list_running_loops` (`scripts/little_loops/fsm/persistence.py:913`) globs
  `*.state.json` (line 929). Its PID-file fallback (line 947) *would* catch a
  live process with no state file, but it is suppressed at line 949 when a
  same-named loop is already in `known_names` — stale `rn-implement-*.state.json`
  from past runs put `"rn-implement"` in that set, so the live run is skipped.
- `_find_instances` (`persistence.py:873`) globs `{loop_name}-*.state.json`
  only. `cmd_stop` (`scripts/little_loops/cli/loop/lifecycle.py:316`) never
  discovers `rn-implement-20260628T192650`, so neither the running-instance
  kill path nor the orphaned-lock fallback (`lifecycle.py:336`, which iterates
  only discovered `instances`) ever touches live PID 50194.

Broken cleanup (same relative-path-after-chdir cause):
- `_cleanup_pid` (`run.py:302-303`, `atexit`) unlinks `.loops/.running/<stem>.pid`
  relative to cwd — after the worktree was `rmtree`d the cwd is gone, so it
  no-ops; the main-repo pid file survives.
- `lock_manager.release(...)` (`run.py:454-458`, `finally`) unlinks via
  `LockManager.running_dir` (relative `.loops/.running`, `concurrency.py:128`,
  `:184`) against the worktree cwd → no-op; the main-repo lock survives.
- `atexit` runs LIFO: `_cleanup_worktree_on_exit` (`run.py:405-414`) fires
  first and `rmtree`s the worktree (`worktree_utils.py:157`), so the worktree's
  own state/log/run_dir are destroyed with no merge-back.

## Expected Behavior

1. A `--worktree` run is **visible** to `ll-loop list --running` and
   **stoppable** via `ll-loop stop <loop>` from the main repo, same as a
   non-worktree run.
2. The run's `.pid`, `.lock`, `.state.json`, `.log`, and `run_dir` live in a
   single, consistent registry (the main repo's `.loops/.running` and
   `.loops/runs`), so discovery/stop/cleanup all agree.
3. Cleanup removes its own `.pid`/`.lock` reliably regardless of cwd changes —
   no orphans left in `.loops/.running/`.
4. Work produced inside the worktree is **not silently discarded**: either the
   branch is merged/retained, or the run refuses to delete an unmerged branch
   and warns loudly (with the branch name to recover from).

## Root Cause

**Anchor:** `scripts/little_loops/cli/loop/run.py` → `cmd_run` → the
`if getattr(args, "worktree", False):` block performing `os.chdir(_worktree_path)`
at `run.py:417`, combined with a **relative** `loops_dir` (`.loops`).

Three coupled defects:

- **Split registry (primary):** `loops_dir` is relative, and tracking files are
  written on both sides of the chdir. Files created before line 417 land in the
  main repo; files created after land in the worktree. Discovery
  (`list_running_loops`, `_find_instances`) and the user's `stop`/`list`
  invocations run from the main repo and only ever see the main-repo half.
- **Cwd-relative cleanup:** `_cleanup_pid` and `lock_manager.release()` resolve
  relative `.loops/.running/...` paths against the post-chdir / post-`rmtree`
  cwd, so they no-op and orphan the main-repo `.pid`/`.lock`.
- **No merge-back:** the `--worktree` path has no merge/commit/push step (grep
  of `run.py` for `merge|commit|push|MergeCoordinator` is empty) yet calls
  `cleanup_worktree(..., delete_branch=True)` on exit — silent loss of any
  uncommitted or unmerged work. (Contrast: `ll-parallel` routes worktree
  results through `parallel/merge_coordinator.py`.)

Secondary amplifier: the PID-file fallback in `list_running_loops`
(`persistence.py:947-950`) is defeated by stale same-name `*.state.json` files,
so even the one path that could have surfaced a stateless live run was inert.

## Implementation Steps

1. **Absolute `loops_dir` before any chdir** — resolve `loops_dir =
   Path(config.loops.loops_dir).resolve()` (pinned to the *main* repo) at the
   top of `cmd_run`, before the worktree block. This is the minimal fix: it
   makes `.pid`/`.lock`/`.state.json`/`.log` all land in the main repo's
   `.loops/.running` regardless of cwd, restoring visibility, stoppability, and
   reliable cleanup in one change. Keep `run_dir` in the main repo too (decide
   deliberately — see step 2).
2. **Decide worktree artifact location intentionally** — `run_dir` and the FSM
   working tree are conceptually different. The loop's *file edits* should
   happen in the worktree (cwd), but its *tracking/diagnostic artifacts*
   (`run_dir`, `.state.json`, `.log`) should live in the main repo so they
   survive `cleanup_worktree` and are discoverable. Verify
   `${context.run_dir}` consumers still resolve correctly once it's absolute.
3. **Merge-back or fail-loud on branch delete** — in `_cleanup_worktree_on_exit`
   (`run.py:405-414`), do not `delete_branch=True` unconditionally. Either
   merge the worktree branch back to the origin branch on success, or detect an
   unmerged/dirty worktree and retain the branch + print recovery instructions
   instead of deleting. Mirror `ll-parallel`'s merge handling where practical.
4. **Harden the stateless-live-run fallback** — in `list_running_loops`
   (`persistence.py:947`), don't suppress a live-PID pid-file entry just because
   the *logical name* exists in `known_names`; match on instance stem, or always
   surface a live PID whose specific `<stem>.state.json` is absent.
5. **Regression test** — `ll-loop run … --worktree` (mocked worktree) asserts
   the `.pid`/`.lock`/`.state.json` all resolve under the main repo's
   `.loops/.running`, that `list_running`/`_find_instances` discover the
   instance, and that exit leaves no orphaned `.pid`/`.lock`.

## Affected Files

- `scripts/little_loops/cli/loop/run.py` (`cmd_run` worktree block, pid/lock
  setup, cleanup registrations)
- `scripts/little_loops/fsm/persistence.py` (`list_running_loops`,
  `_find_instances`)
- `scripts/little_loops/fsm/concurrency.py` (`LockManager` running_dir
  resolution)
- `scripts/little_loops/cli/loop/lifecycle.py` (`cmd_stop` discovery / lock
  fallback)
- `scripts/little_loops/worktree_utils.py` (`cleanup_worktree` delete_branch
  policy)
- `scripts/tests/` (new regression coverage)

## Steps to Reproduce

```bash
ll-loop run rn-implement <ISSUE-ID> --worktree     # foreground
# while it runs, from the main repo:
ll-loop list --running          # → does not show the run
ll-loop stop rn-implement       # → "No state found" / no-op
# on exit: branch deleted, no merge; orphaned .lock/.pid left in .loops/.running/
```

Observed run: `rn-implement-20260628T192650`, PID 50194, branch
`20260628-192650-rn-implement`, run_dir reported as
`.loops/runs/rn-implement-20260628T192650/` (created in worktree, gone after
cleanup). Main repo was left with orphaned
`rn-implement-20260628T192650.{lock,pid}` (lock held live `pid: 50194`).

## Related

- `BUG-823` — `cleanup-orphaned-worktrees` fragile branch derivation; same
  worktree-lifecycle area.
- Contrast `scripts/little_loops/parallel/merge_coordinator.py` — the
  merge-back mechanism `ll-parallel` has and the `--worktree` run path lacks.

## Labels

- worktree
- ll-loop
- data-loss
- lifecycle

## Session Log
- investigation - 2026-06-29T01:04:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:audit-issue-conflicts` - 2026-06-28

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue modifies `worktree_utils.py:cleanup_worktree` (adding a merge-back or fail-loud policy for `delete_branch=True`). Two related open issues are actively coordinating over the same function's `:141` branch-detection call — ENH-2325 mandates that call uses bare `subprocess.run` (not GitLock, because the lock machinery must not block on a partially torn-down worktree), while ENH-2326 plans to route it through `git_lock.run()`. Before touching `cleanup_worktree`, confirm whether the `:141` path falls within your change surface and coordinate with ENH-2325/ENH-2326 implementers accordingly. Related issues: ENH-2325, ENH-2326.

---

## Status

- **Created**: 2026-06-28
- **Status**: open
