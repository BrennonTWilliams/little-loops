---
discovered_date: "2026-04-18"
discovered_by: capture-issue
depends_on: [FEAT-1075, FEAT-1076, FEAT-1174]
---

# ENH-1165: Signal Handler Cannot Reach Parallel Worker Threads

> **Partially superseded by FEAT-1076.** 2026-04-20: Option B (`ThreadPoolExecutor.shutdown(wait=False, cancel_futures=True)` in `try/finally`) was folded into FEAT-1076 as an acceptance criterion ("Signal cancellation — folded from ENH-1165 Option B"). Option A — full per-worker cancellation via a shared `threading.Event` checked between worker state transitions — remains deferred as a post-v1 resilience follow-up. Re-promote to the active queue only if Option B proves insufficient in production.

## Summary

`_helpers.py`'s signal handler kills subprocess via `FSMExecutor._current_process`, but `ParallelRunner`'s `ThreadPoolExecutor` worker threads are unreachable via this mechanism. Ctrl-C or SIGTERM during parallel execution leaves workers running to completion with no cancellation.

## Current Behavior

`cli/loop/_helpers.py:56-66` registers a signal handler that calls `FSMExecutor._current_process.kill()` to terminate a running shell action subprocess. `ParallelRunner` (FEAT-1075) creates a `ThreadPoolExecutor` and submits per-item futures — these are Python threads, not subprocesses tracked by `_current_process`. When the user sends SIGTERM/SIGINT during parallel execution, the signal handler fires but has nothing to kill; workers continue until naturally complete or until the main process dies and the thread pool is forcibly reaped by the OS.

## Expected Behavior

A SIGINT/SIGTERM received while `_execute_parallel_state()` is running should:
1. Cancel pending futures (items not yet started): `executor.shutdown(wait=False, cancel_futures=True)` (Python 3.9+)
2. Signal already-running worker threads to stop early via a shared `threading.Event` checked between FSM state transitions
3. Propagate the interrupt to any subprocess spawned inside worker threads (the same `_current_process` mechanism, applied per-worker)

Minimum acceptable: pending futures are cancelled; running workers complete their current state before stopping.

## Motivation

Parallel loops may fan out over many items for extended durations (e.g., `recursive-refine` over 10 issues at 4 workers). Without graceful cancellation, a user who decides to abort mid-run has no recourse — the process must be SIGKILL'd, leaving worktree branches and issue files in inconsistent states. This is especially risky in worktree isolation mode where merge-back has not yet occurred.

## Proposed Solution

**Option A (recommended) — cancellation event passed to ParallelRunner:**

Add an optional `cancellation_event: threading.Event | None = None` parameter to `ParallelRunner.run()`. `FSMExecutor` creates the event when constructing `ParallelRunner` and stores it as `self._parallel_cancel_event`. The signal handler in `_helpers.py` sets the event when triggered. Workers check the event between sub-loop states (hook into `FSMExecutor`'s event callback).

**Option B (simpler, less complete) — cancel pending futures only:**

Wrap `ThreadPoolExecutor.shutdown(wait=False, cancel_futures=True)` in a try/finally in `_execute_parallel_state()`. Only pending (not-yet-started) futures are cancelled; running workers are unaffected. No signal handler changes needed.

Option B is acceptable as a first step; Option A provides full cancellation but requires more plumbing.

## Implementation Steps

1. (Option B minimum) In `_execute_parallel_state()`, wrap the `runner.run()` call in `try/finally`: on `KeyboardInterrupt` or signal, call `executor.shutdown(wait=False, cancel_futures=True)` before re-raising
2. (Option A full) Add `cancellation_event` param to `ParallelRunner.run()`; wire from `FSMExecutor` via signal handler; check event in worker between states
3. Add test: mock `ThreadPoolExecutor`, assert `shutdown(cancel_futures=True)` called on `KeyboardInterrupt`
4. Document known limitation (running workers are not interrupted mid-state) in `docs/generalized-fsm-loop.md` parallel section

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/parallel_runner.py` — add cancellation_event param (Option A) or rely on KeyboardInterrupt propagation (Option B)
- `scripts/little_loops/fsm/executor.py` — wrap `_execute_parallel_state()` with cleanup on interrupt
- `scripts/little_loops/cli/loop/_helpers.py:56-66` — optionally extend signal handler to reach `FSMExecutor._parallel_cancel_event`

### Noted in FEAT-1076
FEAT-1076 explicitly documents this as a known limitation: "`ParallelRunner` worker threads are not reachable via this mechanism — out of scope for this issue."

## Acceptance Criteria

- Ctrl-C during parallel execution cancels pending futures (items not yet started)
- Worktrees are cleaned up (teardown called) for futures that were cancelled before starting
- Running workers are not abruptly killed mid-state (they complete their current state)
- Test covers the cancellation path

## Impact

- **Priority**: P2 — **Must ship with FEAT-1076 (Option B minimum).** Parallel loops fan out for extended durations; without at least cancellation of pending futures, Ctrl-C during a run leaves workers running to completion and forces users to SIGKILL the process — leaving worktree branches and issue files in inconsistent states (especially risky in `isolation: worktree` before merge-back). Graceful abort is table stakes for production, and uncancellable worker threads are a regression vs. today's sequential loops (where the signal handler does reach the running subprocess).
- **Effort**: Small (Option B — required for ship) to Medium (Option A — can land as a follow-up)
- **Risk**: Low — Additive; existing sequential loop behavior unaffected
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `signal`, `cancellation`

---

## Session Log
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`
- `/ll:capture-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ff9cd96-1544-4ffa-b28c-15aab5e9f3e8.jsonl`

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted from P3 on 2026-04-18 — Option B is a blocker for FEAT-1076 ship; Option A may land as follow-up)

## Ship Bundling

**Option B (cancel pending futures on `KeyboardInterrupt`) must land in the same release as FEAT-1076.** This is a ~10-line `try/finally` around `runner.run()` in `_execute_parallel_state()` — trivial to bundle, and avoids shipping a parallel feature with strictly worse cancellation behavior than the sequential one it replaces. Option A (full per-worker cancellation via shared `threading.Event`) is the right long-term fix but can land as a follow-up once the runner API is stable.
