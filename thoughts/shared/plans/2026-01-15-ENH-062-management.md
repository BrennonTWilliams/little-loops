# ENH-062: Add Timeout Handling Tests for ll-loop - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-062-ll-loop-timeout-handling-tests.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The FSM executor has two distinct timeout mechanisms:

### Action-Level Timeout (`executor.py:140-159`)
- `subprocess.run()` accepts a timeout parameter at line 145
- On `subprocess.TimeoutExpired`, returns `ActionResult` with:
  - `exit_code=124` (standard Unix timeout exit code)
  - `stderr="Action timed out"`
  - `output=""` (empty string)
  - `duration_ms=timeout * 1000`

### Loop-Level Timeout (`executor.py:227-230`)
- Checked on each iteration before executing a state
- Uses `_now_ms() - self.start_time_ms` to track elapsed time
- Returns `ExecutionResult` with `terminated_by="timeout"` via `self._finish("timeout")`

### Key Discoveries
- `MockActionRunner` at `test_fsm_executor.py:21-80` can simulate any exit code but doesn't handle timeouts
- No existing timeout tests in `test_fsm_executor.py`
- `test_subprocess_utils.py:535-599` has patterns for mocking `time.time()` to simulate timeouts
- Default action timeout is 120 seconds (`executor.py:352`)
- `FSMLoop.timeout` is the loop-level timeout (`schema.py:352`)

## Desired End State

A new test class `TestTimeoutHandling` in `test_fsm_executor.py` that verifies:
1. Action-level timeout returns exit code 124
2. Action-level timeout sets appropriate stderr message
3. Action-level timeout event is emitted with exit code 124
4. Action-level timeout with capture stores timeout result
5. Loop-level timeout stops execution and returns `terminated_by="timeout"`
6. Loop-level timeout emits `loop_complete` event with `terminated_by: "timeout"`

### How to Verify
- Run `python -m pytest scripts/tests/test_fsm_executor.py -v -k TestTimeoutHandling`
- All 6 tests pass
- Timeout code paths now have test coverage

## What We're NOT Doing

- Not testing actual subprocess timeouts (too slow, flaky)
- Not modifying `DefaultActionRunner` - tests use `MockActionRunner`
- Not testing `subprocess.TimeoutExpired` directly in executor (mock at action runner level)
- Not testing persistence layer timeout handling (separate concern)
- Not adding integration tests (unit tests are sufficient)

## Problem Analysis

The executor has complete timeout handling code but zero test coverage:
- `DefaultActionRunner.run()` catches `subprocess.TimeoutExpired` and returns exit code 124
- `FSMExecutor.run()` checks `self.fsm.timeout` before each iteration
- Both paths work in production but could silently break without regression tests

The fix: Add unit tests that mock the action runner and time to verify timeout behavior.

## Solution Approach

1. Create a new `MockTimeoutActionRunner` that simulates timeout by returning exit code 124
2. Test action-level timeout by verifying exit code and event emission
3. Test loop-level timeout by mocking `time.time()` to simulate elapsed time
4. Follow existing patterns from `TestErrorHandling` and `TestEvents` classes

## Implementation Phases

### Phase 1: Add Action-Level Timeout Tests

#### Overview
Add tests that verify the action runner's timeout behavior is properly handled by the executor.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add `TestTimeoutHandling` class with action-level timeout tests

```python
class TestTimeoutHandling:
    """Tests for timeout handling."""

    def test_action_timeout_exit_code_124_routes_correctly(self) -> None:
        """Exit code 124 from action timeout is evaluated correctly."""
        fsm = FSMLoop(
            name="test",
            initial="slow",
            states={
                "slow": StateConfig(
                    action="slow_command.sh",
                    on_success="done",
                    on_failure="retry",
                    on_error="error",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        # Exit code 124 is returned on timeout - maps to "failure" by default evaluator
        mock_runner.set_result("slow_command.sh", exit_code=124, stderr="Action timed out")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Exit code 124 != 0 (success), != 1 (failure), so routes to on_error
        assert result.final_state == "error"
        assert result.terminated_by == "terminal"

    def test_action_timeout_emits_event_with_exit_code(self) -> None:
        """action_complete event includes exit code 124 on timeout."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="slow",
            states={
                "slow": StateConfig(
                    action="slow_command.sh",
                    on_success="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("slow_command.sh", exit_code=124)

        executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
        executor.run()

        action_complete = next(e for e in events if e["event"] == "action_complete")
        assert action_complete["exit_code"] == 124

    def test_action_timeout_captured_result(self) -> None:
        """Timeout result is captured when state has capture configured."""
        fsm = FSMLoop(
            name="test",
            initial="slow",
            states={
                "slow": StateConfig(
                    action="slow_command.sh",
                    capture="slow_result",
                    on_success="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result(
            "slow_command.sh",
            exit_code=124,
            stderr="Action timed out",
            output="",
            duration_ms=30000,
        )

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert "slow_result" in result.captured
        assert result.captured["slow_result"]["exit_code"] == 124
        assert result.captured["slow_result"]["stderr"] == "Action timed out"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v -k "test_action_timeout"`

