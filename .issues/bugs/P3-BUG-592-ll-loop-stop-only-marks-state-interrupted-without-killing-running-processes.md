---
discovered_date: 2026-03-05T00:00:00Z
discovered_by: capture-issue
---

# BUG-592: `ll-loop stop` Only Marks State "interrupted" Without Killing Running Processes

## Summary

`ll-loop stop` sends SIGTERM to the background loop process, but the registered SIGTERM handler defers shutdown gracefully — it sets a flag checked *between* iterations. If the process is in the middle of a long-running action (e.g., a Claude API call via subprocess), it will not be interrupted until the current action completes. The subprocess spawned by `FSMExecutor` is never directly killed.

## Current Behavior

1. `ll-loop stop` sends SIGTERM to the `ll-loop run` background process.
2. `_loop_signal_handler()` in `run.py` catches SIGTERM and sets `_loop_shutdown_requested = True`, calling `executor.request_shutdown()`.
3. `request_shutdown()` sets `self._shutdown_requested = True` — a flag checked only between state transitions.
4. If a long subprocess (e.g., `claude` CLI) is currently running inside `ActionRunner._run_action()`, it blocks on `process.communicate()` until the subprocess exits.
5. The loop process keeps running until that subprocess finishes, which could take minutes.

## Expected Behavior

`ll-loop stop` should stop the loop promptly. After a short grace period (e.g., 5s), if the process has not exited on its own, `cmd_stop` should either:
- Send a second SIGTERM to force exit, OR
- Send SIGKILL to the background process (and optionally its child process group)

Alternatively, the SIGTERM handler should kill the currently-running subprocess before waiting for clean shutdown.

## Motivation

Users expect `ll-loop stop` to stop the loop within seconds. When a Claude API call is in progress (which can take 30-120 seconds), the loop appears hung — `ll-loop status` shows "interrupted" in the state file, but the process is still running. This is confusing and can block resource cleanup.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Lines**: 26–43 (`_loop_signal_handler`)
- **Anchor**: `function _loop_signal_handler`

The SIGTERM handler only sets a flag; it does not kill the child subprocess currently blocking in `ActionRunner._run_action()`. The child subprocess PID is not stored or accessible from the signal handler.

- **File**: `scripts/little_loops/fsm/executor.py`
- **Lines**: ~156 (`subprocess.Popen`)
- **Anchor**: `class ActionRunner._run_action`

The `subprocess.Popen` child process is not tracked at a module/class level accessible to the signal handler.

## Steps to Reproduce

1. Start a loop: `ll-loop run my-loop --background`
2. Observe the loop entering a state that triggers a Claude action (long-running)
3. Run `ll-loop stop my-loop`
4. Check `ll-loop status my-loop` — shows "interrupted"
5. Check `ps aux | grep claude` — Claude subprocess still running

## Proposed Solution

**Option B (primary) — Track subprocess in signal handler:**
Store `self._current_process: subprocess.Popen | None` on `DefaultActionRunner`. Set it before `process.communicate()` and clear it after. Expose it so `_loop_signal_handler` can kill the child directly when SIGTERM is received, terminating the blocking subprocess immediately.

```python
# In DefaultActionRunner._run_action():
self._current_process = process
try:
    stdout, stderr = process.communicate(timeout=self._timeout)
finally:
    self._current_process = None

# In _loop_signal_handler():
if executor._action_runner._current_process is not None:
    executor._action_runner._current_process.kill()
```

**Option A (backstop) — Escalating kill in `cmd_stop`:**
After sending SIGTERM to the loop process, poll until exited. If still alive after the grace period, send SIGKILL. Guards against edge cases where the signal handler could not kill the child (e.g., process already exited, reference unavailable).

```python
os.kill(pid, signal.SIGTERM)
for _ in range(10):
    time.sleep(1)
    if not _process_alive(pid):
        break
else:
    os.kill(pid, signal.SIGKILL)
    logger.warning(f"Sent SIGKILL to {loop_name} (process did not exit after SIGTERM)")
```

**Option C — Use process group kill** (out of scope): Requires `os.setsid()` at subprocess spawn time; higher blast radius.

## Implementation Steps

1. In `executor.py::DefaultActionRunner`: add `_current_process: subprocess.Popen | None = None`; set/clear it around `process.communicate()` in `_run_action()`
2. In `run.py::_loop_signal_handler()`: after calling `executor.request_shutdown()`, kill `executor._action_runner._current_process` if it is set
3. In `lifecycle.py::cmd_stop()`: after sending SIGTERM, poll `_process_alive(pid)` for up to 10s; send SIGKILL and log warning if still alive
4. Update state to `"interrupted"` only after confirming the process has exited (or after SIGKILL)
5. Add test: mock a slow subprocess, call `request_shutdown()` with `_current_process` set, verify the process is killed; add integration test for the SIGKILL backstop path

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `DefaultActionRunner._run_action()`: add `_current_process` tracking
- `scripts/little_loops/cli/loop/run.py` — `_loop_signal_handler()`: kill `_current_process` on SIGTERM
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()`: add escalating SIGKILL backstop

### Dependent Files (Callers/Importers)
- TBD - `grep -r "DefaultActionRunner\|ActionRunner" scripts/` to find other instantiation sites
- TBD - `grep -r "cmd_stop\|loop.*stop" scripts/` to find callers of `cmd_stop`

### Similar Patterns
- TBD - `grep -r "subprocess.Popen\|process.communicate" scripts/` to check for consistent subprocess patterns

### Tests
- `scripts/tests/` — add unit test for `_current_process` kill path in `DefaultActionRunner`
- `scripts/tests/` — add unit test for SIGKILL backstop path in `cmd_stop`

### Documentation
- N/A - no user-facing docs reference stop behavior in detail

### Configuration
- N/A

## Impact

- **Priority**: P3 - Confuses users when `ll-loop stop` shows "interrupted" but the process keeps running; workaround is manual `kill`
- **Effort**: Medium - Requires Option B (add `_current_process` tracking to `DefaultActionRunner` and signal handler) plus Option A backstop (escalating SIGKILL in `cmd_stop`)
- **Risk**: Low - Only affects stop behavior; normal run/loop execution path is unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/loop/lifecycle.py` | Primary fix location — `cmd_stop()` |
| `scripts/little_loops/cli/loop/run.py` | Signal handler to optionally enhance |
| `scripts/little_loops/fsm/executor.py` | Child subprocess spawning in `ActionRunner` |

## Labels

`bug`, `ll-loop`, `process-management`, `signal-handling`

## Session Log

- `/ll:capture-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b0f4198-4bb4-4cba-b6a8-cdb86ec3578a.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19557ee2-cfec-4412-af6c-b7b067698753.jsonl`

---

## Status

**State**: Open
**Priority**: P3
