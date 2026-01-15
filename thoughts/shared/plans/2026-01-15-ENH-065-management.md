# ENH-065: Add Capture-Then-Use Workflow Tests - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-065-ll-loop-capture-workflow-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The variable capture and interpolation system allows one state to capture action output that subsequent states can use via `${captured.X.output}` syntax.

### Key Discoveries
- Capture storage implemented in `scripts/little_loops/fsm/executor.py:364-371`
- Interpolation resolution in `scripts/little_loops/fsm/interpolation.py:78-81`
- Existing capture tests only verify storage, not usage: `scripts/tests/test_fsm_executor.py:259-314`
- MockActionRunner pattern for controlling outputs: `scripts/tests/test_fsm_executor.py:22-81`
- Resume preserves captured values: `scripts/little_loops/fsm/persistence.py:330`

### Gap Analysis
1. `test_capture_stores_output()` - verifies storage only
2. `test_multiple_captures()` - verifies multiple captures stored, not used
3. No test verifies `${captured.X.output}` interpolation in subsequent state actions
4. No test verifies captures persist across resume and remain usable
5. No test verifies error handling for missing capture references

## Desired End State

Comprehensive test coverage for capture-then-use workflow:
- State A captures output, state B uses it in action
- Multiple captures from different states all available
- Captures persist across resume and remain usable
- Clear error message for missing capture reference
- Special characters in captured output handled correctly

### How to Verify
- All new tests pass: `pytest scripts/tests/test_fsm_executor.py -k "Capture" -v`
- Tests actually execute interpolation and verify results in mock calls

## What We're NOT Doing

- Not modifying the capture or interpolation implementation
- Not adding new capture features
- Not changing existing test structure
- Not testing persistence to disk (covered by test_fsm_persistence.py)

## Solution Approach

Add a new test class `TestCaptureWorkflow` to `test_fsm_executor.py` with tests that:
1. Define multi-state FSMs with capture configs
2. Use MockActionRunner with `use_indexed_order=True` for sequential results
3. Verify interpolated values appear in `mock_runner.calls`
4. Test error conditions using pytest.raises

## Implementation Phases

### Phase 1: Add TestCaptureWorkflow Class

#### Overview
Add new test class with capture-then-use workflow tests to `test_fsm_executor.py`.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add new test class after line 314 (end of existing TestCapture class)

```python
class TestCaptureWorkflow:
    """Tests for capture-then-use workflow in execution."""

    def test_captured_output_used_in_next_state(self) -> None:
        """Output captured in state A is interpolated in state B action."""
        fsm = FSMLoop(
            name="test",
            initial="fetch",
            states={
                "fetch": StateConfig(
                    action="echo secret-value-123",
                    capture="token",
                    next="use",
                ),
                "use": StateConfig(
                    action='echo "Using: ${captured.token.output}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.results = [
            ("echo secret-value-123", {"output": "secret-value-123", "exit_code": 0}),
            ("echo", {"output": "Using: secret-value-123", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify the interpolated action was called with the captured value
        assert len(mock_runner.calls) == 2
        assert 'echo "Using: secret-value-123"' in mock_runner.calls[1]

    def test_captured_exit_code_interpolation(self) -> None:
        """Captured exit code can be interpolated in subsequent action."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    capture="result",
                    on_success="done",
                    on_failure="report",
                ),
                "report": StateConfig(
                    action='echo "Exit was: ${captured.result.exit_code}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.results = [
            ("check.sh", {"output": "", "exit_code": 42}),
            ("echo", {"output": "Exit was: 42", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify exit code was interpolated
        assert 'echo "Exit was: 42"' in mock_runner.calls[1]

    def test_multiple_captures_available_in_later_state(self) -> None:
        """Multiple captures from different states all available in final state."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            states={
                "step1": StateConfig(
                    action="first.sh",
                    capture="a",
                    next="step2",
                ),
                "step2": StateConfig(
                    action="second.sh",
                    capture="b",
                    next="step3",
                ),
                "step3": StateConfig(
                    action='echo "${captured.a.output} and ${captured.b.output}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.results = [
            ("first.sh", {"output": "first", "exit_code": 0}),
            ("second.sh", {"output": "second", "exit_code": 0}),
            ("echo", {"output": "first and second", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify both captures were interpolated
        assert 'echo "first and second"' in mock_runner.calls[2]

    def test_missing_capture_raises_interpolation_error(self) -> None:
        """Referencing non-existent capture raises InterpolationError."""
        from little_loops.fsm.interpolation import InterpolationError

        fsm = FSMLoop(
            name="test",
            initial="use",
            states={
                "use": StateConfig(
                    action='echo "${captured.nonexistent.output}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        with pytest.raises(InterpolationError, match="not found in captured"):
            executor.run()

    def test_capture_with_special_characters(self) -> None:
        """Captured output with quotes and newlines handled correctly."""
        fsm = FSMLoop(
            name="test",
            initial="fetch",
            states={
                "fetch": StateConfig(
                    action="get_data.sh",
                    capture="data",
                    next="use",
                ),
                "use": StateConfig(
                    action='process "${captured.data.output}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        # Output with quotes and newlines
        special_output = 'line1\nline2 with "quotes"'
        mock_runner.results = [
            ("get_data.sh", {"output": special_output, "exit_code": 0}),
            ("process", {"output": "processed", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify special characters were interpolated correctly
        assert f'process "{special_output}"' in mock_runner.calls[1]

    def test_captured_stderr_interpolation(self) -> None:
        """Captured stderr can be interpolated."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="command.sh",
                    capture="cmd",
                    on_success="done",
                    on_failure="log_error",
                ),
                "log_error": StateConfig(
                    action='echo "Error: ${captured.cmd.stderr}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.results = [
            ("command.sh", {"output": "", "stderr": "file not found", "exit_code": 1}),
            ("echo", {"output": "Error: file not found", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify stderr was interpolated
        assert 'echo "Error: file not found"' in mock_runner.calls[1]

    def test_captured_duration_interpolation(self) -> None:
        """Captured duration_ms can be interpolated."""
        fsm = FSMLoop(
            name="test",
            initial="measure",
            states={
                "measure": StateConfig(
                    action="slow_task.sh",
                    capture="timing",
                    next="report",
                ),
                "report": StateConfig(
                    action='echo "Took: ${captured.timing.duration_ms}ms"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.results = [
            ("slow_task.sh", {"output": "", "exit_code": 0, "duration_ms": 1500}),
            ("echo", {"output": "Took: 1500ms", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify duration was interpolated
        assert 'echo "Took: 1500ms"' in mock_runner.calls[1]
```

