---
id: ENH-2866
title: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation
type: ENH
priority: P2
status: open
discovered_by: epic-review
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
- observability
blocks:
- ENH-2853
---

# ENH-2866: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation

## Summary

Nothing in little-loops records the commit SHA a work item started from. Every
orchestrator — `autodev.yaml`'s `dequeue_next`, `ll-parallel`'s per-issue
worktree creation, `ll-sprint`'s waves — begins work against some tree state and
then discards the fact. (`ll-sprint run` delegates execution to the same
`ParallelOrchestrator` as `ll-parallel` — `cli/sprint/run.py:23` — so stamping
`ll-parallel`'s worker creation covers sprint waves transitively; no separate
`ll-sprint` stamp is needed.)

Stamp that SHA at the point work is dequeued, in a location downstream checks
can read. Carved out of ENH-2853, where it was one of eight workstreams and the
only one that is independently landable and independently useful.

## Motivation

"What did this change start from?" is the base-state question underneath several
things this epic wants:

- ENH-2853's pre-patch test-failure check needs a base tree to run candidate
  tests against. Without a stamp, its primary path is dead code and every run
  silently takes the merge-base fallback — which is wrong whenever a
  verification step spans multiple commits (routine under `ll-auto` and
  `ll-sprint`), and `HEAD~1` is wrong for the same reason.
- FEAT-2855's maintainability windows and any rework-rate measurement are more
  precisely attributable when a run's starting tree is known rather than inferred
  from commit timestamps.

Landing the stamp first means ENH-2853 exercises its real path from day one
instead of shipping a fallback and a TODO.

## Current Behavior

No orchestrator records the commit SHA a work item started from.
`autodev.yaml`'s `dequeue_next` (~L80-141) snapshots pre-refine readiness to
`${context.run_dir}/autodev-pre-readiness.txt` but calls `git rev-parse`
nowhere. `ll-parallel` delegates worktree lifecycle to
`little_loops.parallel.worker_pool` / `orchestrator`, which call the shared
`setup_worktree()` primitive; no SHA is captured at the point a per-issue
worker's worktree is created. A downstream consumer asking "what tree did this
change start from?" has only `HEAD~1` or a merge-base guess, both of which are
wrong whenever a step spans multiple commits.

## Expected Behavior

Each orchestrator writes the dequeue-time SHA — plus whether the tree was dirty
— at the moment it takes work, before anything mutates the tree or the issue
file. A single reader helper resolves that stamp for a run and returns `None`
when absent, so consumers implement the merge-base fallback once and identically
rather than each rolling their own. The stamp is persisted onto the existing run
record so it outlives the run directory. An orchestrator or hand-run loop that
does not stamp keeps working unchanged.

## Proposed Change

1. **`autodev.yaml` `dequeue_next`** — write `git rev-parse HEAD` to
   `${context.run_dir}/autodev-dequeue-sha.txt`, alongside the existing
   pre-refine readiness snapshot written by the same state (FEAT-2751). Same
   run-dir handshake-file idiom, no new mechanism.
2. **`ll-parallel`** — capture the SHA at per-issue worktree creation. `ll-parallel`
   has no direct worktree calls; it delegates to `little_loops.parallel.worker_pool`
   / `orchestrator`, which call the shared `setup_worktree()` primitive in
   `worktree_utils.py`. The stamp belongs at the worker's creation point, in the
   worker's own state, not inside the shared primitive.
3. **Reader helper** — one function that resolves a run's base SHA, returning the
   stamp when present and `None` when not, so consumers implement the
   merge-base fallback once and identically rather than each rolling their own
   lookup.
