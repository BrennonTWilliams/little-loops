---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-236: Spawned process never tracked or reaped in handoff handler

## Summary

The `HandoffHandler._spawn_continuation` creates a subprocess via `subprocess.Popen` but the returned process is never waited on by calling code, creating potential zombie processes. The process output also goes directly to the parent terminal with no capture or tracking.

## Location

- **File**: `scripts/little_loops/fsm/handoff_handler.py`
- **Line(s)**: 114-115 (at scan commit: a8f4144)
- **Anchor**: `in method HandoffHandler._spawn_continuation`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/fsm/handoff_handler.py#L114-L115)
- **Code**:
```python
cmd = ["claude", "-p", prompt]
return subprocess.Popen(cmd, text=True)
```

## Current Behavior

The spawned process is returned as `HandoffResult.spawned_process` but the calling code in `fsm/executor.py` does not wait on or track this process. It becomes a zombie after termination. There is no mechanism to check success or failure.

## Expected Behavior

The spawned continuation should be properly tracked, with its exit status collected via `process.wait()` or `process.communicate()`. Optionally, output should be captured for logging.

## Proposed Solution

Either wait on the process in the executor, or detach it properly as a daemon process using `start_new_session=True` so it doesn't become a zombie.

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p3`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P3
