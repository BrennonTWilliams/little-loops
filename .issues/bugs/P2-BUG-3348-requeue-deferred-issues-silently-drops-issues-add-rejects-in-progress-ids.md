---
id: BUG-3348
type: BUG
title: "_requeue_deferred_issues silently drops issues \u2014 queue.add() rejects\
  \ in_progress ids"
priority: P2
status: open
discovered_by: pre-implementation review of ENH-3346
discovered_date: '2026-08-27'
confidence_score: 100
outcome_confidence: 90
score_complexity: 24
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 24
---

# BUG-3348: _requeue_deferred_issues silently drops issues — queue.add() rejects in_progress ids

## Summary

`ParallelOrchestrator._requeue_deferred_issues` (`scripts/little_loops/parallel/orchestrator.py:1296-1314`) re-adds an overlap-deferred issue via `self.queue.add(issue)` (`:1312`). But `IssuePriorityQueue.add()` rejects any id present in `_in_progress` (`scripts/little_loops/parallel/priority_queue.py:62`) — and a deferred issue **is** in `_in_progress`, because the main loop's `queue.get()` (`orchestrator.py:934`) moved it there (`priority_queue.py:106`) before `_process_parallel` deferred it (`orchestrator.py:1036`). So `add()` returns `False`, the issue is popped from `_deferred_issues` anyway (`:1314`), and it never runs — silently dropped, while staying in `_in_progress` forever (skewing `in_progress_count` and any completion accounting).

## Current Behavior

With `serialize_overlapping` enabled, an issue deferred on overlap conflict is never processed: once the overlap clears, `_requeue_deferred_issues` logs "Re-queuing {id} - no longer overlapping" but the `queue.add()` call is a rejected no-op. The issue vanishes from `_deferred_issues` and is stuck in the queue's `_in_progress` set for the rest of the run.

## Expected Behavior

A deferred issue whose overlap clears is actually re-queued and eventually processed.

## Steps to Reproduce

1. Run `ll-parallel` (or the `ParallelOrchestrator` API directly) with `parallel.serialize_overlapping` enabled and at least two issues whose file scopes overlap.
2. Let the queue dequeue the overlapping issue via `queue.get()` (`orchestrator.py:934`), which moves its id into `IssuePriorityQueue._in_progress` (`priority_queue.py:106`).
3. Let `_process_parallel` detect the overlap and defer it into `self._deferred_issues` (`orchestrator.py:1036`) without clearing `_in_progress`.
4. Wait for the overlapping worker to finish so the overlap clears, triggering `_on_worker_complete` -> `_requeue_deferred_issues` (`orchestrator.py:1087,1296`).
5. Observe: `self.queue.add(issue)` (`orchestrator.py:1312`) returns `False` because the id is still in `_in_progress` (`priority_queue.py:62`); the issue is dropped from `_deferred_issues` regardless (`:1314`) and never runs, while its id remains stuck in `_in_progress` for the rest of the run.

## Proposed Solution

Call `self.queue.requeue(issue)` instead of `self.queue.add(issue)` in `_requeue_deferred_issues` — `requeue()` (`priority_queue.py:146-167`) already discards the id from `_in_progress`/`_failed`/`_skipped` before re-adding, and exists precisely for this "put an already-claimed issue back" case (it is used today for merge-conflict requeues).

## Why the existing test missed it

`test_orchestrator.py::test_on_worker_complete_requeues_deferred_issues` (`:4532`) mocks the queue, so `add()`'s rejection never fires. The fix should add a test using a **real** `IssuePriorityQueue` that walks the actual sequence: `add` → `get` (moves to in_progress) → defer → requeue-deferred → assert the issue is dequeueable again. The test should also assert `in_progress_count` returns to its expected value after the requeue — that is the accounting skew described in the Summary, and it is cheap to cover in the same walk.

## Known Interactions (verified during review, 2026-08-28)

