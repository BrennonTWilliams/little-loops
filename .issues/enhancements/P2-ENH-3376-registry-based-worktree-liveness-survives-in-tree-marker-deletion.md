---
id: ENH-3376
type: ENH
title: registry-based worktree liveness survives in-tree marker deletion
priority: P2
status: done
parent: ENH-3374
relates_to:
- BUG-3373
- BUG-3375
confidence_score: 100
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 20
completed_at: '2026-09-01T20:10:00Z'
---

# ENH-3376: registry-based worktree liveness survives in-tree marker deletion

## Summary

Add an out-of-tree liveness registry (`<worktree_base>/.registry/<worktree-name>`,
plain text: pid + process create_time) written at `setup_worktree` and removed at `cleanup_worktree`, so a
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

- `setup_worktree` writes a registry entry under
  `<worktree_base>/.registry/<worktree-name>` (sibling of, not inside, the
  worktree checkout dirs, so `git clean` cannot reach it), in addition to the
  existing in-tree marker. **Format (decided here, final):** plain text,
  line 1 = pid, line 2 = `psutil.Process(pid).create_time()` as a float
  string, optional line 3 = run id. Bash consumers read line 1 only.
- The registry entry is written **before** `git worktree add`, not after.
  Today the in-tree marker lands at the very end of `setup_worktree` (after
  `git worktree add` and the `.claude/` + `copy_files` copies), so a
  concurrent orphan scan during that window sees a marker-less worktree and
  reaps it. The registry closes this window because it does not need the
  worktree directory to exist yet. If `git worktree add` then fails, the
  entry is removed on the error path.
- `cleanup_worktree` removes the registry entry.
- `MergeCoordinator._cleanup_worktree()` also removes the registry entry (or
  is redirected to call `worktree_utils.cleanup_worktree()`), since it bypasses
  that function today.
- `_cleanup_orphaned_worktrees()` consults the registry first: an entry with a
  live pid **whose `create_time` matches the recorded one** (pid-reuse guard,
  same identity-check shape as `cli/queue.py::_verify_owner_alive` and
  `cli/loop/queue.py::_verify_queue_pid_identity`) means the worktree is live
  regardless of in-tree marker state. A live pid with a mismatched
  `create_time` is a recycled pid: treat the entry as dead. A missing or
  unparseable line 2 falls back to the bare `os.kill(pid, 0)` probe. Only
  when there is no live registry entry does it fall back to the existing
  in-tree marker check. Worktrees with neither a live registry entry nor a
  live marker keep today's behavior (treated as orphaned) — the fallback
  process-cwd check for that path is out of scope here (see ENH-3377).
