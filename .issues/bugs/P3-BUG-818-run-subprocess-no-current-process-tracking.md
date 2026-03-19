---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
---

# BUG-818: `_run_subprocess` has no `_current_process` tracking — shutdown cannot kill MCP subprocesses

## Summary

`FSMExecutor._run_subprocess` (used for MCP calls) follows the same Popen + stderr-drain-thread pattern as `DefaultActionRunner.run`, but omits the `self._current_process` tracking that enables external shutdown code to locate and kill the running process. During a SIGTERM, MCP subprocesses continue running until their natural timeout.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 758-792 (at scan commit: 8c6cf90)
- **Anchor**: `in method FSMExecutor._run_subprocess`
- **Code**:
```python
process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
...
try:
    for line in process.stdout:
        ...
    process.wait(timeout=timeout)
except subprocess.TimeoutExpired:
    process.kill()
    process.wait()
    stderr_thread.join(timeout=5)
    return ActionResult(...)
finally:
    pass        # No _current_process tracking
```

## Current Behavior

`_run_subprocess` has a `finally: pass` block and no `self._current_process` assignment. When a shutdown signal arrives during an MCP subprocess call, there is no mechanism to terminate it from outside the method.

## Expected Behavior

`_run_subprocess` should track the running process in `self._current_process` (or equivalent) and clear it in the `finally` block, matching the pattern used in `DefaultActionRunner.run`.

## Steps to Reproduce

1. Configure a loop with an MCP-calling state
2. Start the loop with `ll-loop run`
3. While the MCP call is in progress, send SIGTERM
4. Observe that the MCP subprocess continues running until its natural timeout

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `in method FSMExecutor._run_subprocess`
- **Cause**: The method's docstring says it "follows the same Popen + stderr-drain-thread pattern as DefaultActionRunner," but the shutdown-tracking behavior was omitted during implementation.

## Proposed Solution

Add `self._current_process = process` before the `try` block and `self._current_process = None` in the `finally` block, mirroring `DefaultActionRunner.run`. Ensure the shutdown signal handler in `FSMExecutor` checks `_current_process` for both the action runner and internal subprocess calls.

## Impact

- **Priority**: P3 - MCP subprocesses can orphan on shutdown, but this is an edge case during signal handling
- **Effort**: Small - Mirror existing pattern from `DefaultActionRunner.run`
- **Risk**: Low - Adding process tracking is additive and matches established pattern
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `shutdown`

## Status

**Open** | Created: 2026-03-19 | Priority: P3


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/fsm/executor.py` exists (1050 lines)
- `FSMExecutor._run_subprocess` is at lines 739–799; code snippet (lines 758–792) matches current code exactly
- `finally: pass` at line 792 confirmed — no `self._current_process` assignment anywhere in `FSMExecutor`
- `DefaultActionRunner.run` (lines 136–212) correctly tracks `_current_process`: set at line 175, cleared in `finally` at line 204
- `FSMExecutor` (class starts line 337) has no `_current_process` attribute — the gap described is accurate
- **Confidence**: High — code is unchanged since scan commit

## Session Log
- `/ll:verify-issues` - 2026-03-19T23:00:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