- **`max_issues` double-count (out of scope — do not fix here, just be aware):** the main loop increments `issues_processed` at `orchestrator.py:944` when an issue is first dequeued, even if `_process_parallel` immediately defers it. Post-fix, the requeued issue is dequeued and counted a second time, so a deferred-then-requeued issue consumes two slots of `parallel.max_issues` (`orchestrator.py:928`). Pre-existing behavior; this fix merely makes the requeue path live. Do not address it in this change.
- **Completion-check race: verified non-issue.** The scenario "last worker finishes → main loop sees `queue.empty() and active_count == 0` (`orchestrator.py:922`) and exits before the callback requeues the deferred issue" cannot happen: `WorkerPool.active_count` (`worker_pool.py:1992-2002`) counts futures that are done but whose completion callbacks are still running (`_pending_callbacks`), so the loop stays alive until `_on_worker_complete` — and therefore `_requeue_deferred_issues` — has completed. No extra synchronization is needed.

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py:1312` — the `self.queue.add(issue)` call inside `_requeue_deferred_issues`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py:1087` — `_on_worker_complete` is the sole caller of `_requeue_deferred_issues`
- `scripts/little_loops/parallel/orchestrator.py:32`, `scripts/little_loops/parallel/__init__.py:21`, `scripts/tests/test_priority_queue.py:24` — importers of `priority_queue.py`

### Conventions in Force
- `IssuePriorityQueue.requeue()` (`priority_queue.py:146-167`) unconditionally discards the id from `_in_progress`/`_failed`/`_skipped` before re-enqueuing, and has no rejection path (returns `None`) — evidence: `priority_queue.py:154-156`.
- No production call site currently invokes `self.queue.requeue(...)` anywhere in `orchestrator.py` — the issue's Proposed Solution claim that `requeue()` "is used today for merge-conflict requeues" does not hold; the only other requeue-like mechanism in the codebase is `MergeCoordinator._queue.put(...)` (`merge_coordinator.py`, exercised by `test_merge_coordinator.py:1284-1298,1352-1399`), a distinct plain queue on a different object, not `IssuePriorityQueue.requeue()`. `requeue()`'s only current callers are its own direct unit tests in `test_priority_queue.py` (lines 394, 404, 413, 424, 435, 448, 488).
- `requeue()`'s `demote_priority` parameter (default `False`) has zero production call sites passing `True` — no existing convention establishes whether this call site should demote priority. Since an overlap-deferred issue was never actually attempted/failed (only held back pending overlap clearance), there is no existing signal in `_requeue_deferred_issues` that maps to "demote."

### Tests
- `scripts/tests/test_orchestrator.py:4532` — `test_on_worker_complete_requeues_deferred_issues`. The shared `orchestrator` fixture (`test_orchestrator.py:123-138`) patches `IssuePriorityQueue` entirely, so `orchestrator.queue` is a `MagicMock`; the test only asserts `orchestrator.queue.add.assert_called_once_with(mock_deferred)`, which passes regardless of the real queue's `_in_progress` rejection behavior. This is why the defect was missed.
- `scripts/tests/test_priority_queue.py:184-191` — `test_add_in_progress_returns_false` exercises the exact rejection mechanics (`add()` after `get()` returns `False`) against a real, unmocked `IssuePriorityQueue`.
- `scripts/tests/test_priority_queue.py:388-499` — the real-queue state-transition pattern for `requeue()`: `queue.add(sample_issue)` → `queue.get()` → (optional `mark_failed`/`mark_skipped`) → `queue.requeue(sample_issue)` → assert on bucket membership/count. No existing test in this range calls through `orchestrator._requeue_deferred_issues` itself — they test `IssuePriorityQueue` in isolation, not the orchestrator call site.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:4560` — `orchestrator.queue.add.assert_called_once_with(mock_deferred)` inside `test_on_worker_complete_requeues_deferred_issues` will fail once the call site changes to `queue.requeue(issue)`; update this assertion (to `orchestrator.queue.requeue.assert_called_once_with(mock_deferred)` or equivalent) in the same change, not just via a new supplementary test.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4115` — the `IssuePriorityQueue.requeue()` table row is documented as "clears it from the failed and skipped buckets," omitting that it also clears `_in_progress` — the exact behavior this fix newly depends on in production. Update the row to mention `_in_progress` alongside `failed`/`skipped`.

## Program Design

### Codebase Research Findings

### Signatures
- `IssuePriorityQueue.add(self, issue: IssueInfo) -> bool` (`priority_queue.py:50`) — existing, rejects if id in `_queued`/`_in_progress`/`_completed`/`_failed`
- `IssuePriorityQueue.requeue(self, issue: IssueInfo, demote_priority: bool = False) -> None` (`priority_queue.py:146`) — existing, unconditionally clears `_in_progress`/`_failed`/`_skipped` before re-enqueuing
- `ParallelOrchestrator._requeue_deferred_issues(self) -> None` (`orchestrator.py:1296`) — existing method whose body changes at the call site (`orchestrator.py:1312`)

