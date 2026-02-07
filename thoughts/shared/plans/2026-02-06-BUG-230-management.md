# BUG-230: Selector resource leak in run_claude_command - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-230-selector-resource-leak-in-run-claude-command.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `run_claude_command` function in `scripts/little_loops/subprocess_utils.py:55-148` creates a `selectors.DefaultSelector()` at line 106 to multiplex non-blocking reads from stdout/stderr pipes. The selector is never closed — neither explicitly via `sel.close()` nor via a `with` statement.

### Key Discoveries
- `selectors.DefaultSelector()` allocates an OS file descriptor (kqueue on macOS, epoll on Linux) at `subprocess_utils.py:106`
- The `try/finally` block at lines 114-141 only calls `on_process_end` — no `sel.close()`
- The selector is the only resource in this function with no cleanup
- Callers invoke this function in loops: `issue_manager.py:153-159` (up to 4 times per issue) and `worker_pool.py:685-690` (up to 4 times per issue per worker thread)
- `selectors.DefaultSelector` supports the context manager protocol natively

## Desired End State

The selector is used as a context manager so the OS file descriptor is always released, on both normal completion and exception paths (including timeout).

### How to Verify
- Existing tests continue to pass (they mock `selectors.DefaultSelector`)
- New test verifies `sel.close()` is called on normal exit
- New test verifies `sel.close()` is called on timeout exception

## What We're NOT Doing

- Not fixing BUG-231 (zombie process after timeout kill) — separate issue
- Not refactoring the `try/finally` block beyond adding `sel.close()`
- Not changing the `process.returncode or 0` behavior (BUG-239, already completed)

## Problem Analysis

On each invocation of `run_claude_command`, `selectors.DefaultSelector()` allocates an OS file descriptor for the kernel event queue. When the function returns, the `sel` local variable goes out of scope but the file descriptor is not deterministically closed — it relies on garbage collection. In CPython's reference counting this often works, but in threaded contexts (worker_pool) or with reference cycles, finalization is delayed, accumulating leaked FDs.

## Solution Approach

Wrap the selector usage in a `with` statement. `selectors.DefaultSelector` already implements `__enter__` and `__exit__` (which calls `self.close()`). The `with` block should encompass the selector registration, the read loop, and the `process.wait()` call — everything that uses the selector. The existing `on_process_end` callback in the `finally` block must remain outside the `with` block since it doesn't depend on the selector.

## Implementation Phases

### Phase 1: Fix the resource leak

#### Overview
Convert bare `sel = selectors.DefaultSelector()` to `with selectors.DefaultSelector() as sel:` and indent the code that uses it under the `with` block.

#### Changes Required

**File**: `scripts/little_loops/subprocess_utils.py`
**Changes**: Wrap selector in context manager

Replace lines 105-141:
```python
    # Use selectors for non-blocking read from both streams
    sel = selectors.DefaultSelector()
    if process.stdout:
        sel.register(process.stdout, selectors.EVENT_READ)
    if process.stderr:
        sel.register(process.stderr, selectors.EVENT_READ)

    start_time = time.time()

    try:
        while sel.get_map():
            ...
        process.wait()
    finally:
        if on_process_end:
            on_process_end(process)
```

With:
```python
    # Use selectors for non-blocking read from both streams
    with selectors.DefaultSelector() as sel:
        if process.stdout:
            sel.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            sel.register(process.stderr, selectors.EVENT_READ)

        start_time = time.time()

        try:
            while sel.get_map():
                ...
            process.wait()
        finally:
            if on_process_end:
                on_process_end(process)
```

The `try/finally` remains inside the `with` block so that:
1. On normal exit: `with` exits normally, calling `sel.close()`
2. On timeout: `TimeoutExpired` propagates through `finally` (calling `on_process_end`), then through the `with` block (calling `sel.close()`), then to the caller

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_subprocess_utils.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/subprocess_utils.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/subprocess_utils.py`

### Phase 2: Add test for selector close

#### Overview
Add tests verifying that `sel.close()` is called on both normal exit and timeout paths.

#### Changes Required

**File**: `scripts/tests/test_subprocess_utils.py`
**Changes**: Add two tests to `TestRunClaudeCommandProcessCallbacks`

```python
def test_selector_closed_on_success(self) -> None:
    """Selector is closed after normal completion."""
    mock_process = Mock()
    mock_process.stdout = io.StringIO("")
    mock_process.stderr = io.StringIO("")
    mock_process.returncode = 0
    mock_process.wait.return_value = None

    with patch("subprocess.Popen", return_value=mock_process):
        with patch("selectors.DefaultSelector") as mock_selector:
            mock_selector.return_value.get_map.return_value = {}
            run_claude_command("test")

    mock_selector.return_value.__exit__.assert_called_once()

def test_selector_closed_on_timeout(self) -> None:
    """Selector is closed even when timeout occurs."""
    # Similar to existing timeout test, assert __exit__ called
```

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_subprocess_utils.py -v -k "selector_closed"`
- [ ] All tests pass: `python -m pytest scripts/tests/test_subprocess_utils.py -v`

## Testing Strategy

### Unit Tests
- Verify `sel.close()` (via `__exit__`) called on normal completion
- Verify `sel.close()` (via `__exit__`) called on timeout exception
- Existing tests remain passing (they mock the selector)

### Edge Cases
- Timeout path: selector closed before exception propagates
- Normal path: selector closed after process.wait()

## References

- Original issue: `.issues/bugs/P2-BUG-230-selector-resource-leak-in-run-claude-command.md`
- Bug location: `scripts/little_loops/subprocess_utils.py:106`
- Related BUG-231: `.issues/bugs/P2-BUG-231-zombie-process-after-timeout-kill.md`
- Context manager pattern: `scripts/little_loops/parallel/git_lock.py:67-79`
- Test patterns: `scripts/tests/test_subprocess_utils.py:187-203`
