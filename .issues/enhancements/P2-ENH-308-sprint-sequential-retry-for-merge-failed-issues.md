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

## Motivation

This enhancement would:
- Recover work that is currently lost: merge-failed issues represent completed implementation that just needs rebasing
- Reduce manual intervention: users currently must manually retry failed issues after sprint completion
- Improve sprint completion rates: sequential retry after parallel wave eliminates merge conflicts

## Scope Boundaries

- **In scope**: Automatic sequential retry of merge-failed issues after each parallel wave
- **Out of scope**: Retrying issues that failed for non-merge reasons (implementation errors, test failures)

## Implementation Steps

1. Add retry detection logic after `orchestrator.run()` in `_cmd_sprint_run()`
2. For each merge-failed issue, call `process_issue_inplace()` sequentially
3. Update sprint state tracking (move retried successes from failed to completed)
4. Add logging for retry attempts and outcomes

## Integration Map

### Files to Modify
- `scripts/little_loops/cli.py` - Add retry logic in `_cmd_sprint_run()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` - Reuse `process_issue_inplace()` (no changes needed)

### Similar Patterns
- Single-issue wave processing at `cli.py:2005` already uses `process_issue_inplace()`

### Tests
- `scripts/tests/test_sprint_integration.py` - Test retry behavior

### Documentation
- `docs/COMMANDS.md` — document retry behavior for ll-sprint
- `README.md` — update ll-sprint feature description if retry changes user workflow

### Configuration
- N/A

## Impact

- **Priority**: P2
- **Effort**: Small-Medium
- **Risk**: Low — uses existing `process_issue_inplace()`, retries are sequential

## Blocked By

_None — ENH-344 (cli.py split into package) is now completed._

## Blocks

- ENH-328: ll-auto verify check implementation markers (shared cli.py)
- BUG-403: dependency graph renders empty nodes without edges (shared sprint.py, test_sprint_integration.py)

## Dependencies

- BUG-307: Sprint state per-issue tracking (completed 2026-02-09)

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

- **Verified**: 2026-02-13 (updated from 2026-02-12)
- **Verdict**: NEEDS_UPDATE
- **ENH-344 blocker resolved**: ENH-344 (cli.py split into package) is now completed. `Blocked By` should be marked resolved.
- **File references stale**: All `cli.py` references should now point to `scripts/little_loops/cli/sprint.py`:
  - `_cmd_sprint_run()` is at `cli/sprint.py:688` (not `cli.py` or previous note's 533)
  - Single-issue wave processing is at `cli/sprint.py:851-860` (not `cli.py:2005` or previous note's 698-705)
  - Multi-issue wave processing with failures is at `cli/sprint.py:881-923` (not previous note's 740-767)
- Confirmed: no retry logic for merge-failed issues exists — core enhancement still needed
- Confirmed: `process_issue_inplace()` exists at `issue_manager.py:249` and is available for reuse
- BUG-307 dependency satisfied (completed 2026-02-09)
- BUG-403 (in Blocks) remains open — commit 3d7713c did not fix the bug

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - High-value feature that improves sprint completion rates, but needs updates for stale file references (cli.py → cli/sprint.py) and resolved blocker (ENH-344 completed). Well-designed with clear integration points.
