---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# BUG-685: `process.returncode or 0` masks killed process as success

## Summary

In `run_claude_command`, when a process is killed after timeout and the second `process.wait()` also times out, `process.returncode` remains `None`. The expression `process.returncode or 0` then evaluates to `0` (success), silently reporting a killed process as having succeeded. All callers that check `result.returncode != 0` to detect failure will miss this case.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 172-186 (at scan commit: 3e9beea)
- **Anchor**: `in function run_claude_command()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/3e9beeaf2bbe8608104beb89fbc7e2e2259310d8/scripts/little_loops/subprocess_utils.py#L172-L186)
- **Code**:
```python
return subprocess.CompletedProcess(
    cmd_args,
    process.returncode or 0,   # None or 0  =>  0
    ...
)
```

## Current Behavior

When the post-stream `process.wait(timeout=30)` times out, the code kills the process with `process.kill()` then calls `process.wait(timeout=10)`. If that inner wait also times out, `process.returncode` is `None`. The `CompletedProcess` is constructed with `process.returncode or 0` which evaluates `None or 0` to `0`. Callers in `worker_pool.py` and `merge_coordinator.py` that check `result.returncode != 0` see success.

## Expected Behavior

A killed or timed-out process should report a non-zero return code (e.g., `-9` for SIGKILL or a sentinel like `1`) so callers can detect the failure.

## Steps to Reproduce

1. Run `ll-parallel` or `ll-auto` with an issue that causes Claude to hang
2. The process times out at the 30s wait, gets killed, and the 10s wait also expires
3. The returned `CompletedProcess` has `returncode=0`
4. The orchestrator treats the run as successful

## Root Cause

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Anchor**: `in function run_claude_command()`
- **Cause**: Python's `or` operator returns the right operand when the left is falsy. `None or 0` is `0`. The code intended a fallback for when returncode is not set, but `0` is also the success code.

## Proposed Solution

Replace `process.returncode or 0` with an explicit check:

```python
returncode = process.returncode if process.returncode is not None else -9
```

This ensures killed/unreapable processes report a non-zero exit code (`-9` for SIGKILL convention).

## Impact

- **Priority**: P1 - Can cause silent data corruption: a failed worker is treated as successful, potentially skipping retries or marking issues as completed when they weren't processed
- **Effort**: Small - Single line fix
- **Risk**: Low - Only changes behavior for the edge case where a process was killed and couldn't be reaped
- **Breaking Change**: No

## Labels

`bug`, `parallel`, `subprocess`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P1
