"""Tests for FSM Executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import (
    ActionResult,
    ExecutionResult,
    FSMExecutor,
)
from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)


@dataclass
class MockActionRunner:
    """Mock action runner for testing."""

    results: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    call_index: int = 0
    calls: list[str] = field(default_factory=list)
    default_result: dict[str, Any] = field(
        default_factory=lambda: {"output": "", "stderr": "", "exit_code": 0}
    )

    use_indexed_order: bool = False

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Return configured result for action."""
        # Suppress unused variable warnings - these match the Protocol signature
        del timeout, is_slash_command
        self.calls.append(action)

        # Use indexed results in order (when results were set as a list)
        if self.use_indexed_order and self.call_index < len(self.results):
            _, result_data = self.results[self.call_index]
            self.call_index += 1
            return ActionResult(
                output=result_data.get("output", ""),
                stderr=result_data.get("stderr", ""),
                exit_code=result_data.get("exit_code", 0),
                duration_ms=result_data.get("duration_ms", 100),
            )

        # Check for specific result by pattern
        for pattern, result_data in self.results:
            if pattern in action or pattern == action:
                return ActionResult(
                    output=result_data.get("output", ""),
                    stderr=result_data.get("stderr", ""),
                    exit_code=result_data.get("exit_code", 0),
                    duration_ms=result_data.get("duration_ms", 100),
                )

        return ActionResult(
            output=self.default_result.get("output", ""),
            stderr=self.default_result.get("stderr", ""),
            exit_code=self.default_result.get("exit_code", 0),
            duration_ms=self.default_result.get("duration_ms", 100),
        )

    def set_result(self, action: str, **kwargs: Any) -> None:
        """Set result for a specific action pattern."""
        self.results.append((action, kwargs))

    def always_return(self, **kwargs: Any) -> None:
        """Set default result for all actions."""
        self.default_result = kwargs


