---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# BUG-420: Missing timeout on process.wait() after kill in subprocess_utils

## Summary

After calling `process.kill()`, `process.wait()` is called without a timeout. While SIGKILL should terminate processes immediately, edge cases (zombie processes, uninterruptible sleep) could cause `wait()` to hang indefinitely, blocking the worker.

## Location

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Line(s)**: 122-129, 150 (at scan commit: 71616c7)
- **Anchor**: `in function run_claude_command()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/71616c711e2fe9f5f1ececcf1c64552bca9d82ec/scripts/little_loops/subprocess_utils.py#L122-L150)
- **Code**:
```python
if timeout and (now - start_time) > timeout:
    process.kill()
    process.wait()  # No timeout on wait
    raise subprocess.TimeoutExpired(cmd_args, timeout)

if idle_timeout and (now - last_output_time) > idle_timeout:
    process.kill()
    process.wait()  # No timeout on wait
    raise subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")

# ... later ...
process.wait()  # No timeout on normal exit either
```

## Current Behavior

`process.wait()` blocks indefinitely after `process.kill()`. If the process enters an uninterruptible state, the entire worker hangs.

## Expected Behavior

`process.wait()` should include a reasonable timeout (e.g., 10 seconds) after kill, with a fallback error if the process still hasn't terminated.

## Steps to Reproduce

1. Run a subprocess that enters uninterruptible sleep (D state) or becomes a zombie
2. Trigger timeout or idle_timeout
3. `process.kill()` is called, then `process.wait()` hangs indefinitely

## Actual Behavior

The worker thread/process blocks forever on `process.wait()` even though a timeout was configured.

## Root Cause

- **File**: `scripts/little_loops/subprocess_utils.py`
- **Anchor**: `in function run_claude_command()`
- **Cause**: `process.wait()` at lines 123, 128, and 150 lacks a `timeout` parameter, so it blocks indefinitely.

## Proposed Solution

Add a timeout to all `process.wait()` calls:

```python
process.kill()
try:
    process.wait(timeout=10)
except subprocess.TimeoutExpired:
    logger.warning("Process did not terminate after kill, may be zombie")
```

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — calls `run_claude_command()`
- `scripts/little_loops/issue_manager.py` — calls `run_claude_command()`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_subprocess_utils.py` — add timeout edge case tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `timeout=10` to all three `process.wait()` calls
2. Wrap in try/except to handle the case where wait times out
3. Add tests for timeout behavior

## Impact

- **Priority**: P3 - Affects automation reliability but requires unusual system state to trigger
- **Effort**: Small - Adding timeout parameter to three call sites
- **Risk**: Low - Additive change, no behavior change for normal operation
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `subprocess`, `reliability`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P3
