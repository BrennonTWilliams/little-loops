"""Tests for FSM Executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

        executor = FSMExecutor(
            fsm, event_callback=events.append, action_runner=mock_runner
        )
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

        executor = FSMExecutor(
            fsm, event_callback=events.append, action_runner=mock_runner
        )
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

        executor = FSMExecutor(
            fsm, event_callback=events.append, action_runner=mock_runner
        )
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
            def run(
                self, action: str, timeout: int, is_slash_command: bool
            ) -> ActionResult:
                del action, timeout, is_slash_command
                raise RuntimeError("Connection failed")

        executor = FSMExecutor(fsm, action_runner=FailingRunner())  # type: ignore[arg-type]
        result = executor.run()

        assert result.terminated_by == "error"
        assert "Connection failed" in (result.error or "")