class TestFSMExecutorBasic:
    """Basic executor tests."""

    def test_simple_success_path(self) -> None:
        """check → done on first success."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix",
                ),
                "done": StateConfig(terminal=True),
                "fix": StateConfig(action="fix.sh", next="check"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("pytest", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert result.terminated_by == "terminal"
        assert "pytest" in mock_runner.calls

    def test_fix_retry_loop(self) -> None:
        """check → fix → check → done with retry."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix",
                ),
                "fix": StateConfig(action="fix.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        # First check fails, fix succeeds, second check passes
        mock_runner.results = [
            ("pytest", {"exit_code": 1}),
            ("fix.sh", {"exit_code": 0}),
            ("pytest", {"exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 3
        assert result.terminated_by == "terminal"

    def test_max_iterations_respected(self) -> None:
        """Loop terminates at max_iterations."""
        fsm = FSMLoop(
            name="test",
            initial="loop",
            max_iterations=3,
            states={
                "loop": StateConfig(
                    action="fail.sh",
                    on_success="done",
                    on_failure="loop",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"

    def test_unconditional_next_transition(self) -> None:
        """State with 'next' transitions unconditionally."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            states={
                "step1": StateConfig(action="echo step1", next="step2"),
                "step2": StateConfig(action="echo step2", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 2
        assert len(mock_runner.calls) == 2

    def test_no_action_state(self) -> None:
        """State without action proceeds to routing."""
        fsm = FSMLoop(
            name="test",
            initial="decide",
            states={
                "decide": StateConfig(on_success="done"),  # No action
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert len(mock_runner.calls) == 0


class TestVariableInterpolation:
    """Tests for variable interpolation in executor."""

    def test_context_interpolation(self) -> None:
        """${context.*} resolves in action."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            context={"target_dir": "src/"},
            states={
                "check": StateConfig(
                    action="mypy ${context.target_dir}",
                    on_success="done",
                    on_failure="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert "mypy src/" in mock_runner.calls

    def test_state_iteration_interpolation(self) -> None:
        """${state.iteration} resolves correctly."""
        fsm = FSMLoop(
            name="test",
            initial="log",
            max_iterations=2,
            states={
                "log": StateConfig(
                    action="echo iteration ${state.iteration}",
                    on_success="log",
                    on_failure="log",
                ),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Iteration is 1-based
        assert "echo iteration 1" in mock_runner.calls
        assert "echo iteration 2" in mock_runner.calls


class TestCapture:
    """Tests for output capture."""

    def test_capture_stores_output(self) -> None:
        """capture: saves action result."""
        fsm = FSMLoop(
            name="test",
            initial="measure",
            states={
                "measure": StateConfig(
                    action="count.sh",
                    capture="errors",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output="42", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert "errors" in result.captured
        assert result.captured["errors"]["output"] == "42"
        assert result.captured["errors"]["exit_code"] == 0

    def test_multiple_captures(self) -> None:
        """Multiple states can capture different values."""
        fsm = FSMLoop(
            name="test",
            initial="count_errors",
            states={
                "count_errors": StateConfig(
                    action="count_errors.sh",
                    capture="errors",
                    next="count_warnings",
                ),
                "count_warnings": StateConfig(
                    action="count_warnings.sh",
                    capture="warnings",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("count_errors.sh", output="5")
        mock_runner.set_result("count_warnings.sh", output="10")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.captured["errors"]["output"] == "5"
        assert result.captured["warnings"]["output"] == "10"


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
        # Exit code 1 -> failure verdict -> routes to report
        mock_runner.results = [
            ("check.sh", {"output": "", "exit_code": 1}),
            ("echo", {"output": "Exit was: 1", "exit_code": 0}),
        ]
        mock_runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        # Verify exit code was interpolated
        assert 'echo "Exit was: 1"' in mock_runner.calls[1]

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

    def test_missing_capture_returns_error(self) -> None:
        """Referencing non-existent capture returns error in result."""
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
        result = executor.run()

        # Executor catches interpolation error and returns it
        assert result.terminated_by == "error"
        assert result.error is not None
        assert "not found in captured" in result.error

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


class TestRouting:
    """Tests for verdict routing."""

    def test_full_route_table(self) -> None:
        """Full route table with custom verdicts."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    evaluate=EvaluateConfig(
                        type="output_contains",
                        pattern="BLOCKED",
                    ),
                    route=RouteConfig(
                        routes={"success": "done", "failure": "blocked"},
                    ),
                ),
                "done": StateConfig(terminal=True),
                "blocked": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", output="BLOCKED: need help", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Pattern found = success, routes to "done"
        assert result.final_state == "done"

    def test_route_default(self) -> None:
        """Route default catches unmatched verdicts."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    route=RouteConfig(
                        routes={"success": "done"},
                        default="fallback",
                    ),
                ),
                "done": StateConfig(terminal=True),
                "fallback": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=1)  # failure verdict

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "fallback"

    def test_current_state_token(self) -> None:
        """$current token routes back to current state."""
        fsm = FSMLoop(
            name="test",
            initial="retry",
            max_iterations=3,
            states={
                "retry": StateConfig(
                    action="flaky.sh",
                    on_success="done",
                    on_failure="$current",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"

    def test_no_valid_route_terminates_with_error(self) -> None:
        """Missing route causes error termination."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                    # No on_failure route
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.terminated_by == "error"
        assert result.error == "No valid transition"


class TestEvents:
    """Tests for event emission."""

    def test_events_emitted(self) -> None:
        """Event callback receives all lifecycle events."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_success="done",
                    on_failure="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
        executor.run()

        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "action_start" in event_types
        assert "action_complete" in event_types
        assert "evaluate" in event_types
        assert "route" in event_types
        assert "loop_complete" in event_types

    def test_event_includes_timestamp(self) -> None:
        """All events include timestamp."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(action="test.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()

        executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
        executor.run()

        for event in events:
            assert "ts" in event

    def test_loop_complete_event_details(self) -> None:
        """loop_complete event includes final state and iteration count."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test-loop",
            initial="check",
            states={
                "check": StateConfig(action="test.sh", on_success="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
        executor.run()

        complete_event = next(e for e in events if e["event"] == "loop_complete")
        assert complete_event["final_state"] == "done"
        assert complete_event["iterations"] == 1
        assert complete_event["terminated_by"] == "terminal"


class TestMaintainMode:
    """Tests for maintain mode."""

    def test_maintain_restarts_after_terminal(self) -> None:
        """maintain: true restarts from initial after terminal."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            maintain=True,
            max_iterations=3,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                    on_failure="check",
                ),
                "done": StateConfig(terminal=True, on_maintain="check"),
            },
        )
        mock_runner = MockActionRunner()
        # All succeed, so should restart from check due to maintain mode
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Should hit max_iterations due to restart cycle
        assert result.terminated_by == "max_iterations"
        assert result.iterations == 3

    def test_maintain_uses_on_maintain_target(self) -> None:
        """on_maintain specifies restart target."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            maintain=True,
            max_iterations=3,
            states={
                "start": StateConfig(action="start.sh", next="check"),
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                ),
                "done": StateConfig(terminal=True, on_maintain="check"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Should restart from "check" (on_maintain), not "start" (initial)
        # Calls: start.sh, check.sh, check.sh (restart), check.sh (restart)
        assert result.terminated_by == "max_iterations"


class TestEvaluators:
    """Tests for evaluator integration."""

    def test_exit_code_evaluator(self) -> None:
        """Exit code evaluator maps codes correctly."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_success="pass",
                    on_failure="fail",
                    on_error="error",
                ),
                "pass": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )

        # Test exit code 0 -> success
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=0)
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "pass"

        # Test exit code 1 -> failure
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=1)
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "fail"

        # Test exit code 2+ -> error
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=2)
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "error"

    def test_output_numeric_evaluator(self) -> None:
        """Output numeric evaluator compares values."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="count.sh",
                    evaluate=EvaluateConfig(
                        type="output_numeric",
                        operator="eq",
                        target=0,
                    ),
                    on_success="done",
                    on_failure="fix",
                ),
                "done": StateConfig(terminal=True),
                "fix": StateConfig(terminal=True),
            },
        )

        # Test value equals target -> success
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output="0")
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

        # Test value not equal -> failure
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output="5")
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "fix"

    def test_output_contains_evaluator(self) -> None:
        """Output contains evaluator matches patterns."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="grep.sh",
                    evaluate=EvaluateConfig(
                        type="output_contains",
                        pattern="SUCCESS",
                    ),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        # Test pattern found -> success
        mock_runner = MockActionRunner()
        mock_runner.set_result("grep.sh", output="Test result: SUCCESS")
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

        # Test pattern not found -> failure
        mock_runner = MockActionRunner()
        mock_runner.set_result("grep.sh", output="Test result: FAILED")
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "retry"

    def test_output_json_evaluator_determines_state(self) -> None:
        """output_json evaluator extracts field and routes state."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="api.sh",
                    evaluate=EvaluateConfig(
                        type="output_json",
                        path=".status",
                        operator="eq",
                        target="ready",
                    ),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        # Test string value matches -> success
        mock_runner = MockActionRunner()
        mock_runner.set_result("api.sh", output='{"status": "ready", "count": 5}')
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

        # Test string value doesn't match -> failure
        mock_runner = MockActionRunner()
        mock_runner.set_result("api.sh", output='{"status": "pending", "count": 5}')
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "retry"

    def test_output_json_nested_path(self) -> None:
        """output_json handles nested JSON paths."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="result.sh",
                    evaluate=EvaluateConfig(
                        type="output_json",
                        path=".data.items.0.value",
                        operator="eq",
                        target=42,
                    ),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result(
            "result.sh",
            output='{"data": {"items": [{"value": 42}, {"value": 100}]}}',
        )
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

    def test_output_json_numeric_comparison(self) -> None:
        """output_json uses numeric comparison for numeric values."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="count.sh",
                    evaluate=EvaluateConfig(
                        type="output_json",
                        path=".count",
                        operator="lt",
                        target=10,
                    ),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        # count=5 < 10 -> success
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output='{"count": 5}')
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

        # count=15 not < 10 -> failure
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output='{"count": 15}')
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "retry"

    def test_convergence_evaluator_detects_target(self) -> None:
        """convergence evaluator returns target verdict when value within tolerance."""
        fsm = FSMLoop(
            name="test",
            initial="optimize",
            states={
                "optimize": StateConfig(
                    action="measure.sh",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        tolerance=1.0,
                        direction="minimize",
                    ),
                    route=RouteConfig(
                        routes={"target": "done", "progress": "optimize", "stall": "stuck"},
                    ),
                ),
                "done": StateConfig(terminal=True),
                "stuck": StateConfig(terminal=True),
            },
        )

        # Value 0.5 within tolerance 1.0 of target 0 -> target verdict
        mock_runner = MockActionRunner()
        mock_runner.set_result("measure.sh", output="0.5")
        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"

    def test_convergence_evaluator_tracks_progress(self) -> None:
        """convergence evaluator tracks progress across iterations."""
        fsm = FSMLoop(
            name="test",
            initial="measure",
            max_iterations=3,
            states={
                "measure": StateConfig(
                    action="count.sh",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        tolerance=0,
                        direction="minimize",
                        previous="${prev.output}",
                    ),
                    route=RouteConfig(
                        routes={"target": "done", "progress": "measure", "stall": "stuck"},
                    ),
                ),
                "done": StateConfig(terminal=True),
                "stuck": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        # Simulate decreasing values: 10 -> 5 -> 0 (progress, progress, target)
        mock_runner.results = [
            ("count.sh", {"output": "10"}),  # First: progress (no previous)
            ("count.sh", {"output": "5"}),  # Second: progress (10 -> 5)
            ("count.sh", {"output": "0"}),  # Third: target reached
        ]
        mock_runner.use_indexed_order = True

        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "done"
        assert result.iterations == 3

    def test_convergence_evaluator_detects_stall(self) -> None:
        """convergence evaluator returns stall when no progress made."""
        fsm = FSMLoop(
            name="test",
            initial="measure",
            max_iterations=2,
            states={
                "measure": StateConfig(
                    action="count.sh",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        tolerance=0,
                        direction="minimize",
                        previous="${prev.output}",
                    ),
                    route=RouteConfig(
                        routes={"target": "done", "progress": "measure", "stall": "stuck"},
                    ),
                ),
                "done": StateConfig(terminal=True),
                "stuck": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        # No progress: 10 -> 10 (stall)
        mock_runner.results = [
            ("count.sh", {"output": "10"}),  # First: progress (no previous)
            ("count.sh", {"output": "10"}),  # Second: stall (no change)
        ]
        mock_runner.use_indexed_order = True

        result = FSMExecutor(fsm, action_runner=mock_runner).run()
        assert result.final_state == "stuck"
        assert result.iterations == 2

    def test_llm_structured_evaluator_routes_on_verdict(self) -> None:
        """llm_structured evaluator calls LLM and routes based on verdict."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="deploy.sh",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        prompt="Did the deployment succeed?",
                    ),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        # Create mock LLM response
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {
            "verdict": "success",
            "confidence": 0.95,
            "reason": "Deployment completed successfully",
        }
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_runner = MockActionRunner()
        mock_runner.set_result("deploy.sh", output="Deployed to production")

        with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
            with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_response

                result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "done"
        # Verify LLM was called
        mock_client.messages.create.assert_called_once()

    def test_llm_structured_evaluator_failure_verdict(self) -> None:
        """llm_structured evaluator routes to failure on failure verdict."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_success="done",
                    on_failure="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {
            "verdict": "failure",
            "confidence": 0.9,
            "reason": "Tests failed",
        }
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", output="3 tests failed")

        with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
            with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_response

                result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "retry"

    def test_llm_structured_evaluator_blocked_verdict(self) -> None:
        """llm_structured evaluator routes blocked verdict to configured state."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="deploy.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    route=RouteConfig(
                        routes={
                            "success": "done",
                            "failure": "retry",
                            "blocked": "needs_help",
                        },
                    ),
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
                "needs_help": StateConfig(terminal=True),
            },
        )

        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {
            "verdict": "blocked",
            "confidence": 0.85,
            "reason": "Missing permissions",
        }
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_runner = MockActionRunner()
        mock_runner.set_result("deploy.sh", output="Permission denied")

        with patch("little_loops.fsm.evaluators.ANTHROPIC_AVAILABLE", True):
            with patch("little_loops.fsm.evaluators.anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_anthropic.Anthropic.return_value = mock_client
                mock_client.messages.create.return_value = mock_response

                result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "needs_help"


class TestExecutionResult:
    """Tests for ExecutionResult."""

    def test_to_dict(self) -> None:
        """to_dict() serializes all fields."""
        result = ExecutionResult(
            final_state="done",
            iterations=5,
            terminated_by="terminal",
            duration_ms=1234,
            captured={"errors": {"output": "0"}},
            error=None,
        )

        d = result.to_dict()

        assert d["final_state"] == "done"
        assert d["iterations"] == 5
        assert d["terminated_by"] == "terminal"
        assert d["duration_ms"] == 1234
        assert d["captured"] == {"errors": {"output": "0"}}
        assert "error" not in d

    def test_to_dict_with_error(self) -> None:
        """to_dict() includes error when present."""
        result = ExecutionResult(
            final_state="fix",
            iterations=3,
            terminated_by="error",
            duration_ms=500,
            captured={},
            error="Something went wrong",
        )

        d = result.to_dict()

        assert d["error"] == "Something went wrong"


class TestErrorHandling:
    """Tests for error handling."""

    def test_exception_during_execution_returns_error_result(self) -> None:
        """Exception during execution terminates with error."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_success="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        class FailingRunner:
            def run(self, action: str, timeout: int, is_slash_command: bool) -> ActionResult:
                del action, timeout, is_slash_command
                raise RuntimeError("Connection failed")

        executor = FSMExecutor(fsm, action_runner=FailingRunner())  # type: ignore[arg-type]
        result = executor.run()

        assert result.terminated_by == "error"
        assert "Connection failed" in (result.error or "")


class TestTimeoutHandling:
    """Tests for timeout handling."""

    def test_action_timeout_exit_code_124_routes_to_error(self) -> None:
        """Exit code 124 from action timeout routes to on_error."""
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
        # Exit code 124 is returned on timeout - maps to "error" by default evaluator
        mock_runner.set_result("slow_command.sh", exit_code=124, stderr="Action timed out")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Exit code 124 >= 2, so maps to "error" verdict
        assert result.final_state == "error"
        assert result.terminated_by == "terminal"

    def test_action_timeout_emits_event_with_exit_code_124(self) -> None:
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

    def test_loop_timeout_stops_execution(self) -> None:
        """Loop terminates when total time exceeds timeout."""
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
        # Timeout check happens BEFORE each iteration starts
        # - start_time_ms = first call
        # - iteration 1: check timeout (ok), execute step1, route to step2
        # - iteration 2: check timeout (exceeds), return timeout
        time_values = [
            start_time,  # run() start (start_time_ms)
            start_time,  # first timeout check (ok)
            start_time + 6.0,  # second timeout check (exceeds 5s)
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
        # One iteration completes (step1 -> step2), then timeout before step2 can execute
        assert result.iterations == 1
        # Current state is step2 (routed there after step1 completed)
        assert result.final_state == "step2"


class TestSignalHandling:
    """Tests for graceful shutdown via signal handling."""

    def test_request_shutdown_sets_flag(self) -> None:
        """request_shutdown() sets the internal flag."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm)

        assert executor._shutdown_requested is False
        executor.request_shutdown()
        assert executor._shutdown_requested is True

    def test_shutdown_terminates_before_first_iteration(self) -> None:
        """Shutdown requested before run() starts terminates immediately."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            max_iterations=10,
            states={
                "check": StateConfig(action="pytest", on_success="done", on_failure="check"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.request_shutdown()  # Request shutdown before run

        result = executor.run()

        assert result.terminated_by == "signal"
        assert result.iterations == 0
        assert result.final_state == "check"  # Never moved from initial
        assert len(mock_runner.calls) == 0  # No actions executed

    def test_shutdown_terminates_after_current_iteration(self) -> None:
        """Shutdown during execution completes current iteration then stops."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            max_iterations=10,
            states={
                "step1": StateConfig(action="step1.sh", next="step2"),
                "step2": StateConfig(action="step2.sh", next="step3"),
                "step3": StateConfig(action="step3.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )

        # Track calls and trigger shutdown after first action
        shutdown_executor: FSMExecutor | None = None
        call_count = [0]

        class ShutdownAfterFirstActionRunner:
            calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
            ) -> ActionResult:
                del timeout, is_slash_command
                self.calls.append(action)
                call_count[0] += 1

                # Shutdown after second action completes
                if call_count[0] == 2 and shutdown_executor:
                    shutdown_executor.request_shutdown()

                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=100)

        runner = ShutdownAfterFirstActionRunner()
        executor = FSMExecutor(fsm, action_runner=runner)
        shutdown_executor = executor

        result = executor.run()

        assert result.terminated_by == "signal"
        # Two iterations completed before shutdown was detected
        assert result.iterations == 2
        assert result.final_state == "step3"
        assert len(runner.calls) == 2  # step1.sh and step2.sh executed

    def test_shutdown_emits_loop_complete_event(self) -> None:
        """Shutdown emits loop_complete event with terminated_by=signal."""
        fsm = FSMLoop(
            name="test-signal",
            initial="check",
            states={
                "check": StateConfig(action="check.sh", on_success="done", on_failure="check"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        events: list[dict[str, Any]] = []

        def capture_event(event: dict[str, Any]) -> None:
            events.append(event)

        executor = FSMExecutor(fsm, event_callback=capture_event, action_runner=mock_runner)
        executor.request_shutdown()

        result = executor.run()

        assert result.terminated_by == "signal"

        # Find loop_complete event
        loop_complete_events = [e for e in events if e.get("event") == "loop_complete"]
        assert len(loop_complete_events) == 1
        assert loop_complete_events[0]["terminated_by"] == "signal"

    def test_shutdown_preserves_captured_values(self) -> None:
        """Shutdown preserves captured values from completed iterations."""
        fsm = FSMLoop(
            name="test",
            initial="capture_step",
            max_iterations=10,
            states={
                "capture_step": StateConfig(
                    action="get_value.sh",
                    capture="my_value",
                    next="process_step",
                ),
                "process_step": StateConfig(action="process.sh", next="capture_step"),
            },
        )

        shutdown_executor: FSMExecutor | None = None
        call_count = [0]

        class CaptureAndShutdownRunner:
            calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
            ) -> ActionResult:
                del timeout, is_slash_command
                self.calls.append(action)
                call_count[0] += 1

                # Shutdown after first iteration (capture_step + process_step)
                if call_count[0] == 2 and shutdown_executor:
                    shutdown_executor.request_shutdown()

                if "get_value" in action:
                    return ActionResult(
                        output="captured_data_123", stderr="", exit_code=0, duration_ms=100
                    )
                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=100)

        runner = CaptureAndShutdownRunner()
        executor = FSMExecutor(fsm, action_runner=runner)
        shutdown_executor = executor

        result = executor.run()

        assert result.terminated_by == "signal"
        assert "my_value" in result.captured
        assert result.captured["my_value"]["output"] == "captured_data_123"

    def test_shutdown_checked_before_max_iterations(self) -> None:
        """Shutdown is checked before max_iterations check."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            max_iterations=1,  # Would trigger max_iterations
            states={
                "check": StateConfig(action="check.sh", on_success="done", on_failure="check"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        # Both conditions true: shutdown requested AND at max_iterations
        executor._shutdown_requested = True
        executor.iteration = 1  # At max_iterations

        result = executor.run()

        # Signal takes precedence over max_iterations
        assert result.terminated_by == "signal"

    def test_shutdown_checked_before_timeout(self) -> None:
        """Shutdown is checked before timeout check."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            max_iterations=100,
            timeout=1,  # 1 second timeout
            states={
                "check": StateConfig(action="check.sh", on_success="done", on_failure="check"),
                "done": StateConfig(terminal=True),
            },
        )

        executor = FSMExecutor(fsm)
        executor._shutdown_requested = True
        # Simulate timeout by setting start_time far in the past
        executor.start_time_ms = 0
        executor.started_at = "2024-01-01T00:00:00+00:00"

        # Mock time to return a value that exceeds timeout
        with patch("little_loops.fsm.executor.time.time", return_value=10.0):
            result = executor.run()

        # Signal takes precedence over timeout
        assert result.terminated_by == "signal"
