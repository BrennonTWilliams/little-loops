---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# BUG-239: returncode or 0 masks None returncode

## Summary

The expression `process.returncode or 0` in `run_claude_command` uses Python's truthy evaluation, which means `None` (process not waited on) evaluates to `0` (success), hiding a potential problem.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 145 (at scan commit: a8f4144)
- **Anchor**: `in function run_claude_command, return statement`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/subprocess_utils.py#L145)
- **Code**:
```python
return subprocess.CompletedProcess(
    cmd_args,
    process.returncode or 0,
    stdout="\n".join(stdout_lines),
    stderr="\n".join(stderr_lines),
)
```

## Current Behavior

If `process.returncode` is `None` (process not properly waited on), the `or 0` expression returns `0`, falsely indicating success. Note: this also maps a successful `returncode=0` through the `or` operator, but since `0` is falsy in Python, it also becomes `0` -- so that case happens to be correct.

## Expected Behavior

Use an explicit None check: `process.returncode if process.returncode is not None else 0`

## Proposed Solution

```python
return subprocess.CompletedProcess(
    cmd_args,
    process.returncode if process.returncode is not None else 0,
    stdout="\n".join(stdout_lines),
    stderr="\n".join(stderr_lines),
)
```

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `priority-p4`

---

## Status
**Closed (Superseded)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4

**Closure reason**: Superseded by BUG-231. The None returncode only occurs when process.wait() isn't called, which is exactly what BUG-231 (zombie process after timeout) fixes. Once BUG-231 is resolved, this edge case becomes unreachable.
