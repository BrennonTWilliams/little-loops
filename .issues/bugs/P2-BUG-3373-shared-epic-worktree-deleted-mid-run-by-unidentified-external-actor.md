---
id: BUG-3373
type: BUG
title: shared epic worktree deleted mid-run by unidentified external actor
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T04:10:53Z'
relates_to: [ENH-3374, BUG-3375]
---

# BUG-3373: shared epic worktree deleted mid-run by unidentified external actor

## Summary

During `ll-loop run sprint-refine-and-implement EPIC-1463`, the shared epic
worktree (`.worktrees/20260831-221633-subloop-epic-epic-1463-...`) was
deleted out from under a live `/ll:refine-issue FEAT-2122 --auto` session,
mid-run. The deleter has not been identified. An earlier version of this
issue attributed the deletion to `_execute_sub_loop`'s `finally`-block
`detach_worktree()` in `scripts/little_loops/fsm/executor.py`; the run's own
`events.jsonl` disproves that attribution (see Root Cause), so this issue is
now an investigation: identify the actual deleter and fix it at the source.

Downstream hardening has been split off:
- ENH-3374 — make the `.ll-session-<pid>` liveness marker resilient so an
  active sub-loop worktree can never be classified orphaned.
- BUG-3375 — autodev cascades `[Errno 2]` into a clean terminal exit and
  silently abandons its queue when its worktree vanishes.

## Current Behavior

Something removed the shared epic worktree cleanly (`git worktree list` no
longer showed it — a `git worktree remove`-style removal, not a stray
`rm -rf`) between `03:54:58Z` and `03:57:14Z` on 2026-09-01, while:

- the owning `ll-loop run` process was alive (it kept executing states
  until `03:57:15Z`), and
- a dispatched `/ll:refine-issue FEAT-2122 --auto` subprocess was actively
  using the worktree as its cwd.

No component in the run's own call path performed the deletion in that
window (see Root Cause), so the deleter is external to the
`sprint-refine-and-implement` lifecycle: another session, a cleanup pass, or
a tool invoked from inside one of the dispatched Claude sessions.

## Expected Behavior

Nothing deletes a worktree that is (a) registered to a live `ll-loop`/
`ll-parallel` process or (b) the cwd of a live dispatched subprocess. Any
cleanup path that can remove `.worktrees/*` must positively verify
non-liveness first, and the deleter responsible for this incident is
identified and fixed (or, if it was a manual/external action, documented as
out of scope and this issue closed with ENH-3374/BUG-3375 carrying the
hardening).

## Motivation

An active-worktree deletion silently truncates a batch run: in the observed
incident it killed the FEAT-2122 refine mid-flight and left ENH-1722
undequeued, with the run reporting `verdict=incomplete-abandoned` and no
error pointing at the real cause. Until the deleter is identified, every
long `auto-refine-and-implement` / `sprint-refine-and-implement` run is
exposed to a recurrence, and any fix aimed at the wrong component (as the
original version of this issue was) leaves the actual hole open.

## Proposed Solution

Investigate and identify the deleter, then fix at the source. Leads, in
order of suspicion:

1. **Orphan-cleanup misclassification** (`ll-parallel --cleanup-orphans`,
   `/ll:cleanup-worktrees`): orphan detection trusts a `.ll-session-<pid>`
   marker written at `setup_worktree`
   (`scripts/little_loops/worktree_utils.py:280`) and checked in
   `parallel/orchestrator.py:334-345`. The marker is an untracked file
   inside the worktree — if anything deleted it (e.g. a `git clean -fdx`
   run by the FEAT-2123 manage-issue session, which did an editable-package
   reinstall and full test pass inside this worktree minutes before the
   deletion window), a subsequent cleanup pass would see the active
   worktree as orphaned and remove it. Check whether any
   `ll-parallel --cleanup-orphans` invocation ran ~22:55–22:57 local on
   2026-08-31 (shell history, other Claude session transcripts, analytics
   events).
2. **A dispatched session's own tooling**: the FEAT-2123 manage-issue
   session (ended `03:54:47Z`) or the FEAT-2122 refine session itself may
   have invoked a cleanup command or `git worktree remove` via a subagent
   or hook. Grep both sessions' transcripts for `worktree remove`,
   `cleanup-orphans`, `cleanup-worktrees`, `git clean`.
3. **Concurrent manual action**: a second interactive session or terminal
   command. `.loops/.history/` shows no concurrent loop run in the window,
   but a plain CLI invocation would leave no history entry there.