### Call Path
`ParallelOrchestrator._on_worker_complete` (`orchestrator.py:1087`) -> `ParallelOrchestrator._requeue_deferred_issues` (`orchestrator.py:1296`) -> `IssuePriorityQueue.requeue` (`priority_queue.py:146`, replacing the current `IssuePriorityQueue.add` call at `orchestrator.py:1312`)

### Decision Rules
N/A — no new decision logic; this issue swaps one existing queue method call for another existing one at a single call site.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

1. The re-add call at `orchestrator.py:1312` uses a queue method that succeeds even though the deferred issue's id is still in `IssuePriorityQueue._in_progress` — `requeue()` (`priority_queue.py:146-167`) is the existing method built for this exact "re-add an already-claimed id" case, and it never rejects.
2. The overlap-cleared deferred issue is dequeueable again after resubmission — verified by a test that walks a real (unmocked) `IssuePriorityQueue` through `add` → `get` (moves to `_in_progress`) → defer (append to `_deferred_issues`, per current `_process_parallel` behavior) → the fixed `_requeue_deferred_issues` → assert the issue is present in the queue, absent from `_in_progress`, and that `in_progress_count` has returned to its expected value. `test_orchestrator.py`'s existing `orchestrator` fixture (`:123-138`) mocks `IssuePriorityQueue` entirely, so this coverage cannot reuse that fixture as-is for the assertion that matters (see `test_priority_queue.py:388-499` for the real-queue pattern this test should follow).
3. `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_priority_queue.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_orchestrator.py:4560` — change `orchestrator.queue.add.assert_called_once_with(mock_deferred)` to assert on `requeue` instead, or the existing test will fail once the call site changes
- Update `docs/reference/API.md:4115` — mention that `requeue()` also clears `_in_progress`, not just `failed`/`skipped`

## Impact

- **Priority**: P2 — silent work loss in parallel runs whenever overlap serialization defers an issue
- **Effort**: Small — one-line call-site change plus a real-queue regression test
- **Risk**: Low

## Related Issues

- ENH-3346 depends on this fix: its `parallel.worker_unblocked` event is emitted at this resubmit point and must be gated on the requeue actually succeeding.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Anchor**: `ParallelOrchestrator._requeue_deferred_issues` (lines 1296-1314), called from `_on_worker_complete` (line 1087) — this is its only caller
- **Cause**: `queue.get()` (`orchestrator.py:934`, delegating to `priority_queue.py:92-109`) moves the issue's id into `IssuePriorityQueue._in_progress` (`priority_queue.py:106`) at initial dequeue. When `_process_parallel` (`orchestrator.py:1021-1047`) detects an overlap, it appends the issue to `self._deferred_issues` (`orchestrator.py:1036`) and returns — nothing in that path calls `mark_completed`/`mark_failed`/`mark_skipped`/`requeue` to clear the id from `_in_progress`, so it stays there.
- When the overlap later clears, `_requeue_deferred_issues` calls `self.queue.add(issue)` (`orchestrator.py:1312`) with **no check of the boolean return value**. `IssuePriorityQueue.add()` (`priority_queue.py:50-75`) rejects any id already in `_in_progress` (`priority_queue.py:62`) and returns `False` without enqueuing. Because the deferred issue is never re-appended to the loop's local `still_deferred` list, `self._deferred_issues = still_deferred` (`orchestrator.py:1314`) drops it unconditionally — regardless of whether `add()` succeeded. The issue ends up absent from both the queue and `_deferred_issues`, while its id remains in `_in_progress` for the rest of the run, permanently skewing `in_progress_count` and the run's completion check (`self.queue.empty() and self.worker_pool.active_count == 0`, `orchestrator.py:922`).


## Session Log
- `/ll:confidence-check` - 2026-08-28T00:36:37 - `9ec5f3ec-b4d2-4b79-b4c8-e01cc64d4578.jsonl`
- `/ll:wire-issue` - 2026-08-28T00:33:50 - `52578ca5-b353-4a6a-84db-a98fe4dd673c.jsonl`
- `/ll:format-issue` - 2026-08-28T00:28:41 - `a9c9f3c5-52b9-439c-83a8-f6c0aaa9f64f.jsonl`
- `/ll:refine-issue` - 2026-08-28T00:19:19 - `d1beae10-4eb8-49b3-9178-351e6ef08d8b.jsonl`
