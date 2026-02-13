# BUG-236: Spawned process never tracked or reaped in handoff handler - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-236-spawned-process-never-tracked-in-handoff.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `HandoffHandler._spawn_continuation` at `handoff_handler.py:114-115` creates a `subprocess.Popen` to spawn a new Claude CLI session. This `Popen` object is returned in `HandoffResult.spawned_process`, but the calling code in `executor.py:727` discards the return value entirely:

```python
# executor.py:727 - return value discarded
self.handoff_handler.handle(self.fsm.name, signal.payload)
```

The spawned process has:
- No stdout/stderr capture (output leaks to parent terminal)
- No `process.wait()` or `process.communicate()` call
- No `start_new_session=True` for proper daemon detachment
- No tracking in any data structure

### Key Discoveries
- `subprocess_utils.py:55-149` has a mature pattern (`run_claude_command`) with full lifecycle management, zombie prevention, and callbacks
- `worker_pool.py:81-86` tracks processes in a `dict` with a `threading.Lock`
- The `_spawn_continuation` is intentionally fire-and-forget (spawn a new Claude session that runs independently)
- `ExecutionResult` has no field for process tracking, and the CLI exits after getting the result

## Desired End State

The spawned continuation process should be properly detached as an independent daemon process so it doesn't become a zombie. Since this is a fire-and-forget spawn of a new Claude session that should outlive the parent:

1. Use `start_new_session=True` to fully detach the process (new process group)
2. Redirect stdout/stderr to `subprocess.DEVNULL` to prevent I/O issues after parent exits
3. Log the spawned process PID for debugging
4. Call `process.wait()` in the executor's `_handle_handoff` is NOT appropriate here because the spawned process is a long-running Claude session that should continue after the parent exits

### How to Verify
- Tests pass with `python -m pytest scripts/tests/test_handoff_handler.py -v`
- Full test suite passes
- Lint, types pass

## What We're NOT Doing

- Not adding process tracking/reaping infrastructure (the spawned process is intentionally independent)
- Not adding a `spawned_process` field to `ExecutionResult` (the process should outlive the executor)
- Not capturing stdout/stderr to a log file (could be a future enhancement)
- Not changing the executor's `_handle_handoff` to wait on the process

## Problem Analysis

The root cause has two parts:

1. **`_spawn_continuation` creates a bare Popen** without `start_new_session=True`, so the child stays in the parent's process group. When the parent exits, the child becomes a zombie until init reaps it.

2. **The executor discards the HandoffResult** at `executor.py:727`, so the `Popen` object is garbage collected. While Python's GC eventually collects it, the child process is not properly detached.

The fix is to make the spawned process a proper daemon: detach it into its own session and redirect its I/O to DEVNULL so it's fully independent of the parent.

## Solution Approach

Minimal changes to `_spawn_continuation` to properly detach the process, and capture the return value in `_handle_handoff` to log the PID for observability.

## Implementation Phases

### Phase 1: Fix `_spawn_continuation` to properly detach the process

#### Overview
Modify the Popen call to use `start_new_session=True` and redirect stdout/stderr to `subprocess.DEVNULL`.

#### Changes Required

**File**: `scripts/little_loops/fsm/handoff_handler.py`
**Changes**: Update `_spawn_continuation` Popen call

```python
cmd = ["claude", "-p", prompt]
return subprocess.Popen(
    cmd,
    text=True,
    start_new_session=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
)
```

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Capture the HandoffResult to log the spawned process PID

At line 725-727, change from:
```python
# Invoke handler if configured
if self.handoff_handler:
    self.handoff_handler.handle(self.fsm.name, signal.payload)
```
to:
```python
# Invoke handler if configured
if self.handoff_handler:
    result = self.handoff_handler.handle(self.fsm.name, signal.payload)
    if result.spawned_process is not None:
        self._emit(
            "handoff_spawned",
            {
                "pid": result.spawned_process.pid,
                "state": self.current_state,
            },
        )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_handoff_handler.py -v`
- [ ] Full test suite: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

### Phase 2: Update tests

#### Overview
Update existing spawn test to verify the new Popen arguments and add a test for the executor handoff_spawned event.

#### Changes Required

**File**: `scripts/tests/test_handoff_handler.py`
**Changes**: Update `test_spawn_behavior` and `test_spawn_with_none_continuation` to verify `start_new_session=True`, `stdout=DEVNULL`, `stderr=DEVNULL`, `stdin=DEVNULL`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_handoff_handler.py -v`
- [ ] Full test suite: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Verify `subprocess.Popen` is called with `start_new_session=True`
- Verify `stdout=DEVNULL`, `stderr=DEVNULL`, `stdin=DEVNULL`
- Verify the executor emits a `handoff_spawned` event with the process PID

## References

- Original issue: `.issues/bugs/P3-BUG-236-spawned-process-never-tracked-in-handoff.md`
- Process lifecycle pattern: `scripts/little_loops/subprocess_utils.py:55-149`
- Worker pool tracking pattern: `scripts/little_loops/parallel/worker_pool.py:81-86`
