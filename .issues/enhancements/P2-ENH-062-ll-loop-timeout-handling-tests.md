# ENH-062: Add Timeout Handling Tests for ll-loop

## Summary

The `ll-loop` executor has timeout handling code that is completely untested. The `subprocess.TimeoutExpired` exception handler and loop-level timeout enforcement are never verified, meaning timeout behavior could silently break.

## Current State

- **Executor File**: `scripts/little_loops/fsm/executor.py`
- **Timeout Code**: Lines 140-159 (subprocess timeout), lines 227-230 (loop-level timeout)
- **Exit Code**: 124 on timeout (never verified)
- **Test Coverage**: None

### What's Missing

The executor handles timeouts in two places:
1. **Action timeout** - `subprocess.TimeoutExpired` caught at action execution
2. **Loop timeout** - Overall loop execution time limit

Neither is tested:
- No tests mock `subprocess.TimeoutExpired`
- No tests verify exit code 124 on timeout
- No tests confirm loop-level timeout enforcement

## Proposed Tests

### Action-Level Timeout Tests

```python
class TestTimeoutHandling:
    """Tests for subprocess and loop-level timeout handling."""

    def test_action_timeout_returns_exit_code_124(self, executor_fixture):
        """Subprocess timeout should return exit code 124."""
        import subprocess
        with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('cmd', 30)):
            result = executor_fixture.execute_action(action_config)
            assert result.exit_code == 124

    def test_action_timeout_records_timeout_event(self, tmp_path):
        """Timeout should be recorded in events log."""
        # Setup executor with timeout-triggering action
        # Verify event log contains timeout entry

    def test_action_timeout_captures_partial_output(self, executor_fixture):
        """If action times out after partial output, capture what we have."""
        # Mock subprocess to raise TimeoutExpired with partial stdout
```

### Loop-Level Timeout Tests

```python
    def test_loop_timeout_stops_execution(self, tmp_path):
        """Loop should stop when total execution time exceeds timeout."""
        loop_config = {
            "timeout": 5,  # 5 second total timeout
            "states": [...]  # States that would take longer than 5s
        }
        # Verify execution stops and returns appropriate code

    def test_loop_timeout_persists_state_before_exit(self, tmp_path):
        """On loop timeout, current state should be persisted."""
        # Verify state file exists after timeout
        # Verify status is "interrupted" or similar
```

## Implementation Approach

Add tests to `test_fsm_executor.py`:

1. Mock `subprocess.run` to raise `TimeoutExpired`
2. Verify exit code 124 is returned/recorded
3. Test with various timeout values (0, negative, large)
4. Test loop-level timeout with slow-executing states

Use `pytest` fixtures to:
- Create temporary state directories
- Mock subprocess execution
- Control time (if needed for loop timeout)

## Impact

- **Priority**: P2 (High)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Test verifies exit code 124 on `subprocess.TimeoutExpired`
- [ ] Test verifies timeout event is logged
- [ ] Test verifies loop-level timeout stops execution
- [ ] Test verifies state is persisted on timeout
- [ ] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `timeout`, `fsm`

---

## Status

**Open** | Created: 2026-01-15 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_fsm_executor.py`: Added `TestTimeoutHandling` class with 6 tests:
  - `test_action_timeout_exit_code_124_routes_to_error`: Verifies exit code 124 routes to on_error
  - `test_action_timeout_emits_event_with_exit_code_124`: Verifies action_complete event includes exit code 124
  - `test_action_timeout_captured_result`: Verifies timeout results are captured when configured
  - `test_loop_timeout_stops_execution`: Verifies loop terminates on timeout
  - `test_loop_timeout_emits_loop_complete_event`: Verifies loop_complete event has terminated_by: timeout
  - `test_loop_timeout_preserves_state`: Verifies final_state and iterations are preserved on timeout

### Verification Results
- Tests: PASS (30 passed in 0.06s)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
