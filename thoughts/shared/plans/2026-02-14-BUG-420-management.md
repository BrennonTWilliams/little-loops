# Implementation Plan: BUG-420 - Missing timeout on process.wait() after kill

**Issue**: P3-BUG-420-missing-timeout-on-process-wait-after-kill.md
**Action**: fix
**Date**: 2026-02-14

## Research Findings

### Current State
`subprocess_utils.py:run_claude_command()` has three `process.wait()` calls without timeout:
- **Line 123**: After `process.kill()` on total timeout
- **Line 128**: After `process.kill()` on idle timeout
- **Line 150**: After normal stream completion

### Existing Pattern
`worker_pool.py:156-161` already implements the correct pattern:
```python
process.wait(timeout=5)   # after SIGTERM
process.wait(timeout=2)   # after SIGKILL
```

### Impact
- Lines 123, 128: After SIGKILL, process should terminate almost immediately. A 10-second timeout is generous.
- Line 150: After normal completion (all streams closed), the process has already exited. A 30-second timeout is a safety net.

## Plan

### Phase 1: Fix subprocess_utils.py

**File**: `scripts/little_loops/subprocess_utils.py`

1. Add `import logging` at top
2. Create module logger
3. Add `timeout=10` to `process.wait()` at lines 123 and 128 (after kill)
4. Wrap in try/except to log warning if process doesn't terminate
5. Add `timeout=30` to `process.wait()` at line 150 (normal completion) with try/except

### Phase 2: Update Tests

**File**: `scripts/tests/test_subprocess_utils.py`

1. Add test: `test_wait_has_timeout_after_kill` - verify `process.wait(timeout=10)` is called after kill on total timeout
2. Add test: `test_wait_has_timeout_after_idle_kill` - verify `process.wait(timeout=10)` is called after kill on idle timeout
3. Add test: `test_wait_has_timeout_on_normal_completion` - verify `process.wait(timeout=30)` is called on normal exit
4. Add test: `test_logs_warning_when_wait_times_out_after_kill` - verify warning logged when wait times out
5. Update existing test assertions that check `process.wait.assert_called_once()` to verify the timeout parameter

### Success Criteria

- [ ] All three `process.wait()` calls have timeout parameter
- [ ] Warning logged if process doesn't respond to kill within 10 seconds
- [ ] Existing tests pass
- [ ] New tests cover timeout behavior
- [ ] Type checks pass
- [ ] Lint passes
