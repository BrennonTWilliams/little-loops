---
id: BUG-3373
type: BUG
title: autodev tears down shared epic worktree while its dispatched issue's subprocess
  is still running
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-01'
captured_at: '2026-09-01T04:10:53Z'
---

# BUG-3373: autodev tears down shared epic worktree while its dispatched issue's subprocess is still running

## Summary

`auto-refine-and-implement`'s parent sub-loop tears down the shared epic
worktree as soon as the inner `autodev` sub-loop returns, but `autodev` can
reach its own terminal state while the currently-dispatched issue's
`refine-issue`/`manage-issue` subprocess is still actively running in that
same worktree. The teardown races the still-live subprocess and yanks the
worktree out from under it.

## Current Behavior

`FSMExecutor._execute_sub_loop` (`scripts/little_loops/fsm/executor.py:914`)
tears down a per-state shared worktree unconditionally: once
`child_result = child_executor.run()` returns (line 1124), the `finally`
block at line 1127 calls `detach_worktree()` regardless of whether a
dispatched issue's `refine-issue`/`manage-issue` action subprocess inside
that worktree has actually finished. A child FSM (`autodev`) can reach its
own terminal state — and thus return from `run()` — while a subprocess it
launched is still doing real work in the shared directory, so the worktree
is removed out from under it.

## Expected Behavior

`_execute_sub_loop`'s teardown should not fire until the parent has
confirmed no dispatched-issue action subprocess is still using the shared
worktree — e.g. by checking the child's own in-flight sentinel
(`${context.run_dir}/autodev-inflight`, written/cleared by `autodev.yaml`)
before calling `detach_worktree()`, or by waiting for it to clear (bounded by
the remaining timeout budget) instead of detaching immediately on
`child_executor.run()` returning.

## Motivation

Left unfixed, this is a silent data-loss/availability risk for every
`auto-refine-and-implement` / `sprint-refine-and-implement` run: any time
`autodev`'s FSM concludes while a dispatched issue's subprocess is still
live in the shared worktree, the race can recur, truncating the batch and
leaving later-queued issues abandoned (as it did for `ENH-1722` in the
reproduction below) with no error surfaced to the operator — `autodev` exits
via its terminal state, not a crash.

## Proposed Solution

Don't tear down the shared worktree until the parent has confirmed no
in-flight child subprocess is still using it — e.g. track the dispatched
issue's action subprocess completion explicitly, or gate detach on
`autodev`'s queue-drain state confirming the currently-dispatched issue's
action genuinely completed/errored (not merely that `autodev`'s own FSM
returned).

## Program Design

### Types

- No new types — reuse `Callable[[], None] | None` (`detach_worktree`,
  already local to `_execute_sub_loop`).

### Signatures

- `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
  (existing, `scripts/little_loops/fsm/executor.py:914`) — gate the
  `finally: detach_worktree()` block (line 1127) on dispatch liveness
  instead of calling it unconditionally.
- `_dispatch_still_inflight(run_dir: Path) -> bool` (new, local helper in
  `executor.py`) — `True` while `${run_dir}/autodev-inflight` exists and is
  non-empty.

### Call Path

`_execute_sub_loop` -> `child_executor.run()` (blocks until `autodev`'s own
FSM reaches a terminal state) -> `finally:` -> `_dispatch_still_inflight(child_fsm.context["run_dir"])`
gate -> `detach_worktree()` only once it returns `False` (or the bounded
wait/timeout budget is exhausted, at which point detach proceeds and emits a
distinct warning event rather than detaching silently).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` (line 914),
  specifically the `finally` block at lines 1124-1127.

