---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-231: Zombie process after timeout kill in run_claude_command

## Summary

When a timeout occurs in `run_claude_command`, `process.kill()` sends SIGKILL but `process.wait()` is never called on the timeout path, leaving a zombie process.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 114-141 (at scan commit: a8f4144)
- **Anchor**: `in function run_claude_command, timeout handling`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/subprocess_utils.py#L116-L141)
- **Code**:
```python
with selectors.DefaultSelector() as sel:
    # ... register stdout/stderr ...
    try:
        while sel.get_map():
            if timeout and (time.time() - start_time) > timeout:
                process.kill()                                    # sends SIGKILL
                raise subprocess.TimeoutExpired(cmd_args, timeout)  # exits immediately
            # ...
        process.wait()  # only reached on normal exit
    finally:
        if on_process_end:
            on_process_end(process)  # called even on timeout path
```

## Current Behavior

After `process.kill()`, the code immediately raises `TimeoutExpired` without calling `process.wait()`. The killed process becomes a zombie because its exit status is never collected.

## Expected Behavior

`process.wait()` should be called after `process.kill()` to reap the child process before raising the timeout exception.

## Reproduction Steps

1. Run `ll-auto` or `ll-parallel` with a timeout configured
2. Wait for a timeout to occur
3. Check for zombie processes with `ps aux | grep Z`

## Proposed Solution

Add `process.wait()` after `process.kill()`:
```python
if timeout and (time.time() - start_time) > timeout:
    process.kill()
    process.wait()  # reap the zombie
    raise subprocess.TimeoutExpired(cmd_args, timeout)
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p2`

---

## Status
**Completed** | Created: 2026-02-06T03:41:30Z | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/subprocess_utils.py`: Added `process.wait()` after `process.kill()` on timeout path to reap child process
- `scripts/tests/test_subprocess_utils.py`: Added assertion that `process.wait()` is called after kill on timeout

### Verification Results
- Tests: PASS (2460 passed)
- Lint: PASS
- Types: PASS
