---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# BUG-930: Done / Active Counts Stuck at 0 in Parallel Merge Path

## Summary

In `ll-sprint` parallel runs, the status line shows `Done: 0` and `Active: N` throughout, even after issues successfully merge. The parallel merge path in `_on_worker_complete()` never calls `mark_completed()` or `mark_failed()`, so `PriorityQueue` state is never updated.

## Context

Observed during `ll-sprint run tech-debt-04-26`: ENH-497 and ENH-825 merged successfully but `Done: 0` persisted for the entire run. The sequential (P0) path and `_merge_sequential()` both call `mark_completed()` correctly — the parallel `else` branch does not.

## Root Cause

- **File**: `scripts/little_loops/parallel/orchestrator.py`
- **Anchor**: `_on_worker_complete()`, lines 893–899 (parallel merge branch)
- **Cause**: After `self.merge_coordinator.wait_for_completion(timeout=120)`, neither `self.queue.mark_completed()` nor `self.queue.mark_failed()` is called. `PriorityQueue.mark_completed()` (priority_queue.py:110–118) does `_in_progress.discard(issue_id)` and `_completed.add(issue_id)` — without it, Active never decrements and Done never increments.

## Current Behavior

Status line shows `Done: 0 / Active: N` for the entire sprint run regardless of merge outcomes.

## Expected Behavior

`Done` increments and `Active` decrements each time an issue merges in the parallel path.

## Fix

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

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
