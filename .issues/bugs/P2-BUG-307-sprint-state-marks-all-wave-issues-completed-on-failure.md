---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# BUG-307: Sprint state marks all wave issues as completed even when some fail

## Summary

When a multi-issue wave completes with failures (orchestrator returns exit code 1), `_cmd_sprint_run()` marks ALL issues in the wave as both `completed_issues` AND `failed_issues`. This means issues whose work was never merged appear in `completed_issues`, creating a false record that prevents proper resume and retry.

## Context

Identified from root cause analysis of a sprint failure. FEAT-031's merge was never completed (branch orphaned), but the sprint state listed it in `completed_issues`. This happened because the sprint runner doesn't query the orchestrator for per-issue results — it uses the wave-level exit code and then marks all wave IDs identically.

## Current Behavior

At `cli.py:1979-1986`, when `result != 0`:
```python
# Some issues failed - continue but track failures
failed_waves += 1
completed.update(wave_ids)              # BUG: ALL marked completed
state.completed_issues.extend(wave_ids) # BUG: ALL marked completed
for issue_id in wave_ids:
    state.failed_issues[issue_id] = "Wave execution had failures"
```

Similarly, at `cli.py:1969-1977`, when `result == 0`, ALL wave IDs are marked completed without verifying per-issue merge status.

## Expected Behavior

After a wave completes:
1. Query `orchestrator.queue.completed_ids` for issues that were actually merged
2. Query `orchestrator.queue.failed_ids` for issues that actually failed
3. Only add actually-completed issues to `state.completed_issues`
4. Only add actually-failed issues to `state.failed_issues`
5. Issues that were neither (interrupted, stranded) should remain untracked so they can be retried on resume

## Steps to Reproduce

1. Create a sprint with 3 issues that will conflict (same file, same wave)
2. Run `ll-sprint run <sprint-name>`
3. Some issues merge, some fail due to conflicts
4. Check sprint state file — all issues are in `completed_issues`

## Proposed Solution

Replace the all-or-nothing wave tracking with per-issue tracking from the orchestrator's queue state. The `orchestrator.queue.completed_ids` and `orchestrator.queue.failed_ids` lists contain the accurate per-issue results.

## Impact

- **Priority**: P2
- **Effort**: Small (modify ~20 lines in `_cmd_sprint_run`)
- **Risk**: Low — better accuracy, no new dependencies

## Files

- `scripts/little_loops/cli.py` (lines ~1969-1986 in `_cmd_sprint_run()`)
- `scripts/tests/test_sprint_integration.py` — Add test for per-issue tracking

## Labels

`bug`, `captured`, `sprint`, `state-tracking`

---

## Status

**Open** | Created: 2026-02-09 | Priority: P2
