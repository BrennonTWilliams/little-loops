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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Confirmed via direct code read: `MergeCoordinator._cleanup_worktree()` (`merge_coordinator.py:1148-1192`) has no import of `worktree_utils` anywhere in the file and independently reimplements the full unlock/remove/rmtree/branch-delete sequence — verifies this issue's Current Behavior claim. Its branch-delete guard is `branch_name.startswith("parallel/")` (narrower than the `_is_ll_branch()` guard used by `worktree_utils.cleanup_worktree()` and the orphan-reap loop) — the "redirect to call `worktree_utils.cleanup_worktree()`" option in Proposed Solution step 3 would also normalize this guard difference as a side effect; "add the same registry-removal call" would leave it unchanged.
- Two additional call sites already call `worktree_utils.cleanup_worktree()` directly and therefore need no separate registry-removal wiring once step 2 lands. `WorkerPool._cleanup_worktree()` (`scripts/little_loops/parallel/worker_pool.py:880-918`, called from `cleanup_all_worktrees()` at line 2088) imports and calls `cleanup_worktree()` at line 912; its one early-return branch (`worker_pool.py:889-895`, BUG-142 guard, worktree actively in use) never reaches that call, correctly, since the worktree isn't being torn down on that path.
- `scripts/little_loops/cli/loop/run.py`'s `_cleanup_worktree_on_exit()` (registered via `atexit.register` at line 566) is the other such call site — it calls `cleanup_worktree()` directly at line 543.
- The `_save_state`/`_load_state` atomic-write pattern this issue's registry write is meant to mirror (`orchestrator.py:720-782`) uses `tempfile.mkstemp(dir=state_file.parent)` + `os.replace()` for atomicity, guarded only by an in-process `threading.Lock` (`self._state_lock`) — no cross-process file lock (`fcntl`/`flock`) exists anywhere in this path. Each registry entry is a distinct per-worktree file, so cross-worker write collision is not a concern here, but there is no existing precedent in this codebase for locking a shared registry *directory* if a future change ever needs one.
- `_prune_ghost_worktree_refs()` (`orchestrator.py:424-473`, called unconditionally at the end of `_cleanup_orphaned_worktrees()`) does not scan `worktree_base` via `iterdir()` — it walks `git worktree list --porcelain` output instead. A `.registry/` sibling directory is therefore already outside its candidate set, independent of the `_is_ll_worktree()` guard the Tests section cites for the orphan-detection loop.

## Program Design

### Types

- Registry entry: `pid: int`, `run_id: str` (on-disk encoding — filename-embedded
  pid vs. plain-text `pid\nrun_id\n` vs. JSON — is the open Format decision in
  Proposed Solution step 1)

### Signatures

- `_registry_dir(worktree_path: Path) -> Path` — `worktree_path.parent / ".registry"`
- `_write_registry_entry(worktree_path: Path, pid: int, run_id: str) -> None` —
  atomic write via the `_save_state` `tempfile.mkstemp` + `os.replace` pattern
- `_remove_registry_entry(worktree_path: Path) -> None`
- `_registry_entry_is_live(worktree_path: Path) -> bool` — reads the entry,
  reuses the existing `os.kill(pid, 0)` liveness probe

### Call Path

`setup_worktree` -> `_write_registry_entry`
`cleanup_worktree` / `MergeCoordinator._cleanup_worktree` -> `_remove_registry_entry`
`ParallelOrchestrator.run` -> `_cleanup_orphaned_worktrees` -> `_registry_entry_is_live`
-> (fallback) existing `.ll-session-*` glob check

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Format-decision precedent (relevant to step 1's "choose with ENH-3378's bash consumer in mind"): `hooks/scripts/scratch-cleanup.sh:49` already extracts a filename-embedded pid via `sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'`, a working, proven-in-this-codebase precedent for the filename-embedded-pid option. By contrast, no bash code anywhere in this repo extracts a single field from JSON content without `jq` — every existing "jq-optional" fallback (`hooks/scripts/lib/common.sh:162-234`, and `session-cleanup.sh`'s own `WORKTREE_BASE` resolution) either requires `jq` or substitutes a fixed default/shape check, never a field extraction. This favors the filename-embedded-pid or plain-text-line options over JSON for bash readability, consistent with the issue's own leaning.

## Scope Boundaries

- The process-cwd fallback liveness check for worktrees with neither a live
  registry entry nor a live marker is out of scope — split into ENH-3377.
- Hardening `hooks/scripts/session-cleanup.sh` to consult the registry is out
  of scope — split into ENH-3378.
- No backfill: worktrees created before this feature ships have no registry
  entry and fall back to marker-only behavior until they're recreated.
- The on-disk registry-entry format is decided once here (with ENH-3378's bash
  consumer in mind, per Proposed Solution step 1); reopening that format later
  is out of scope for this issue.

## Files to Modify

- `scripts/little_loops/worktree_utils.py` (`setup_worktree`, `cleanup_worktree`)
- `scripts/little_loops/parallel/orchestrator.py` (`_cleanup_orphaned_worktrees`)
- `scripts/little_loops/parallel/merge_coordinator.py` (`_cleanup_worktree`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- No additional files require registry-removal wiring beyond the three listed above. `WorkerPool._cleanup_worktree()` (`scripts/little_loops/parallel/worker_pool.py:880-918`) and `scripts/little_loops/cli/loop/run.py`'s `_cleanup_worktree_on_exit()` (~line 510-566) already call `worktree_utils.cleanup_worktree()` directly, so they automatically inherit the registry-removal addition once it lands there.

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
- `/ll:refine-issue` - 2026-09-01T18:27:46 - `f0c0abcb-9bb0-4011-99a7-b965b2d4e8f5.jsonl`
- `/ll:format-issue` - 2026-09-01T18:11:44 - `a022c67c-3828-4e2e-96d1-3bcdf7adfc60.jsonl`
- `/ll:issue-size-review` - 2026-09-01T15:20:22 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
