---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# BUG-604: PID file not cleaned up after SIGTERM/SIGKILL stop path

## Summary

After `cmd_stop` sends SIGTERM (and optionally SIGKILL) to a loop process, it saves state as `"interrupted"` but never removes the PID file. The `pid_file.unlink(missing_ok=True)` call only executes in the "process already dead" branch, leaving stale PID files after successful stops.

## Location

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 111-124 (at scan commit: c010880)
- **Anchor**: `in function cmd_stop()`, SIGTERM wait loop
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/lifecycle.py#L111-L124)
- **Code**:
```python
os.kill(pid, signal.SIGTERM)
for _ in range(10):
    time.sleep(1)
    if not _process_alive(pid):
        break
else:
    try:
        os.kill(pid, signal.SIGKILL)
        logger.warning(f"Sent SIGKILL to {loop_name} (PID: {pid})")
    except OSError:
        pass
state.status = "interrupted"
persistence.save_state(state)
logger.success(f"Stopped {loop_name} (PID: {pid})")
# pid_file.unlink() is NOT called here
```

## Current Behavior

After stopping a loop, the PID file remains on disk. Subsequent `ll-loop status` shows "not running - stale PID file".

## Expected Behavior

The PID file should be removed after successfully stopping the process.

## Steps to Reproduce

1. Run a loop in background mode
2. Run `ll-loop stop <loop>`
3. Check `.loops/.running/<loop>.pid` — file still exists
4. Run `ll-loop status <loop>` — shows stale PID message

## Proposed Solution

Add `pid_file.unlink(missing_ok=True)` after `persistence.save_state(state)` in the SIGTERM/SIGKILL path.

## Impact

- **Priority**: P4 - Cosmetic issue, stale files don't cause functional problems
- **Effort**: Small - One-line addition
- **Risk**: Low - Cleanup operation
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `lifecycle`

---

**Open** | Created: 2026-03-06 | Priority: P4