### Dependent Files (Callers/Importers)
- `_execute_sub_loop` has one caller: `executor.py:1831`
  (`FSMExecutor`'s main state dispatch for `sub_loop` states). No other
  module calls it directly; loop YAMLs (`autodev.yaml`,
  `auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`,
  `refine-to-ready-issue.yaml`, `recursive-refine.yaml`, `rn-build.yaml`,
  `rn-remediate.yaml`, `flux-image-generator.yaml`, `rlhf-svg-evaluate.yaml`,
  `oracles/resolve-decision.yaml`) reference `_execute_sub_loop`'s routing
  behavior only in comments, not code.

### Similar Patterns
- N/A — `_execute_sub_loop` is the only site that attaches/detaches a shared
  `state.worktree` around a nested FSM call.

### Tests
- `scripts/tests/test_fsm_executor.py` — already exercises
  `_execute_sub_loop`; add a case where the child FSM reaches a terminal
  state while `${run_dir}/autodev-inflight` is still populated, and assert
  `detach_worktree()`/`cleanup_worktree` is not called until the sentinel
  clears (or the wait budget is exhausted).

### Documentation
- N/A — `_execute_sub_loop`'s worktree-attach behavior is documented only in
  inline comments (ENH-2609, BUG-2614) at the call site itself; no external
  doc describes it.

### Configuration
- N/A

## Implementation Steps

1. Add `_dispatch_still_inflight(run_dir: Path) -> bool` in `executor.py`,
   checking `${run_dir}/autodev-inflight` for existence and non-empty
   content.
2. In `_execute_sub_loop`'s `finally` block (line 1127), before calling
   `detach_worktree()`, poll `_dispatch_still_inflight` against the child's
   `run_dir` with a bounded wait (respecting the remaining timeout budget
   already computed earlier in the method); only call `detach_worktree()`
   once it clears or the budget is exhausted.
3. When the wait budget is exhausted with the sentinel still set, emit a
   distinct event (e.g. `sub_loop_worktree_detach_forced`) alongside the
   existing `sub_loop_worktree_detached` so a forced detach is
   distinguishable from a clean one in `events.jsonl`.
4. Add the `test_fsm_executor.py` case described in Integration Map →
   Tests, and confirm the reproduction sequence in `Steps to Reproduce`
   no longer races (worktree stays attached while `autodev-inflight` is
   set).

## Impact

Reproducible risk for any `auto-refine-and-implement` /
`sprint-refine-and-implement` run, not a one-off fluke: any time `autodev`'s
FSM concludes while it still has a live child subprocess in the shared
worktree, the race can recur, silently truncating the batch and leaving
later-queued issues abandoned.

## Steps to Reproduce

Observed during `ll-loop run sprint-refine-and-implement EPIC-1463`:

- Run dir: `.loops/runs/sprint-refine-and-implement-20260831T221623/`
- History: `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`

Sequence:

1. `FEAT-2123` committed successfully on branch
   `epic/epic-1463-track-deferred-codex-cli-interop-gaps` inside worktree
   `.worktrees/20260831-221633-subloop-epic-epic-1463-track-deferred-codex-cli-interop-gaps`.
2. `autodev` dequeued `FEAT-2122` and started `/ll:refine-issue FEAT-2122
   --auto` in that same worktree.
3. ~2 minutes later, the worktree was removed out from under the still-running
   refine session. The subagent's own diagnosis (`events.jsonl`,
   `2026-09-01T03:57:14.539Z`): "the working directory vanished... cleanly
   removed (not just orphaned)... possibly a concurrent cleanup-worktrees run
   or the epic/subloop orchestrator concluding this branch."
4. `events.jsonl` confirms the teardown is `auto-refine-and-implement`'s own
   lifecycle, not an external process:
   `sub_loop_worktree_attached` fires once at `03:16:34.994Z` (run start),
   `sub_loop_worktree_detached` fires once at `03:57:15.371Z` — immediately
   after (within ~800ms of) the refine subprocess discovering the worktree
   gone. One worktree is attached for the whole run and detached
   unconditionally when the `autodev` sub-loop call returns.
5. That return happened before `FEAT-2122`'s dispatched subprocess had
   finished: `autodev`'s `skip_inflight` state itself then errored on the
   now-missing path (`[Errno 2] No such file or directory`), and `autodev`
   exited cleanly via its terminal state rather than crashing.
6. Because `autodev` stopped there, the third queued issue `ENH-1722` was
   never even dequeued — it sat untouched in `autodev-queue.txt`, reported by
   the finalize script as "abandoned" rather than "attempted."

Net run result (`summary.json`): `verdict=incomplete-abandoned, closed=1,
inflight_unresolved=1, abandoned=1, parked_rate=0.6667`. No data was lost —
`FEAT-2122`'s refine session hadn't written any changes yet — but the batch
terminated early and left two of three dispatched issues parked.

## Root Cause

`scripts/little_loops/fsm/executor.py`, `FSMExecutor._execute_sub_loop`
(line 914):
<!-- ll-prose-ok: sub_loop_worktree_attached/sub_loop_worktree_detached are event-name string literals passed to self._emit(), not Python def-sites or module-level constants -->
`sub_loop_worktree_attached` is emitted once when the shared
worktree is set up (line 1065), and `_detach()` (removing the worktree via
`worktree_utils.cleanup_worktree`, then emitting
`sub_loop_worktree_detached`) is registered as `detach_worktree` and run
unconditionally in the `finally` block at line 1127, immediately after
`child_result = child_executor.run()` (line 1124) returns. This detach does
not verify that the currently-dispatched issue's action subprocess (e.g. the
`refine-issue` / `manage-issue` Claude invocation `autodev` shells out to)
has actually finished — only that the child `autodev` sub-loop's own FSM
call returned. Whenever `autodev`'s own FSM concludes for any reason while a
dispatched issue's subprocess is still doing work in the shared worktree,
the parent's detach-on-return removes the worktree out from under it.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-01T04:17:10 - `6ed91f4a-37bf-454d-8c78-490c7b5f663f.jsonl`
- `/ll:capture-issue` - 2026-09-01T04:11:01 - `619baadf-ddf4-410d-b209-baf9424402fe.jsonl`