4. **Persist to `.ll/history.db`** where a run is already recorded, so the stamp
   outlives the run directory. Concretely: additive nullable columns
   (`base_sha TEXT`, `base_dirty INTEGER`) on the existing run rows —
   `loop_runs` (`session_store/schema.py:553`) for the autodev/FSM path and
   `orchestration_runs` (`session_store/schema.py:523`) for
   `ll-parallel` — via a new `_MIGRATIONS` entry in
   `session_store/schema.py` (NULL = "unstamped", matching
   the reader's `None` contract). No new table.

## Design Notes

- **Additive only.** `setup_worktree()` / `cleanup_worktree()` are called
  directly by `scripts/little_loops/fsm/executor.py`,
  `scripts/little_loops/cli/loop/run.py`,
  `scripts/little_loops/parallel/orchestrator.py`, and the epic-branch verify
  path. Any signature change must be backward compatible or those four call
  sites break.
- **The stamp is advisory, never a hard dependency.** A consumer that finds no
  stamp falls back to merge-base and *says which base it used*. An orchestrator
  that hasn't been taught to stamp (or a hand-run loop) must keep working.
- **Resolve the SHA before any mutation.** In `dequeue_next` this means before
  refinement writes to the issue file — a stamp taken after the first commit of
  the run describes the wrong tree.
- **Detached/dirty trees.** Record the SHA plus whether the tree was dirty at
  stamp time; a dirty base means a pre-patch reconstruction is approximate and
  the consumer should be able to say so rather than assert a clean comparison.
- No LLM involvement — this is a `git rev-parse` and a file write.
- **`ll-auto` is a third dequeue site and was missing from the stamp set** (placement review, 2026-07-30). This issue's Motivation names `ll-auto` as a case where a verification step spans multiple commits and merge-base is wrong — but the Proposed Change stamps only `autodev.yaml`'s `dequeue_next` and `ll-parallel`'s worker creation. `ll-auto` routes through neither: `cli/auto.py` → `issue_manager.py`'s `AutoProcessor` is its own sequential dequeue loop, not a wrapper over `autodev.yaml` (a grep of `issue_manager.py` for `autodev` returns only a comment at L905). As written, the one orchestrator the Motivation calls out would always take ENH-2853's merge-base fallback. Stamp `issue_manager.py`'s per-issue dequeue as a third site. Check first whether the `_baseline_sha` it already computes for `verify_work_was_done()` (~L1072, ~L1109) is the same value — if so this is a persistence change, not a new capture.
- **`ll-queue run` is a fourth dequeue site — stamp it or exempt it explicitly** (placement review, 2026-07-30). FEAT-2906's `ll-queue run` serially dequeues `pending` entries and drives each to completion, which makes it an orchestrator by this issue's own definition ("the point work is dequeued"). Decide during implementation: stamp it alongside the other three, or record in § Scope Boundaries why it is exempt. Leaving it unaddressed reproduces exactly the `ll-auto` gap this note corrects.

## Acceptance Criteria

- [ ] `autodev.yaml`'s `dequeue_next` writes the dequeue-time SHA to the run
      directory, resolved before any state mutates the tree or issue file.
- [ ] `ll-parallel` records the same stamp at per-issue worktree creation, in the
      worker's state rather than inside the shared `setup_worktree()` primitive.
- [ ] `setup_worktree()` / `cleanup_worktree()` signatures remain backward
      compatible; the four existing direct call sites are unchanged or updated
      additively.
- [ ] A single reader helper resolves a run's base SHA and returns `None` when
      unstamped, so the merge-base fallback is implemented once.
- [ ] Whether the tree was dirty at stamp time is recorded alongside the SHA.
- [ ] The stamp is persisted to `.ll/history.db` as additive nullable columns on
      the existing run rows (`loop_runs` / `orchestration_runs`), not a new
      table; NULL means unstamped.
- [ ] An orchestrator or hand-run loop with no stamp continues to work
      unchanged.
- [ ] Tests cover: the stamp written by `dequeue_next`, the stamp written at
      `ll-parallel` worker creation, the reader returning `None` when unstamped,
      and the dirty-tree flag.

_Added 2026-07-30 (placement review) — see Design Notes:_

- [ ] `ll-auto` records the stamp at its own per-issue dequeue in
      `issue_manager.py`, resolved before Phase 1 mutates the issue file. A test
      covers it, and asserts an `ll-auto` run is not left taking the merge-base
      fallback.
- [ ] All three orchestrators write the stamp in a form the *same* reader helper
      resolves — no per-orchestrator lookup logic.
- [ ] `ll-queue run` is either stamped or explicitly exempted in
      § Scope Boundaries with a stated reason.

## Integration Map

### Files to Modify

_`issue_manager.py` added 2026-07-30 (placement review) — see Design Notes,
"`ll-auto` is a third dequeue site."_

- `scripts/little_loops/loops/autodev.yaml` — `dequeue_next` (~L80-141); the
  pre-readiness snapshot at ~L104-117 is the idiom to follow
- `scripts/little_loops/parallel/worker_pool.py` /
  `scripts/little_loops/parallel/orchestrator.py` — per-issue worktree creation
  call sites
- `scripts/little_loops/issue_manager.py` — `ll-auto`'s own sequential dequeue,
  which routes through neither of the two sites above. Stamp at the point the
  issue is taken, before Phase 1 mutates the issue file; check whether the
  existing `_baseline_sha` (~L1072, ~L1109) already holds the right value
- `scripts/little_loops/worktree_utils.py` — only if an additive parameter is
  the cleanest carrier; prefer stamping at the caller
- `scripts/little_loops/session_store/schema.py` — the `_MIGRATIONS` entry adding
  the nullable stamp columns — and `scripts/little_loops/session_store/writers.py`
  — persist the stamp on the run record (note: `session_store.py` was split into
  the `session_store/` package by ENH-2890; the former flat-module line refs in
  this issue's research are stale)

### Dependent Files (Callers of the shared worktree primitives)
- `scripts/little_loops/fsm/executor.py` (~L927)
- `scripts/little_loops/cli/loop/run.py` (~L472, `cleanup_worktree` via `atexit`
  ~L535/560)
- `scripts/little_loops/parallel/merge_coordinator.py` (~L1061) — has a private
  `_cleanup_worktree` wrapper; confirm whether it needs updating
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~L462, ~L653) —
  calls `verify_epic_branch_before_merge()`

### Similar Patterns
- `autodev.yaml`'s `autodev-pre-readiness.txt` snapshot (FEAT-2751) — run-dir
  handshake-file convention this stamp copies
- `scripts/little_loops/session_store/writers.py:_backfill_commit_events()` (~L781) —
  established `git log` subprocess-invocation shape (timeout, `cwd=repo_root`,
  `capture_output=True, text=True`)
- `scripts/tests/test_worker_pool.py:TestSetupWorktreeAndCleanup` (~L634, e.g.
  `test_setup_worktree_passes_base_branch_in_feature_mode` ~L963) — closest
  analog for a worker-creation-point test; currently asserts only on
  `git worktree add` argv shape

### Tests
- `scripts/tests/test_autodev_loop.py` — follow
  `TestDequeueNextPreReadinessSnapshot` (~L172-186), which does string-containment
  assertions against the raw YAML `action:` block rather than live execution;
  no existing test executes `dequeue_next` live
- `scripts/tests/test_worker_pool.py`, `scripts/tests/test_orchestrator.py` —
  the latter patches `setup_worktree` at ~7 sites (L1761-1888)
- `scripts/tests/test_session_store_writers.py` / `test_session_store_schema.py` —
  stamp persistence (the flat `test_session_store.py` no longer exists; the suite
  was split alongside the ENH-2890 package split)

### Consumers
- `ENH-2853` — pre-patch test-failure check (primary consumer; blocked on this)
- `FEAT-2855` / `FEAT-2867` — *optional* window-attribution precision; neither is blocked on this stamp, and FEAT-2867 intentionally sequences first using commit-timestamp windows. Both must work without it.

## Scope Boundaries

**In scope:** capturing the SHA (plus dirty-tree flag) at `autodev.yaml`'s
`dequeue_next`, `ll-parallel`'s per-issue worktree creation, and (added
2026-07-30, placement review) `issue_manager.py`'s `ll-auto` dequeue; one reader
helper that returns `None` when unstamped; persistence onto the existing run
record.

