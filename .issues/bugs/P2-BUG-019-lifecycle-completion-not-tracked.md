---
discovered_commit: 8279174
discovered_date: 2026-01-12
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# BUG-019: Lifecycle completion missing for successfully merged issues

## Summary

Issues that are successfully merged are being reported as "failed" in the final summary because their lifecycle (issue file move to completed/) was never completed. The merge succeeds, but the issue file is not moved, and the issue ID appears in the failed list.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 1
**Affected External Issues**: BUG-642

### Sample Log Output

```
[12:17:01] Processing BUG-642 sequentially (P0)
[12:25:56] Found 2 file(s) changed: ['src/blender_agents/ai/ooda/executor/mixins/execution_mixin.py', 'tests/unit/test_ooda_prompt.py']
[12:25:56] Queued merge for BUG-642 (branch: parallel/bug-642-20260112-121701)
[12:25:56] Processing merge for BUG-642
[12:25:58] Merged BUG-642 successfully

... (no lifecycle completion for BUG-642 anywhere in log) ...

[13:01:47] Failed issues:
[13:01:47]   - BUG-642
```

## Current Behavior

1. BUG-642 is processed sequentially (P0 priority)
2. Work is completed - 2 files changed
3. Merge is queued and processed successfully at 12:25:58
4. No lifecycle completion is performed (no `git mv` for issue file)
5. BUG-642 appears in "Failed issues" list at end of run
6. The work is actually completed and merged, but status reporting is incorrect

## Expected Behavior

1. After successful merge, the issue file should be moved to `completed/`
2. The issue should appear in "Completed" count, not "Failed" count
3. If lifecycle completion can't be performed immediately, it should be queued and completed later (as happens for some issues like ENH-625)

## Affected Components

- **Tool**: ll-parallel
- **Likely Module**: `scripts/little_loops/parallel/orchestrator.py` (lifecycle tracking)
- **Related**: `scripts/little_loops/parallel/merge_coordinator.py` (post-merge processing)
- **Related**: `scripts/little_loops/parallel/worker_pool.py` (worker completion handling)

## Root Cause Analysis

Comparing BUG-642 (missing lifecycle) with ENH-625 (lifecycle completed):

**ENH-625** (lifecycle worked):
```
[12:38:43] ENH-625 completed in 6.6 minutes
[12:38:43] Queued merge for ENH-625 (branch: ...)
...
[13:01:46] Completing lifecycle for ENH-625 (merged but file not moved)
[13:01:47] Completed lifecycle for ENH-625: 67da44a1
```

**BUG-642** (lifecycle missing):
```
[12:25:58] Merged BUG-642 successfully
... (no lifecycle completion ever)
```

The difference may be:
1. BUG-642 was processed **sequentially** (P0 priority), not via worker pool
2. Sequential processing path may not properly track lifecycle completion
3. Or the merge succeeded but the orchestrator lost track of it

## Proposed Investigation

1. Review sequential processing path in `orchestrator.py` vs worker pool path
2. Check how lifecycle completion is queued/tracked for sequential vs parallel issues
3. Verify that merge success triggers lifecycle completion queueing
4. Add logging to trace why BUG-642's lifecycle was never completed

## Proposed Fix

1. Ensure sequential processing path queues lifecycle completion after merge
2. Add a final sweep at end of run to complete any orphaned lifecycles
3. Improve tracking to ensure merged issues are correctly counted as completed

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in single run (affects P0 sequential issues)
- **Data Risk**: Low - work is completed and merged, only reporting is incorrect

## Reproduction Steps

1. Run ll-parallel with a P0 (critical) priority issue
2. The P0 issue will be processed sequentially, not via worker pool
3. Let the issue complete and merge successfully
4. Observe that the issue appears in "Failed" list despite successful merge

---

## Status
**Open** | Created: 2026-01-12 | Priority: P2
