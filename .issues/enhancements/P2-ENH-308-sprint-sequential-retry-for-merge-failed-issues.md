---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-308: Add immediate sequential retry for merge-failed issues in sprint

## Summary

When issues fail due to merge conflicts during a parallel wave, the sprint currently just marks them as failed and moves on. Add automatic sequential retry — immediately after a wave completes with failures, retry the failed issues one at a time using `process_issue_inplace()`. This must happen before the next wave, since later waves may depend on the current wave's issues being on main.

## Context

Identified from root cause analysis of a sprint failure. FEAT-031 failed due to merge conflict and was never retried. ENH-032 and ENH-033 also initially failed but were manually retried sequentially and succeeded. This retry pattern should be automated.

The `process_issue_inplace()` function already exists in `issue_manager.py` and handles single-issue processing in the working tree (no worktree overhead). The sprint runner already uses it for single-issue waves at `cli.py:2005`.

## Current Behavior

1. Multi-issue wave executes via `ParallelOrchestrator`
2. Some issues fail due to merge conflicts
3. Sprint marks them as failed and proceeds to next wave
4. Failed issues are never retried

## Expected Behavior

1. Multi-issue wave executes via `ParallelOrchestrator`
2. After wave completes, query orchestrator for per-issue results (per BUG-307 fix)
3. For each failed issue, log that a sequential retry is being attempted
4. Retry each failed issue using `process_issue_inplace()` (sequential, no merge conflicts possible)
5. If retry succeeds, move issue from `failed_issues` to `completed_issues`
6. If retry also fails, keep as failed
7. Proceed to next wave only after all retries complete

## Proposed Solution

In `_cmd_sprint_run()`, after the multi-issue wave block, add retry logic:

```python
# After orchestrator.run() returns with failures:
failed_ids = set(orchestrator.queue.failed_ids)
if failed_ids:
    logger.info(f"Retrying {len(failed_ids)} failed issue(s) sequentially...")
    for issue in wave:
        if issue.issue_id in failed_ids:
            retry_result = process_issue_inplace(issue, config, logger, dry_run)
            if retry_result.success:
                # Move from failed to completed
                state.completed_issues.append(issue.issue_id)
                state.failed_issues.pop(issue.issue_id, None)
```

## Impact

- **Priority**: P2
- **Effort**: Small-Medium
- **Risk**: Low — uses existing `process_issue_inplace()`, retries are sequential

## Dependencies

- BUG-307: Sprint state per-issue tracking (needed to identify which issues failed)

## Files

- `scripts/little_loops/cli.py` — Add retry logic in `_cmd_sprint_run()`
- `scripts/little_loops/issue_manager.py` — Reuse `process_issue_inplace()` (no changes needed)
- `scripts/tests/test_sprint_integration.py` — Test retry behavior

## Labels

`enhancement`, `captured`, `sprint`, `retry`

---

## Status

**Open** | Created: 2026-02-09 | Priority: P2

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID (after update)
- Fixed line reference: `process_issue_inplace()` used at `cli.py:2005`, not 1927
- Confirmed: no retry logic for merge-failed issues exists in `_cmd_sprint_run()`
- Confirmed: `process_issue_inplace()` exists at `issue_manager.py:248` and is available for reuse
- BUG-307 dependency satisfied (completed 2026-02-09)
