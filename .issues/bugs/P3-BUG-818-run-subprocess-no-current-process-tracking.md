---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_run_subprocess` stores `process` as a local variable only (`executor.py:773`); `finally: pass` at `executor.py:806-807` performs no tracking
- `FSMExecutor.__init__` (`executor.py:350-406`) declares no `_current_process` attribute — only `_shutdown_requested = False` at line 388
- The signal handler at `_helpers.py:50-59` traverses `PersistentExecutor._executor.action_runner._current_process` — it reaches `DefaultActionRunner._current_process`, not anything on `FSMExecutor` itself
- `_run_subprocess` is called exclusively for `action_mode == "mcp_tool"` at `executor.py:703-711`; all other action modes go through `self.action_runner.run(...)` which does have tracking

## Proposed Solution

Add `self._current_process = process` before the `try` block and `self._current_process = None` in the `finally` block, mirroring `DefaultActionRunner.run`. Ensure the shutdown signal handler in `FSMExecutor` checks `_current_process` for both the action runner and internal subprocess calls.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact pattern to mirror** (`executor.py:169-204`, `DefaultActionRunner.run`):
```python
# Line 175 — immediately after Popen, before stderr thread start:
self._current_process = process
# ... stderr thread, blocking stdout loop, TimeoutExpired handling ...
finally:
    self._current_process = None   # line 204 — unconditional
```

**Signal handler update needed** (`_helpers.py:50-59`): After the existing `runner._current_process` check, add a check for `inner._current_process` (the `FSMExecutor` instance) so MCP subprocess kills are also attempted:
```python
# Existing (covers DefaultActionRunner path):
proc = getattr(runner, "_current_process", None)
if proc is not None:
    proc.kill()
# New (covers FSMExecutor._run_subprocess / MCP path):
fsm_proc = getattr(inner, "_current_process", None)
if fsm_proc is not None:
    fsm_proc.kill()
```

**Attribute declaration** — add to `FSMExecutor.__init__` near `self._shutdown_requested = False` (`executor.py:388`):
```python
self._current_process: subprocess.Popen[str] | None = None
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.__init__` (line 388) to declare `_current_process`; `FSMExecutor._run_subprocess` (lines 773, 806-807) to assign/clear it
- `scripts/little_loops/cli/loop/_helpers.py` — `_loop_signal_handler` (lines 50-59) to also check `inner._current_process` (the `FSMExecutor` instance)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:320` — `PersistentExecutor._executor` holds the `FSMExecutor` instance; signal handler traversal passes through here
- `scripts/little_loops/cli/loop/run.py` — registers signal handlers and creates `PersistentExecutor`

### Similar Patterns
- `executor.py:133-134` — `_current_process` declaration pattern in `DefaultActionRunner.__init__`
- `executor.py:175` — set pattern: `self._current_process = process` (immediately after `Popen`)
- `executor.py:204` — clear pattern: `self._current_process = None` in `finally`

### Tests
- `scripts/tests/test_fsm_executor.py:2886-2927` — `TestDefaultActionRunnerProcessTracking` class to model new test class after
- `scripts/tests/test_cli_loop_background.py:60-83` — `TestLoopSignalHandler` tests to extend with `inner._current_process` kill path

## Implementation Steps

1. **Declare `_current_process` on `FSMExecutor`**: In `FSMExecutor.__init__` (`executor.py:388`), add `self._current_process: subprocess.Popen[str] | None = None` after the `self._shutdown_requested = False` line.

2. **Track process in `_run_subprocess`**: After `subprocess.Popen(...)` at `executor.py:773`, add `self._current_process = process`. In the `finally` block at lines 806-807, replace `pass` with `self._current_process = None`.

3. **Update signal handler**: In `_helpers.py:50-59`, after the existing check of `runner._current_process`, add a parallel check of `getattr(inner, "_current_process", None)` and call `.kill()` if not `None`.

4. **Add tests**: Add a new test class in `test_fsm_executor.py` after line 2927, following the `TestDefaultActionRunnerProcessTracking` pattern (test: cleared after normal run, cleared after timeout, initially None). Add a test in `test_cli_loop_background.py` for the `inner._current_process` kill path (mock `mock_inner._current_process = mock_process`, verify `proc.kill()` called).

5. **Verify**: Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_cli_loop_background.py -v`.

## Impact

- **Priority**: P3 - MCP subprocesses can orphan on shutdown, but this is an edge case during signal handling
- **Effort**: Small - Mirror existing pattern from `DefaultActionRunner.run`
- **Risk**: Low - Adding process tracking is additive and matches established pattern
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `shutdown`

## Status

**Completed** | Created: 2026-03-19 | Resolved: 2026-03-20 | Priority: P3

## Resolution

**Fixed** — Added `_current_process` tracking to `FSMExecutor._run_subprocess` to match the existing `DefaultActionRunner.run` pattern:

1. Declared `self._current_process: subprocess.Popen[str] | None = None` in `FSMExecutor.__init__` (`executor.py:391`)
2. Set `self._current_process = process` immediately after `Popen` in `_run_subprocess` (`executor.py:784`)
3. Replaced `finally: pass` with `finally: self._current_process = None` (`executor.py:812`)
4. Updated `_loop_signal_handler` in `_helpers.py` to also kill `inner._current_process` (the FSMExecutor MCP path) after the existing `action_runner._current_process` kill

Tests added: `TestFSMExecutorProcessTracking` (3 tests) in `test_fsm_executor.py`; `test_signal_handler_kills_fsm_executor_current_process` in `test_cli_loop_background.py`. All 156 tests pass.


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/fsm/executor.py` exists (1050 lines)
- `FSMExecutor._run_subprocess` is at lines 739–799; code snippet (lines 758–792) matches current code exactly
- `finally: pass` at line 792 confirmed — no `self._current_process` assignment anywhere in `FSMExecutor`
- `DefaultActionRunner.run` (lines 136–212) correctly tracks `_current_process`: set at line 175, cleared in `finally` at line 204
- `FSMExecutor` (class starts line 337) has no `_current_process` attribute — the gap described is accurate
- **Confidence**: High — code is unchanged since scan commit

## Session Log
- `/ll:manage-issue` - 2026-03-20T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-03-20T20:20:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8a0e158-a601-46eb-8fe7-1f8e98586d32.jsonl`
- `/ll:refine-issue` - 2026-03-20T20:14:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9839f80c-9a2c-41c0-89ac-f549658ef724.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:00:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac759df3-de78-495c-9b0f-b6a627ce9b04.jsonl`