**Open decision (2026-07-30):** `ll-queue run` (FEAT-2906) also dequeues work
items. Stamp it or move it to *Out of scope* with a stated reason before
implementation — do not leave it unaddressed.

**Out of scope:** the merge-base fallback logic itself and any use of the base
state (ENH-2853 owns both); stamping `ll-loop run --worktree` or the epic-branch
verify path — neither dequeues work items; a separate `ll-sprint` stamp —
`ll-sprint run` delegates to the same `ParallelOrchestrator` as `ll-parallel`
(`cli/sprint/run.py:23`), so the `ll-parallel` stamp covers sprint waves;
changing `setup_worktree()` /
`cleanup_worktree()` semantics for their four existing callers.

## Impact

Turns ENH-2853's base-state resolution from a fallback-only path into its
intended one, and offers FEAT-2855 / FEAT-2867 an *optional* precise window
boundary instead of one inferred from commit timestamps — an additive refinement
those two do not depend on. Small and self-contained: a
`git rev-parse`, a run-dir file write in the same idiom `dequeue_next` already
uses for its readiness snapshot, and one reader.

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
- gate-placement review (manual, no skill) - 2026-07-30 - added `issue_manager.py` (`ll-auto`) as a third stamp site and `ll-queue run` as an open decision; Design Notes, Files to Modify, 3 ACs, Scope Boundaries
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
