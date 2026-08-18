---
id: BUG-3254
type: BUG
title: ll-parallel counts BLOCKED issues as failed in the queue while recording them
  as skipped, diverging from the sequential path
priority: P3
status: open
testable: true
discovered_by: review
discovered_date: '2026-08-18'
discovered_source: pre-implementation review of BUG-3252/BUG-3253, 2026-08-18
relates_to:
- BUG-3252
- BUG-3253
---

# BUG-3254: ll-parallel counts BLOCKED issues as failed in the queue while recording them as skipped, diverging from the sequential path

## Summary

`ParallelOrchestrator._on_worker_complete` classifies a single BLOCKED-verdict
result two different ways within one function. Its queue-counter dispatch
(`orchestrator.py:1096-1232`) has no `was_blocked` arm, so a BLOCKED result
falls through to the terminal `else: self.queue.mark_failed(...)` at
`orchestrator.py:1229-1232`. Forty lines later the same result is recorded as
`orchestration_status = "skipped"` (`orchestrator.py:1249-1251`) — the function
already knows the outcome is not a failure and says so in the persisted record,
while the counters say the opposite.

The sequential path resolved this: `AutoManager._process_issue` routes
`was_blocked` to `mark_skipped()` (`issue_manager.py:2107-2111`). The parallel
path never got the matching arm.

Separately, `WorkerResult.corrections` is populated only on the success return
(`worker_pool.py:743-744`); every failure return, including BLOCKED
(`worker_pool.py:508-520`), omits it. So a blocked-after-correction issue on the
parallel path is counted in the correction-rate denominator but can never appear
in its numerator — the mirror image of the sequential path's defect.

This was factored out of BUG-3253 during its 2026-08-18 review, which correctly
scoped it out as a distinct defect rather than a variant of the one it was
fixing. BUG-3253 was subsequently cancelled into BUG-3252, so this was left
unowned; filed here to keep it tracked.

## Steps to Reproduce

1. Run `ll-parallel` over a set including an issue whose `/ll:ready-issue` pass
   returns a BLOCKED verdict (open dependency).
2. Observe the run summary's failed count, and the correction rate if any other
   issue was corrected.
3. Compare against the orchestration record for the same issue.

Expected divergence: the issue is `status="skipped"` in the orchestration record
but contributes to `queue.failed_count` and therefore to the summary's failed
tally and its correction-rate denominator.

## Current Behavior

**Queue dispatch — no `was_blocked` arm.** `_on_worker_complete`'s branching
(`orchestrator.py:1096-1232`) covers `should_close` (1096), `success` (1124), and
a terminal `else` (1229):

```python
else:
    self.logger.error(f"{result.issue_id} failed: {result.error}")
    self._worker_errors[result.issue_id] = result.error or "Failed"
    self.queue.mark_failed(result.issue_id)
```

A BLOCKED result has `success=False` and `should_close=False`
(`worker_pool.py:508-520`), so it lands here — logged at `error` level as
"failed", with its BLOCKED verdict string as the error text.

**Orchestration record — correctly classified.** Immediately after, at
`orchestrator.py:1249-1251`:

```python
if result.was_blocked:
    orchestration_status = "skipped"
    orchestration_reason = result.error or recorded_error
```

Both read the same `result`. The field the record consults is the field the
dispatch does not.

**Corrections attached on success only.** `worker_pool.py:743-744` passes
`corrections=corrections` on the success return. The BLOCKED return
(`508-520`), the NOT_READY return, and the exception return all omit it. The
orchestrator's rate (`orchestrator.py:1647-1653`) divides
`len(corrections_snapshot)` by `queue.completed_count + queue.failed_count`
(`priority_queue.py:167,173`), so a corrected-then-blocked issue sits in the
denominator with its corrections discarded.

## Expected Behavior

1. **One classification per outcome.** A BLOCKED result is a skip in the queue
   counters as well as the orchestration record. It should not be logged at
   `error` level as a failure.
2. **Parity with the sequential path.** `issue_manager.py:2107-2111` is the
   reference behavior; the parallel path mirrors it.
3. **Numerator and denominator filtered on the same predicate.** Whatever is
   excluded from `completed_count + failed_count` must also be excluded from
   the corrections snapshot, or the rate can exceed 100% — or divide by zero
   with a nonzero numerator. This invariant is inherited from BUG-3252 Part 4;
   it is the reason the corrections-attachment half cannot be fixed
   independently of the counter half without checking the interaction.

## Impact

- **Severity**: P3 — no data loss, and the persisted orchestration record is
  already correct, so post-hoc analysis over that table is unaffected. The
  live run summary and the counters are what mislead.
- **Frequency**: every `ll-parallel` run containing a BLOCKED-verdict issue.
- **Data Risk**: None.

## Root Cause

The two paths were built separately and are maintained as lockstep-edited
duplicate blocks rather than a shared module, so a fix applied to one does not
propagate. `mark_skipped`-style routing was added to the sequential path
(BUG-3005 precedent) without a parallel counterpart, and `IssuePriorityQueue`
has no skip bucket to route to — it tracks only `completed_count` and
`failed_count` (`priority_queue.py:110-194`), so the arm has nowhere to land
without a queue-side change first.