#### Success Criteria

**Automated Verification**:
- [x] Tests pass: `pytest scripts/tests/test_fsm_executor.py::TestCaptureWorkflow -v`
- [x] Lint passes: `ruff check scripts/tests/test_fsm_executor.py`
- [x] Types pass: `mypy scripts/tests/test_fsm_executor.py`

---

### Phase 2: Add Resume Capture Tests

#### Overview
Add tests verifying that captured variables persist across resume and remain usable for interpolation.

#### Changes Required

**File**: `scripts/tests/test_fsm_persistence.py`
**Changes**: Add test to existing `TestPersistentExecutorResume` class or create new class

```python
def test_resume_preserves_captured_for_interpolation(
    self, tmp_loops_dir: Path
) -> None:
    """AC: Captures from before interrupt are usable after resume."""
    # FSM where step2 uses captured value from step1
    fsm = FSMLoop(
        name="capture-resume",
        initial="step1",
        states={
            "step1": StateConfig(
                action="fetch.sh",
                capture="data",
                next="step2",
            ),
            "step2": StateConfig(
                action='use "${captured.data.output}"',
                next="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )

    persistence = StatePersistence("capture-resume", tmp_loops_dir)
    persistence.initialize()

    # Simulate interrupted execution: step1 completed, about to start step2
    state = LoopState(
        loop_name="capture-resume",
        current_state="step2",
        iteration=2,
        captured={"data": {"output": "captured-value", "stderr": "", "exit_code": 0, "duration_ms": 100}},
        prev_result={"output": "captured-value", "stderr": "", "exit_code": 0, "state": "step1"},
        last_result=None,
        started_at="2026-01-15T10:00:00Z",
        updated_at="",
        status="running",
    )
    persistence.save_state(state)

    mock_runner = MockActionRunner()
    mock_runner.always_return(exit_code=0)

    executor = PersistentExecutor(
        fsm, persistence=persistence, action_runner=mock_runner
    )
    result = executor.resume()

    assert result is not None
    # Verify the interpolation used the captured value from before resume
    assert 'use "captured-value"' in mock_runner.calls[0]
```

#### Success Criteria

**Automated Verification**:
- [x] Tests pass: `pytest scripts/tests/test_fsm_persistence.py -k "capture" -v`
- [x] Lint passes: `ruff check scripts/tests/test_fsm_persistence.py`

---

## Testing Strategy

### Unit Tests
- All tests use MockActionRunner to control subprocess results
- Tests verify interpolated values in `mock_runner.calls`
- Tests verify error conditions with `pytest.raises`

### Coverage
- Output interpolation: `${captured.X.output}`
- Exit code interpolation: `${captured.X.exit_code}`
- Stderr interpolation: `${captured.X.stderr}`
- Duration interpolation: `${captured.X.duration_ms}`
- Multiple captures available
- Missing capture error
- Special characters in output
- Resume with captures

## References

- Original issue: `.issues/enhancements/P3-ENH-065-ll-loop-capture-workflow-tests.md`
- Capture storage: `scripts/little_loops/fsm/executor.py:364-371`
- Interpolation resolution: `scripts/little_loops/fsm/interpolation.py:78-81`
- Existing capture tests: `scripts/tests/test_fsm_executor.py:259-314`
- Resume logic: `scripts/little_loops/fsm/persistence.py:314-347`
