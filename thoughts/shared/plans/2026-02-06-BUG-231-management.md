# BUG-231: Zombie Process After Timeout Kill - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-231-zombie-process-after-timeout-kill.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

In `scripts/little_loops/subprocess_utils.py:116-118`, when a timeout occurs in `run_claude_command`, `process.kill()` sends SIGKILL but the code immediately raises `TimeoutExpired` without calling `process.wait()`. The `process.wait()` at line 138 is only reachable on the normal (non-timeout) path. This leaves a zombie process because the OS process entry is never reaped.

### Key Discoveries
- `subprocess_utils.py:117` — `process.kill()` called without subsequent `process.wait()`
- `subprocess_utils.py:138` — `process.wait()` only reached on normal exit path
- `worker_pool.py:152-159` — Correct pattern exists: `terminate()` → `wait()` → `kill()` → `wait()`
- BUG-239 (completed/superseded) — `returncode or 0` masking `None` is a downstream symptom of this bug

## Desired End State

After `process.kill()` on the timeout path, `process.wait()` is called to reap the child process before raising `TimeoutExpired`.

### How to Verify
- Existing timeout tests pass (they already mock `process.wait`)
- New test assertion: `process.wait()` is called on the timeout path
- `process.kill()` is still called exactly once on timeout

## What We're NOT Doing

- Not changing the timeout detection logic
- Not adding graceful SIGTERM-then-SIGKILL escalation (that pattern is for worker_pool shutdown, not individual command timeouts where SIGKILL is appropriate)
- Not modifying the `on_process_end` callback behavior
- Not changing the return value construction

## Problem Analysis

The `raise subprocess.TimeoutExpired(...)` at line 118 causes an exception that skips `process.wait()` at line 138. The killed child process transitions to zombie state (`Z` in `ps`) because its exit status is never collected by the parent.

## Solution Approach

Add `process.wait()` between `process.kill()` and `raise TimeoutExpired`. This follows the pattern used by Python's own `subprocess.run()` internally and aligns with the existing pattern in `worker_pool.py:terminate_all_processes`.

## Implementation Phases

### Phase 1: Fix the Timeout Path

#### Overview
Add `process.wait()` after `process.kill()` in the timeout handler.

#### Changes Required

**File**: `scripts/little_loops/subprocess_utils.py`
**Changes**: Add `process.wait()` between `process.kill()` and `raise subprocess.TimeoutExpired(...)` at lines 117-118.

```python
if timeout and (time.time() - start_time) > timeout:
    process.kill()
    process.wait()  # reap child to prevent zombie
    raise subprocess.TimeoutExpired(cmd_args, timeout)
```

### Phase 2: Update Tests

#### Overview
Add assertion that `process.wait()` is called on the timeout path in existing tests, and verify test coverage.

#### Changes Required

**File**: `scripts/tests/test_subprocess_utils.py`
**Changes**: In `test_kills_process_on_timeout` (line 593), add assertion that `mock_process.wait` was called after kill.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_subprocess_utils.py -v`
- [ ] Full test suite: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## References

- Original issue: `.issues/bugs/P2-BUG-231-zombie-process-after-timeout-kill.md`
- Correct pattern: `scripts/little_loops/parallel/worker_pool.py:152-159`
- Related completed issue: `.issues/completed/P2-BUG-230-selector-resource-leak-in-run-claude-command.md`