## Proposed Solution

Not yet designed — the queue-side gap makes this larger than the sequential
fix it mirrors. Sketch:

1. Give `IssuePriorityQueue` a skip concept (a `mark_skipped()` and a
   `skipped_count`, mirroring `ProcessingState.skipped_issues` /
   `StateManager.mark_skipped()` at `state.py:53,221-232`).
2. Add an `elif result.was_blocked:` arm ahead of the terminal `else` at
   `orchestrator.py:1229`, routing there and logging at `info` rather than
   `error`. Reuse the same `result.was_blocked` the record consults at `1249`.
3. Decide the corrections question deliberately: either attach `corrections` to
   the BLOCKED return in `worker_pool.py` (matching the sequential path, which
   passes `corrections=corrections` on its blocked return at
   `issue_manager.py:1068-1075`) *and* exclude blocked issues from the
   denominator, or leave both out. Do not change one half alone.

Whether the summary should surface a skipped count, as the sequential path's
summary also fails to do (`issue_manager.py:1949-1991` renders no
`skipped_issues` block), is a shared gap worth settling once for both paths.

## Program Design

_Preliminary — this issue is filed to keep the defect tracked, not yet designed.
The entries below are the verified call sites a design would have to touch;
`/ll:refine-issue` should complete this section before implementation._

### Types
- `IssuePriorityQueue` — `scripts/little_loops/parallel/priority_queue.py:110-194` — tracks `completed_count` (`:167`) and `failed_count` (`:173`) via `mark_completed()` (`:110`) and `mark_failed()` (`:120`). Has no skip concept; a skip arm has nowhere to land until one is added. Contrast `ProcessingState.skipped_issues: dict[str, str]` (`state.py:53`), which the sequential path already has.
- `WorkerResult` — `scripts/little_loops/parallel/worker_pool.py` — already carries `was_blocked` (set at `:513`) and a corrections field (populated only at `:744`). No new field is needed on it; the defect is in which consumers read them.

### Signatures
- `ParallelOrchestrator._on_worker_complete(self, result: WorkerResult) -> None` — `scripts/little_loops/parallel/orchestrator.py:1071` — contains both halves of the contradiction: the queue-counter dispatch (`1096-1232`, terminal `else` → `mark_failed` at `1229-1232`) and the orchestration-record classification (`1249-1251`, `if result.was_blocked` → `"skipped"`).
- `IssuePriorityQueue.mark_failed(self, issue_id: str) -> None` — `scripts/little_loops/parallel/priority_queue.py:120` — where BLOCKED results wrongly land today.
- `StateManager.mark_skipped(issue_id: str, reason: str) -> None` — `scripts/little_loops/state.py:221-232` — the sequential path's reference implementation, for shape only; it operates on `ProcessingState`, not the queue.

### Call Path
`ll-parallel` worker finishes -> `ParallelOrchestrator._on_worker_complete(result)` (`orchestrator.py:1071`) -> dispatch falls past `should_close` (`:1096`) and `success` (`:1124`) to the terminal `else` (`:1229`) -> `self.queue.mark_failed(result.issue_id)` (`:1232`) -> `queue.failed_count` (`priority_queue.py:173`) -> the run summary's failed tally and the correction-rate denominator at `orchestrator.py:1649`.

The same `result` then reaches `:1249`, where `if result.was_blocked` sets `orchestration_status = "skipped"` for `_record_orchestration_result()` — the divergence this issue reports.

### Decision Rules
- **Fix the queue half and the corrections half together, or neither.** They move the denominator and the numerator of the same rate in opposite directions; changing one alone can push it above 100% or produce `N/0`. Inherited from BUG-3252 Part 4's symmetry invariant.
- **Reuse `result.was_blocked`, do not introduce a new signal.** The field already exists, is already set by `worker_pool.py:513`, and is already consulted forty lines below the dispatch that ignores it.
- **The sequential path is the reference, not the implementation.** `issue_manager.py:2107-2111` establishes the intended behavior; its `mark_skipped`/`skipped_issues` mechanism operates on `ProcessingState` and cannot be lifted into `IssuePriorityQueue` unchanged.

## Related Issues

- BUG-3252 — the sequential-path equivalent of the classification half, plus the
  correction-rate denominator fix. Establishes the `was_gated`/`mark_skipped`
  routing pattern and the numerator/denominator symmetry invariant this issue
  inherits. Explicitly scoped to exclude the parallel path.
- BUG-3253 — cancelled into BUG-3252. Its Behavior Parity analysis of the three
  run paths, and its Codebase Research Findings on the parallel path's
  divergences, are the origin of this issue.

## Related Key Documentation

- `scripts/little_loops/state.py:32-34` — auto-corrections are tracked as a
  quality signal, the reason the rate's accuracy matters.

## Status

**Open** | Created: 2026-08-18 | Priority: P3

## Session Log
- filed from pre-implementation review - 2026-08-18 - factored out of BUG-3253 before its cancellation into BUG-3252; claims verified against `orchestrator.py:1096-1251`, `worker_pool.py:508-520,743-744`, `priority_queue.py:110-194`
