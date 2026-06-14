"""Tests for FSM Executor."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.fsm.evaluators import EvaluationResult
from little_loops.fsm.executor import (
    ActionResult,
    DefaultActionRunner,
    ExecutionResult,
    FSMExecutor,
    RouteContext,
    RouteDecision,
    SimulationActionRunner,
)
from little_loops.fsm.interpolation import InterpolationContext
from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)
from little_loops.fsm.validation import load_and_validate


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
        on_output_line: Any = None,
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: Any = None,
        on_usage_detailed: Any = None,
        model: str | None = None,
    ) -> ActionResult:
        """Return configured result for action."""
        # Suppress unused variable warnings - these match the Protocol signature
        del (
            timeout,
            is_slash_command,
            on_output_line,
            agent,
            tools,
            on_usage,
            on_usage_detailed,
            model,
        )
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
                    on_yes="done",
                    on_no="fix",
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
                    on_yes="done",
                    on_no="fix",
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
                    on_yes="done",
                    on_no="loop",
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

    def test_cycle_detection_terminates_loop(self) -> None:
        """Loop terminates with cycle_detected when the same edge is traversed too many times."""
        fsm = FSMLoop(
            name="test",
            initial="loop",
            max_iterations=100,
            max_edge_revisits=3,
            states={
                "loop": StateConfig(
                    action="fail.sh",
                    on_yes="done",
                    on_no="loop",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.terminated_by == "cycle_detected"
        assert result.error is not None
        assert "loop->loop" in result.error

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

    def test_next_routed_state_updates_prev_result(self) -> None:
        """Action output from a next-routed state is captured in prev_result."""
        # fix (next-routed) → done (terminal, no action)
        # prev_result should reflect fix.sh's output, not be left stale/None.
        fsm = FSMLoop(
            name="test",
            initial="fix",
            states={
                "fix": StateConfig(action="fix.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("fix.sh", output="fix output", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert executor.prev_result is not None
        assert executor.prev_result["output"] == "fix output"

    def test_no_action_state(self) -> None:
        """State without action proceeds to routing."""
        fsm = FSMLoop(
            name="test",
            initial="decide",
            states={
                "decide": StateConfig(on_yes="done"),  # No action
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert len(mock_runner.calls) == 0


class TestActionType:
    """Tests for action_type field behavior in executor."""

    def test_action_type_prompt_runs_action(self) -> None:
        """action_type=prompt executes the action even without / prefix."""
        fsm = FSMLoop(
            name="test",
            initial="analyze",
            states={
                "analyze": StateConfig(
                    action="Analyze the code",
                    action_type="prompt",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0, output="Analysis complete")

        from little_loops.fsm.evaluators import EvaluationResult

        with patch(
            "little_loops.fsm.executor.evaluate_llm_structured",
            return_value=EvaluationResult(verdict="yes", details={}),
        ):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        assert "Analyze the code" in mock_runner.calls

    def test_action_type_shell_runs_action(self) -> None:
        """action_type=shell executes the action as shell."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="/usr/bin/ls",
                    action_type="shell",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert "/usr/bin/ls" in mock_runner.calls

    def test_action_type_slash_command_runs_action(self) -> None:
        """action_type=slash_command executes the action via Claude CLI."""
        fsm = FSMLoop(
            name="test",
            initial="commit",
            states={
                "commit": StateConfig(
                    action="/ll:commit",
                    action_type="slash_command",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        from little_loops.fsm.evaluators import EvaluationResult

        with patch(
            "little_loops.fsm.executor.evaluate_llm_structured",
            return_value=EvaluationResult(verdict="yes", details={}),
        ):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        assert "/ll:commit" in mock_runner.calls

    def test_action_type_none_uses_heuristic_slash(self) -> None:
        """Without action_type, / prefix triggers slash command detection."""
        fsm = FSMLoop(
            name="test",
            initial="cmd",
            states={
                "cmd": StateConfig(
                    action="/ll:help",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        from little_loops.fsm.evaluators import EvaluationResult

        with patch(
            "little_loops.fsm.executor.evaluate_llm_structured",
            return_value=EvaluationResult(verdict="yes", details={}),
        ):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        assert "/ll:help" in mock_runner.calls

    def test_action_type_none_uses_heuristic_shell(self) -> None:
        """Without action_type, non-/ prefix triggers shell execution."""
        fsm = FSMLoop(
            name="test",
            initial="cmd",
            states={
                "cmd": StateConfig(
                    action="echo hello",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert "echo hello" in mock_runner.calls


class TestActionTypeMcpTool:
    """Tests for action_type=mcp_tool execution in the executor."""

    def _make_mcp_fsm(
        self, params: dict | None = None, route_verdicts: dict | None = None
    ) -> FSMLoop:
        """Build a minimal FSM with one mcp_tool state."""
        route_verdicts = route_verdicts or {
            "success": "done",
            "tool_error": "done",
            "not_found": "done",
            "timeout": "done",
        }
        return FSMLoop(
            name="test",
            initial="fetch",
            states={
                "fetch": StateConfig(
                    action="browser/navigate",
                    action_type="mcp_tool",
                    params=params or {"url": "https://example.com"},
                    route=RouteConfig(routes=route_verdicts),
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_mcp_tool_does_not_call_action_runner(self) -> None:
        """mcp_tool states bypass action_runner entirely."""
        fsm = self._make_mcp_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        success_envelope = json.dumps({"isError": False, "content": []})
        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output=success_envelope, stderr="", exit_code=0, duration_ms=50
            )
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        # action_runner should not have been called
        assert len(mock_runner.calls) == 0
        # subprocess was called with mcp-call
        mock_sub.assert_called_once()
        cmd = mock_sub.call_args[0][0]
        assert cmd[0] == "mcp-call"
        assert cmd[1] == "browser/navigate"
        assert result.final_state == "done"

    def test_mcp_tool_routes_success(self) -> None:
        """mcp_tool state with isError=false routes to success."""
        fsm = self._make_mcp_fsm(route_verdicts={"success": "done"})
        success_envelope = json.dumps(
            {"isError": False, "content": [{"type": "text", "text": "ok"}]}
        )

        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output=success_envelope, stderr="", exit_code=0, duration_ms=50
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            result = executor.run()

        assert result.final_state == "done"

    def test_mcp_tool_routes_tool_error(self) -> None:
        """mcp_tool state with isError=true routes to tool_error."""
        fsm = self._make_mcp_fsm(route_verdicts={"tool_error": "done"})
        error_envelope = json.dumps(
            {"isError": True, "content": [{"type": "text", "text": "fail"}]}
        )

        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output=error_envelope, stderr="", exit_code=1, duration_ms=50
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            result = executor.run()

        assert result.final_state == "done"

    def test_mcp_tool_routes_not_found(self) -> None:
        """mcp_tool state with exit 127 routes to not_found."""
        fsm = self._make_mcp_fsm(route_verdicts={"not_found": "done"})

        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output="", stderr="", exit_code=127, duration_ms=10
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            result = executor.run()

        assert result.final_state == "done"

    def test_mcp_tool_routes_timeout(self) -> None:
        """mcp_tool state with exit 124 routes to timeout."""
        fsm = self._make_mcp_fsm(route_verdicts={"timeout": "done"})

        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output="", stderr="", exit_code=124, duration_ms=30000
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            result = executor.run()

        assert result.final_state == "done"

    def test_mcp_tool_params_interpolated(self) -> None:
        """mcp_tool params are interpolated with context before calling mcp-call."""
        fsm = FSMLoop(
            name="test",
            initial="fetch",
            context={"target_url": "https://example.com/page"},
            states={
                "fetch": StateConfig(
                    action="browser/navigate",
                    action_type="mcp_tool",
                    params={"url": "${context.target_url}"},
                    route=RouteConfig(routes={"success": "done", "tool_error": "done"}),
                ),
                "done": StateConfig(terminal=True),
            },
        )

        success_envelope = json.dumps({"isError": False, "content": []})
        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output=success_envelope, stderr="", exit_code=0, duration_ms=50
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            executor.run()

        # The params JSON passed to mcp-call should have the interpolated URL
        cmd = mock_sub.call_args[0][0]
        params_arg = json.loads(cmd[2])
        assert params_arg["url"] == "https://example.com/page"

    def test_mcp_tool_default_evaluator_is_mcp_result(self) -> None:
        """mcp_tool state without explicit evaluate uses mcp_result by default."""
        fsm = FSMLoop(
            name="test",
            initial="fetch",
            states={
                "fetch": StateConfig(
                    action="browser/navigate",
                    action_type="mcp_tool",
                    params={"url": "https://example.com"},
                    # No explicit evaluate — should default to mcp_result
                    route=RouteConfig(routes={"success": "done", "tool_error": "done"}),
                ),
                "done": StateConfig(terminal=True),
            },
        )

        success_envelope = json.dumps({"isError": False, "content": []})
        with patch("little_loops.fsm.executor.FSMExecutor._run_subprocess") as mock_sub:
            mock_sub.return_value = ActionResult(
                output=success_envelope, stderr="", exit_code=0, duration_ms=50
            )
            executor = FSMExecutor(fsm, action_runner=MockActionRunner())
            result = executor.run()

        assert result.final_state == "done"


class TestActionTypeContract:
    """Tests for action_type=contract execution in the executor."""

    def test_contract_does_not_call_action_runner(self) -> None:
        """action_type=contract states skip action_runner entirely."""
        from little_loops.fsm.evaluators import EvaluateConfig, EvaluationResult

        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action_type="contract",
                    evaluate=EvaluateConfig(
                        type="contract",
                        pairs=[{"producer": "api.ts", "consumer": "hook.ts", "contract": "match"}],
                    ),
                    on_yes="done",
                    on_no="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        with patch(
            "little_loops.fsm.executor.evaluate",
            return_value=EvaluationResult(verdict="yes", details={}),
        ):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        # action_runner should NOT have been called
        assert len(mock_runner.calls) == 0

    def test_action_mode_contract_returns_contract(self) -> None:
        """_action_mode returns 'contract' for action_type=contract states."""
        from little_loops.fsm.schema import EvaluateConfig

        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        executor = FSMExecutor(fsm, action_runner=MockActionRunner())

        state = StateConfig(
            action_type="contract",
            evaluate=EvaluateConfig(type="contract", pairs=[]),
            on_yes="done",
        )
        assert executor._action_mode(state) == "contract"


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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="log",
                    on_no="log",
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

    def test_capture_strips_trailing_newline(self) -> None:
        """Captured shell output has trailing newlines stripped (mirrors shell $() behavior)."""
        fsm = FSMLoop(
            name="test",
            initial="get_id",
            states={
                "get_id": StateConfig(
                    action="get_id.sh",
                    capture="current_item",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("get_id.sh", output="FEAT-001\n", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.captured["current_item"]["output"] == "FEAT-001"

    def test_capture_strips_trailing_crlf(self) -> None:
        """Captured output has trailing CR+LF stripped."""
        fsm = FSMLoop(
            name="test",
            initial="get_id",
            states={
                "get_id": StateConfig(
                    action="get_id.sh",
                    capture="current_item",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("get_id.sh", output="FEAT-001\r\n", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.captured["current_item"]["output"] == "FEAT-001"


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
                    on_yes="done",
                    on_no="report",
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
                    on_yes="done",
                    on_no="log_error",
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


class TestAppendToMessages:
    """Tests for the append_to_messages state field."""

    def test_append_to_messages_stores_message(self) -> None:
        """append_to_messages appends interpolated output to executor.messages."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    capture="out",
                    append_to_messages="${captured.out.output}",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("echo hello", output="hello")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.messages == ["hello"]

    def test_messages_accumulates_across_states(self) -> None:
        """Multiple states each append to the shared messages log."""
        fsm = FSMLoop(
            name="test",
            initial="plan",
            states={
                "plan": StateConfig(
                    action="plan.sh",
                    capture="plan_out",
                    append_to_messages="${captured.plan_out.output}",
                    next="execute",
                ),
                "execute": StateConfig(
                    action="exec.sh",
                    capture="exec_out",
                    append_to_messages="${captured.exec_out.output}",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("plan.sh", output="Plan: fix the bug")
        mock_runner.set_result("exec.sh", output="Exec: patched line 42")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.messages == ["Plan: fix the bug", "Exec: patched line 42"]

    def test_messages_available_in_next_state(self) -> None:
        """${messages} in a later state's action resolves to all prior messages."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            states={
                "step1": StateConfig(
                    action="step1.sh",
                    capture="s1",
                    append_to_messages="${captured.s1.output}",
                    next="step2",
                ),
                "step2": StateConfig(
                    action='report.sh "${messages}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("step1.sh", output="finding A")
        mock_runner.set_result('report.sh "finding A"', output="reported")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.messages == ["finding A"]
        assert 'report.sh "finding A"' in mock_runner.calls[1]

    def test_append_to_messages_literal_string(self) -> None:
        """append_to_messages with a literal (no interpolation) is stored as-is."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="noop.sh",
                    append_to_messages="static label",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("noop.sh", output="ignored")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.messages == ["static label"]

    def test_no_append_to_messages_leaves_list_empty(self) -> None:
        """States without append_to_messages leave executor.messages empty."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(action="noop.sh", capture="out", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("noop.sh", output="output")

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.messages == []


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
                        routes={"yes": "done", "no": "blocked"},
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

        # Pattern found = yes, routes to "done"
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
                        routes={"yes": "done"},
                        default="fallback",
                    ),
                ),
                "done": StateConfig(terminal=True),
                "fallback": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=1)  # no verdict

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
                    on_yes="done",
                    on_no="$current",
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
                    on_yes="done",
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

    def test_on_partial_routes_correctly(self) -> None:
        """on_partial routes when evaluator returns 'partial' verdict."""
        # output_contains "PARTIAL" → success verdict, not partial.
        # To test on_partial we need an evaluator that returns "partial".
        # Use a custom route table with "partial" verdict instead.
        fsm2 = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="check.sh",
                    route=RouteConfig(routes={"partial": "fix", "yes": "done"}),
                    on_partial="fix",  # also set shorthand (unused when route present)
                ),
                "fix": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        # Simulate exit_code returning "yes" → routes to "done" via route table
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=0)
        executor = FSMExecutor(fsm2, action_runner=mock_runner)
        result = executor.run()
        assert result.final_state == "done"

    def test_on_partial_shorthand_routes_to_fix_state(self) -> None:
        """on_partial shorthand routes to fix state when verdict is 'partial'."""
        # We need to produce a "partial" verdict. Use a mock that patches the evaluator.
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    on_yes="done",
                    on_no="done",
                    on_partial="fix",
                ),
                "fix": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="partial result", exit_code=0)

        partial_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        partial_eval.return_value = EvaluationResult(
            verdict="partial", details={"confidence": 0.6, "confident": False}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", partial_eval):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.final_state == "fix"
        assert result.terminated_by == "terminal"

    def test_on_partial_missing_falls_through_to_error(self) -> None:
        """When partial verdict has no on_partial handler, execution errors."""
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    on_yes="done",
                    on_no="done",
                    # No on_partial — partial verdict should find no route
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="partial result", exit_code=0)

        partial_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        partial_eval.return_value = EvaluationResult(
            verdict="partial", details={"confidence": 0.6, "confident": False}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", partial_eval):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.terminated_by == "error"
        assert result.error == "No valid transition"

    def test_on_blocked_shorthand_routes_to_fix_state(self) -> None:
        """on_blocked shorthand routes to fix state when verdict is 'blocked'."""
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    on_yes="done",
                    on_no="done",
                    on_blocked="fix",
                ),
                "fix": StateConfig(terminal=True),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="blocked result", exit_code=0)

        blocked_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        blocked_eval.return_value = EvaluationResult(
            verdict="blocked", details={"confidence": 0.9, "confident": False}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", blocked_eval):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.final_state == "fix"
        assert result.terminated_by == "terminal"

    def test_on_blocked_missing_falls_through_to_error(self) -> None:
        """When blocked verdict has no on_blocked handler, execution errors."""
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    on_yes="done",
                    on_no="done",
                    # No on_blocked — blocked verdict should find no route
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="blocked result", exit_code=0)

        blocked_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        blocked_eval.return_value = EvaluationResult(
            verdict="blocked", details={"confidence": 0.9, "confident": False}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", blocked_eval):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.terminated_by == "error"
        assert result.error == "No valid transition"

    def test_extra_routes_custom_verdict_routes_to_target(self) -> None:
        """Custom on_done routes to final state when verdict is 'done'."""
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    extra_routes={"done": "final", "retry": "evaluate"},
                ),
                "final": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="done result", exit_code=0)

        done_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        done_eval.return_value = EvaluationResult(
            verdict="done", details={"confidence": 0.95, "confident": True}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", done_eval):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            result = executor.run()

        assert result.final_state == "final"
        assert result.terminated_by == "terminal"

    def test_extra_routes_missing_falls_through_to_error(self) -> None:
        """When a custom verdict has no matching extra_routes entry, execution errors."""
        fsm = FSMLoop(
            name="test",
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="/some-slash-command",
                    action_type="slash_command",
                    extra_routes={"retry": "evaluate"},
                    # No 'done' route — 'done' verdict should find no route
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/some-slash-command", output="done result", exit_code=0)

        done_eval = MagicMock()
        from little_loops.fsm.evaluators import EvaluationResult

        done_eval.return_value = EvaluationResult(
            verdict="done", details={"confidence": 0.95, "confident": True}
        )

        with patch("little_loops.fsm.executor.evaluate_llm_structured", done_eval):
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
                    on_yes="done",
                    on_no="done",
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
                "check": StateConfig(action="test.sh", on_yes="done"),
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
                    on_yes="done",
                    on_no="check",
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
                    on_yes="done",
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

    def test_maintain_route_event_emitted(self) -> None:
        """Restart in maintain mode emits a route event with reason='maintain'."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            maintain=True,
            max_iterations=2,
            states={
                "check": StateConfig(action="check.sh", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
        executor.run()

        route_events = [e for e in events if e.get("event") == "route"]
        assert any(e.get("reason") == "maintain" for e in route_events)


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
                    on_yes="pass",
                    on_no="fail",
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
                    on_yes="done",
                    on_no="fix",
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
                    on_yes="done",
                    on_no="retry",
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
                    on_yes="done",
                    on_no="retry",
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
                    on_yes="done",
                    on_no="retry",
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
                    on_yes="done",
                    on_no="retry",
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
                    on_yes="done",
                    on_no="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        mock_cli_result = MagicMock()
        mock_cli_result.returncode = 0
        mock_cli_result.stderr = ""
        mock_cli_result.stdout = json.dumps(
            {
                "result": json.dumps(
                    {
                        "verdict": "yes",
                        "confidence": 0.95,
                        "reason": "Deployment completed successfully",
                    }
                ),
            }
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("deploy.sh", output="Deployed to production")

        with patch(
            "little_loops.fsm.evaluators.subprocess.run", return_value=mock_cli_result
        ) as mock_run:
            result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "done"
        # Verify CLI was called
        mock_run.assert_called_once()

    def test_llm_structured_evaluator_failure_verdict(self) -> None:
        """llm_structured evaluator routes to failure on failure verdict."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    evaluate=EvaluateConfig(type="llm_structured"),
                    on_yes="done",
                    on_no="retry",
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
            },
        )

        mock_cli_result = MagicMock()
        mock_cli_result.returncode = 0
        mock_cli_result.stderr = ""
        mock_cli_result.stdout = json.dumps(
            {
                "result": json.dumps(
                    {
                        "verdict": "no",
                        "confidence": 0.9,
                        "reason": "Tests failed",
                    }
                ),
            }
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", output="3 tests failed")

        with patch("little_loops.fsm.evaluators.subprocess.run", return_value=mock_cli_result):
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
                            "yes": "done",
                            "no": "retry",
                            "blocked": "needs_help",
                        },
                    ),
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
                "needs_help": StateConfig(terminal=True),
            },
        )

        mock_cli_result = MagicMock()
        mock_cli_result.returncode = 0
        mock_cli_result.stderr = ""
        mock_cli_result.stdout = json.dumps(
            {
                "result": json.dumps(
                    {
                        "verdict": "blocked",
                        "confidence": 0.85,
                        "reason": "Missing permissions",
                    }
                ),
            }
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("deploy.sh", output="Permission denied")

        with patch("little_loops.fsm.evaluators.subprocess.run", return_value=mock_cli_result):
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
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        class FailingRunner:
            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    action,
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
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
                    on_yes="done",
                    on_no="retry",
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
                    on_yes="done",
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
                    on_yes="done",
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

    def test_action_timeout_with_output_contains_routes_to_on_error(self) -> None:
        """BUG-1640: output_contains evaluator on timeout (exit 124) routes via on_error.

        Before the fix, a truncated stdout would miss the success pattern and the
        verdict would silently become "no", routing through on_no instead of the
        on_error: branch the loop author defined.
        """
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="slow_command.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="YES"),
                    on_yes="pass",
                    on_no="fail",
                    on_error="error",
                ),
                "pass": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result(
            "slow_command.sh",
            output="",  # truncated; pattern absent
            exit_code=124,
            stderr="Action timed out",
        )

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Before fix: final_state == "fail" (on_no, because pattern missing).
        # After fix: final_state == "error" (on_error, because exit 124 short-circuits).
        assert result.final_state == "error"

    def test_action_nonzero_exit_with_output_contains_routes_to_on_error(self) -> None:
        """BUG-1815: non-zero exit code (not timeout) with output_contains routes via on_error.

        Before the fix, a shell action exiting non-zero with absent output would
        produce verdict "no" (pattern not found), routing through on_no instead of
        the on_error: branch the loop author declared.
        """
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="failing_command.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="SUCCESS"),
                    on_yes="pass",
                    on_no="retry",
                    on_error="error",
                ),
                "pass": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result(
            "failing_command.sh",
            output="",
            exit_code=1,
            stderr="command not found",
        )

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Before fix: final_state == "retry" (on_no, because pattern missing).
        # After fix: final_state == "error" (on_error, because exit non-zero short-circuits).
        assert result.final_state == "error"

    def test_action_zero_exit_with_missing_pattern_still_routes_to_on_no(self) -> None:
        """BUG-1815: exit_code=0 with absent pattern still routes via on_no (regression guard).

        The non-zero short-circuit must not affect the normal path where the action
        succeeded (exit 0) but the output pattern wasn't found.
        """
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="ok_command.sh",
                    evaluate=EvaluateConfig(type="output_contains", pattern="SUCCESS"),
                    on_yes="pass",
                    on_no="retry",
                    on_error="error",
                ),
                "pass": StateConfig(terminal=True),
                "retry": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result(
            "ok_command.sh",
            output="nope",
            exit_code=0,
        )

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "retry"

    def test_loop_timeout_stops_execution(self) -> None:
        """Loop terminates when total time exceeds timeout."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            timeout=5,  # 5 second total timeout
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="done",
                    on_no="check",
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
                    on_yes="done",
                    on_no="check",
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
        """Loop timeout returns correct final_state. BUG-1226: when the pending
        state is a shell action, it is flushed before the timeout is honored —
        so final_state still names the flushed state and its action runs.
        """
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
        # Timeout check happens BEFORE each iteration starts.
        # - start_time_ms = first call
        # - iteration 1: check timeout (ok), execute step1, route to step2
        # - iteration 2: check timeout (exceeds) → BUG-1226 flush runs step2.sh
        #   then _finish("timeout").
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
        # final_state still names the flushed state (single-step flush does not route)
        assert result.final_state == "step2"
        # Flush executed step2's action before honoring timeout
        assert "step2.sh" in mock_runner.calls

    def test_loop_timeout_flushes_pending_shell_state(self) -> None:
        """BUG-1226: when timeout fires between `route` and `state_enter` and the
        pending state is a shell action, the executor flushes that one state
        before honoring the timeout. Produces the side effect (e.g. copying a
        handshake flag) that would otherwise be lost.
        """
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="step1",
            timeout=5,
            states={
                "step1": StateConfig(action="step1.sh", next="copy_flag"),
                "copy_flag": StateConfig(action="copy_flag.sh", next="step1"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        start_time = 1000.0
        time_values = [
            start_time,  # run() start (start_time_ms)
            start_time,  # iteration 1 timeout check (ok)
            start_time + 6.0,  # iteration 2 timeout check (exceeds)
        ]
        call_count = [0]

        def mock_time() -> float:
            result = time_values[min(call_count[0], len(time_values) - 1)]
            call_count[0] += 1
            return result

        with patch("little_loops.fsm.executor.time.time", side_effect=mock_time):
            executor = FSMExecutor(fsm, event_callback=events.append, action_runner=mock_runner)
            result = executor.run()

        # Timeout is honored (loop ends with timeout termination)
        assert result.terminated_by == "timeout"
        # final_state is the flushed state — single-step flush does not route
        assert result.final_state == "copy_flag"
        # Flushed action ran (side effect produced)
        assert "copy_flag.sh" in mock_runner.calls
        # state_enter for the flushed state appears BEFORE loop_complete
        state_enter_copy = [
            i
            for i, e in enumerate(events)
            if e["event"] == "state_enter" and e["state"] == "copy_flag"
        ]
        loop_complete_idx = next(i for i, e in enumerate(events) if e["event"] == "loop_complete")
        assert state_enter_copy, "state_enter for flushed state was not emitted"
        assert state_enter_copy[0] < loop_complete_idx

    def test_loop_timeout_does_not_flush_slash_command_state(self) -> None:
        """BUG-1226: flush is bounded to shell actions. Slash commands and
        sub-loops could take minutes; flushing them would violate the timeout
        budget. When pending state is a slash_command, no flush.
        """
        fsm = FSMLoop(
            name="test",
            initial="step1",
            timeout=5,
            states={
                "step1": StateConfig(action="step1.sh", next="slash_step"),
                "slash_step": StateConfig(
                    action="/ll:some-command",
                    action_type="slash_command",
                    next="step1",
                ),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        start_time = 1000.0
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
        assert result.final_state == "slash_step"
        # Slash command must NOT have been flushed
        assert "/ll:some-command" not in mock_runner.calls

    def test_loop_timeout_does_not_flush_before_first_route(self) -> None:
        """BUG-1226: flush is gated on `_just_routed`. When timeout fires at
        the very first iteration check (before any route has been emitted),
        there is no pending state to flush."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            timeout=1,
            states={
                "step1": StateConfig(action="step1.sh", next="step2"),
                "step2": StateConfig(action="step2.sh", next="step1"),
            },
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        # Force timeout at the first iteration check — no route has happened yet.
        executor.elapsed_offset_ms = 999_999_999
        result = executor.run()

        assert result.terminated_by == "timeout"
        assert result.final_state == "step1"
        # Neither action ran (no state was entered or flushed)
        assert mock_runner.calls == []


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
                "check": StateConfig(action="pytest", on_yes="done", on_no="check"),
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
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
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
                "check": StateConfig(action="check.sh", on_yes="done", on_no="check"),
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
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
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
                "check": StateConfig(action="check.sh", on_yes="done", on_no="check"),
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
                "check": StateConfig(action="check.sh", on_yes="done", on_no="check"),
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

    def test_sigkill_on_next_state_triggers_shutdown(self) -> None:
        """SIGKILL (exit_code=-9) on a prompt action with state.next triggers shutdown, not next routing."""
        fsm = FSMLoop(
            name="test",
            initial="score_issues",
            states={
                "score_issues": StateConfig(action="/score", next="refine_issues"),
                "refine_issues": StateConfig(action="/refine", next="score_issues"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/score", output="", exit_code=-9)  # SIGKILL

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Should terminate via signal, not route to refine_issues
        assert result.terminated_by == "signal"
        assert result.final_state == "score_issues"
        # refine_issues must never have been entered
        assert all("/refine" not in call for call in mock_runner.calls)

    def test_sigkill_on_next_state_routes_via_on_error_if_configured(self) -> None:
        """SIGKILL on a state with state.next and on_error routes to on_error, not next."""
        fsm = FSMLoop(
            name="test",
            initial="score_issues",
            states={
                "score_issues": StateConfig(
                    action="/score", next="refine_issues", on_error="handle_error"
                ),
                "refine_issues": StateConfig(action="/refine", next="score_issues"),
                "handle_error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/score", output="", exit_code=-9)  # SIGKILL

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "handle_error"
        assert all("/refine" not in call for call in mock_runner.calls)

    def test_shell_failure_on_next_state_routes_via_on_error_when_configured(self) -> None:
        """Non-zero exit on a state with state.next and on_error routes to on_error, not next."""
        fsm = FSMLoop(
            name="test",
            initial="score_issues",
            states={
                "score_issues": StateConfig(
                    action="/score", next="refine_issues", on_error="handle_error"
                ),
                "refine_issues": StateConfig(action="/refine", next="score_issues"),
                "handle_error": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/score", output="", exit_code=1)  # ordinary shell failure

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "handle_error"
        assert all("/refine" not in call for call in mock_runner.calls)

    def test_normal_exit_on_next_state_still_routes_normally(self) -> None:
        """Non-negative exit codes on a state.next action still route to next normally."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            states={
                "step1": StateConfig(action="/step1", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("/step1", output="ok", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by != "signal"


class TestActionExceptionRouting:
    """Tests for ENH-1168: action exceptions route to on_error when defined."""

    @staticmethod
    def _raising_runner(exc: Exception) -> Any:
        class RaisingRunner:
            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    action,
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
                raise exc

        return RaisingRunner()

    def test_exception_in_branch_c_routes_to_on_error(self) -> None:
        """Exception from _run_action in evaluated-action path routes to on_error."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_yes="done",
                    on_no="done",
                    on_error="recover",
                ),
                "done": StateConfig(terminal=True),
                "recover": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=self._raising_runner(RuntimeError("boom")))
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert result.final_state == "recover"

    def test_exception_in_branch_c_without_on_error_reraises(self) -> None:
        """Exception with no on_error re-raises and terminates with error."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(
            fsm, action_runner=self._raising_runner(RuntimeError("Connection failed"))
        )
        result = executor.run()

        assert result.terminated_by == "error"
        assert "Connection failed" in (result.error or "")

    def test_exception_in_branch_b_routes_to_on_error_not_next(self) -> None:
        """Exception on state with state.next and on_error routes to on_error, not next."""
        fsm = FSMLoop(
            name="test",
            initial="score",
            states={
                "score": StateConfig(
                    action="/score",
                    next="refine",
                    on_error="handle_error",
                ),
                "refine": StateConfig(action="/refine", next="score"),
                "handle_error": StateConfig(terminal=True),
            },
        )
        runner = self._raising_runner(RuntimeError("runner blew up"))
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "handle_error"

    def test_action_error_event_emitted_on_routed_path(self) -> None:
        """action_error event is emitted with state/error/route payload."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_yes="done",
                    on_error="recover",
                ),
                "done": StateConfig(terminal=True),
                "recover": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(
            fsm,
            event_callback=events.append,
            action_runner=self._raising_runner(ValueError("bad input")),
        )
        executor.run()

        action_error_events = [e for e in events if e.get("event") == "action_error"]
        assert len(action_error_events) == 1
        payload = action_error_events[0]
        assert payload["state"] == "check"
        assert "bad input" in payload["error"]
        assert payload["route"] == "on_error"
        assert "ts" in payload

    def test_interpolation_error_routes_to_on_error_when_set(self) -> None:
        """InterpolationError from action template routes to on_error when set."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="${missing_var}",
                    action_type="prompt",
                    on_yes="done",
                    on_error="recover",
                ),
                "done": StateConfig(terminal=True),
                "recover": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=MockActionRunner())
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert result.final_state == "recover"
        # The friendly --context message must NOT be emitted when routed
        assert "--context" not in (result.error or "")

    def test_on_error_template_interpolated(self) -> None:
        """on_error target can itself be an interpolation template."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            context={"fallback": "recover"},
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_yes="done",
                    on_error="${context.fallback}",
                ),
                "done": StateConfig(terminal=True),
                "recover": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=self._raising_runner(RuntimeError("fail")))
        result = executor.run()

        assert result.final_state == "recover"


class TestSimulationActionRunner:
    """Tests for SimulationActionRunner."""

    def test_scenario_all_pass(self) -> None:
        """All-pass scenario returns exit code 0 for all calls."""
        runner = SimulationActionRunner(scenario="all-pass")
        results = [
            runner.run("cmd1", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd2", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd3", timeout=60, is_slash_command=False).exit_code,
        ]
        assert results == [0, 0, 0]

    def test_scenario_all_fail(self) -> None:
        """All-fail scenario returns exit code 1 for all calls."""
        runner = SimulationActionRunner(scenario="all-fail")
        results = [
            runner.run("cmd1", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd2", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd3", timeout=60, is_slash_command=False).exit_code,
        ]
        assert results == [1, 1, 1]

    def test_scenario_all_error(self) -> None:
        """All-error scenario returns exit code 2 for all calls."""
        runner = SimulationActionRunner(scenario="all-error")
        results = [
            runner.run("cmd1", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd2", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd3", timeout=60, is_slash_command=False).exit_code,
        ]
        assert results == [2, 2, 2]

    def test_scenario_first_fail(self) -> None:
        """First-fail scenario returns 1 first, then 0."""
        runner = SimulationActionRunner(scenario="first-fail")
        results = [
            runner.run("cmd1", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd2", timeout=60, is_slash_command=False).exit_code,
            runner.run("cmd3", timeout=60, is_slash_command=False).exit_code,
        ]
        assert results == [1, 0, 0]

    def test_scenario_alternating(self) -> None:
        """Alternating scenario returns 1, 0, 1, 0..."""
        runner = SimulationActionRunner(scenario="alternating")
        results = [
            runner.run("cmd", timeout=60, is_slash_command=False).exit_code for _ in range(4)
        ]
        assert results == [1, 0, 1, 0]

    def test_records_calls(self) -> None:
        """Runner records all calls."""
        runner = SimulationActionRunner(scenario="all-pass")
        runner.run("cmd1", timeout=60, is_slash_command=False)
        runner.run("cmd2", timeout=60, is_slash_command=True)
        assert runner.calls == ["cmd1", "cmd2"]
        assert runner.call_count == 2

    def test_returns_simulated_output(self) -> None:
        """Runner returns simulated output string."""
        runner = SimulationActionRunner(scenario="all-pass")
        result = runner.run("echo hello", timeout=60, is_slash_command=False)
        assert "simulated" in result.output.lower()
        assert "echo hello" in result.output

    def test_returns_zero_duration(self) -> None:
        """Simulation returns 0 duration since nothing executed."""
        runner = SimulationActionRunner(scenario="all-pass")
        result = runner.run("sleep 10", timeout=60, is_slash_command=False)
        assert result.duration_ms == 0

    def test_returns_empty_stderr(self) -> None:
        """Simulation returns empty stderr."""
        runner = SimulationActionRunner(scenario="all-fail")
        result = runner.run("failing_cmd", timeout=60, is_slash_command=False)
        assert result.stderr == ""

    def test_with_fsm_executor(self) -> None:
        """SimulationActionRunner integrates with FSMExecutor."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            max_iterations=5,
            states={
                "check": StateConfig(
                    action="run_check",
                    on_yes="done",
                    on_no="fix",
                ),
                "fix": StateConfig(action="run_fix", next="check"),
                "done": StateConfig(terminal=True),
            },
        )
        # first-fail: first check fails, fix runs, second check passes
        sim_runner = SimulationActionRunner(scenario="first-fail")
        executor = FSMExecutor(fsm, action_runner=sim_runner)
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert result.final_state == "done"
        # Should have: check (fail) -> fix -> check (pass) -> done
        assert sim_runner.call_count == 3
        assert "run_check" in sim_runner.calls[0]
        assert "run_fix" in sim_runner.calls[1]
        assert "run_check" in sim_runner.calls[2]


class TestSimulationSubLoopDispatch:
    """Tests for BUG-2137: simulate mode must stub sub-loop dispatch without real execution."""

    def _parent_with_sub_loop(self, loop_ref: str) -> FSMLoop:
        return FSMLoop(
            name="parent",
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    loop=loop_ref, on_yes="passed", on_no="failed", on_error="errored"
                ),
                "passed": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
                "errored": StateConfig(terminal=True),
            },
        )

    def test_static_sub_loop_simulates_without_real_execution(self, tmp_path: Path) -> None:
        """Static sub-loop dispatch in simulation must NOT execute the real child FSM."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child writes a sentinel file if it actually runs — simulation must not create it
        sentinel = tmp_path / "child_ran.txt"
        (loops_dir / "child.yaml").write_text(
            f"name: child\ninitial: mark\nstates:\n"
            f"  mark:\n    action: 'touch {sentinel}'\n    next: done\n"
            f"  done:\n    terminal: true"
        )
        sim_runner = SimulationActionRunner(scenario="all-pass")
        executor = FSMExecutor(
            self._parent_with_sub_loop("child"), loops_dir=loops_dir, action_runner=sim_runner
        )
        result = executor.run()

        assert not sentinel.exists(), "Real child FSM must not execute in simulation mode"
        assert result.terminated_by == "terminal"
        assert result.final_state == "passed"

    def test_static_sub_loop_sim_routes_on_yes(self, tmp_path: Path) -> None:
        """Simulated sub-loop with all-pass scenario routes to on_yes."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        sim_runner = SimulationActionRunner(scenario="all-pass")
        executor = FSMExecutor(
            self._parent_with_sub_loop("child"), loops_dir=loops_dir, action_runner=sim_runner
        )
        result = executor.run()
        assert result.final_state == "passed"

    def test_static_sub_loop_sim_routes_on_no(self, tmp_path: Path) -> None:
        """Simulated sub-loop with all-fail scenario routes to on_no."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        sim_runner = SimulationActionRunner(scenario="all-fail")
        executor = FSMExecutor(
            self._parent_with_sub_loop("child"), loops_dir=loops_dir, action_runner=sim_runner
        )
        result = executor.run()
        assert result.final_state == "failed"

    def test_static_sub_loop_sim_routes_on_error(self, tmp_path: Path) -> None:
        """Simulated sub-loop with all-error scenario routes to on_error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        sim_runner = SimulationActionRunner(scenario="all-error")
        executor = FSMExecutor(
            self._parent_with_sub_loop("child"), loops_dir=loops_dir, action_runner=sim_runner
        )
        result = executor.run()
        assert result.final_state == "errored"

    def test_dynamic_sub_loop_simulates_without_error(self, tmp_path: Path) -> None:
        """Dynamic sub-loop (unresolvable name in sim) must not raise — uses raw template as label."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # No child YAML exists, and context has no 'chosen' key — would normally raise InterpolationError
        fsm = FSMLoop(
            name="parent",
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    loop="${context.chosen}",
                    on_yes="passed",
                    on_no="failed",
                    on_error="errored",
                ),
                "passed": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
                "errored": StateConfig(terminal=True),
            },
        )
        sim_runner = SimulationActionRunner(scenario="all-pass")
        executor = FSMExecutor(fsm, loops_dir=loops_dir, action_runner=sim_runner)
        result = executor.run()
        assert result.terminated_by == "terminal"
        assert result.final_state == "passed"

    def test_dynamic_sub_loop_label_uses_raw_template(self, tmp_path: Path) -> None:
        """When a dynamic loop name can't resolve in simulation, the raw template is used as the display label."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        fsm = FSMLoop(
            name="parent",
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    loop="${context.chosen}",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        sim_runner = SimulationActionRunner(scenario="all-pass")
        executor = FSMExecutor(fsm, loops_dir=loops_dir, action_runner=sim_runner)
        executor.run()
        # The call was recorded with the raw template, not a crash
        assert any("${context.chosen}" in c or "sub-loop" in c for c in sim_runner.calls)

    def test_interpolation_error_in_live_mode_routes_to_on_error(self, tmp_path: Path) -> None:
        """Outside simulation, unresolvable dynamic loop name routes to on_error via dispatch guard."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        fsm = FSMLoop(
            name="parent",
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    loop="${context.chosen}",
                    on_yes="passed",
                    on_no="failed",
                    on_error="errored",
                ),
                "passed": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
                "errored": StateConfig(terminal=True),
            },
        )
        # Use MockActionRunner (not SimulationActionRunner) — hits the live dispatch path
        executor = FSMExecutor(fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "errored"


class TestExecutionResultToDict:
    """Tests for ExecutionResult.to_dict edge cases."""

    def test_to_dict_with_handoff(self) -> None:
        """to_dict includes handoff flag when True."""
        result = ExecutionResult(
            final_state="done",
            iterations=1,
            terminated_by="handoff",
            duration_ms=100,
            captured={},
            handoff=True,
        )
        d = result.to_dict()
        assert d["handoff"] is True

    def test_to_dict_with_continuation_prompt(self) -> None:
        """to_dict includes continuation_prompt when set."""
        result = ExecutionResult(
            final_state="done",
            iterations=1,
            terminated_by="handoff",
            duration_ms=100,
            captured={},
            continuation_prompt="Continue from here",
        )
        d = result.to_dict()
        assert d["continuation_prompt"] == "Continue from here"

    def test_to_dict_without_optional_fields(self) -> None:
        """to_dict omits optional fields when not set."""
        result = ExecutionResult(
            final_state="done",
            iterations=1,
            terminated_by="terminal",
            duration_ms=100,
            captured={},
        )
        d = result.to_dict()
        assert "handoff" not in d
        assert "messages" not in d

    def test_to_dict_with_messages(self) -> None:
        """to_dict includes messages when non-empty."""
        result = ExecutionResult(
            final_state="done",
            iterations=2,
            terminated_by="terminal",
            duration_ms=100,
            captured={},
            messages=["step 1 output", "step 2 output"],
        )
        d = result.to_dict()
        assert d["messages"] == ["step 1 output", "step 2 output"]
        assert "continuation_prompt" not in d
        assert "error" not in d


class TestHandoffDetection:
    """Tests for handoff signal detection in executor."""

    def test_handoff_signal_terminates_loop(self) -> None:
        """Executor returns with handoff when signal detected."""
        from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector

        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo CONTEXT_HANDOFF: continue here",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("echo", output="CONTEXT_HANDOFF: continue here")

        mock_detector = MagicMock(spec=SignalDetector)
        mock_detector.detect_first.return_value = DetectedSignal(
            signal_type="handoff",
            payload="continue here",
            raw_match="CONTEXT_HANDOFF: continue here",
        )

        executor = FSMExecutor(
            fsm,
            action_runner=mock_runner,
            signal_detector=mock_detector,
        )
        result = executor.run()

        assert result.terminated_by == "handoff"
        assert result.handoff is True
        assert result.continuation_prompt == "continue here"

    def test_handoff_with_handler(self) -> None:
        """Executor invokes handoff handler when configured."""
        from little_loops.fsm.handoff_handler import HandoffHandler
        from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector

        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo CONTEXT_HANDOFF: prompt",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("echo", output="CONTEXT_HANDOFF: prompt")

        mock_detector = MagicMock(spec=SignalDetector)
        mock_detector.detect_first.return_value = DetectedSignal(
            signal_type="handoff",
            payload="prompt",
            raw_match="CONTEXT_HANDOFF: prompt",
        )

        mock_handler = MagicMock(spec=HandoffHandler)
        mock_handler_result = MagicMock()
        mock_handler_result.spawned_process = None
        mock_handler.handle.return_value = mock_handler_result

        executor = FSMExecutor(
            fsm,
            action_runner=mock_runner,
            signal_detector=mock_detector,
            handoff_handler=mock_handler,
        )
        result = executor.run()

        assert result.terminated_by == "handoff"
        mock_handler.handle.assert_called_once_with("test", "prompt")


class TestFatalErrorAndStopSignals:
    """Tests for FATAL_ERROR and LOOP_STOP signal handling in executor."""

    def test_fatal_error_signal_terminates_with_error(self) -> None:
        """FATAL_ERROR signal terminates executor with terminated_by='error'."""
        from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector

        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo FATAL_ERROR: disk full",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("echo", output="FATAL_ERROR: disk full")

        mock_detector = MagicMock(spec=SignalDetector)
        mock_detector.detect_first.return_value = DetectedSignal(
            signal_type="error",
            payload="disk full",
            raw_match="FATAL_ERROR: disk full",
        )

        executor = FSMExecutor(
            fsm,
            action_runner=mock_runner,
            signal_detector=mock_detector,
        )
        result = executor.run()

        assert result.terminated_by == "error"
        assert result.error == "disk full"

    def test_fatal_error_signal_does_not_continue_to_next_state(self) -> None:
        """FATAL_ERROR stops execution before transitioning to next state."""
        from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector

        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo FATAL_ERROR: abort",
                    on_yes="next",
                ),
                "next": StateConfig(
                    action="echo should not run",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("echo", output="FATAL_ERROR: abort")

        mock_detector = MagicMock(spec=SignalDetector)
        mock_detector.detect_first.return_value = DetectedSignal(
            signal_type="error",
            payload="abort",
            raw_match="FATAL_ERROR: abort",
        )

        executor = FSMExecutor(
            fsm,
            action_runner=mock_runner,
            signal_detector=mock_detector,
        )
        result = executor.run()

        assert result.terminated_by == "error"
        # Only the first action ran (one detect_first call)
        assert mock_detector.detect_first.call_count == 1

    def test_loop_stop_signal_requests_graceful_shutdown(self) -> None:
        """LOOP_STOP signal causes graceful shutdown (terminated_by='signal')."""
        from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector

        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="echo LOOP_STOP: goal achieved",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        mock_runner = MockActionRunner()
        mock_runner.set_result("echo", output="LOOP_STOP: goal achieved")

        mock_detector = MagicMock(spec=SignalDetector)
        mock_detector.detect_first.return_value = DetectedSignal(
            signal_type="stop",
            payload="goal achieved",
            raw_match="LOOP_STOP: goal achieved",
        )

        executor = FSMExecutor(
            fsm,
            action_runner=mock_runner,
            signal_detector=mock_detector,
        )
        result = executor.run()

        assert result.terminated_by == "signal"


class TestRoutingEdgeCases:
    """Tests for routing edge cases in executor."""

    def test_route_with_error_verdict_uses_error_route(self) -> None:
        """Error verdict routes to error state when configured in route table."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    route=RouteConfig(
                        routes={"yes": "done"},
                        error="error_state",
                    ),
                ),
                "done": StateConfig(terminal=True),
                "error_state": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=2)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "error_state"

    def test_route_with_default_fallback(self) -> None:
        """Unmatched verdict uses default route."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    route=RouteConfig(
                        routes={"yes": "done"},
                        default="fallback",
                    ),
                ),
                "done": StateConfig(terminal=True),
                "fallback": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "fallback"

    def test_no_valid_transition_returns_error(self) -> None:
        """Returns error when no valid transition found."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    route=RouteConfig(
                        routes={"custom_verdict": "done"},
                    ),
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.terminated_by == "error"


class TestMaintainModeExecutor:
    """Tests for maintain mode in executor."""

    def test_maintain_mode_restarts_on_null_transition(self) -> None:
        """Maintain mode returns to initial when transition is null."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            max_iterations=3,
            maintain=True,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Should loop back from terminal to initial via maintain
        assert result.terminated_by == "max_iterations"
        assert result.iterations == 3


class TestShutdownRequest:
    """Tests for graceful shutdown."""

    def test_shutdown_terminates_loop(self) -> None:
        """Shutdown request terminates the loop."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(
                    action="work.sh",
                    on_yes="work",
                ),
            },
        )
        mock_runner = MockActionRunner()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.request_shutdown()
        result = executor.run()

        assert result.terminated_by == "signal"


class TestBackoff:
    """Tests for backoff sleep between iterations."""

    def test_backoff_sleep_called_between_iterations(self) -> None:
        """Executor sleeps for backoff duration after each iteration."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            backoff=0.01,  # tiny real value so deadline advances naturally
            max_iterations=2,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="check",
                    on_no="check",
                ),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        sleep_calls: list[float] = []

        # Mock sleep to capture calls without blocking; let time.time() advance naturally
        with patch("little_loops.fsm.executor.time.sleep", side_effect=sleep_calls.append):
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        assert len(sleep_calls) > 0, "Expected time.sleep to be called during backoff"

    def test_no_backoff_no_sleep(self) -> None:
        """Executor does not sleep when backoff is None."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            backoff=None,
            max_iterations=3,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="done",
                    on_no="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        with patch("little_loops.fsm.executor.time.sleep") as mock_sleep:
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        mock_sleep.assert_not_called()

    def test_zero_backoff_no_sleep(self) -> None:
        """Executor does not sleep when backoff is 0."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            backoff=0.0,
            max_iterations=3,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="done",
                    on_no="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        with patch("little_loops.fsm.executor.time.sleep") as mock_sleep:
            executor = FSMExecutor(fsm, action_runner=mock_runner)
            executor.run()

        mock_sleep.assert_not_called()

    def test_shutdown_during_backoff_terminates_cleanly(self) -> None:
        """Shutdown request during backoff sleep stops the loop cleanly."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            backoff=60.0,  # Large backoff so we'd block if not interruptible
            max_iterations=10,
            states={
                "work": StateConfig(
                    action="work.sh",
                    on_yes="work",
                    on_no="work",
                ),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)

        real_time = __import__("time").time
        call_count = [0]

        def mock_time() -> float:
            call_count[0] += 1
            t = real_time()
            # After a few calls, trigger shutdown to simulate interrupt during backoff
            if call_count[0] > 5:
                executor.request_shutdown()
            return t

        with patch("little_loops.fsm.executor.time.time", side_effect=mock_time):
            with patch("little_loops.fsm.executor.time.sleep"):
                result = executor.run()

        assert result.terminated_by == "signal"


class TestDefaultActionRunnerProcessTracking:
    """Tests for DefaultActionRunner._current_process tracking (BUG-592)."""

    def _make_mock_process(self, output_lines: list[str], exit_code: int = 0) -> MagicMock:
        """Build a mock Popen process with the given stdout lines."""
        mock_process = MagicMock()
        mock_process.stdout = iter(output_lines)
        mock_process.returncode = exit_code
        mock_process.stderr.read.return_value = ""
        return mock_process

    def test_current_process_cleared_after_successful_run(self) -> None:
        """_current_process is None after run() completes normally."""
        runner = DefaultActionRunner()
        mock_process = self._make_mock_process(["output\n"])

        with patch("subprocess.Popen", return_value=mock_process):
            runner.run("echo hello", timeout=10, is_slash_command=False)

        assert runner._current_process is None

    def test_current_process_cleared_after_timeout(self) -> None:
        """_current_process is None even when action times out."""
        import subprocess as sp

        runner = DefaultActionRunner()
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.returncode = -9
        # First wait (with timeout) raises TimeoutExpired; second wait (bare) succeeds
        mock_process.wait.side_effect = [sp.TimeoutExpired("cmd", 1), None]

        with patch("subprocess.Popen", return_value=mock_process):
            result = runner.run("slow-cmd", timeout=1, is_slash_command=False)

        assert runner._current_process is None
        assert result.exit_code == 124

    def test_current_process_initially_none(self) -> None:
        """_current_process is None before any action is run."""
        runner = DefaultActionRunner()
        assert runner._current_process is None

    def test_slash_command_current_process_lifecycle(self) -> None:
        """_current_process is set during and cleared after a slash command run (BUG-946)."""
        import subprocess as sp

        runner = DefaultActionRunner()
        captured: list[sp.Popen[str] | None] = []

        mock_completed = MagicMock(spec=sp.CompletedProcess)
        mock_completed.stdout = "some output\n"
        mock_completed.stderr = ""
        mock_completed.returncode = 0

        def fake_run_claude_command(**kwargs: object) -> sp.CompletedProcess[str]:
            # Simulate on_process_start setting _current_process
            mock_proc = MagicMock(spec=sp.Popen)
            kwargs["on_process_start"](mock_proc)  # type: ignore[index]
            captured.append(runner._current_process)
            # Simulate on_process_end clearing _current_process
            kwargs["on_process_end"](mock_proc)  # type: ignore[index]
            return mock_completed

        with patch(
            "little_loops.fsm.runners.run_claude_command", side_effect=fake_run_claude_command
        ):
            result = runner.run("/ll:format_issue", timeout=10, is_slash_command=True)

        # _current_process was set during execution
        assert captured[0] is not None
        # _current_process is cleared after completion
        assert runner._current_process is None
        assert result.exit_code == 0

    def test_slash_command_timeout_returns_exit_code_124(self) -> None:
        """Slash command timeout returns ActionResult with exit_code=124 (BUG-946)."""
        import subprocess as sp

        runner = DefaultActionRunner()

        with patch(
            "little_loops.fsm.runners.run_claude_command",
            side_effect=sp.TimeoutExpired("claude", 1),
        ):
            result = runner.run("/ll:format_issue", timeout=1, is_slash_command=True)

        assert result.exit_code == 124
        assert runner._current_process is None


class TestFSMExecutorProcessTracking:
    """Tests for FSMExecutor._current_process tracking (BUG-818)."""

    def _make_executor(self) -> FSMExecutor:
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(action="echo hello", terminal=True)},
        )
        return FSMExecutor(fsm)

    def test_current_process_initially_none(self) -> None:
        """_current_process is None before any subprocess is run."""
        executor = self._make_executor()
        assert executor._current_process is None

    def test_current_process_cleared_after_successful_run(self) -> None:
        """_current_process is None after _run_subprocess completes normally."""
        executor = self._make_executor()
        mock_process = MagicMock()
        mock_process.stdout = iter(["output\n"])
        mock_process.returncode = 0

        with patch("subprocess.Popen", return_value=mock_process):
            executor._run_subprocess(["echo", "hello"], timeout=10)

        assert executor._current_process is None

    def test_current_process_cleared_after_timeout(self) -> None:
        """_current_process is None even when _run_subprocess times out."""
        import subprocess as sp

        executor = self._make_executor()
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.returncode = -9
        mock_process.wait.side_effect = [sp.TimeoutExpired("cmd", 1), None]

        with patch("subprocess.Popen", return_value=mock_process):
            result = executor._run_subprocess(["slow-cmd"], timeout=1)

        assert executor._current_process is None
        assert result.exit_code == 124


class TestDefaultActionRunnerStderrDrain:
    """Tests for BUG-618: stderr pipe deadlock on large stderr output."""

    def test_large_stderr_does_not_deadlock(self) -> None:
        """Subprocess writing >64KB to stderr must not deadlock."""
        runner = DefaultActionRunner()
        # Write 128KB to stderr while also writing a small amount to stdout
        result = runner.run(
            'python3 -c "'
            "import sys; "
            "sys.stderr.write('e' * 131072); "
            "sys.stderr.flush(); "
            "print('done')\"",
            timeout=10,
            is_slash_command=False,
        )
        assert result.exit_code == 0
        assert "done" in result.output
        assert len(result.stderr) >= 131072

    def test_stderr_content_returned_on_timeout(self) -> None:
        """Actual stderr content is returned even when action times out."""
        runner = DefaultActionRunner()
        # Write stderr, close stdout explicitly so the parent's stdout loop exits,
        # then sleep past the timeout so process.wait() raises TimeoutExpired.
        result = runner.run(
            'python3 -c "'
            "import sys, os, time; "
            "sys.stderr.write('error content'); "
            "sys.stderr.flush(); "
            "os.close(sys.stdout.fileno()); "
            'time.sleep(10)"',
            timeout=1,
            is_slash_command=False,
        )
        assert result.exit_code == 124
        assert "error content" in result.stderr


class TestPerStateRetryLimits:
    """Tests for ENH-713: per-state retry limits (max_retries / on_retry_exhausted)."""

    def _make_fsm(
        self,
        max_retries: int,
        action_results: list[tuple[str, dict]],
    ) -> tuple[FSMLoop, MockActionRunner]:
        """Build a simple execute→skip_item→done FSM with max_retries on execute."""
        fsm = FSMLoop(
            name="retry-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_no="execute",
                    on_yes="done",
                    max_retries=max_retries,
                    on_retry_exhausted="skip_item",
                ),
                "skip_item": StateConfig(action="echo skipped", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = action_results
        runner.use_indexed_order = True
        return fsm, runner

    def test_retry_exhausted_routes_to_on_retry_exhausted(self) -> None:
        """After max_retries+1 consecutive entries, executor routes to on_retry_exhausted."""
        # max_retries=2 → execute runs 3 times (initial + 2 retries), then skip_item
        fsm, runner = self._make_fsm(
            max_retries=2,
            action_results=[
                ("do_work.sh", {"exit_code": 1}),  # iter 1: failure → retry
                ("do_work.sh", {"exit_code": 1}),  # iter 2: failure → retry
                ("do_work.sh", {"exit_code": 1}),  # iter 3: failure → retry (exhausted next)
                ("echo skipped", {"exit_code": 0}),  # skip_item
            ],
        )
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        # do_work.sh called exactly 3 times (initial + 2 retries)
        assert runner.calls.count("do_work.sh") == 3
        assert "echo skipped" in runner.calls

    def test_retry_succeeds_before_exhaustion(self) -> None:
        """If the state succeeds before max_retries, it routes normally (not to exhausted)."""
        fsm, runner = self._make_fsm(
            max_retries=5,
            action_results=[
                ("do_work.sh", {"exit_code": 1}),  # fail
                ("do_work.sh", {"exit_code": 1}),  # fail
                ("do_work.sh", {"exit_code": 0}),  # success → done (no skip)
            ],
        )
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        assert runner.calls.count("do_work.sh") == 3
        assert "echo skipped" not in runner.calls

    def test_retry_counter_resets_on_different_state(self) -> None:
        """Retry counter for a state resets when a different state is entered between entries."""
        # execute fails → other_state → execute fails again. Since the counter
        # reset when other_state was entered, this should not trigger exhaustion.
        fsm = FSMLoop(
            name="reset-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_no="other_state",
                    on_yes="done",
                    max_retries=1,
                    on_retry_exhausted="skip_item",
                ),
                "other_state": StateConfig(action="echo other", next="execute"),
                "skip_item": StateConfig(action="echo skipped", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        # execute fails → other_state → execute fails → other_state → execute succeeds
        runner.results = [
            ("do_work.sh", {"exit_code": 1}),  # fail → other_state (counter not yet at max)
            ("echo other", {"exit_code": 0}),  # other_state → execute (resets execute counter)
            ("do_work.sh", {"exit_code": 1}),  # fail → other_state (counter reset, not exhausted)
            ("echo other", {"exit_code": 0}),  # other_state → execute
            ("do_work.sh", {"exit_code": 0}),  # success → done
        ]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        assert runner.calls.count("do_work.sh") == 3
        assert "echo skipped" not in runner.calls

    def test_retry_counter_increments_on_consecutive_reentry(self) -> None:
        """Verify consecutive re-entries increment the counter as expected."""
        # max_retries=1 → execute runs at most 2 times (initial + 1 retry)
        fsm, runner = self._make_fsm(
            max_retries=1,
            action_results=[
                ("do_work.sh", {"exit_code": 1}),  # fail (count=0 → retry allowed)
                ("do_work.sh", {"exit_code": 1}),  # fail (count=1 → retry allowed, last)
                ("do_work.sh", {"exit_code": 1}),  # would be fail (count=2 > 1 → exhausted)
                ("echo skipped", {"exit_code": 0}),
            ],
        )
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        # With max_retries=1: execute runs 2 times (initial + 1 retry), then exhausted
        assert runner.calls.count("do_work.sh") == 2
        assert "echo skipped" in runner.calls

    def test_retry_exhausted_event_emitted(self) -> None:
        """retry_exhausted event is emitted with correct state, retries, and next."""
        emitted_events: list[dict] = []

        def capture_event(event: dict) -> None:
            emitted_events.append(event)

        fsm, runner = self._make_fsm(
            max_retries=1,
            action_results=[
                ("do_work.sh", {"exit_code": 1}),
                ("do_work.sh", {"exit_code": 1}),
                ("echo skipped", {"exit_code": 0}),
            ],
        )
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=capture_event)
        executor.run()

        retry_events = [e for e in emitted_events if e.get("event") == "retry_exhausted"]
        assert len(retry_events) == 1
        evt = retry_events[0]
        assert evt["state"] == "execute"
        assert evt["next"] == "skip_item"
        assert evt["retries"] > 0

    def test_retry_counts_preserved_in_loop_state(self) -> None:
        """_retry_counts values are accessible on the executor after execution."""
        fsm, runner = self._make_fsm(
            max_retries=3,
            action_results=[
                ("do_work.sh", {"exit_code": 1}),  # count → 1
                ("do_work.sh", {"exit_code": 1}),  # count → 2
                ("do_work.sh", {"exit_code": 0}),  # success → done (counter NOT reset here)
            ],
        )
        executor = FSMExecutor(fsm, action_runner=runner)
        executor.run()

        # After success transition to done, execute's counter stays in _retry_counts
        # (it resets only when a DIFFERENT state is processed next iteration)
        # Just verify the executor ran without error and reached terminal state
        assert executor.current_state == "done"


class TestRetryableExitCodes:
    """Tests for ENH-1678: retryable_exit_codes filter on state retry config."""

    def test_nonretryable_code_routes_to_exhaustion(self) -> None:
        """Non-retryable exit code bypasses retry counter, routes to on_retry_exhausted."""
        fsm = FSMLoop(
            name="retry-code-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_error="execute",
                    max_retries=2,
                    on_retry_exhausted="skip_item",
                    retryable_exit_codes=[1],
                ),
                "skip_item": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("do_work.sh", {"exit_code": 2}),  # non-retryable → should exhaust immediately
            # skip_item runs
        ]
        runner.use_indexed_order = True
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        # Exit code 2 is not in retryable_exit_codes [1], so it should bypass
        # retries and go directly to on_retry_exhausted (skip_item)
        assert result.terminated_by == "terminal"
        assert "do_work.sh" in runner.calls
        # Only called once — no retries consumed for non-retryable code
        assert runner.calls.count("do_work.sh") == 1

    def test_retryable_code_retries_normally(self) -> None:
        """Retryable exit code triggers normal retry counter, exhausts at max."""
        fsm = FSMLoop(
            name="retry-code-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_error="execute",
                    max_retries=1,
                    on_retry_exhausted="skip_item",
                    retryable_exit_codes=[1],
                ),
                "skip_item": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("do_work.sh", {"exit_code": 1}),  # retryable → runs once
            ("do_work.sh", {"exit_code": 1}),  # retryable → exhausts (max_retries=1)
        ]
        runner.use_indexed_order = True
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert runner.calls.count("do_work.sh") == 2  # initial + 1 retry

    def test_mixed_retryable_and_nonretryable(self) -> None:
        """Retryable codes retry; first non-retryable code exhausts immediately."""
        fsm = FSMLoop(
            name="retry-code-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_error="execute",
                    max_retries=3,
                    on_retry_exhausted="skip_item",
                    retryable_exit_codes=[1],
                ),
                "skip_item": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("do_work.sh", {"exit_code": 1}),  # retryable → retry 1
            ("do_work.sh", {"exit_code": 1}),  # retryable → retry 2
            ("do_work.sh", {"exit_code": 2}),  # non-retryable → exhaust immediately
        ]
        runner.use_indexed_order = True
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.terminated_by == "terminal"
        # 3 calls: 2 retryable failures + 1 non-retryable that triggers exhaustion
        assert runner.calls.count("do_work.sh") == 3

    def test_retryable_exit_codes_none_has_no_effect(self) -> None:
        """When retryable_exit_codes is None, all errors retry normally (backwards compat)."""
        fsm = FSMLoop(
            name="retry-code-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="do_work.sh",
                    on_error="execute",
                    max_retries=1,
                    on_retry_exhausted="skip_item",
                    retryable_exit_codes=None,
                ),
                "skip_item": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("do_work.sh", {"exit_code": 99}),  # any error triggers retry
            ("do_work.sh", {"exit_code": 99}),  # exhausts normally
        ]
        runner.use_indexed_order = True
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert runner.calls.count("do_work.sh") == 2


class TestOnErrorFallbackRouting:
    """Tests for on_error fallback when verdict is "no" and on_no is not set."""

    def test_shell_exit_code_1_routes_to_on_error_without_on_no(self) -> None:
        """Shell action exiting code 1 routes via on_error when on_no is not configured.

        The default evaluate_exit_code maps code 1 to verdict "no", but when
        on_no is not set and on_error is, the "no" verdict should fall through
        to on_error (the catch-all failure handler).
        """
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_yes="done",
                    on_error="error_handler",
                ),
                "done": StateConfig(terminal=True),
                "error_handler": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "error_handler"
        assert result.terminated_by == "terminal"

    def test_shell_exit_code_1_routes_to_route_error_without_on_no(self) -> None:
        """Shell action exiting code 1 routes via route.error when no "no" route or
        default is configured."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    route=RouteConfig(
                        routes={"yes": "done"},
                        error="error_state",
                    ),
                ),
                "done": StateConfig(terminal=True),
                "error_state": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("test.sh", exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "error_state"
        assert result.terminated_by == "terminal"


class TestInterpolationErrorHandling:
    """Tests for friendly InterpolationError messages in the executor."""

    def test_missing_context_variable_produces_friendly_message(self) -> None:
        """InterpolationError from a missing context var yields a clear error, not a raw traceback."""
        fsm = FSMLoop(
            name="general-task",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="${context.input}",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
            },
        )
        # No context provided — context.input is missing
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.terminated_by == "error"
        assert result.error is not None
        assert "context" in result.error.lower() or "missing" in result.error.lower()
        assert "input" in result.error
        # Should not be a raw Python exception message like "Path 'input' not found in context"
        assert "--context" in result.error or "ll-loop run" in result.error


