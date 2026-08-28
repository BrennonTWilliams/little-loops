---
id: BUG-3348
type: BUG
title: _requeue_deferred_issues silently drops issues — queue.add() rejects in_progress ids
priority: P2
status: open
discovered_by: pre-implementation review of ENH-3346
discovered_date: '2026-08-27'
---

# BUG-3348: _requeue_deferred_issues silently drops issues — queue.add() rejects in_progress ids

## Summary

`ParallelOrchestrator._requeue_deferred_issues` (`scripts/little_loops/parallel/orchestrator.py:1296-1314`) re-adds an overlap-deferred issue via `self.queue.add(issue)` (`:1312`). But `IssuePriorityQueue.add()` rejects any id present in `_in_progress` (`scripts/little_loops/parallel/priority_queue.py:62`) — and a deferred issue **is** in `_in_progress`, because the main loop's `queue.get()` (`orchestrator.py:934`) moved it there (`priority_queue.py:106`) before `_process_parallel` deferred it (`orchestrator.py:1036`). So `add()` returns `False`, the issue is popped from `_deferred_issues` anyway (`:1314`), and it never runs — silently dropped, while staying in `_in_progress` forever (skewing `in_progress_count` and any completion accounting).

## Current Behavior

With `serialize_overlapping` enabled, an issue deferred on overlap conflict is never processed: once the overlap clears, `_requeue_deferred_issues` logs "Re-queuing {id} - no longer overlapping" but the `queue.add()` call is a rejected no-op. The issue vanishes from `_deferred_issues` and is stuck in the queue's `_in_progress` set for the rest of the run.

## Expected Behavior

A deferred issue whose overlap clears is actually re-queued and eventually processed.

## Proposed Solution

Call `self.queue.requeue(issue)` instead of `self.queue.add(issue)` in `_requeue_deferred_issues` — `requeue()` (`priority_queue.py:146-167`) already discards the id from `_in_progress`/`_failed`/`_skipped` before re-adding, and exists precisely for this "put an already-claimed issue back" case (it is used today for merge-conflict requeues).

## Why the existing test missed it

`test_orchestrator.py::test_on_worker_complete_requeues_deferred_issues` (`:4532`) mocks the queue, so `add()`'s rejection never fires. The fix should add a test using a **real** `IssuePriorityQueue` that walks the actual sequence: `add` → `get` (moves to in_progress) → defer → requeue-deferred → assert the issue is dequeueable again.

## Impact

- **Priority**: P2 — silent work loss in parallel runs whenever overlap serialization defers an issue
- **Effort**: Small — one-line call-site change plus a real-queue regression test
- **Risk**: Low

## Related Issues

- ENH-3346 depends on this fix: its `parallel.worker_unblocked` event is emitted at this resubmit point and must be gated on the requeue actually succeeding.

## Status

**Open** | Created: 2026-08-27 | Priority: P2