- Registry entries do not accumulate: when `_cleanup_orphaned_worktrees()`
  deletes an orphaned worktree it also removes that worktree's registry
  entry, and it prunes any registry entry whose worktree directory no longer
  exists **and whose pid is dead**. The dead-pid condition is required: the
  entry is now written before `git worktree add` (see above), so a
  dir-missing-only prune would delete a just-written entry for a worktree
  whose creation is still in flight, and the next pass would then reap the
  new worktree as marker-less and registry-less. (The orphan path inlines removal at `orchestrator.py:356-398` and
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

1. `setup_worktree` (`worktree_utils.py:160`): add a registry write to
   `<worktree_base>/.registry/` for the worktree, placed **before** the
   `git worktree add` call (~line 232) rather than beside the marker write
   (~line 280) — see Expected Behavior for why. **Exact placement:**
   immediately before the `git_lock.run(worktree_args, ...)` call, which
   means *after* both (a) the pre-existing-path teardown at lines 211-214
   (`if worktree_path.exists(): cleanup_worktree(...)` — that call will now
   remove the registry entry, so writing earlier would self-delete it) and
   (b) the `base_branch` `rev-parse --verify` check at lines 216-223 (which
   raises `RuntimeError` before `worktree add`, so writing earlier would leak
   an entry on that path). Use the same
   `tempfile.mkstemp` + `os.replace` atomic-write pattern as `_save_state`;
   `mkdir(parents=True, exist_ok=True)` the `.registry/` dir first (the
   worktree base may not exist yet on first use). Line 2 comes from
   `psutil.Process(os.getpid()).create_time()` (psutil is already a required
   dependency, `scripts/pyproject.toml:58`).
   Remove the entry on the `RuntimeError` path if `git worktree add` fails.
   Keep the in-tree marker write unchanged (backward compatibility). Derive
   the registry dir as `worktree_path.parent / ".registry"` (the function
   receives `worktree_path`, not `worktree_base`).

   **Format decision (final — do not reopen in ENH-3378):** plain-text file
   named exactly `<worktree-name>` (no pid in the filename, so removal and
   prune never need a glob). Line 1 = pid, line 2 = `create_time` float,
   optional line 3 = run id. Rationale: `session-cleanup.sh` has no
   guaranteed JSON parser, and its "jq-optional" pattern (lines 21-26) only
   substitutes a default config value — it cannot extract a field from JSON.
   `head -n1` + a `[[ "$PID" =~ ^[0-9]+$ ]]` check is the whole bash reader.
2. `cleanup_worktree` (`worktree_utils.py:284`): add an explicit registry-entry
   removal call (best-effort; a `git clean` inside the worktree never reaches
   this function, so the registry is the durable record).
3. `MergeCoordinator._cleanup_worktree()`
   (`merge_coordinator.py:1148-1192`): **add the registry-removal call**; do
   not redirect this method to `worktree_utils.cleanup_worktree()`. The
   redirect would also change its branch-delete guard from `parallel/`-only
   to `_is_ll_branch()` (see Codebase Research Findings) — a behavior change
   unrelated to liveness. File that normalization separately if wanted.
4. `_cleanup_orphaned_worktrees()` (`orchestrator.py:317`): consult the
   registry before the existing `.ll-session-*` glob (line 337); treat
   "registry entry with live pid and matching `create_time`" as live
   regardless of in-tree marker state. Reuse the existing `os.kill(pid, 0)`
   probe for existence (keep its `PermissionError` → alive semantics), then
   compare `psutil.Process(pid).create_time()` against line 2 with a small
   float tolerance (`abs(a - b) < 1.0`; psutil rounds on some platforms). A
   mismatch means the pid was recycled → treat as dead.
5. Registry hygiene in the same method: when the orphan-deletion loop
   (`orchestrator.py:356-398`) removes a worktree, also remove its registry
   entry (this path inlines removal and never calls `cleanup_worktree()`);
   additionally prune any registry entry whose worktree directory no longer
   exists **and** whose pid is dead (or recycled). Never prune on
   dir-missing alone — see Expected Behavior for the in-flight-creation race.
6. `run_id` is optional metadata, not a liveness input. Add
   `run_id: str | None = None` to `setup_worktree`; the orchestrator passes
   `self.run_id` (`orchestrator.py:124`), other callers
   (`setup_prepatch_worktree`, `ensure_epic_branch`, `fsm/executor.py`'s
   sub-loop path) pass nothing and line 3 is omitted. Nothing reads line 3
   in this issue set; it exists only to make a registry entry attributable
   when debugging.

### Tests

- Registry entry is written by `setup_worktree` and removed by
  `cleanup_worktree` (round-trip).
- `_cleanup_orphaned_worktrees()` skips a worktree with a live registry entry
  even when its in-tree marker was deleted (the direct BUG-3373 regression
  test).
- Registry entry exists before `git worktree add` runs: patch
  `git_lock.run` to assert the entry is present when the `worktree add`
  argv arrives; and the entry is removed when `worktree add` returns
  non-zero.
- Pid-reuse guard: a registry entry whose pid is alive but whose recorded
  `create_time` does not match `psutil.Process(pid).create_time()` is
  treated as dead (worktree reaped, entry removed). A missing line 2 falls
  back to the bare `os.kill` probe.
- Prune requires dead pid: a registry entry whose worktree dir is missing
  but whose pid is alive with matching `create_time` is NOT pruned.
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
  worktree dir is gone **and whose pid is dead** is pruned on the next pass
  (same condition as the "Prune requires dead pid" bullet above).
- The `.registry/` directory itself is never treated as an orphan candidate
  by the `worktree_base.iterdir()` scan (guaranteed today by
  `_is_ll_worktree()`'s name shapes — pin it with a test so a future filter
  change can't regress it).
- Existing marker-only tests
  (`test_orchestrator.py::TestOrphanedWorktreeCleanup`,
  `test_worktree_utils.py`, `test_cli_loop_worktree.py`) must continue to pass
  unmodified where they don't touch the registry.

_Wiring pass added by `/ll:wire-issue`:_
- Pattern to follow for the atomic registry-write test:
  `test_file_utils.py::TestAtomicWriteJson` (covers `little_loops.file_utils.
  atomic_write_json`, the same `tempfile.mkstemp`+`os.replace` shape) has the
  exact three properties a registry-write test needs and `_save_state`'s own
  tests don't check: no orphaned `.tmp` on success, no orphaned `.tmp` on
  `os.replace` failure, and prior content preserved on failure.

### Documentation

- `docs/reference/API.md` — update `setup_worktree`/`cleanup_worktree`
  reference entries to describe the registry alongside the marker.
- `commands/cleanup-worktrees.md` and `docs/reference/COMMANDS.md` §
  `/ll:cleanup-worktrees` — update liveness semantics prose to mention the
  registry as the primary signal.
- Host-adapter mirrors of `commands/cleanup-worktrees.md` — these copy its
  body verbatim with no drift test (ENH-2968), so re-mirror them in the same
  change: `.qwen/commands/ll/cleanup-worktrees.md`,
  `.gemini/commands/cleanup-worktrees.toml`,
  `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md`. (This obligation
  belongs here and in ENH-3377 — the issues that actually edit the source
  file — not in ENH-3378, which doesn't touch it.)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` (§ "Worktree creation fails", lines
  147-148, and § "Too many worktrees", lines 232-233) — both sections state
  orphan cleanup is "liveness-aware — skips any worktree whose session-marker
  PID is still alive", phrased purely in marker terms; will read as
  incomplete once the registry becomes the primary signal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Confirmed via direct code read: `MergeCoordinator._cleanup_worktree()` (`merge_coordinator.py:1148-1192`) has no import of `worktree_utils` anywhere in the file and independently reimplements the full unlock/remove/rmtree/branch-delete sequence — verifies this issue's Current Behavior claim. Its branch-delete guard is `branch_name.startswith("parallel/")` (narrower than the `_is_ll_branch()` guard used by `worktree_utils.cleanup_worktree()` and the orphan-reap loop) — the "redirect to call `worktree_utils.cleanup_worktree()`" option in Proposed Solution step 3 would also normalize this guard difference as a side effect; "add the same registry-removal call" would leave it unchanged.
- Two additional call sites already call `worktree_utils.cleanup_worktree()` directly and therefore need no separate registry-removal wiring once step 2 lands. `WorkerPool._cleanup_worktree()` (`scripts/little_loops/parallel/worker_pool.py:880-918`, called from `cleanup_all_worktrees()` at line 2088) imports and calls `cleanup_worktree()` at line 912; its one early-return branch (`worker_pool.py:889-895`, BUG-142 guard, worktree actively in use) never reaches that call, correctly, since the worktree isn't being torn down on that path.
- `scripts/little_loops/cli/loop/run.py`'s `_cleanup_worktree_on_exit()` (registered via `atexit.register` at line 566) is the other such call site — it calls `cleanup_worktree()` directly at line 543.
- The `_save_state`/`_load_state` atomic-write pattern this issue's registry write is meant to mirror (`orchestrator.py:720-782`) uses `tempfile.mkstemp(dir=state_file.parent)` + `os.replace()` for atomicity, guarded only by an in-process `threading.Lock` (`self._state_lock`) — no cross-process file lock (`fcntl`/`flock`) exists anywhere in this path. Each registry entry is a distinct per-worktree file, so cross-worker write collision is not a concern here, but there is no existing precedent in this codebase for locking a shared registry *directory* if a future change ever needs one.
- `_prune_ghost_worktree_refs()` (`orchestrator.py:424-473`, called unconditionally at the end of `_cleanup_orphaned_worktrees()`) does not scan `worktree_base` via `iterdir()` — it walks `git worktree list --porcelain` output instead. A `.registry/` sibling directory is therefore already outside its candidate set, independent of the `_is_ll_worktree()` guard the Tests section cites for the orphan-detection loop.

## Program Design

### Types

- Registry entry (on-disk, plain text, file `<worktree_base>/.registry/<worktree-name>`):
  line 1 `pid: int`, line 2 `create_time: float`, optional line 3 `run_id: str`.
  Decided in Proposed Solution step 1; final.

### Signatures

- `_registry_dir(worktree_path: Path) -> Path` — `worktree_path.parent / ".registry"`
- `_write_registry_entry(worktree_path: Path, pid: int, create_time: float, run_id: str | None = None) -> None` —
  atomic write via the `_save_state` `tempfile.mkstemp` + `os.replace` pattern
- `_remove_registry_entry(worktree_path: Path) -> None`
- `_read_registry_entry(worktree_path: Path) -> tuple[int, float | None] | None` —
  None when absent or line 1 is not an int
- `_registry_entry_is_live(worktree_path: Path) -> bool` — reads the entry,
  reuses the existing `os.kill(pid, 0)` existence probe, then compares
  `create_time` when line 2 is present (mismatch → False)

### Call Path

`setup_worktree` -> `_write_registry_entry` -> `git worktree add` (-> `_remove_registry_entry` on failure)
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
- The on-disk registry-entry format is decided here (Proposed Solution step 1:
  plain text, pid / create_time / optional run id); ENH-3378 consumes it and
  must not reopen it.
- Normalizing `MergeCoordinator._cleanup_worktree()`'s `parallel/`-only
  branch-delete guard to `_is_ll_branch()` is out of scope (step 3).
- Closing the marker-write window for the in-tree marker itself is out of
  scope; the registry-before-`worktree add` ordering makes the registry the
  signal that covers that window.

## Files to Modify

- `scripts/little_loops/worktree_utils.py` (`setup_worktree`, `cleanup_worktree`)
- `scripts/little_loops/parallel/orchestrator.py` (`_cleanup_orphaned_worktrees`)
- `scripts/little_loops/parallel/merge_coordinator.py` (`_cleanup_worktree`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- No additional files require registry-removal wiring beyond the three listed above. `WorkerPool._cleanup_worktree()` (`scripts/little_loops/parallel/worker_pool.py:880-918`) and `scripts/little_loops/cli/loop/run.py`'s `_cleanup_worktree_on_exit()` (~line 510-566) already call `worktree_utils.cleanup_worktree()` directly, so they automatically inherit the registry-removal addition once it lands there.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/work_verification.py:213-237` (`_prepatch_teardown`) and
  `scripts/little_loops/fsm/executor.py:1649-1677` (`_prepatch_teardown`) —
  both import and call `worktree_utils.cleanup_worktree()` directly, same
  shape as the two call sites already noted above. No edit needed — they
  automatically inherit the registry-removal addition once it lands in
  `cleanup_worktree()`. This extends (does not contradict) the "no additional
  files require wiring" conclusion above — the enumeration of *why* was
  incomplete by two sites, not the conclusion itself.
- `scripts/little_loops/fsm/executor.py:1070` — the sub-loop `_detach`
  closure inside `_execute_sub_loop` (assigned to `detach_worktree` at line
  1082, invoked from the `finally` block at line 1127) calls
  `worktree_utils.cleanup_worktree()` directly. No edit needed — it inherits
  registry removal. Listed explicitly because this is the teardown path for
  the exact worktree shape BUG-3373 lost (`<ts>-subloop-<branch>` under
  `Config.get_worktree_base()`).
- `scripts/little_loops/parallel/worker_pool.py:2078-2088`
  (`WorkerPool.cleanup_all_worktrees()`) — a separate `worktree_base.iterdir()`
  enumeration (filtered by `_is_ll_worktree`) that calls
  `self._cleanup_worktree()` per match; reached via
  `scripts/little_loops/cli/parallel.py:207` (`main_parallel`'s `--cleanup`
  branch) and `scripts/little_loops/parallel/orchestrator.py:1952` (shutdown
  path). No edit needed — `WorkerPool._cleanup_worktree()` already calls
  `worktree_utils.cleanup_worktree()` (per the finding above this one), so
  this whole call chain inherits registry-removal automatically.
- `scripts/little_loops/parallel/orchestrator.py:558-584`
  (`_check_pending_worktrees()`) — a distinct `worktree_base.iterdir()` scan,
  separate from `_cleanup_orphaned_worktrees()`. Confirmed read-only: it only
  reports pending-work status (commits ahead, uncommitted changes) via
  `self.logger.warning`, and never deletes a worktree or makes a
  liveness/orphan classification. No wiring needed — not a liveness decision
  point.

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
- `/ll:manage-issue` - 2026-09-01T20:09:25 - `d5a9a03c-f68b-4fb9-95f0-031f088cbb82.jsonl`
- `/ll:ready-issue` - 2026-09-01T19:47:11 - `fb785ce3-4ca9-4f3f-8f22-cf643fea5f65.jsonl`
- Pre-implementation review (2nd pass) - 2026-09-01 - pinned registry-write placement (after the line-211 pre-cleanup and base_branch verify, immediately before `worktree add`), made the hygiene test bullet consistent with the dead-pid prune rule, added the executor sub-loop `_detach` inheriting site, moved the command-doc mirror obligation here from ENH-3378.
- `/ll:confidence-check` - 2026-09-01T19:10:49 - `9df9cefa-f639-494c-867c-39fd1ac3ff91.jsonl`
- Pre-implementation review - 2026-09-01 - format decided (plain text pid/create_time/run_id), registry written before `git worktree add`, prune requires dead pid, create_time pid-reuse guard, MergeCoordinator gets an explicit removal call (no redirect), run_id demoted to optional metadata.
- `/ll:wire-issue` - 2026-09-01T18:47:09 - `79009b58-7363-45db-90f1-4e47ed1282ba.jsonl`
- `/ll:refine-issue` - 2026-09-01T18:27:46 - `f0c0abcb-9bb0-4011-99a7-b965b2d4e8f5.jsonl`
- `/ll:format-issue` - 2026-09-01T18:11:44 - `a022c67c-3828-4e2e-96d1-3bcdf7adfc60.jsonl`
- `/ll:issue-size-review` - 2026-09-01T15:20:22 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
