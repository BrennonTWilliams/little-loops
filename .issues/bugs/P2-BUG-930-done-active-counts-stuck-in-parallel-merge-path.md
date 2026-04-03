---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# BUG-930: Done / Active Counts Stuck at 0 in Parallel Merge Path

## Summary

In `ll-sprint` parallel runs, the status line shows `Done: 0` and `Active: N` throughout, even after issues successfully merge. The parallel merge path in `_on_worker_complete()` never calls `mark_completed()` or `mark_failed()`, so `PriorityQueue` state is never updated.

## Context

Observed during `ll-sprint run tech-debt-04-26`: ENH-497 and ENH-825 merged successfully but `Done: 0` persisted for the entire run. The sequential (P0) path and `_merge_sequential()` both call `mark_completed()` correctly — the parallel `else` branch does not.

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` with 2+ issues and `max_workers >= 2`
2. Monitor the status line during the run
3. Observe `Done: 0` and `Active: N` throughout — even after issues successfully merge
4. After the run completes, confirm `Done: 0` never incremented despite successful merges

## Root Cause

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Anchor**: `_on_worker_complete()`, lines 893–899 (parallel merge branch)
- **Cause**: After `self.merge_coordinator.wait_for_completion(timeout=120)`, neither `self.queue.mark_completed()` nor `self.queue.mark_failed()` is called. `PriorityQueue.mark_completed()` (priority_queue.py:110–118) does `_in_progress.discard(issue_id)` and `_completed.add(issue_id)` — without it, Active never decrements and Done never increments.

## Current Behavior

Status line shows `Done: 0 / Active: N` for the entire sprint run regardless of merge outcomes.

## Expected Behavior

`Done` increments and `Active` decrements each time an issue merges in the parallel path.

## Proposed Solution

After `wait_for_completion()`, mirror the `_merge_sequential()` pattern:

```python
else:
    self.merge_coordinator.queue_merge(result)
    self.merge_coordinator.wait_for_completion(timeout=120)
    if result.issue_id in self.merge_coordinator.merged_ids:
        self.queue.mark_completed(result.issue_id)
        self._complete_issue_lifecycle_if_needed(result.issue_id)
    else:
        self.queue.mark_failed(result.issue_id)
```

## Implementation Steps

1. Open `scripts/little_loops/parallel/orchestrator.py`
2. Locate `_on_worker_complete()` parallel merge branch (after `wait_for_completion` call, ~line 899)
3. Add the `if result.issue_id in self.merge_coordinator.merged_ids:` block as shown above
4. Verify the feature-branch path (lines 886–892) already calls `mark_completed()` — do not touch it
5. Run tests: `python -m pytest scripts/tests/ -v -k "sprint or parallel or worktree or merge"`

## Verification

- Run a 2-issue sprint with `max_workers=2`
- Confirm `Done: N` increments as each issue merges
- Confirm `Active: N` decrements correspondingly
- No regression in sequential (P0) or feature-branch merge paths

## Motivation

Sprint operators monitoring `ll-sprint run` cannot track real progress because `Done: 0` persists for the entire run. This makes it impossible to estimate time remaining, detect stalls, or confirm merges are succeeding — reducing trust in the automation.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete()` parallel merge branch (~line 899)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/priority_queue.py` — `mark_completed()` (lines 110–118), `mark_failed()` called by fix

### Similar Patterns
- `scripts/little_loops/parallel/orchestrator.py:975–979` — `_merge_sequential()` checks `if result.issue_id in self.merge_coordinator.merged_ids: self.queue.mark_completed(result.issue_id)` else `self.queue.mark_failed(result.issue_id)` — exact pattern to mirror
- `scripts/little_loops/parallel/orchestrator.py:889–890` — feature-branch path calls `self.queue.mark_completed(result.issue_id)` then `self._complete_issue_lifecycle_if_needed(result.issue_id)` immediately after the success condition

### Tests
- `scripts/tests/test_orchestrator.py:1233` — `test_on_worker_complete_success` in `TestOnWorkerComplete` — currently asserts `queue_merge` is called but does NOT assert `mark_completed`; this is the test to extend
- `scripts/tests/test_orchestrator.py:1363` — `test_on_worker_complete_waits_for_merge` — asserts `wait_for_completion` ordering but not `mark_completed`; should also be updated
- `python -m pytest scripts/tests/ -v -k "sprint or parallel or worktree or merge"`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — Misleading status display undermines sprint monitoring; confirmed in `ll-sprint run tech-debt-04-26`
- **Effort**: Small — One-line fix adding `mark_completed()` call in the parallel merge branch; mirrors existing pattern in `_merge_sequential()`
- **Risk**: Low — Only affects status counters; no effect on actual merge logic or issue completion
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `parallel`, `status-tracking`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P2

## Verification Notes

**Verdict**: VALID — Re-verified 2026-04-03

- `scripts/little_loops/parallel/orchestrator.py` `_on_worker_complete()` parallel merge branch confirmed: `queue_merge(result)` at line 894, `wait_for_completion(timeout=120)` at line 899 — NO `mark_completed()` or `mark_failed()` call after wait ✓
- Sequential path (`mark_completed` at line 868) and feature-branch path (line 889) both call `mark_completed()` correctly ✓
- `PriorityQueue.mark_completed()` exists at `priority_queue.py` and is not called in the parallel merge branch ✓
- Note: `_wait_for_completion()` at lines 1003–1009 does call `mark_completed` for all `merged_ids` at end-of-run, but this is only after all workers finish — Done remains 0 throughout active parallel execution ✓
- Bug accurately describes the stuck `Done: 0` counter issue

## Session Log
- `/ll:verify-issues` - 2026-04-03T05:17:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b45ed298-5c0e-4210-81fa-321bbdd0f5d6.jsonl`
- `/ll:refine-issue` - 2026-04-03T05:00:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c6eb14c-ae28-48b5-a6c5-331e0ce26f1f.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/677939b4-0616-4d61-b3ac-9611ab44a683.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