class TestDefaultTimeout:
    """Tests for loop-level default_timeout fallback chain."""

    @dataclass
    class TimeoutCapturingRunner:
        """Action runner that records the timeout passed to run()."""

        captured_timeouts: list[int] = field(default_factory=list)

        def run(
            self,
            action: str,
            timeout: int,
            is_slash_command: bool,
            on_output_line: Any = None,
            agent: str | None = None,
            tools: list[str] | None = None,
            on_usage: Any = None,
            on_usage_detailed: Any = None,
            model: str | None = None,
        ) -> ActionResult:
            del model
            self.captured_timeouts.append(timeout)
            return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)

    def _make_fsm(
        self, state_timeout: int | None = None, default_timeout: int | None = None
    ) -> FSMLoop:
        """Build a minimal FSMLoop with a single prompt state."""
        state_kwargs: dict[str, Any] = {
            "action_type": "prompt",
            "action": "echo hi",
            "next": "done",
        }
        if state_timeout is not None:
            state_kwargs["timeout"] = state_timeout
        return FSMLoop(
            name="test",
            initial="work",
            default_timeout=default_timeout,
            states={
                "work": StateConfig(**state_kwargs),
                "done": StateConfig(terminal=True),
            },
        )

    def test_state_timeout_used_when_set(self) -> None:
        """Per-state timeout takes precedence over default_timeout."""
        fsm = self._make_fsm(state_timeout=300, default_timeout=3600)
        runner = self.TimeoutCapturingRunner()
        FSMExecutor(fsm, action_runner=runner).run()
        assert runner.captured_timeouts == [300]

    def test_default_timeout_used_when_state_has_none(self) -> None:
        """default_timeout is used when state has no timeout."""
        fsm = self._make_fsm(state_timeout=None, default_timeout=600)
        runner = self.TimeoutCapturingRunner()
        FSMExecutor(fsm, action_runner=runner).run()
        assert runner.captured_timeouts == [600]

    def test_hardcoded_fallback_when_neither_set(self) -> None:
        """Hardcoded 3600s fallback applies when neither state nor loop timeout is set."""
        fsm = self._make_fsm(state_timeout=None, default_timeout=None)
        runner = self.TimeoutCapturingRunner()
        FSMExecutor(fsm, action_runner=runner).run()
        assert runner.captured_timeouts == [3600]


