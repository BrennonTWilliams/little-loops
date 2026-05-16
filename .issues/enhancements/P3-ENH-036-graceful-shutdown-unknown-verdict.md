---
discovered_commit: b0fced8
discovered_date: 2026-01-13
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# ENH-036: Graceful shutdown: workers report UNKNOWN when interrupted during ready_issue

## Summary

When ll-parallel receives a signal interrupt (e.g., Ctrl+C), workers that are mid-operation report failures with `ready_issue verdict: UNKNOWN - No output from ready_issue`. This may be expected behavior, but it could be improved with clearer messaging or a dedicated shutdown state.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `<external-repo>`
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
- **Likely Module**: `scripts/little_loops/parallel/orchestrator.py` (signal handling, lines 122-132)
- **Related**: `scripts/little_loops/parallel/worker_pool.py` (worker shutdown behavior, UNKNOWN verdict handling at lines 261-277)
- **Related**: `scripts/little_loops/parallel/output_parsing.py` (verdict parsing, UNKNOWN fallback)

## Proposed Solution

Based on code review, the implementation should:

1. **Add INTERRUPTED verdict to output_parsing.py** - New verdict type alongside READY/CORRECTED/NOT_READY/CLOSE/UNKNOWN
2. **Detect interruption in worker_pool.py** - When process is killed during ready_issue, detect via signal/exit code and return INTERRUPTED instead of UNKNOWN
3. **Update orchestrator.py signal handler** - Set a shutdown flag that workers can check
4. **Modify result reporting** - Don't count INTERRUPTED as failures in the final summary; show them separately as "Interrupted (can retry)"

Key files to modify:
- `scripts/little_loops/parallel/output_parsing.py` - Add INTERRUPTED verdict string alongside existing verdicts (READY/CORRECTED/NOT_READY/CLOSE/UNKNOWN)
- `scripts/little_loops/parallel/worker_pool.py` - Detect interruption via exit code or shutdown flag, return INTERRUPTED instead of UNKNOWN
- `scripts/little_loops/parallel/orchestrator.py` - Propagate shutdown flag to workers; update result summary to show INTERRUPTED separately from failures

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
**Completed** | Created: 2026-01-13 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-13
- **Status**: Completed

### Changes Made

1. **types.py**: Added `interrupted` boolean field to `WorkerResult` dataclass
   - Defaults to `False`
   - Serialized in `to_dict()` and deserialized in `from_dict()`

2. **worker_pool.py**: Added shutdown state tracking and interrupted detection
   - Added `_shutdown_requested` flag and `_terminated_during_shutdown` set
   - Added `set_shutdown_requested()` method for orchestrator to call
   - Updated `terminate_all_processes()` to track issues terminated during shutdown
   - Added interrupted checks after both `ready_issue` and `manage_issue` commands
   - Returns `WorkerResult(interrupted=True)` for workers killed during shutdown

3. **orchestrator.py**: Propagated shutdown flag and updated result handling
   - Signal handler now calls `worker_pool.set_shutdown_requested(True)`
   - Added `_interrupted_issues` tracking list
   - Updated `_on_worker_complete()` to handle interrupted workers specially (not counted as failed)
   - Updated `_report_results()` to show interrupted count separately from failures

4. **Tests added**:
   - `TestWorkerResult`: Tests for `interrupted` field defaults and serialization
   - `TestWorkerPoolShutdownFlag`: Tests for `set_shutdown_requested()`
   - `TestWorkerPoolTerminateProcesses`: Tests for shutdown tracking during termination
   - `TestSignalHandlers`: Test for shutdown propagation to worker pool

### Verification Results
- Tests: PASS (744 passed)
- Lint: PASS (ruff check)
- Types: PASS (mypy)

### Implementation Notes

The solution uses the `interrupted` flag on `WorkerResult` rather than adding a new verdict type to avoid changing the parsing layer. The key insight is that interruption is detected at the worker level (via the `_terminated_during_shutdown` set) rather than at the parsing level, since a killed subprocess produces no output to parse.

Now when users press Ctrl+C:
1. Workers mid-operation are tracked as "terminated during shutdown"
2. When they complete (with empty/partial output), they return `WorkerResult(interrupted=True)`
3. The orchestrator logs "BUG-001 was interrupted during shutdown (can retry)"
4. The final report shows "Interrupted: N (can retry)" separately from "Failed: N"
