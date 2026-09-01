---
id: ENH-3376
type: ENH
title: registry-based worktree liveness survives in-tree marker deletion
priority: P2
status: open
parent: ENH-3374
relates_to:
- BUG-3373
- BUG-3375
---

# ENH-3376: registry-based worktree liveness survives in-tree marker deletion

## Summary

Add an out-of-tree liveness registry (`<worktree_base>/.registry/<worktree-name>`,
pid + run id) written at `setup_worktree` and removed at `cleanup_worktree`, so a
`git clean -fdx` run from inside a worktree can no longer erase its liveness
record. `_cleanup_orphaned_worktrees()` consults the registry first, then falls
back to the existing in-tree `.ll-session-<pid>` marker. This is the direct fix
for the BUG-3373 failure mode: a live worktree whose in-tree marker was deleted
is still recognized as live via the registry.

## Parent Issue

Decomposed from ENH-3374: make worktree liveness marker resilient so active
worktrees cannot be classified orphaned. Covers Proposed Solution steps 1-2 and
the first two Phase-4 test bullets (registry write/remove; cleanup skips a
registry-live worktree whose in-tree marker was deleted), plus the
`MergeCoordinator` wiring item and the `ParallelOrchestrator.run()`
auto-invocation test-coverage item from the parent's Wiring Phase. The
process-cwd fallback (parent's step 3, flagged unproven) and the
`session-cleanup.sh` hardening (parent's Wiring Phase) are split into sibling
issues (ENH-3377, ENH-3378) since they are
independently shippable concerns.

## Current Behavior

- `setup_worktree` (`scripts/little_loops/worktree_utils.py:278-281`) writes
  only the in-tree `.ll-session-<pid>` marker at creation.
- `_cleanup_orphaned_worktrees()` (`scripts/little_loops/parallel/orchestrator.py:317-345`)
  globs `.ll-session-*` inside each worktree; if no marker is found, the
  worktree is deleted regardless of whether it is actually live.
- `MergeCoordinator._cleanup_worktree()` (`scripts/little_loops/parallel/merge_coordinator.py:1148-1192`)
  independently reimplements worktree removal via direct git calls; it does
  not call `worktree_utils.cleanup_worktree()`.

## Expected Behavior

- `setup_worktree` writes a registry entry `{pid, run_id}` under
  `<worktree_base>/.registry/<worktree-name>` (sibling of, not inside, the
  worktree checkout dirs, so `git clean` cannot reach it), in addition to the
  existing in-tree marker.
- `cleanup_worktree` removes the registry entry.
- `MergeCoordinator._cleanup_worktree()` also removes the registry entry (or
  is redirected to call `worktree_utils.cleanup_worktree()`), since it bypasses
  that function today.
- `_cleanup_orphaned_worktrees()` consults the registry first: an entry with a
  live pid means the worktree is live regardless of in-tree marker state. Only
  when there is no live registry entry does it fall back to the existing
  in-tree marker check. Worktrees with neither a live registry entry nor a
  live marker keep today's behavior (treated as orphaned) — the fallback
  process-cwd check for that path is out of scope here (see ENH-3377).
- Registry entries do not accumulate: when `_cleanup_orphaned_worktrees()`
  deletes an orphaned worktree it also removes that worktree's registry
  entry, and it prunes any registry entry whose worktree directory no longer
  exists. (The orphan path inlines removal at `orchestrator.py:356-398` and
  never calls `cleanup_worktree()`, so without this the registry grows
  unbounded — worker names embed timestamps and are never reused — and every
  stale entry is a pid-reuse hazard: once the OS recycles that pid, a genuine
  orphan is skipped forever as "live".)

## Motivation

This closes the exact BUG-3373 mechanism (marker deleted mid-run by a
dispatched session or stray cleanup, then the worktree is reaped out from
under its owning process) without depending on any unproven mechanism: it
directly extends the already-proven atomic-write JSON pattern used by
`ParallelOrchestrator._load_state`/`_save_state`
(`scripts/little_loops/parallel/orchestrator.py:720-782`).

## Proposed Solution

1. `setup_worktree` (`worktree_utils.py:160`, marker write ~line 280): add a
   registry write to `<worktree_base>/.registry/` for the worktree, using the
   same `tempfile.mkstemp` + `os.replace` atomic-write pattern as
   `_save_state`. Keep the in-tree marker write unchanged (backward
   compatibility). Derive the registry dir as `worktree_path.parent /
   ".registry"` (the function receives `worktree_path`, not `worktree_base`).

   **Format decision — choose with ENH-3378's bash consumer in mind, before
   landing:** `session-cleanup.sh` has no guaranteed JSON parser, and its
   existing "jq-optional" pattern (line 24-26) only substitutes a default
   config value — it cannot extract a pid from JSON. Prefer a format bash can
   read in one line, e.g. encode the pid in the filename
   (`<worktree-name>.<pid>.json`, mirroring the `.ll-session-<pid>` marker
   convention) or write plain text (`pid\nrun_id\n`) instead of JSON. If JSON
   is kept, ENH-3378 must specify a grep/sed extraction fallback.
2. `cleanup_worktree` (`worktree_utils.py:284`): add an explicit registry-entry
   removal call (best-effort; a `git clean` inside the worktree never reaches
   this function, so the registry is the durable record).
3. `MergeCoordinator._cleanup_worktree()`
   (`merge_coordinator.py:1148-1192`): add the same registry-removal call, or
   redirect this method to call `worktree_utils.cleanup_worktree()` — pick
   whichever keeps the removal logic in one place.
4. `_cleanup_orphaned_worktrees()` (`orchestrator.py:317`): consult the
   registry before the existing `.ll-session-*` glob (line 337); treat "registry
   entry with live pid" (reusing the existing `os.kill(pid, 0)` liveness probe)
   as live regardless of in-tree marker state.
5. Registry hygiene in the same method: when the orphan-deletion loop
   (`orchestrator.py:356-398`) removes a worktree, also remove its registry
   entry (this path inlines removal and never calls `cleanup_worktree()`);
   additionally prune any registry entry whose worktree directory no longer
   exists. Both are required to bound pid-reuse exposure (see Expected
   Behavior).
6. Determine where `run_id` comes from for non-orchestrator callers
   (`setup_prepatch_worktree`, `ensure_epic_branch` in `worktree_utils.py`) —
   `ParallelOrchestrator.run_id` exists today (`orchestrator.py:124`) but
   `worktree_utils.py` has no `run_id` concept; either add an optional
   `run_id: str | None = None` parameter to `setup_worktree` (falling back to
   e.g. the pid as a string when absent) or synthesize one locally. This gap
   was flagged UNSPECIFIED in the parent's Program Design.

### Tests

- Registry entry is written by `setup_worktree` and removed by
  `cleanup_worktree` (round-trip).
- `_cleanup_orphaned_worktrees()` skips a worktree with a live registry entry
  even when its in-tree marker was deleted (the direct BUG-3373 regression
  test).
- `MergeCoordinator._cleanup_worktree()` removes the registry entry it created
  (extend `test_merge_coordinator.py::TestCleanupWorktreeFallback`).
- `ParallelOrchestrator.run()` invokes `_cleanup_orphaned_worktrees()` — add
  coverage to `test_orchestrator.py::TestRunMethod` (~lines 2239-2293); no
  existing test in that class asserts the auto-invocation at `orchestrator.py:245`.
- Concurrency regression: extend
  `test_worktree_concurrency.py::test_concurrent_setup_cleanup_leaves_no_orphans`
  to assert no stray registry entries survive the same concurrent
  setup/cleanup race.
- Registry hygiene: orphan deletion via `_cleanup_orphaned_worktrees()`
  removes the deleted worktree's registry entry; a registry entry whose
  worktree dir is gone is pruned on the next pass.
- The `.registry/` directory itself is never treated as an orphan candidate
  by the `worktree_base.iterdir()` scan (guaranteed today by
  `_is_ll_worktree()`'s name shapes — pin it with a test so a future filter
  change can't regress it).
- Existing marker-only tests
  (`test_orchestrator.py::TestOrphanedWorktreeCleanup`,
  `test_worktree_utils.py`, `test_cli_loop_worktree.py`) must continue to pass
  unmodified where they don't touch the registry.

### Documentation

- `docs/reference/API.md` — update `setup_worktree`/`cleanup_worktree`
  reference entries to describe the registry alongside the marker.
- `commands/cleanup-worktrees.md` and `docs/reference/COMMANDS.md` §
  `/ll:cleanup-worktrees` — update liveness semantics prose to mention the
  registry as the primary signal.

## Files to Modify

- `scripts/little_loops/worktree_utils.py` (`setup_worktree`, `cleanup_worktree`)
- `scripts/little_loops/parallel/orchestrator.py` (`_cleanup_orphaned_worktrees`)
- `scripts/little_loops/parallel/merge_coordinator.py` (`_cleanup_worktree`)

## Impact

Closes the primary BUG-3373 misclassification hole: a live worktree whose
in-tree marker is deleted is no longer indistinguishable from a genuine
orphan, independent of whether the process-cwd fallback (ENH-3377) ever
ships.

## Related Key Documentation

- `scripts/little_loops/worktree_utils.py` (setup/cleanup, BUG-579 marker)
- `scripts/little_loops/parallel/orchestrator.py` (orphan detection)
- `scripts/little_loops/parallel/orchestrator.py:720-782` (`_load_state`/`_save_state` registry precedent)

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-01T15:20:22 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