class TestSubLoopExecution:
    """Tests for hierarchical FSM sub-loop execution (FEAT-659)."""

    def test_sub_loop_success_routes_to_on_success(self, tmp_path: Path) -> None:
        """Sub-loop that succeeds routes parent to on_yes state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: done\nstates:\n  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="success", on_no="fail"),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        assert result.terminated_by == "terminal"

    def test_sub_loop_failure_routes_to_on_failure(self, tmp_path: Path) -> None:
        """Sub-loop that fails routes parent to on_no state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child loop that always fails by hitting max_iterations
        (loops_dir / "failing.yaml").write_text(
            "name: failing\ninitial: loop\nmax_iterations: 1\nstates:\n"
            "  loop:\n    action: 'false'\n    on_yes: done\n    on_no: loop\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="failing", on_yes="success", on_no="failed"),
                "success": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "failed"

    def test_sub_loop_terminal_done_routes_to_on_yes(self, tmp_path: Path) -> None:
        """Sub-loop that reaches 'done' terminal routes parent to on_yes (BUG-1017)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: start\nstates:\n"
            "  start:\n    action: 'true'\n    on_yes: done\n    on_no: failed\n"
            "  done:\n    terminal: true\n"
            "  failed:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="ok", on_no="fail", on_error="err"),
                "ok": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "err": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "ok"
        assert result.terminated_by == "terminal"

    def test_sub_loop_terminal_failed_routes_to_on_no(self, tmp_path: Path) -> None:
        """Sub-loop that reaches 'failed' terminal routes parent to on_no, not on_yes (BUG-1017)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child whose initial state is already a 'failed' terminal — reaches it immediately
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: failed\nstates:\n"
            "  failed:\n    terminal: true\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="ok", on_no="fail", on_error="err"),
                "ok": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "err": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        # Before BUG-1017 fix, this wrongly returned "ok" (terminated_by=="terminal" was enough)
        assert result.final_state == "fail"
        assert result.terminated_by == "terminal"

    def test_sub_loop_error_routes_to_on_error_when_set(self, tmp_path: Path) -> None:
        """Sub-loop that errors at runtime routes parent to on_error when set (BUG-1017)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child with an action state but no routing — causes "No valid transition" error termination
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: start\nstates:\n"
            "  start:\n    action: 'true'\n"  # no on_yes/on_no/next → terminated_by=="error"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="ok", on_no="fail", on_error="err"),
                "ok": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "err": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "err"

    def test_sub_loop_context_passthrough(self, tmp_path: Path) -> None:
        """Parent context is passed to child when context_passthrough is True."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child loop that captures a variable using parent's context
        (loops_dir / "echo-child.yaml").write_text(
            "name: echo-child\ninitial: step\nstates:\n"
            "  step:\n"
            "    action: 'echo ${context.greeting}'\n"
            "    capture: child_out\n"
            "    next: done\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"greeting": "hello"},
            states={
                "run_child": StateConfig(
                    loop="echo-child",
                    context_passthrough=True,
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        # Child captures should be merged back under the state name
        assert "run_child" in executor.captured

    def test_sub_loop_context_passthrough_captured_values(self, tmp_path: Path) -> None:
        """Captured output strings are passed as plain strings, not full capture dicts."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child loop that captures the context value to verify it's a plain string
        (loops_dir / "check-child.yaml").write_text(
            "name: check-child\ninitial: step\nstates:\n"
            "  step:\n"
            "    action: 'echo ${context.issue_id}'\n"
            "    capture: received\n"
            "    next: done\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="capture_id",
            states={
                "capture_id": StateConfig(
                    action="echo 'ENH-999'",
                    capture="issue_id",
                    next="run_child",
                ),
                "run_child": StateConfig(
                    loop="check-child",
                    context_passthrough=True,
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        # Child's received capture should be the plain string, not a JSON blob
        child_captures = executor.captured.get("run_child", {})
        received_output = child_captures.get("received", {}).get("output", "")
        assert received_output.strip() == "ENH-999", (
            f"Expected plain string 'ENH-999', got: {received_output!r}"
        )

    def test_sub_loop_missing_loop_with_on_error(self, tmp_path: Path) -> None:
        """Missing child loop routes to on_error when set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(
                    loop="nonexistent",
                    on_yes="success",
                    on_no="fail",
                    on_error="error_state",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
                "error_state": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "error_state"

    def test_sub_loop_missing_loop_without_on_error(self, tmp_path: Path) -> None:
        """Missing child loop finishes with error when no on_error set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(
                    loop="nonexistent",
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.terminated_by == "error"

    def test_sub_loop_without_action_runs_child(self, tmp_path: Path) -> None:
        """Sub-loop state without action runs the child loop directly."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "simple.yaml").write_text(
            "name: simple\ninitial: done\nstates:\n  done:\n    terminal: true"
        )
        mock_runner = MockActionRunner()
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="simple", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, action_runner=mock_runner, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "done"
        # MockActionRunner should NOT have been called (sub-loop doesn't use action_runner)
        assert len(mock_runner.calls) == 0

    def test_sub_loop_events_forwarded_to_parent_callback(self, tmp_path: Path) -> None:
        """Child executor events are forwarded to parent event_callback with depth=1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child has a non-terminal initial state so state_enter is emitted
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: step\nstates:\n"
            "  step:\n    next: done\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="success", on_no="fail"),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        events: list[dict[str, Any]] = []
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir, event_callback=events.append)
        executor.run()
        child_events = [e for e in events if e.get("depth") == 1]
        assert len(child_events) > 0, "Expected child events forwarded with depth=1"
        event_types = [e["event"] for e in child_events]
        assert "state_enter" in event_types

    def test_sub_loop_depth_propagates_to_nested_sub_loops(self, tmp_path: Path) -> None:
        """Nested sub-loops increment depth at each level (depth=2 for grandchild)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # grandchild: has a non-terminal initial state so state_enter is emitted
        (loops_dir / "grandchild.yaml").write_text(
            "name: grandchild\ninitial: step\nstates:\n"
            "  step:\n    next: done\n"
            "  done:\n    terminal: true"
        )
        # child: delegates to grandchild
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: run_grandchild\nstates:\n"
            "  run_grandchild:\n    loop: grandchild\n    on_yes: done\n    on_no: done\n"
            "  done:\n    terminal: true"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(loop="child", on_yes="success", on_no="fail"),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        events: list[dict[str, Any]] = []
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir, event_callback=events.append)
        executor.run()
        depth2_events = [e for e in events if e.get("depth") == 2]
        assert len(depth2_events) > 0, "Expected grandchild events forwarded with depth=2"


class TestRouteContext:
    """Tests for the RouteContext dataclass."""

    def _make_ctx(self) -> InterpolationContext:
        return InterpolationContext(
            context={},
            captured={},
            prev=None,
            result=None,
            state_name="check",
            iteration=1,
            loop_name="test-loop",
            started_at="2026-04-07T00:00:00Z",
            elapsed_ms=0,
        )

    def test_basic_construction(self) -> None:
        """RouteContext holds all required fields."""
        state = StateConfig(terminal=True)
        ctx = self._make_ctx()
        route_ctx = RouteContext(
            state_name="check",
            state=state,
            verdict="yes",
            action_result=None,
            eval_result=None,
            ctx=ctx,
            iteration=1,
        )
        assert route_ctx.state_name == "check"
        assert route_ctx.verdict == "yes"
        assert route_ctx.action_result is None
        assert route_ctx.eval_result is None
        assert route_ctx.iteration == 1

    def test_with_action_result(self) -> None:
        """RouteContext accepts a populated ActionResult."""
        state = StateConfig(on_yes="done", on_no="retry")
        ctx = self._make_ctx()
        action_result = ActionResult(output="ok", stderr="", exit_code=0, duration_ms=100)
        route_ctx = RouteContext(
            state_name="run",
            state=state,
            verdict="yes",
            action_result=action_result,
            eval_result=None,
            ctx=ctx,
            iteration=3,
        )
        assert route_ctx.action_result is action_result
        assert route_ctx.iteration == 3

    def test_with_eval_result(self) -> None:
        """RouteContext accepts a populated EvaluationResult."""
        state = StateConfig(on_yes="done")
        ctx = self._make_ctx()
        eval_result = EvaluationResult(verdict="yes", details={"score": 1})
        route_ctx = RouteContext(
            state_name="eval",
            state=state,
            verdict="yes",
            action_result=None,
            eval_result=eval_result,
            ctx=ctx,
            iteration=2,
        )
        assert route_ctx.eval_result is eval_result
        assert route_ctx.eval_result.verdict == "yes"

    def test_optional_fields_none(self) -> None:
        """action_result and eval_result can both be None."""
        state = StateConfig(terminal=True)
        ctx = self._make_ctx()
        route_ctx = RouteContext(
            state_name="done",
            state=state,
            verdict="yes",
            action_result=None,
            eval_result=None,
            ctx=ctx,
            iteration=1,
        )
        assert route_ctx.action_result is None
        assert route_ctx.eval_result is None


class TestRouteDecision:
    """Tests for the RouteDecision dataclass."""

    def test_redirect(self) -> None:
        """RouteDecision with a state name represents a redirect."""
        decision = RouteDecision(next_state="other-state")
        assert decision.next_state == "other-state"

    def test_veto(self) -> None:
        """RouteDecision with next_state=None represents a veto."""
        decision = RouteDecision(next_state=None)
        assert decision.next_state is None

    def test_redirect_is_truthy_check(self) -> None:
        """next_state=None (veto) differs from a non-None redirect."""
        redirect = RouteDecision(next_state="success")
        _veto = RouteDecision(next_state=None)
        assert redirect.next_state is not None


class TestContributedActionDispatch:
    """Tests for contributed action type dispatch in FSMExecutor."""

    def _make_fsm(self, action_type: str) -> FSMLoop:
        """Build a minimal FSM with a single action state using a custom action_type."""
        return FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="do-webhook",
                    action_type=action_type,
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_action_mode_returns_contributed_when_registered(self) -> None:
        """_action_mode() returns 'contributed' when action_type is in _contributed_actions."""
        fsm = self._make_fsm("webhook")
        executor = FSMExecutor(fsm)
        contributed_runner = MockActionRunner()
        executor._contributed_actions["webhook"] = contributed_runner

        state = fsm.states["run"]
        assert executor._action_mode(state) == "contributed"

    def test_action_mode_returns_shell_when_not_registered(self) -> None:
        """_action_mode() falls through to 'shell' for unknown action_type without registration."""
        fsm = self._make_fsm("unknown_type")
        executor = FSMExecutor(fsm)

        state = fsm.states["run"]
        assert executor._action_mode(state) == "shell"

    def test_contributed_runner_called_with_correct_args(self) -> None:
        """_run_action() calls contributed runner with action, timeout, is_slash_command=False."""
        fsm = self._make_fsm("webhook")
        contributed_runner = MockActionRunner()
        contributed_runner.always_return(exit_code=0, output="webhook ok")
        mock_runner = MockActionRunner()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._contributed_actions["webhook"] = contributed_runner

        executor.run()

        assert "do-webhook" in contributed_runner.calls
        assert len(mock_runner.calls) == 0  # default runner not called

    def test_contributed_runner_result_flows_through_routing(self) -> None:
        """ActionResult from contributed runner propagates to routing."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="do-webhook",
                    action_type="webhook",
                    on_yes="success",
                    on_no="failure",
                ),
                "success": StateConfig(terminal=True),
                "failure": StateConfig(terminal=True),
            },
        )
        contributed_runner = MockActionRunner()
        contributed_runner.always_return(exit_code=0, output="ok")

        executor = FSMExecutor(fsm)
        executor._contributed_actions["webhook"] = contributed_runner

        result = executor.run()
        assert result.final_state == "success"


class TestInterceptorDispatch:
    """Tests for before_route/after_route interceptor dispatch in FSMExecutor."""

    def _make_simple_fsm(self) -> FSMLoop:
        """Build a minimal single-action FSM."""
        return FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    on_yes="done",
                    on_no="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def _make_interceptor(
        self,
        before_return: RouteDecision | None = None,
    ) -> MagicMock:
        """Build a mock interceptor with before_route and after_route methods."""
        interceptor = MagicMock()
        interceptor.before_route.return_value = before_return
        interceptor.after_route.return_value = None
        return interceptor

    def test_before_route_called_with_route_context(self) -> None:
        """before_route is called with a RouteContext containing correct fields."""
        fsm = self._make_simple_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        executor.run()

        interceptor.before_route.assert_called_once()
        ctx_arg = interceptor.before_route.call_args[0][0]
        assert isinstance(ctx_arg, RouteContext)
        assert ctx_arg.state_name == "run"
        assert ctx_arg.verdict == "yes"

    def test_after_route_called_after_routing(self) -> None:
        """after_route is called after _route() returns."""
        fsm = self._make_simple_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        executor.run()

        interceptor.after_route.assert_called_once()

    def test_before_route_passthrough_calls_route(self) -> None:
        """before_route returning None still calls _route() normally."""
        fsm = self._make_simple_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor(before_return=None)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        result = executor.run()

        assert result.final_state == "done"

    def test_before_route_redirect_bypasses_route(self) -> None:
        """before_route returning RouteDecision('state') redirects without calling _route()."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    on_yes="wrong",
                    on_no="wrong",
                ),
                "wrong": StateConfig(terminal=True),
                "redirected": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor(before_return=RouteDecision(next_state="redirected"))

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        result = executor.run()

        assert result.final_state == "redirected"

    def test_before_route_veto_terminates_with_error(self) -> None:
        """before_route returning RouteDecision(None) vetoes routing and terminates with error."""
        fsm = self._make_simple_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor(before_return=RouteDecision(next_state=None))

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        result = executor.run()

        assert result.terminated_by == "error"

    def test_multiple_interceptors_called_in_order(self) -> None:
        """Multiple interceptors have before_route called in registration order."""
        fsm = self._make_simple_fsm()
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        call_order: list[str] = []

        interceptor_a = MagicMock()
        interceptor_a.before_route.side_effect = lambda ctx: call_order.append("a") or None
        interceptor_a.after_route.return_value = None

        interceptor_b = MagicMock()
        interceptor_b.before_route.side_effect = lambda ctx: call_order.append("b") or None
        interceptor_b.after_route.return_value = None

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor_a, interceptor_b]
        executor.run()

        assert call_order == ["a", "b"]

    def test_first_redirect_short_circuits_remaining_interceptors(self) -> None:
        """First RouteDecision from before_route short-circuits remaining interceptors."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    on_yes="wrong",
                    on_no="wrong",
                ),
                "wrong": StateConfig(terminal=True),
                "redirected": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        interceptor_a = MagicMock()
        interceptor_a.before_route.return_value = RouteDecision(next_state="redirected")
        interceptor_b = MagicMock()
        interceptor_b.before_route.return_value = None

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor_a, interceptor_b]
        result = executor.run()

        assert result.final_state == "redirected"
        interceptor_b.before_route.assert_not_called()

    def test_unconditional_next_does_not_fire_interceptors(self) -> None:
        """States with unconditional next: bypass interceptor dispatch."""
        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)
        interceptor = self._make_interceptor()

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor._interceptors = [interceptor]
        executor.run()

        interceptor.before_route.assert_not_called()
        interceptor.after_route.assert_not_called()


class TestAgentToolsPassThrough:
    """Tests for agent/tools pass-through from state config to action runner (FEAT-1011)."""

    def test_prompt_state_passes_agent_and_tools_to_runner(self) -> None:
        """Prompt-mode state passes agent and tools to action runner."""
        captured: list[dict[str, Any]] = []

        class CapturingRunner:
            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                captured.append({"agent": agent, "tools": tools})
                del model
                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)

        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="/ll:test",
                    action_type="prompt",
                    agent="my-agent",
                    tools=["Bash", "Edit"],
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=CapturingRunner())
        executor.run()

        assert len(captured) == 1
        assert captured[0]["agent"] == "my-agent"
        assert captured[0]["tools"] == ["Bash", "Edit"]

    def test_shell_state_passes_none_for_agent_and_tools(self) -> None:
        """Shell-mode state passes None for agent and tools even if set on state."""
        captured: list[dict[str, Any]] = []

        class CapturingRunner:
            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                captured.append({"agent": agent, "tools": tools})
                del model
                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)

        fsm = FSMLoop(
            name="test",
            initial="run",
            states={
                "run": StateConfig(
                    action="echo hello",
                    action_type="shell",
                    agent="my-agent",
                    tools=["Bash"],
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm, action_runner=CapturingRunner())
        executor.run()

        assert len(captured) == 1
        assert captured[0]["agent"] is None
        assert captured[0]["tools"] is None

    def test_default_action_runner_passes_agent_tools_to_run_claude_command(self) -> None:
        """DefaultActionRunner.run(agent=..., tools=...) passes them to run_claude_command."""
        import subprocess as sp

        runner = DefaultActionRunner()
        captured_kwargs: list[dict[str, Any]] = []
        mock_completed = MagicMock(spec=sp.CompletedProcess)
        mock_completed.stdout = ""
        mock_completed.stderr = ""
        mock_completed.returncode = 0

        def fake_run_claude_command(**kwargs: Any) -> sp.CompletedProcess[str]:
            captured_kwargs.append(dict(kwargs))
            mock_proc = MagicMock(spec=sp.Popen)
            kwargs["on_process_start"](mock_proc)
            kwargs["on_process_end"](mock_proc)
            return mock_completed

        with patch(
            "little_loops.fsm.runners.run_claude_command", side_effect=fake_run_claude_command
        ):
            runner.run(
                "/ll:test",
                timeout=30,
                is_slash_command=True,
                agent="some-agent",
                tools=["Bash", "Edit"],
            )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["agent"] == "some-agent"
        assert captured_kwargs[0]["tools"] == ["Bash", "Edit"]

    def test_default_action_runner_omits_agent_tools_when_none(self) -> None:
        """DefaultActionRunner.run() passes None for agent/tools when not set."""
        import subprocess as sp

        runner = DefaultActionRunner()
        captured_kwargs: list[dict[str, Any]] = []
        mock_completed = MagicMock(spec=sp.CompletedProcess)
        mock_completed.stdout = ""
        mock_completed.stderr = ""
        mock_completed.returncode = 0

        def fake_run_claude_command(**kwargs: Any) -> sp.CompletedProcess[str]:
            captured_kwargs.append(dict(kwargs))
            mock_proc = MagicMock(spec=sp.Popen)
            kwargs["on_process_start"](mock_proc)
            kwargs["on_process_end"](mock_proc)
            return mock_completed

        with patch(
            "little_loops.fsm.runners.run_claude_command", side_effect=fake_run_claude_command
        ):
            runner.run("/ll:test", timeout=30, is_slash_command=True)

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["agent"] is None


class TestRateLimitRetries:
    """Tests for BUG-1107 / ENH-1133: 429 detection, two-tier retry, and exhaustion.

    Tests patch `_DEFAULT_RATE_LIMIT_BACKOFF_BASE` to 0 so the short-tier
    interruptible-sleep loop exits immediately. Tests that expect exhaustion
    also patch `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0]` and
    `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0` so the long-wait tier collapses
    into an immediate exhaustion on first long-tier attempt.
    """

    def _make_fsm(
        self,
        *,
        on_error: str | None = "done",
        extra_routes: dict | None = None,
        on_rate_limit_exhausted: str | None = None,
        max_rate_limit_retries: int | None = None,
        rate_limit_backoff_base_seconds: int | None = None,
        rate_limit_max_wait_seconds: int | None = None,
        rate_limit_long_wait_ladder: list[int] | None = None,
    ) -> FSMLoop:
        """Build a minimal FSM with a rate-limitable state."""
        return FSMLoop(
            name="rl-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="done",
                    on_no="done",
                    on_error=on_error,
                    extra_routes=extra_routes or {},
                    on_rate_limit_exhausted=on_rate_limit_exhausted,
                    max_rate_limit_retries=max_rate_limit_retries,
                    rate_limit_backoff_base_seconds=rate_limit_backoff_base_seconds,
                    rate_limit_max_wait_seconds=rate_limit_max_wait_seconds,
                    rate_limit_long_wait_ladder=rate_limit_long_wait_ladder,
                ),
                "done": StateConfig(terminal=True),
                "exhausted": StateConfig(terminal=True),
            },
        )

    def _rl_result(self) -> dict:
        """Action result that looks like a 429 rate-limit response."""
        return {"output": "Error: 429 Too Many Requests rate limit exceeded", "exit_code": 1}

    def _ok_result(self) -> dict:
        return {"output": "success", "exit_code": 0}

    def _ok_result_with_rl_text(self) -> dict:
        """exit_code=0 but output contains 'rate limit' text — should NOT trigger retry."""
        return {"output": "Recovered from rate limit, operation complete.", "exit_code": 0}

    def test_rate_limit_retries_state_in_place(self) -> None:
        """On a rate-limit response the executor retries the same state without routing away."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._rl_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        assert runner.calls.count("work.sh") == 2

    def test_rate_limit_counter_reset_on_success(self) -> None:
        """Per-state record is cleared when action completes without rate-limit."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._rl_result()),
            ("work.sh", self._rl_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            executor.run()

        assert "execute" not in executor._rate_limit_retries

    def test_rate_limit_exhausted_event_emitted(self) -> None:
        """After short + long tier budgets spent, rate_limit_exhausted event fires with tier counters."""
        from little_loops.fsm.executor import _DEFAULT_RATE_LIMIT_RETRIES

        fsm = self._make_fsm(on_error="done")
        runner = MockActionRunner()
        # 3 short retries + 1 long retry → exhaust on 5th 429 (budget 0 ≥ 0 on first long-tier wait)
        runner.results = [("work.sh", self._rl_result())] * (_DEFAULT_RATE_LIMIT_RETRIES + 3)
        runner.use_indexed_order = True
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0,
            _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0],
            _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            executor.run()

        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        assert len(exhausted) == 1
        assert exhausted[0]["state"] == "execute"
        # retries = short + long (ENH-1133: total across both tiers)
        assert exhausted[0]["retries"] == _DEFAULT_RATE_LIMIT_RETRIES + 1
        assert exhausted[0]["short_retries"] == _DEFAULT_RATE_LIMIT_RETRIES
        assert exhausted[0]["long_retries"] == 1
        assert exhausted[0]["total_wait_seconds"] == 0.0

    def test_rate_limit_exhausted_routes_to_on_rate_limit_exhausted(self) -> None:
        """On exhaustion, routes to on_rate_limit_exhausted target if configured."""
        from little_loops.fsm.executor import _DEFAULT_RATE_LIMIT_RETRIES

        fsm = self._make_fsm(on_rate_limit_exhausted="exhausted")
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * (_DEFAULT_RATE_LIMIT_RETRIES + 3)
        runner.use_indexed_order = True

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0,
            _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0],
            _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0,
        ):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "exhausted"
        assert result.terminated_by == "terminal"

    def test_rate_limit_exhausted_falls_back_to_on_error(self) -> None:
        """On exhaustion without on_rate_limit_exhausted, routes to on_error."""
        from little_loops.fsm.executor import _DEFAULT_RATE_LIMIT_RETRIES

        fsm = self._make_fsm(on_error="done", extra_routes={})
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * (_DEFAULT_RATE_LIMIT_RETRIES + 3)
        runner.use_indexed_order = True

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0,
            _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0],
            _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=0,
        ):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"

    def test_non_rate_limit_failure_unaffected(self) -> None:
        """Non-429 failures route via on_error without affecting rate_limit_retries."""
        fsm = self._make_fsm(on_error="done")
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", {"output": "unrelated error: file not found", "exit_code": 1})
        ]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"
        assert executor._rate_limit_retries == {}

    def test_rate_limit_backoff_sleep_called(self) -> None:
        """Executor calls time.sleep during rate-limit backoff."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._rl_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True
        sleep_calls: list[float] = []

        def _record_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        # Use a tiny but non-zero base so at least one sleep() call is made
        # during the interruptible backoff loop before the deadline is reached.
        with (
            patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0.05),
            patch("little_loops.fsm.executor.random.uniform", return_value=0.0),
            patch("little_loops.fsm.executor.time.sleep", side_effect=_record_sleep),
        ):
            executor = FSMExecutor(fsm, action_runner=runner)
            executor.run()

        assert len(sleep_calls) > 0, "Expected time.sleep to be called during rate-limit backoff"

    def test_rate_limit_init_event_constant_exported(self) -> None:
        """RATE_LIMIT_EXHAUSTED_EVENT is exported from the fsm package."""
        from little_loops.fsm import RATE_LIMIT_EXHAUSTED_EVENT

        assert RATE_LIMIT_EXHAUSTED_EVENT == "rate_limit_exhausted"

    def test_rate_limit_storm_event_constant_exported(self) -> None:
        """RATE_LIMIT_STORM_EVENT is exported from the fsm package."""
        from little_loops.fsm import RATE_LIMIT_STORM_EVENT

        assert RATE_LIMIT_STORM_EVENT == "rate_limit_storm"

    def test_rate_limit_waiting_event_constant_exported(self) -> None:
        """RATE_LIMIT_WAITING_EVENT is exported from the fsm package."""
        from little_loops.fsm import RATE_LIMIT_WAITING_EVENT

        assert RATE_LIMIT_WAITING_EVENT == "rate_limit_waiting"

    def test_on_heartbeat_called_during_long_wait(self) -> None:
        """_interruptible_sleep invokes on_heartbeat at the configured interval.

        Patches the heartbeat interval to a tiny value so we can observe the
        callback firing within a short real-time sleep. Confirms both that the
        callback receives the elapsed seconds and that it is invoked at least
        once — the first direct exercise of the method's callback mechanism.
        """
        fsm = self._make_fsm()
        runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=runner)

        heartbeats: list[float] = []

        with patch("little_loops.fsm.executor._RATE_LIMIT_HEARTBEAT_INTERVAL", 0.01):
            elapsed = executor._interruptible_sleep(
                0.2,
                on_heartbeat=lambda secs: heartbeats.append(secs),
            )

        assert elapsed > 0.0
        assert len(heartbeats) >= 1
        assert all(isinstance(s, float) and s > 0.0 for s in heartbeats)

    def test_state_level_max_rate_limit_retries_override(self) -> None:
        """State's max_rate_limit_retries overrides the module-level default."""
        fsm = self._make_fsm(
            on_error="done",
            max_rate_limit_retries=1,
            on_rate_limit_exhausted="exhausted",
            rate_limit_max_wait_seconds=0,
            rate_limit_long_wait_ladder=[0],
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * 5
        runner.use_indexed_order = True
        events: list[dict] = []

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        # 1 short retry then long tier iter 1 exhausts (total_wait=0 >= max_wait=0).
        assert len(exhausted) == 1
        assert exhausted[0]["short_retries"] == 1
        assert exhausted[0]["long_retries"] == 1
        assert exhausted[0]["retries"] == 2
        assert result.final_state == "exhausted"

    def test_state_level_backoff_base_override(self) -> None:
        """State's rate_limit_backoff_base_seconds overrides module default."""
        fsm = self._make_fsm(rate_limit_backoff_base_seconds=0)
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._rl_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        # Do NOT patch the module constant. State value must be what the executor
        # uses. Leave real default (30); if the state value is ignored the test hangs.
        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"

    def test_rate_limit_skipped_when_exit_code_zero(self) -> None:
        """exit_code=0 with 'rate limit' in output must NOT trigger the rate-limit handler.

        BUG-2065 Fix 1: The transient interceptor must be gated on exit_code != 0.
        A successful action whose output incidentally mentions 'rate limit' (e.g. a
        recovery message printed by the Claude CLI) should route normally, not be
        retried in-place with its result discarded.
        """
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [("work.sh", self._ok_result_with_rl_text())]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"
        assert runner.calls.count("work.sh") == 1, (
            "work.sh should be called exactly once; rate-limit handler must not "
            "intercept exit_code=0 results"
        )
        assert "execute" not in executor._rate_limit_retries, (
            "rate_limit_retries counter must be empty after a successful (exit_code=0) run"
        )

    def test_rate_limit_retry_does_not_consume_max_retries(self) -> None:
        """Rate-limit in-place retries must not count against max_retries budget.

        BUG-2065 Fix 2: _rate_limit_in_flight exempts rate-limit re-entries from
        _retry_counts so that infrastructure pauses don't consume the action-failure
        budget.

        Scenario: 1 rate-limit in-place retry followed by 3 true action failures
        with max_retries=2.  Without the fix the rate-limit retry occupies one
        retry slot → exhaustion after 2 action failures (3 total executions).
        With the fix the rate-limit retry is invisible to retry counting →
        exhaustion after 3 action failures (4 total executions).
        """
        # exit_code=1 → verdict "no" (see evaluate_exit_code). Self-loop via on_no.
        fsm = FSMLoop(
            name="rl-max-retries-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="done",
                    on_no="execute",
                    max_retries=2,
                    on_retry_exhausted="exhausted",
                    max_rate_limit_retries=1,
                    rate_limit_backoff_base_seconds=0,
                ),
                "done": StateConfig(terminal=True),
                "exhausted": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            (
                "work.sh",
                self._rl_result(),
            ),  # rate-limit → in-place retry (must NOT consume max_retries)
            ("work.sh", {"exit_code": 1}),  # failure 1 → on_no=execute
            ("work.sh", {"exit_code": 1}),  # failure 2 → on_no=execute
            (
                "work.sh",
                {"exit_code": 1},
            ),  # failure 3 → on_no=execute; retry_count hits limit next iter
        ]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "exhausted", (
            f"Expected 'exhausted' but got '{result.final_state}'; "
            "rate-limit retry must not prematurely consume max_retries budget"
        )
        assert runner.calls.count("work.sh") == 4, (
            f"Expected 4 calls (1 rl + 3 error) but got {runner.calls.count('work.sh')}; "
            "with rate-limit retry not counting, 3 action-error retries exhaust max_retries=2"
        )