Deliverable: the identified mechanism written into this issue's Root Cause,
plus a source fix (likely landing in the component ENH-3374 also touches —
coordinate the two).

## Impact

Silent batch truncation for epic/sprint automation runs: 1 of 3 issues
completed, 1 killed mid-refine, 1 abandoned untouched
(`verdict=incomplete-abandoned, closed=1, inflight_unresolved=1,
abandoned=1, parked_rate=0.6667`). No data loss in the observed instance
(the refine session had not yet written changes), but only by luck of
timing — the same deletion during a manage-issue implementation phase would
destroy uncommitted work.

## Steps to Reproduce

Not deterministically reproducible until the deleter is identified.
Observed during `ll-loop run sprint-refine-and-implement EPIC-1463`:

- Run dir: `.loops/runs/sprint-refine-and-implement-20260831T221623/`
- History: `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`

Verified timeline (all timestamps from `events.jsonl`, UTC):

1. `03:16:34.994` — `sub_loop_worktree_attached` (auto-refine-and-implement
   attaches the shared epic worktree for the autodev sub-loop; the only
   attach event in the run).
2. `03:54:47` — FEAT-2123 completes inside the worktree (`ll-auto` summary,
   commit `46ef469e0` on the epic branch).
3. `03:54:58.712` — `refine-to-ready-issue` sub-loop starts
   `/ll:refine-issue FEAT-2122 --auto` in the same worktree.
4. **`03:54:58`–`03:57:14` — the worktree is deleted mid-action.** The
   refine session reports "the working directory vanished... cleanly
   removed (not just orphaned)... `git worktree list` no longer shows it"
   and exits 0 at `03:57:14.917`.
5. `03:57:14.937`–`03:57:15.36` — `refine-to-ready-issue` then autodev
   states (`skip_inflight`, `dequeue_next`, `finalize_done`) cascade
   `[Errno 2] No such file or directory` on the missing cwd; autodev
   reaches `loop_complete` at `03:57:15.369` (see BUG-3375).
6. `03:57:15.371` — `sub_loop_worktree_detached`: `_execute_sub_loop`'s
   `finally` block runs its normal teardown against the already-deleted
   path (a no-op removal), then the run finalizes as
   `incomplete-abandoned` with ENH-1722 never dequeued.

## Root Cause

Unknown — under investigation (see Proposed Solution leads).

Ruled out: `FSMExecutor._execute_sub_loop`'s `finally`-block
`detach_worktree()` (`scripts/little_loops/fsm/executor.py:1125-1127`),
which the original version of this issue blamed. That block cannot run
before `child_executor.run()` returns, and `events.jsonl` shows the child
(autodev) executing states until `03:57:15.369` — up to two minutes *after*
the deletion and ~800ms after the refine subprocess reported the worktree
gone. The `sub_loop_worktree_detached` event at `03:57:15.371` is downstream
fallout (teardown of an already-deleted tree), not the cause. Gating that
teardown on autodev's `autodev-inflight` sentinel (the originally proposed
fix) would not have prevented this incident, and could not work as designed
anyway: every site that clears the sentinel is an autodev FSM state, so
nothing clears it after autodev's FSM has returned.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-parallel --cleanup-orphans`
- `scripts/little_loops/worktree_utils.py` — session-marker write (BUG-579)

## Status

**Open** | Created: 2026-09-01 | Priority: P2

## Session Log
- Rewritten 2026-09-01 after events.jsonl replay disproved the original root cause; hardening split to ENH-3374 / BUG-3375.
- `/ll:confidence-check` - 2026-09-01T05:03:18 - `cb6b213f-3d5d-4d43-865a-115ce8e42c87.jsonl` (against superseded content)
- `/ll:verify-issues` - 2026-09-01T05:00:57 - `59d87293-a76b-4fa5-956d-fafc8b453dfc.jsonl` (against superseded content)
- `/ll:wire-issue` - 2026-09-01T04:58:50 - `f09f6f25-9595-48be-95b3-0d16ac1ab171.jsonl` (against superseded content)
- `/ll:refine-issue` - 2026-09-01T04:50:45 - `b9117cb4-7742-4681-b184-d660daf97ebc.jsonl` (against superseded content)
- `/ll:format-issue` - 2026-09-01T04:17:10 - `6ed91f4a-37bf-454d-8c78-490c7b5f663f.jsonl`
- `/ll:capture-issue` - 2026-09-01T04:11:01 - `619baadf-ddf4-410d-b209-baf9424402fe.jsonl`
