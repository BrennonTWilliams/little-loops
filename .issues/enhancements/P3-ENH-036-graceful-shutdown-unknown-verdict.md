---
discovered_commit: b0fced8
discovered_date: 2026-01-13
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# ENH-036: Graceful shutdown: workers report UNKNOWN when interrupted during ready_issue

## Summary

When ll-parallel receives a signal interrupt (e.g., Ctrl+C), workers that are mid-operation report failures with `ready_issue verdict: UNKNOWN - No output from ready_issue`. This may be expected behavior, but it could be improved with clearer messaging or a dedicated shutdown state.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 2
**Affected External Issues**: BUG-695, ENH-686

### Sample Log Output

```
^C[15:24:33] Received signal 2, shutting down gracefully...
[15:24:33] Waiting for workers to complete...
[15:24:33] BUG-695 failed: ready_issue verdict: UNKNOWN - No output from ready_issue
[15:24:33] ENH-686 failed: ready_issue verdict: UNKNOWN - No output from ready_issue
[15:24:34] Waiting for pending merges...
```

## Current Behavior

1. User presses Ctrl+C (signal 2)
2. Orchestrator catches signal and initiates graceful shutdown
3. Workers that are in the middle of `ready_issue` operation cannot complete
4. Workers report failure with generic `verdict: UNKNOWN - No output from ready_issue`
5. These appear as failures in the final report even though they were interrupted

## Expected Behavior

Options for improvement:

1. **Dedicated shutdown state**: Introduce a `SHUTDOWN` or `INTERRUPTED` verdict/state that is distinct from failure
2. **Clearer messaging**: Change message to "Interrupted during ready_issue (signal 2)" instead of generic UNKNOWN
3. **Skip reporting interrupted workers**: Don't count interrupted workers as "failed" in the summary
4. **Graceful completion**: Allow workers to finish current operation before shutting down (with timeout)

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/orchestrator.py` (signal handling)
- **Related**: `scripts/little_loops/parallel/worker.py` (worker shutdown behavior)

## Proposed Investigation

1. Review signal handling in `orchestrator.py` to understand shutdown sequence
2. Check if workers receive shutdown signal or just stop when orchestrator stops
3. Determine if workers can be allowed to finish current operation with a timeout
4. Consider adding a dedicated "interrupted" state to distinguish from actual failures

## Impact

- **Severity**: Low (P3) - This is expected behavior on user interrupt, not a tool bug
- **Frequency**: 2 occurrences in single run (both interrupted by same signal)
- **Data Risk**: None - work can be resumed by running ll-parallel again
- **User Experience**: Medium - Users may be confused seeing "failures" that were actually just interrupted

## Reproduction Steps

1. Start ll-parallel with multiple issues
2. Wait for some workers to start processing
3. Press Ctrl+C to interrupt
4. Observe that mid-operation workers report as "failed" with UNKNOWN verdict

---

## Status
**Open** | Created: 2026-01-13 | Priority: P3