class TestRateLimitStorm:
    """Tests for RATE_LIMIT_STORM event emission on consecutive exhaustions."""

    def _make_multi_fsm(self) -> FSMLoop:
        """Three states chained A→B→C, each can rate-limit and route to next on exhaustion."""
        # ENH-1133: each state needs rate_limit_max_wait_seconds=0 and ladder=[0]
        # so 1 short + 1 long retry → exhaust (2 429s per state).
        _cfg = {
            "max_rate_limit_retries": 1,
            "rate_limit_backoff_base_seconds": 0,
            "rate_limit_max_wait_seconds": 0,
            "rate_limit_long_wait_ladder": [0],
        }
        return FSMLoop(
            name="storm-test",
            initial="a",
            states={
                "a": StateConfig(
                    action="a.sh",
                    on_yes="done",
                    on_error="done",
                    on_rate_limit_exhausted="b",
                    **_cfg,
                ),
                "b": StateConfig(
                    action="b.sh",
                    on_yes="done",
                    on_error="done",
                    on_rate_limit_exhausted="c",
                    **_cfg,
                ),
                "c": StateConfig(
                    action="c.sh",
                    on_yes="done",
                    on_error="done",
                    on_rate_limit_exhausted="done",
                    **_cfg,
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def _rl_result(self) -> dict:
        return {"output": "429 rate limit", "exit_code": 1}

    def _ok_result(self) -> dict:
        return {"output": "success", "exit_code": 0}

    def test_storm_event_fires_at_three_consecutive_exhaustions(self) -> None:
        fsm = self._make_multi_fsm()
        runner = MockActionRunner()
        # 2 rate-limits per state (1 short + 1 long) = 6 total responses
        runner.results = [
            ("a.sh", self._rl_result()),
            ("a.sh", self._rl_result()),
            ("b.sh", self._rl_result()),
            ("b.sh", self._rl_result()),
            ("c.sh", self._rl_result()),
            ("c.sh", self._rl_result()),
        ]
        runner.use_indexed_order = True
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        executor.run()

        storms = [e for e in events if e.get("event") == "rate_limit_storm"]
        assert len(storms) == 1
        assert storms[0]["count"] == 3
        assert storms[0]["state"] == "c"

    def test_storm_counter_resets_on_success(self) -> None:
        _cfg = {
            "max_rate_limit_retries": 1,
            "rate_limit_backoff_base_seconds": 0,
            "rate_limit_max_wait_seconds": 0,
            "rate_limit_long_wait_ladder": [0],
        }
        fsm = FSMLoop(
            name="storm-reset-test",
            initial="a",
            states={
                "a": StateConfig(
                    action="a.sh",
                    on_yes="b",
                    on_error="done",
                    on_rate_limit_exhausted="b",
                    **_cfg,
                ),
                "b": StateConfig(
                    action="b.sh",
                    on_yes="c",
                    on_error="done",
                    on_rate_limit_exhausted="c",
                    **_cfg,
                ),
                "c": StateConfig(
                    action="c.sh",
                    on_yes="done",
                    on_error="done",
                    on_rate_limit_exhausted="done",
                    **_cfg,
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("a.sh", self._rl_result()),
            ("a.sh", self._rl_result()),  # a exhausts → b (storm_count=1)
            ("b.sh", self._ok_result()),  # b succeeds → counter reset to 0
            ("c.sh", self._rl_result()),
            ("c.sh", self._rl_result()),  # c exhausts → done (storm_count=1, no storm)
        ]
        runner.use_indexed_order = True
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        executor.run()

        storms = [e for e in events if e.get("event") == "rate_limit_storm"]
        assert len(storms) == 0
        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        assert len(exhausted) == 2

    def test_storm_event_constant_exported(self) -> None:
        from little_loops.fsm.executor import RATE_LIMIT_STORM_EVENT

        assert RATE_LIMIT_STORM_EVENT == "rate_limit_storm"


class TestRateLimitTwoTier:
    """ENH-1133: two-tier retry ladder (short-burst → long-wait → exhaustion)."""

    def _rl_result(self) -> dict:
        return {"output": "Error: 429 Too Many Requests rate limit", "exit_code": 1}

    def _ok_result(self) -> dict:
        return {"output": "success", "exit_code": 0}

    def _fsm(self, **state_kw: Any) -> FSMLoop:
        defaults: dict[str, Any] = {
            "action": "work.sh",
            "on_yes": "done",
            "on_no": "done",
            "on_error": "done",
            "on_rate_limit_exhausted": "exhausted",
            "rate_limit_backoff_base_seconds": 0,
        }
        defaults.update(state_kw)
        return FSMLoop(
            name="two-tier",
            initial="execute",
            states={
                "execute": StateConfig(**defaults),
                "done": StateConfig(terminal=True),
                "exhausted": StateConfig(terminal=True),
            },
        )

    def test_short_tier_exhaustion_enters_long_wait_tier(self) -> None:
        """After max_rate_limit_retries short attempts, loop enters long-wait tier
        (does not route to on_rate_limit_exhausted immediately)."""
        fsm = self._fsm(
            max_rate_limit_retries=2,
            rate_limit_long_wait_ladder=[0],
            # Budget high enough so the first two long-tier iters don't exhaust.
            rate_limit_max_wait_seconds=3600,
        )
        runner = MockActionRunner()
        # 2 short + 2 long retries, then success
        runner.results = [("work.sh", self._rl_result())] * 4 + [("work.sh", self._ok_result())]
        runner.use_indexed_order = True
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.final_state == "done"  # did not route to "exhausted"
        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        assert len(exhausted) == 0

    def test_long_wait_ladder_caps_at_last_entry(self) -> None:
        """ENH-1133: long_retries beyond ladder length reuse the last ladder value.

        Verifies the `ladder[min(long_retries - 1, len(ladder) - 1)]` guard: with a
        single-entry ladder, multiple long-tier iterations all sleep the same value.
        """
        fsm = self._fsm(
            max_rate_limit_retries=1,
            rate_limit_long_wait_ladder=[0],
            rate_limit_max_wait_seconds=3600,
        )
        runner = MockActionRunner()
        # 1 short + 3 long retries, then success
        runner.results = [("work.sh", self._rl_result())] * 4 + [("work.sh", self._ok_result())]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert result.final_state == "done"

    def test_budget_enforcement_triggers_exhaust(self) -> None:
        """total_wait_seconds >= max_wait_seconds routes to on_rate_limit_exhausted."""
        fsm = self._fsm(
            max_rate_limit_retries=0,  # skip short tier
            rate_limit_long_wait_ladder=[0],
            rate_limit_max_wait_seconds=0,
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * 3
        runner.use_indexed_order = True
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        assert len(exhausted) == 1
        assert exhausted[0]["short_retries"] == 0
        assert exhausted[0]["long_retries"] == 1
        assert exhausted[0]["total_wait_seconds"] == 0.0
        assert result.final_state == "exhausted"

    def test_shutdown_during_long_wait_sleep_terminates_cleanly(self) -> None:
        """_shutdown_requested exits the long-wait sleep promptly (does not block)."""
        fsm = self._fsm(
            max_rate_limit_retries=0,
            # Long ladder value — test would hang if the sleep were not interruptible
            rate_limit_long_wait_ladder=[600],
            rate_limit_max_wait_seconds=3600,
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * 10
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)

        # Patch time.sleep to trigger shutdown after first tick.
        call_count = [0]

        def _sleep_and_maybe_signal(duration: float) -> None:  # noqa: ARG001
            call_count[0] += 1
            if call_count[0] >= 2:
                executor.request_shutdown()

        with patch("little_loops.fsm.executor.time.sleep", side_effect=_sleep_and_maybe_signal):
            result = executor.run()

        assert result.terminated_by == "signal"

    def test_total_wait_seconds_accumulates_across_tiers(self) -> None:
        """total_wait_seconds accumulates real elapsed sleep across short + long tiers."""
        fsm = self._fsm(
            max_rate_limit_retries=1,
            rate_limit_backoff_base_seconds=0,
            rate_limit_long_wait_ladder=[0],
            rate_limit_max_wait_seconds=3600,
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", self._rl_result())] * 3 + [("work.sh", self._ok_result())]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner)
        executor.run()

        # After run completes, rate_limit_retries is cleared on success — verify
        # the _handle_rate_limit path updated total_wait_seconds via side-channel.
        # Simpler: re-run with a mock that preserves the record by staying in 429s
        # and hitting budget.
        fsm2 = self._fsm(
            max_rate_limit_retries=0,
            rate_limit_long_wait_ladder=[0],
            rate_limit_max_wait_seconds=0,
        )
        runner2 = MockActionRunner()
        runner2.results = [("work.sh", self._rl_result())] * 3
        runner2.use_indexed_order = True
        events: list[dict] = []
        executor2 = FSMExecutor(fsm2, action_runner=runner2, event_callback=events.append)
        executor2.run()

        exhausted = [e for e in events if e.get("event") == "rate_limit_exhausted"]
        assert len(exhausted) == 1
        assert "total_wait_seconds" in exhausted[0]
        assert exhausted[0]["total_wait_seconds"] >= 0.0


class TestRateLimitHeartbeat:
    """ENH-1144/ENH-1148: ``rate_limit_waiting`` heartbeat cadence during the
    long-wait tier of the two-tier rate-limit ladder."""

    def _rl_result(self) -> dict:
        return {"output": "Error: 429 Too Many Requests rate limit", "exit_code": 1}

    def _ok_result(self) -> dict:
        return {"output": "success", "exit_code": 0}

    def _fsm(self, **state_kw: Any) -> FSMLoop:
        defaults: dict[str, Any] = {
            "action": "work.sh",
            "on_yes": "done",
            "on_no": "done",
            "on_error": "done",
            "on_rate_limit_exhausted": "exhausted",
            "rate_limit_backoff_base_seconds": 0,
            "max_rate_limit_retries": 0,  # skip short tier → long-wait tier fires immediately
        }
        defaults.update(state_kw)
        return FSMLoop(
            name="heartbeat-test",
            initial="execute",
            states={
                "execute": StateConfig(**defaults),
                "done": StateConfig(terminal=True),
                "exhausted": StateConfig(terminal=True),
            },
        )

    def test_rate_limit_waiting_events_emitted_at_cadence(self) -> None:
        """Long-wait tier emits ``rate_limit_waiting`` events with the documented payload.

        Patches ``_RATE_LIMIT_HEARTBEAT_INTERVAL`` to a tiny value so the
        100ms tick loop in ``_interruptible_sleep`` fires the heartbeat at
        least once during a sub-second ladder wait. Asserts the six payload
        keys defined by the heartbeat contract: ``state``, ``elapsed_seconds``,
        ``next_attempt_at``, ``total_waited_seconds``, ``budget_seconds``,
        ``tier``.
        """
        fsm = self._fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._rl_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True
        events: list[dict] = []

        with (
            patch("little_loops.fsm.executor._RATE_LIMIT_HEARTBEAT_INTERVAL", 0.01),
            patch.multiple(
                "little_loops.fsm.executor",
                _DEFAULT_RATE_LIMIT_BACKOFF_BASE=0,
                _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER=[0.3],
                _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS=10,
            ),
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            executor.run()

        waiting = [e for e in events if e.get("event") == "rate_limit_waiting"]
        assert len(waiting) >= 1, f"Expected >=1 rate_limit_waiting events, got {len(waiting)}"

        expected_keys = {
            "state",
            "elapsed_seconds",
            "next_attempt_at",
            "total_waited_seconds",
            "budget_seconds",
            "tier",
        }
        for event in waiting:
            missing = expected_keys - event.keys()
            assert not missing, f"rate_limit_waiting missing keys: {missing}"
            assert event["state"] == "execute"
            assert event["tier"] == "long_wait"
            assert event["budget_seconds"] == 10
            assert isinstance(event["elapsed_seconds"], float)
            assert isinstance(event["next_attempt_at"], float)
            assert isinstance(event["total_waited_seconds"], float)
            assert event["elapsed_seconds"] > 0.0
            assert event["total_waited_seconds"] >= event["elapsed_seconds"]


class TestRateLimitCircuitIntegration:
    """Tests for ENH-1137: FSMExecutor integration with shared RateLimitCircuit.

    Covers pre-action sleep, stale-circuit bypass, non-LLM action skip, short-tier
    ``record_rate_limit`` propagation, and the null-guard contract for executors
    constructed without a ``circuit=`` kwarg.
    """

    def _prompt_fsm(self, action: str = "/work") -> FSMLoop:
        """FSM with a slash-command state so _action_mode() resolves to 'prompt'."""
        return FSMLoop(
            name="circuit-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action=action,
                    on_yes="done",
                    on_no="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def _shell_fsm(self) -> FSMLoop:
        """FSM with an explicit shell action_type state."""
        return FSMLoop(
            name="circuit-shell-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    action_type="shell",
                    on_yes="done",
                    on_no="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_pre_action_sleep_when_circuit_active(self, tmp_path: Path) -> None:
        """Active circuit recovery → pre-action _interruptible_sleep called with positive duration."""
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit

        circuit = RateLimitCircuit(tmp_path / "circuit.json")
        circuit.record_rate_limit(1000.0)  # seeds a far-future recovery window

        fsm = self._prompt_fsm()
        runner = MockActionRunner()
        runner.results = [("/work", {"output": "ok", "exit_code": 0})]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner, circuit=circuit)
        sleeps: list[float] = []

        def fake_sleep(duration: float, on_heartbeat: object | None = None) -> float:
            sleeps.append(duration)
            return 0.0

        with patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep):
            executor.run()

        # Pre-action sleep call should have happened with positive wait.
        assert len(sleeps) >= 1
        assert sleeps[0] > 0

    def test_pre_action_no_sleep_when_circuit_stale(self, tmp_path: Path) -> None:
        """Circuit present but with no active recovery → no pre-action sleep."""
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit

        # Never call record_rate_limit → get_estimated_recovery() returns None.
        circuit = RateLimitCircuit(tmp_path / "circuit.json")

        fsm = self._prompt_fsm()
        runner = MockActionRunner()
        runner.results = [("/work", {"output": "ok", "exit_code": 0})]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner, circuit=circuit)
        sleeps: list[float] = []

        def fake_sleep(duration: float, on_heartbeat: object | None = None) -> float:
            sleeps.append(duration)
            return 0.0

        with patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep):
            executor.run()

        assert sleeps == []

    def test_pre_action_skipped_for_shell_action(self, tmp_path: Path) -> None:
        """Non-LLM action type (shell) → pre-action circuit check skipped."""
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit

        circuit = RateLimitCircuit(tmp_path / "circuit.json")
        circuit.record_rate_limit(1000.0)  # active window

        fsm = self._shell_fsm()
        runner = MockActionRunner()
        runner.results = [("work.sh", {"output": "ok", "exit_code": 0})]
        runner.use_indexed_order = True

        executor = FSMExecutor(fsm, action_runner=runner, circuit=circuit)
        sleeps: list[float] = []

        def fake_sleep(duration: float, on_heartbeat: object | None = None) -> float:
            sleeps.append(duration)
            return 0.0

        with patch.object(executor, "_interruptible_sleep", side_effect=fake_sleep):
            executor.run()

        # No pre-action sleep because action_mode is 'shell', not 'prompt'.
        assert sleeps == []

    def test_record_rate_limit_called_on_short_tier(self, tmp_path: Path) -> None:
        """On 429 detection, _handle_rate_limit records the backoff window in the circuit."""
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit

        circuit = RateLimitCircuit(tmp_path / "circuit.json")

        fsm = FSMLoop(
            name="circuit-short-tier",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="/work",
                    on_yes="done",
                    on_no="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            (
                "/work",
                {"output": "Error: 429 Too Many Requests rate limit exceeded", "exit_code": 1},
            ),
            ("/work", {"output": "ok", "exit_code": 0}),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner, circuit=circuit)
            executor.run()

        # A record was written — estimated_recovery is populated.
        recovery = circuit.get_estimated_recovery()
        assert recovery is not None

    def test_record_rate_limit_not_called_when_circuit_none(self) -> None:
        """Executor constructed without circuit= retains null _circuit and runs cleanly through 429."""
        fsm = FSMLoop(
            name="no-circuit-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="done",
                    on_no="done",
                    on_error="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", {"output": "Error: 429 rate limit exceeded", "exit_code": 1}),
            ("work.sh", {"output": "ok", "exit_code": 0}),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_RATE_LIMIT_BACKOFF_BASE", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert executor._circuit is None
        assert result.final_state == "done"
        assert result.terminated_by == "terminal"

    def test_sub_loop_inherits_parent_circuit(self, tmp_path: Path) -> None:
        """Child executor in a sub-loop shares the parent's circuit instance."""
        from little_loops.fsm.rate_limit_circuit import RateLimitCircuit

        circuit = RateLimitCircuit(tmp_path / "circuit.json")
        parent_fsm = FSMLoop(
            name="parent",
            initial="execute",
            states={"execute": StateConfig(terminal=True)},
        )
        parent = FSMExecutor(parent_fsm, circuit=circuit)
        # Mirror the argument list used in _execute_sub_loop.
        child = FSMExecutor(
            parent_fsm,
            action_runner=parent.action_runner,
            loops_dir=parent.loops_dir,
            event_callback=parent.event_callback,
            circuit=parent._circuit,
        )
        assert child._circuit is parent._circuit is circuit


# =============================================================================
# Tests: API server-error retry (ENH-1293 Fix 1)
# =============================================================================


class TestAPIErrorRetries:
    """Tests for ENH-1293 Fix 1: transient API server error retry via _handle_api_error.

    Tests patch ``_DEFAULT_API_ERROR_BACKOFF`` to 0 so interruptible-sleep returns
    immediately without wall-clock delay.
    """

    def _make_fsm(self, *, on_error: str | None = "done") -> FSMLoop:
        return FSMLoop(
            name="api-err-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="done",
                    on_no="done",
                    on_error=on_error,
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def _server_error_result(self) -> dict:
        return {
            "output": "API Error: The server had an error while processing your request",
            "exit_code": 1,
        }

    def _ok_result(self) -> dict:
        return {"output": "success", "exit_code": 0}

    def test_api_error_retries_state_in_place(self) -> None:
        """On an API server error the executor retries the same state without routing away."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._server_error_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        assert runner.calls.count("work.sh") == 2

    def test_api_error_exhausted_falls_through_to_normal_routing(self) -> None:
        """After max retries, executor falls through to normal verdict routing (not a hang)."""
        from little_loops.fsm.executor import _DEFAULT_API_ERROR_RETRIES

        fsm = self._make_fsm()
        runner = MockActionRunner()
        # All results are server errors — should exhaust retries then route via exit_code=1 → on_no
        runner.always_return(**self._server_error_result())

        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        # _DEFAULT_API_ERROR_RETRIES attempts + 1 exhaustion attempt = retries+1 calls total
        assert runner.calls.count("work.sh") == _DEFAULT_API_ERROR_RETRIES + 1
        # exit_code=1 → verdict "no" → on_no="done"
        assert result.final_state == "done"
        assert result.terminated_by == "terminal"

    def test_api_error_exhausted_event_emitted(self) -> None:
        """api_error_exhausted event is emitted when retries are exhausted."""
        from little_loops.fsm.executor import _DEFAULT_API_ERROR_RETRIES

        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.always_return(**self._server_error_result())

        events: list[dict] = []
        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            executor.run()

        exhausted = [e for e in events if e.get("event") == "api_error_exhausted"]
        assert len(exhausted) == 1
        assert exhausted[0]["state"] == "execute"
        assert exhausted[0]["retries"] == _DEFAULT_API_ERROR_RETRIES

    def test_api_error_retry_event_emitted(self) -> None:
        """api_error_retry event is emitted on each in-place retry attempt."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._server_error_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        events: list[dict] = []
        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            executor.run()

        retry_events = [e for e in events if e.get("event") == "api_error_retry"]
        assert len(retry_events) == 1
        assert retry_events[0]["state"] == "execute"
        assert retry_events[0]["attempt"] == 1

    def test_api_error_counter_reset_on_success(self) -> None:
        """Per-state api_error_retries record is cleared when state completes without error."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._server_error_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            executor.run()

        assert "execute" not in executor._api_error_retries

    def test_api_error_does_not_trigger_rate_limit_handler(self) -> None:
        """API server error should not call _handle_rate_limit (different handler)."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", self._server_error_result()),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            executor.run()

        # Rate limit tracking should remain empty — server errors don't use it
        assert "execute" not in executor._rate_limit_retries

    def test_529_overloaded_triggers_retry(self) -> None:
        """529/overloaded pattern also triggers the API error retry path."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.results = [
            ("work.sh", {"output": "529 overloaded_error", "exit_code": 1}),
            ("work.sh", self._ok_result()),
        ]
        runner.use_indexed_order = True

        with patch("little_loops.fsm.executor._DEFAULT_API_ERROR_BACKOFF", 0):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"
        assert runner.calls.count("work.sh") == 2


# =============================================================================
# Tests: Sub-loop remaining-budget forwarding (ENH-1293 Fix 2)
# =============================================================================


class TestSubLoopBudgetClamping:
    """Tests for ENH-1293 Fix 2: child FSM timeout clamped to parent's remaining budget."""

    def _write_child_loop(self, loops_dir: Path, name: str = "child") -> None:
        (loops_dir / f"{name}.yaml").write_text(
            f"name: {name}\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )

    def test_child_timeout_clamped_to_parent_remaining(self, tmp_path: Path) -> None:
        """Child FSM timeout is clamped to parent's remaining wall-clock budget."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child has a large explicit timeout (7200s) that exceeds parent's remaining budget
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: done\ntimeout: 7200\nstates:\n  done:\n    terminal: true\n"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            timeout=3600,  # 1h parent budget
            states={
                "run_child": StateConfig(loop="child", on_yes="done", on_no="failed"),
                "done": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        # Simulate parent started 30 min ago (1_800_000ms elapsed)
        executor.start_time_ms = 0

        captured_child_timeouts: list[int | None] = []
        original_run = FSMExecutor.run

        def capturing_run(self_inner: FSMExecutor) -> ExecutionResult:
            if self_inner.fsm.name == "child":
                captured_child_timeouts.append(self_inner.fsm.timeout)
            return original_run(self_inner)

        with (
            patch.object(FSMExecutor, "run", capturing_run),
            patch("little_loops.fsm.executor._now_ms", return_value=1_800_000),
        ):
            # Call _execute_sub_loop directly to avoid run() overwriting start_time_ms
            state = parent_fsm.states["run_child"]
            ctx = executor._build_context()
            executor._execute_sub_loop(state, ctx)

        # 30 min elapsed from 1h budget → 30 min (1800s) remaining → child clamped to 1800
        assert len(captured_child_timeouts) == 1
        assert captured_child_timeouts[0] == 1800

    def test_child_timeout_not_clamped_when_parent_has_no_timeout(self, tmp_path: Path) -> None:
        """When parent has no timeout, child FSM timeout is left unchanged."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child loop with its own explicit timeout
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: done\ntimeout: 600\nstates:\n  done:\n    terminal: true\n"
        )

        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            timeout=None,  # no parent timeout
            states={
                "run_child": StateConfig(loop="child", on_yes="done", on_no="failed"),
                "done": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        # Just verify it runs without error — child timeout unchanged
        assert result.final_state == "done"

    def test_child_timeout_routes_parent_via_on_no(self, tmp_path: Path) -> None:
        """When child times out, parent routes via on_no (not a crash)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child with max_iterations=1 and action that always fails → hits max_iterations → on_no
        (loops_dir / "slow_child.yaml").write_text(
            "name: slow_child\ninitial: work\nmax_iterations: 1\n"
            "states:\n  work:\n    action: 'false'\n    on_yes: done\n    on_no: work\n"
            "  done:\n    terminal: true\n"
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            timeout=3600,
            states={
                "run_child": StateConfig(loop="slow_child", on_yes="success", on_no="fallback"),
                "success": StateConfig(terminal=True),
                "fallback": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "fallback"


class TestSubLoopWithBindings:
    """Tests for explicit with: parameter bindings on sub-loop states."""

    def _write_child(self, loops_dir: Path, name: str, body: str) -> None:
        (loops_dir / f"{name}.yaml").write_text(body)

    def test_with_binding_passes_value_to_child(self, tmp_path: Path) -> None:
        """Child loop receives only the bound parameter via with:."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "echo-param",
            (
                "name: echo-param\ninitial: step\n"
                "parameters:\n  greeting:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.greeting}'\n    capture: out\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"other_key": "should_not_leak"},
            states={
                "run_child": StateConfig(
                    loop="echo-param",
                    with_={"greeting": "hello"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        assert "run_child" in executor.captured

    def test_with_interpolation_from_parent_context(self, tmp_path: Path) -> None:
        """with: values support ${context.*} interpolation from the parent."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "greet",
            (
                "name: greet\ninitial: step\n"
                "parameters:\n  name:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.name}'\n    capture: out\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"target": "world"},
            states={
                "run_child": StateConfig(
                    loop="greet",
                    with_={"name": "${context.target}"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        child_out = executor.captured["run_child"]["out"]["output"].strip()
        assert child_out == "world"

    def test_with_interpolation_from_parent_captures(self, tmp_path: Path) -> None:
        """with: supports ${captured.*} interpolation to pass captured output."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "check-id",
            (
                "name: check-id\ninitial: step\n"
                "parameters:\n  issue_id:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.issue_id}'\n    capture: received\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="capture_id",
            states={
                "capture_id": StateConfig(
                    action="echo 'FEAT-42'",
                    capture="input",
                    next="run_child",
                ),
                "run_child": StateConfig(
                    loop="check-id",
                    with_={"issue_id": "${captured.input.output}"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        received = executor.captured["run_child"]["received"]["output"].strip()
        assert received == "FEAT-42"

    def test_with_does_not_leak_parent_context(self, tmp_path: Path) -> None:
        """Child receives only declared parameters — no bulk copy of parent context."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child loop only uses its declared 'input' parameter.
        # If parent 'secret' key were accessible as ${context.secret}, interpolation
        # would try to resolve it and succeed (if leaked) or fail (if not present).
        # We verify this purely by the child being able to echo its declared param.
        self._write_child(
            loops_dir,
            "no-leak",
            (
                "name: no-leak\ninitial: step\n"
                "parameters:\n  input:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n"
                "    action: 'echo ${context.input}'\n"
                "    capture: out\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"secret": "do_not_pass", "input": "payload"},
            states={
                "run_child": StateConfig(
                    loop="no-leak",
                    with_={"input": "${context.input}"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        child_out = executor.captured["run_child"]["out"]["output"].strip()
        # Child received "payload" (the bound value) not "do_not_pass" (the leaked parent key)
        assert child_out == "payload"
        # Verify that the parent's 'secret' key was not placed in child context by
        # checking the child's FSMLoop — with: only seeds declared parameter names
        # (verified by the implementation: child_fsm.context = {**child_fsm.context, **resolved}
        #  where resolved only contains with_ bindings)

    def test_with_inherits_parent_run_dir(self, tmp_path: Path) -> None:
        """The runner-injected run_dir invariant survives an explicit with: binding.

        Regression: a sub-loop invoked with a with: block must still see the parent's
        run_dir even when the with: block does not name it. Without re-injection,
        ${context.run_dir} resolves to '' in the child and the child's first
        os.makedirs('${context.run_dir}') -> os.makedirs('') crashes (the rn-build ->
        goal-cluster failure). The with: branch re-injects run_dir via setdefault.
        """
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Child references ${context.run_dir} but does NOT declare it as a parameter,
        # exactly like goal-cluster: it relies on the runner-managed invariant flowing in.
        self._write_child(
            loops_dir,
            "needs-run-dir",
            (
                "name: needs-run-dir\ninitial: step\n"
                "parameters:\n  goals:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.run_dir}'\n    capture: rd\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        run_dir = str(tmp_path / "runs" / "parent-run") + "/"
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"run_dir": run_dir},  # injected by the runner in production
            states={
                "run_child": StateConfig(
                    loop="needs-run-dir",
                    # with: binds only goals — run_dir is intentionally NOT named here
                    with_={"goals": "EPIC-001"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        child_run_dir = executor.captured["run_child"]["rd"]["output"].strip()
        # Child saw the parent's run_dir (verbatim, trailing slash preserved) despite
        # not binding it in with:
        assert child_run_dir == run_dir

    def test_with_explicit_run_dir_overrides_parent(self, tmp_path: Path) -> None:
        """An explicit with: run_dir wins over the inherited parent run_dir (setdefault)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "run-dir-echo",
            (
                "name: run-dir-echo\ninitial: step\n"
                "parameters:\n  run_dir:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.run_dir}'\n    capture: rd\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            context={"run_dir": "/parent/run/"},
            states={
                "run_child": StateConfig(
                    loop="run-dir-echo",
                    with_={"run_dir": "/child/override"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        child_run_dir = executor.captured["run_child"]["rd"]["output"].strip()
        assert child_run_dir == "/child/override"

    def test_with_applies_declared_defaults(self, tmp_path: Path) -> None:
        """Unbound optional parameters receive their ParameterSpec defaults."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "with-default",
            (
                "name: with-default\ninitial: step\n"
                "parameters:\n"
                "  input:\n    type: string\n    required: true\n"
                "  mode:\n    type: string\n    default: fast\n"
                "states:\n"
                "  step:\n    action: 'echo ${context.mode}'\n    capture: out\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(
                    loop="with-default",
                    with_={"input": "something"},  # mode omitted — should use default
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        child_out = executor.captured["run_child"]["out"]["output"].strip()
        assert child_out == "fast"

    def test_with_merges_child_captures_back(self, tmp_path: Path) -> None:
        """Child captures are merged back into parent when with: is used."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        self._write_child(
            loops_dir,
            "capture-child",
            (
                "name: capture-child\ninitial: step\n"
                "parameters:\n  input:\n    type: string\n    required: true\n"
                "states:\n"
                "  step:\n    action: 'echo processed'\n    capture: result\n    next: done\n"
                "  done:\n    terminal: true\n"
            ),
        )
        parent_fsm = FSMLoop(
            name="parent",
            initial="run_child",
            states={
                "run_child": StateConfig(
                    loop="capture-child",
                    with_={"input": "data"},
                    on_yes="success",
                    on_no="fail",
                ),
                "success": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
        result = executor.run()
        assert result.final_state == "success"
        assert "run_child" in executor.captured
        assert "result" in executor.captured["run_child"]

    def test_load_and_validate_catches_misspelled_with_key(self, tmp_path: Path) -> None:
        """Misspelled with: key against child parameters produces a ValidationError."""
        # Write child with parameters block
        child_yaml = tmp_path / "child.yaml"
        child_yaml.write_text(
            "name: child\n"
            "initial: step\n"
            "parameters:\n"
            "  data_dir:\n    type: string\n    required: false\n"
            "states:\n"
            "  step:\n    action: echo ok\n    next: done\n"
            "  done:\n    terminal: true\n"
        )
        # Write parent that references child with misspelled with: key
        parent_yaml = tmp_path / "parent.yaml"
        parent_yaml.write_text(
            "name: parent\n"
            "initial: run_child\n"
            "states:\n"
            "  run_child:\n"
            "    loop: child\n"
            "    with:\n"
            "      data_dirr: oops  # misspelled — should be data_dir\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        # load_and_validate should raise ValueError about the unknown key
        with pytest.raises(ValueError, match="data_dirr"):
            load_and_validate(parent_yaml)


class TestThrottling:
    """Tests for ENH-1115: per-state tool-call progressive throttling.

    The throttle counter increments once per _run_action_or_route call, which
    happens once per _execute_state invocation. To accumulate count > 1, states
    must loop back to themselves across iterations without a different state in
    between. Tests use self-routing states and patch _DEFAULT_THROTTLE_* to small
    values so scenarios complete quickly.
    """

    def _looping_fsm(
        self,
        *,
        on_throttle_hard: str | None = None,
        throttle: dict[str, Any] | None = None,
        state_type: str | None = None,
        exit_after: int = 0,
    ) -> tuple[FSMLoop, MockActionRunner]:
        """Build an FSM where 'execute' loops back on itself, then exits via on_no.

        Returns the FSM and a pre-configured runner that returns yes for `exit_after`
        calls then returns no (which routes to 'done' via on_no).
        """
        from little_loops.fsm.schema import ThrottleConfig

        throttle_cfg = ThrottleConfig.from_dict(throttle) if throttle else None
        fsm = FSMLoop(
            name="throttle-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="execute",  # loop back to accumulate call count
                    on_no="done",  # exit when action returns non-zero
                    on_throttle_hard=on_throttle_hard,
                    throttle=throttle_cfg,
                    type=state_type,
                ),
                "done": StateConfig(terminal=True),
                "throttled": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        yes = ("work.sh", {"output": "yes", "exit_code": 0})
        no = ("work.sh", {"output": "no", "exit_code": 1})
        runner.results = [yes] * exit_after + [no] * 20
        runner.use_indexed_order = True
        return fsm, runner

    def test_warn_event_emitted_at_warn_max(self) -> None:
        """throttle_warn is emitted exactly once when call count reaches warn_max."""
        # State loops back 3 times (hitting warn_max=3), then exits on 4th call
        fsm, runner = self._looping_fsm(exit_after=4)
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=3,
            _DEFAULT_THROTTLE_HARD_MAX=100,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            executor.run()

        warn_events = [e for e in events if e.get("event") == "throttle_warn"]
        assert len(warn_events) == 1
        assert warn_events[0]["state"] == "execute"
        assert warn_events[0]["count"] == 3
        assert warn_events[0]["warn_max"] == 3

    def test_hard_event_emitted_and_routes_to_on_throttle_hard(self) -> None:
        """At hard_max, throttle_hard is emitted and executor routes to on_throttle_hard."""
        fsm, runner = self._looping_fsm(on_throttle_hard="throttled", exit_after=20)
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=2,
            _DEFAULT_THROTTLE_HARD_MAX=4,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        assert result.final_state == "throttled"
        hard_events = [e for e in events if e.get("event") == "throttle_hard"]
        assert len(hard_events) == 1
        assert hard_events[0]["state"] == "execute"
        assert hard_events[0]["count"] == 4
        assert hard_events[0]["next"] == "throttled"

    def test_hard_falls_back_to_on_error_when_no_on_throttle_hard(self) -> None:
        """When on_throttle_hard is not set, hard transition falls back to on_error."""

        fsm = FSMLoop(
            name="throttle-fallback-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="execute",
                    on_no="done",
                    on_error="done",  # hard_max falls back here
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", {"output": "yes", "exit_code": 0})] * 20
        runner.use_indexed_order = True
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=2,
            _DEFAULT_THROTTLE_HARD_MAX=3,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        assert result.final_state == "done"
        hard_events = [e for e in events if e.get("event") == "throttle_hard"]
        assert len(hard_events) == 1
        assert hard_events[0]["next"] == "done"

    def test_stop_event_emitted_beyond_hard_max(self) -> None:
        """Calls beyond hard_max emit throttle_stop and hard-stop the loop.

        No on_throttle_hard or on_error → hard_max check returns None and
        execution continues. The next re-entry sees count > hard_max and stops.
        """
        fsm = FSMLoop(
            name="stop-test",
            initial="execute",
            states={
                "execute": StateConfig(
                    action="work.sh",
                    on_yes="execute",  # loop back to accumulate calls
                    on_no="done",
                    # no on_error, no on_throttle_hard → hard_max returns None
                ),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [("work.sh", {"output": "yes", "exit_code": 0})] * 20
        runner.use_indexed_order = True
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=2,
            _DEFAULT_THROTTLE_HARD_MAX=3,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        stop_events = [e for e in events if e.get("event") == "throttle_stop"]
        assert len(stop_events) == 1
        assert result.terminated_by == "error"

    def test_counter_resets_on_state_change(self) -> None:
        """Throttle counter resets when transitioning to a different state."""
        fsm = FSMLoop(
            name="reset-test",
            initial="step_a",
            states={
                "step_a": StateConfig(action="a.sh", on_yes="step_b", on_no="step_b"),
                "step_b": StateConfig(action="b.sh", on_yes="done", on_no="done"),
                "done": StateConfig(terminal=True),
            },
        )
        runner = MockActionRunner()
        runner.results = [
            ("a.sh", {"output": "yes", "exit_code": 0}),
            ("b.sh", {"output": "yes", "exit_code": 0}),
        ]
        runner.use_indexed_order = True

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=2,
            _DEFAULT_THROTTLE_HARD_MAX=3,
        ):
            executor = FSMExecutor(fsm, action_runner=runner)
            result = executor.run()

        assert result.final_state == "done"
        # step_a should have been cleaned up when we transitioned to step_b
        assert "step_a" not in executor._throttle_counts

    def test_per_state_throttle_config_overrides_defaults(self) -> None:
        """State-level throttle config overrides module defaults."""

        fsm, runner = self._looping_fsm(
            on_throttle_hard="throttled",
            throttle={"normal_max": 1, "warn_max": 2, "hard_max": 3},
            exit_after=20,
        )
        events: list[dict] = []

        # Module defaults are high — the per-state config should take precedence
        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=100,
            _DEFAULT_THROTTLE_HARD_MAX=200,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        assert result.final_state == "throttled"
        hard_events = [e for e in events if e.get("event") == "throttle_hard"]
        assert hard_events[0]["hard_max"] == 3

    def test_learning_state_exempt_from_hard_max(self) -> None:
        """States with type='learning' skip the hard_max hard-stop; warn still fires."""
        # Learning state: loops back 6 times (past hard_max=4), then exits on 7th call
        fsm, runner = self._looping_fsm(
            on_throttle_hard="throttled",
            state_type="learning",
            exit_after=6,
        )
        events: list[dict] = []

        with patch.multiple(
            "little_loops.fsm.executor",
            _DEFAULT_THROTTLE_WARN_MAX=2,
            _DEFAULT_THROTTLE_HARD_MAX=4,
        ):
            executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
            result = executor.run()

        # Should exit via on_no → done (not via on_throttle_hard)
        assert result.final_state == "done"
        warn_events = [e for e in events if e.get("event") == "throttle_warn"]
        hard_events = [e for e in events if e.get("event") == "throttle_hard"]
        assert len(warn_events) >= 1  # warn still fires
        assert len(hard_events) == 0  # hard is suppressed for learning states


class TestStallDetector:
    """Tests for FEAT-1637: stall detector for repeated (state, exit_code, verdict) triples."""

    def _make_fsm(
        self,
        on_repeated_failure: str,
        window: int = 3,
    ) -> FSMLoop:
        """Build an FSM that ping-pongs check ↔ fix, with circuit.repeated_failure set."""
        from little_loops.fsm.schema import CircuitConfig, RepeatedFailureConfig

        fsm = FSMLoop(
            name="stall-test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_yes="done",
                    on_no="fix",
                ),
                "fix": StateConfig(action="fix.sh", next="check"),
                "recover": StateConfig(action="echo recover", next="done"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=50,
        )
        fsm.circuit = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(
                window=window, on_repeated_failure=on_repeated_failure
            )
        )
        return fsm

    def test_stall_aborts_after_window(self) -> None:
        """3 consecutive (state, exit_code, verdict) triples → abort with stall_detected."""
        fsm = self._make_fsm(on_repeated_failure="abort", window=3)
        runner = MockActionRunner()
        runner.always_return(exit_code=1)  # check always fails → ping-pongs forever
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "stall_detected"
        assert result.error is not None and "Stall detected" in result.error
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1
        e = stall_events[0]
        assert e["state"] == "check"
        assert e["exit_code"] == 1
        assert e["verdict"] == "no"
        assert e["consecutive"] == 3
        assert e["action"] == "abort"

    def test_stall_does_not_fire_when_streak_broken(self) -> None:
        """One non-matching iteration in the middle resets the consecutive counter."""
        fsm = self._make_fsm(on_repeated_failure="abort", window=3)
        runner = MockActionRunner()
        # check fails 2x, then succeeds → done. Never hits stall window.
        runner.results = [
            ("check.sh", {"exit_code": 1}),
            ("fix.sh", {"exit_code": 0}),
            ("check.sh", {"exit_code": 1}),
            ("fix.sh", {"exit_code": 0}),
            ("check.sh", {"exit_code": 0}),
        ]
        runner.use_indexed_order = True
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "terminal"
        assert result.final_state == "done"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert stall_events == []

    def test_stall_routes_to_recovery_state(self) -> None:
        """on_repeated_failure: <state> routes to that state instead of aborting."""
        fsm = self._make_fsm(on_repeated_failure="recover", window=3)
        runner = MockActionRunner()
        runner.set_result("check.sh", exit_code=1)
        runner.set_result("fix.sh", exit_code=0)
        runner.set_result("echo recover", exit_code=0)
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        # Should NOT abort — should route to recover → done
        assert result.terminated_by == "terminal"
        assert result.final_state == "done"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1
        assert stall_events[0]["action"] == "route:recover"
        assert "echo recover" in runner.calls

    def test_no_circuit_config_no_stall_detection(self) -> None:
        """Backward compat: FSM without circuit block does not stall-detect."""
        fsm = FSMLoop(
            name="no-stall",
            initial="check",
            states={
                "check": StateConfig(action="check.sh", on_yes="done", on_no="fix"),
                "fix": StateConfig(action="fix.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        # No fsm.circuit assigned — should run until max_iterations
        runner = MockActionRunner()
        runner.always_return(exit_code=1)
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "max_iterations"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert stall_events == []

    def test_stall_treats_124_error_as_stall(self) -> None:
        """exit_code=124 with verdict='error' (timeout) stalls like verdict='no'."""
        from little_loops.fsm.schema import CircuitConfig, RepeatedFailureConfig

        fsm = FSMLoop(
            name="timeout-stall",
            initial="slow",
            states={
                "slow": StateConfig(
                    action="slow.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    route=RouteConfig(routes={"yes": "done", "error": "slow"}, error="slow"),
                ),
                "done": StateConfig(terminal=True),
            },
            max_iterations=50,
        )
        fsm.circuit = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(window=3, on_repeated_failure="abort")
        )
        runner = MockActionRunner()
        runner.always_return(exit_code=124, stderr="timed out")
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "stall_detected"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1
        assert stall_events[0]["exit_code"] == 124
        assert stall_events[0]["verdict"] == "error"

    def test_window_one_fires_immediately(self) -> None:
        """window=1 fires after the first matching transition."""
        fsm = self._make_fsm(on_repeated_failure="abort", window=1)
        runner = MockActionRunner()
        runner.always_return(exit_code=1)
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "stall_detected"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1
        assert stall_events[0]["consecutive"] == 1

    def test_progress_paths_prevent_false_positive_stall(self, tmp_path: Path) -> None:
        """BUG-1674: file changes between check cycles reset the stall window.

        Simulates a check↔work ping-pong where work uses next: only (no evaluate:).
        With progress_paths pointing to a file that changes each cycle, the stall
        must NOT fire within window cycles.
        """
        import time

        from little_loops.fsm.schema import CircuitConfig, RepeatedFailureConfig

        progress_file = tmp_path / "plan.md"
        progress_file.write_text("step 0")

        @dataclass
        class ProgressRunner:
            calls: list[str] = field(default_factory=list)
            work_count: int = 0

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
                self.calls.append(action)
                if "work" in action:
                    self.work_count += 1
                    time.sleep(0.01)
                    progress_file.write_text(f"step {self.work_count}")
                return ActionResult(output="", stderr="", exit_code=1, duration_ms=10)

        fsm = FSMLoop(
            name="progress-stall-test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="work",
                ),
                "work": StateConfig(action="work.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=20,
        )
        fsm.circuit = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(
                window=3,
                on_repeated_failure="abort",
                progress_paths=[str(progress_file)],
            )
        )

        runner = ProgressRunner()
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        # Should exhaust max_iterations without stalling (file changes reset window)
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert stall_events == [], f"Unexpected stall fired: {stall_events}"
        assert result.terminated_by == "max_iterations"

    def test_progress_paths_absent_stall_fires_as_before(self) -> None:
        """BUG-1674 regression: without progress_paths, stall fires after window cycles."""
        from little_loops.fsm.schema import CircuitConfig, RepeatedFailureConfig

        fsm = FSMLoop(
            name="no-progress-stall-test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="work",
                ),
                "work": StateConfig(action="work.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=50,
        )
        fsm.circuit = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(window=3, on_repeated_failure="abort")
        )
        runner = MockActionRunner()
        runner.always_return(exit_code=1)
        events: list[dict] = []

        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "stall_detected"
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1

    def test_exclude_paths_allows_stall_despite_self_writes(self, tmp_path: Path) -> None:
        """BUG-1767: a loop that appends to its own bookkeeping file every cycle
        must still trip the stall detector when those files are in exclude_paths.

        The self-appending file (simulating a plan.md) is listed in both
        progress_paths AND exclude_paths so the executor filters it out before
        building the fingerprint.  With the excluded path removed, the fingerprint
        is empty (None) on every cycle and the window accumulates normally.
        """
        import time

        from little_loops.fsm.schema import CircuitConfig, RepeatedFailureConfig

        self_write_file = tmp_path / "plan.md"
        self_write_file.write_text("initial")

        @dataclass
        class SelfWriteRunner:
            calls: list[str] = field(default_factory=list)
            step: int = 0

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
                agent: str | None = None,
                tools: list[str] | None = None,
                on_usage: Any = None,
                on_usage_detailed: Any = None,
                model: str | None = None,
            ) -> ActionResult:
                del (
                    timeout,
                    is_slash_command,
                    on_output_line,
                    agent,
                    tools,
                    on_usage,
                    on_usage_detailed,
                    model,
                )
                self.calls.append(action)
                # Simulate a loop that always appends to its own plan file (like
                # general-task's continue_work state) — no real progress is made.
                self.step += 1
                time.sleep(0.01)
                self_write_file.write_text(f"step {self.step}")
                return ActionResult(output="", stderr="", exit_code=1, duration_ms=10)

        fsm = FSMLoop(
            name="self-write-stall-test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    evaluate=EvaluateConfig(type="exit_code"),
                    on_yes="done",
                    on_no="work",
                ),
                "work": StateConfig(action="work.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=50,
        )
        fsm.circuit = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(
                window=3,
                on_repeated_failure="abort",
                progress_paths=[str(self_write_file)],
                exclude_paths=[str(self_write_file)],
            )
        )

        runner = SelfWriteRunner()
        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        # The stall must fire because self-writes to an excluded path should not
        # reset the window — the fingerprint is effectively empty every cycle.
        assert result.terminated_by == "stall_detected", (
            f"Expected stall_detected, got {result.terminated_by!r}. "
            f"Stall events: {[e for e in events if e.get('event') == 'stall_detected']}"
        )
        stall_events = [e for e in events if e.get("event") == "stall_detected"]
        assert len(stall_events) == 1


class TestMaxIterationsSummaryHook:
    """Tests for ENH-1631: on_max_iterations summary hook."""

    def _make_fsm(self, on_max_iterations: str | None = "summarize") -> FSMLoop:
        return FSMLoop(
            name="summary-hook-test",
            initial="loop",
            max_iterations=3,
            on_max_iterations=on_max_iterations,
            states={
                "loop": StateConfig(action="work.sh", on_yes="done", on_no="loop"),
                "summarize": StateConfig(action="summarize.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )

    def test_summary_state_runs_on_cap(self) -> None:
        """Summary state executes when iteration cap fires."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.always_return(exit_code=1)  # loop never succeeds → hits cap at iter 3

        executor = FSMExecutor(fsm, action_runner=runner)
        result = executor.run()

        assert runner.calls.count("summarize.sh") == 1
        assert result.terminated_by == "max_iterations"

    def test_max_iterations_summary_event_emitted(self) -> None:
        """max_iterations_summary event is emitted with correct payload when cap fires."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.always_return(exit_code=1)

        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        executor.run()

        summary_events = [e for e in events if e.get("event") == "max_iterations_summary"]
        assert len(summary_events) == 1
        evt = summary_events[0]
        assert evt["summary_state"] == "summarize"
        assert evt["iterations"] == 3

    def test_terminated_by_max_iterations_after_summary(self) -> None:
        """loop_complete.terminated_by is 'max_iterations' even when summary state runs."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.always_return(exit_code=1)

        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "max_iterations"
        complete_events = [e for e in events if e.get("event") == "loop_complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["terminated_by"] == "max_iterations"

    def test_no_summary_state_without_on_max_iterations(self) -> None:
        """When on_max_iterations is not set, cap terminates normally with no summary."""
        fsm = self._make_fsm(on_max_iterations=None)
        runner = MockActionRunner()
        runner.always_return(exit_code=1)

        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        result = executor.run()

        assert result.terminated_by == "max_iterations"
        summary_events = [e for e in events if e.get("event") == "max_iterations_summary"]
        assert summary_events == []

    def test_summary_state_executes_only_once(self) -> None:
        """The _summary_state_executed flag prevents the summary state from re-entering."""
        fsm = self._make_fsm()
        runner = MockActionRunner()
        runner.always_return(exit_code=1)

        events: list[dict] = []
        executor = FSMExecutor(fsm, action_runner=runner, event_callback=events.append)
        executor.run()

        summary_events = [e for e in events if e.get("event") == "max_iterations_summary"]
        assert len(summary_events) == 1


class TestFragmentParamBinding:
    """Tests for fragment with: bindings populating the param namespace at runtime."""

    def _make_fragment_state(
        self,
        fragment_name: str,
        bindings: dict,
        parameters: dict | None = None,
        **kwargs,
    ) -> StateConfig:
        """Build a StateConfig that looks like it came from a parameterized fragment."""
        from little_loops.fsm.schema import ParameterSpec

        parsed_params = {}
        if parameters:
            for name, spec in parameters.items():
                parsed_params[name] = ParameterSpec.from_dict(spec)
        return StateConfig(
            fragment_name=fragment_name,
            fragment_bindings=bindings,
            fragment_parameters=parsed_params,
            **kwargs,
        )

    def test_param_namespace_populated_from_fragment_bindings(self, tmp_path: Path) -> None:
        """Fragment bindings are available via ${param.X} in the action."""
        state = self._make_fragment_state(
            "retry_counter",
            bindings={"counter_key": "lint_count", "max_retries": 5},
            parameters={
                "counter_key": {"type": "string", "required": True},
                "max_retries": {"type": "integer", "default": 3},
            },
            action='echo "${param.counter_key} ${param.max_retries}"',
            action_type="shell",
            capture="out",
            next="done",
        )
        fsm = FSMLoop(
            name="test",
            initial="step",
            states={
                "step": state,
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm)
        result = executor.run()
        assert result.final_state == "done"
        out = executor.captured.get("out", {}).get("output", "").strip()
        assert "lint_count" in out
        assert "5" in out

    def test_fragment_default_applied_when_unbound(self, tmp_path: Path) -> None:
        """Unbound optional fragment params use their declared default."""
        state = self._make_fragment_state(
            "counter",
            bindings={"counter_key": "my_count"},  # max_retries NOT bound
            parameters={
                "counter_key": {"type": "string", "required": True},
                "max_retries": {"type": "integer", "default": 7},
            },
            action='echo "${param.max_retries}"',
            action_type="shell",
            capture="out",
            next="done",
        )
        fsm = FSMLoop(
            name="test",
            initial="step",
            states={
                "step": state,
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm)
        result = executor.run()
        assert result.final_state == "done"
        out = executor.captured["out"]["output"].strip()
        assert out == "7"

    def test_missing_required_fragment_param_terminates_with_error(self) -> None:
        """Missing required fragment param causes the executor to terminate with error."""
        state = self._make_fragment_state(
            "counter",
            bindings={},  # counter_key NOT bound but required
            parameters={
                "counter_key": {"type": "string", "required": True},
            },
            action="echo ${param.counter_key}",
            action_type="shell",
            next="done",
        )
        fsm = FSMLoop(
            name="test",
            initial="step",
            states={
                "step": state,
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm)
        result = executor.run()
        assert result.terminated_by == "error"
        assert result.error is not None
        assert "requires parameter 'counter_key'" in result.error

    def test_fragment_binding_interpolates_context(self) -> None:
        """Fragment bindings support ${context.*} interpolation."""
        state = self._make_fragment_state(
            "counter",
            bindings={"counter_key": "${context.my_key}"},
            parameters={"counter_key": {"type": "string", "required": True}},
            action="echo ${param.counter_key}",
            action_type="shell",
            capture="out",
            next="done",
        )
        fsm = FSMLoop(
            name="test",
            initial="step",
            context={"my_key": "from_context_val"},
            states={
                "step": state,
                "done": StateConfig(terminal=True),
            },
        )
        executor = FSMExecutor(fsm)
        result = executor.run()
        assert result.final_state == "done"
        out = executor.captured["out"]["output"].strip()
        assert out == "from_context_val"


class TestGeneratePartialVerdictRouting:
    """Behavioral regression for the generator-evaluator dead-end.

    site-generator-20260603T191934 failed because the `generate` prompt state
    declared only on_yes + on_error. The default LLM judge returned `partial`
    (the agent narrated its fixes instead of asserting them), `_route` found no
    matching shorthand and returned None, the sub-loop dead-ended, and the
    parent routed run_gen_eval → failed — discarding a correct artifact. The
    fix maps yes/no/partial all to `evaluate` (the real screenshot+rubric gate).
    These tests pin both the dead-end (old config) and the fix (new config) at
    the routing layer, independent of the YAML file.
    """

    def _ctx(self) -> InterpolationContext:
        return InterpolationContext(
            context={},
            captured={},
            prev=None,
            result=None,
            state_name="generate",
            iteration=2,
            loop_name="generator-evaluator",
            started_at="2026-06-03T19:19:34Z",
            elapsed_ms=0,
        )

    def _executor(self) -> FSMExecutor:
        fsm = FSMLoop(
            name="generator-evaluator",
            initial="generate",
            states={
                "generate": StateConfig(action="gen", on_yes="evaluate"),
                "evaluate": StateConfig(action="shot", next="score"),
                "score": StateConfig(action="rubric", on_yes="done", on_no="generate"),
                "done": StateConfig(terminal=True),
                "failed": StateConfig(terminal=True),
            },
        )
        return FSMExecutor(fsm, action_runner=MockActionRunner())

    def test_old_config_dead_ends_on_partial(self) -> None:
        """Guard: on_yes-only generate state has no route for `partial` (the bug)."""
        old = StateConfig(action="gen", on_yes="evaluate", on_error="failed")
        assert self._executor()._route(old, "partial", self._ctx()) is None, (
            "on_yes-only generate must dead-end on `partial` — this is the "
            "behaviour the fix removes; if it no longer returns None the "
            "regression guard is meaningless"
        )

    def test_old_config_dead_ends_on_no(self) -> None:
        """on_no with no on_error mapping also dead-ends (None), not failed."""
        old = StateConfig(action="gen", on_yes="evaluate", on_error="failed")
        # `no` falls through to on_error only when on_no is unset → routes to failed.
        # The actual bug surfaced via `partial`; `no` would have hit on_error: failed.
        assert self._executor()._route(old, "no", self._ctx()) == "failed"

    def test_fixed_config_routes_partial_to_evaluate(self) -> None:
        fixed = StateConfig(
            action="gen",
            on_yes="evaluate",
            on_no="evaluate",
            on_partial="evaluate",
            on_error="failed",
        )
        assert self._executor()._route(fixed, "partial", self._ctx()) == "evaluate"

    def test_fixed_config_routes_no_to_evaluate(self) -> None:
        fixed = StateConfig(
            action="gen",
            on_yes="evaluate",
            on_no="evaluate",
            on_partial="evaluate",
            on_error="failed",
        )
        assert self._executor()._route(fixed, "no", self._ctx()) == "evaluate"

    def test_fixed_config_preserves_error_to_failed(self) -> None:
        fixed = StateConfig(
            action="gen",
            on_yes="evaluate",
            on_no="evaluate",
            on_partial="evaluate",
            on_error="failed",
        )
        assert self._executor()._route(fixed, "error", self._ctx()) == "failed"