---

### Phase 2: Add Loop-Level Timeout Tests

#### Overview
Add tests that verify loop-level timeout enforcement using mocked time.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add loop-level timeout tests to `TestTimeoutHandling` class

```python
    def test_loop_timeout_stops_execution(self) -> None:
        """Loop terminates when total time exceeds timeout."""
        from unittest.mock import patch

        fsm = FSMLoop(
            name="test",
            initial="check",
            timeout=5,  # 5 second total timeout
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                    on_failure="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)  # Always fail to keep looping

        # Mock time to simulate timeout after first iteration
        start_time = 1000.0
        # First call: start_time_ms, second: check timeout (after 6s)
        time_values = [start_time, start_time, start_time + 6.0]
        call_count = [0]

        def mock_time() -> float:
            result = time_values[min(call_count[0], len(time_values) - 1)]
            call_count[0] += 1
            return result

        with patch("little_loops.fsm.executor.time.time", side_effect=mock_time):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.terminated_by == "timeout"

    def test_loop_timeout_emits_loop_complete_event(self) -> None:
        """loop_complete event includes terminated_by: timeout."""
        from unittest.mock import patch

        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            timeout=5,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                    on_failure="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        start_time = 1000.0
        time_values = [start_time, start_time, start_time + 6.0]
        call_count = [0]

        def mock_time() -> float:
            result = time_values[min(call_count[0], len(time_values) - 1)]
            call_count[0] += 1
            return result

        with patch("little_loops.fsm.executor.time.time", side_effect=mock_time):
            executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
            executor.run()

        loop_complete = next(e for e in events if e["event"] == "loop_complete")
        assert loop_complete["terminated_by"] == "timeout"

    def test_loop_timeout_preserves_state(self) -> None:
        """Loop timeout returns correct final_state and iterations."""
        from unittest.mock import patch

        fsm = FSMLoop(
            name="test",
            initial="step1",
            timeout=5,
            states={
                "step1": StateConfig(action="step1.sh", next="step2"),
                "step2": StateConfig(action="step2.sh", next="step1"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        start_time = 1000.0
        # Allow 2 iterations before timeout
        time_values = [
            start_time,  # run() start
            start_time,  # first timeout check
            start_time + 1.0,  # second timeout check
            start_time + 6.0,  # third timeout check (exceeds 5s)
        ]
        call_count = [0]

        def mock_time() -> float:
            result = time_values[min(call_count[0], len(time_values) - 1)]
            call_count[0] += 1
            return result

        with patch("little_loops.fsm.executor.time.time", side_effect=mock_time):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.terminated_by == "timeout"
        assert result.iterations == 2
        # After step1 -> step2 -> would go to step1, but timeout occurs
        assert result.final_state == "step1"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v -k "test_loop_timeout"`

---

### Phase 3: Final Verification

#### Overview
Run full test suite to ensure no regressions and all acceptance criteria are met.

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v -k TestTimeoutHandling`
- [ ] Full executor tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Test exit code 124 routing with mock action runner
- Test event emission with exit code 124
- Test capture of timeout results
- Test loop timeout with mocked time

### Key Edge Cases
- Exit code 124 is mapped by `evaluate_exit_code()` to "error" verdict (not "failure")
- Loop timeout check happens before state execution, not after
- Timeout with multiple iterations to verify state preservation

## References

- Original issue: `.issues/enhancements/P2-ENH-062-ll-loop-timeout-handling-tests.md`
- Timeout handling: `scripts/little_loops/fsm/executor.py:140-159`, `227-230`
- Mock patterns: `scripts/tests/test_fsm_executor.py:21-80`
- Time mocking pattern: `scripts/tests/test_subprocess_utils.py:535-599`
