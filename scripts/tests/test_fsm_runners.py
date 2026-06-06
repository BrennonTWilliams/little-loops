"""Tests for FSM action runner implementations (runners.py).

Covers SimulationActionRunner scenarios, _prompt_result() inputs, and
DefaultActionRunner shell/slash paths. Skips _current_process lifecycle
(already tested in test_fsm_executor.py:TestDefaultActionRunnerProcessTracking).
"""

from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import ActionResult, DefaultActionRunner, SimulationActionRunner


class TestSimulationActionRunnerScenarios:
    """Test all five predefined scenario patterns."""

    def _make_runner(self, scenario: str) -> SimulationActionRunner:
        return SimulationActionRunner(scenario=scenario)

    def test_all_pass_always_returns_zero(self) -> None:
        runner = self._make_runner("all-pass")
        for _ in range(3):
            result = runner.run("echo hi", 30, False)
            assert result.exit_code == 0

    def test_all_fail_always_returns_one(self) -> None:
        runner = self._make_runner("all-fail")
        for _ in range(3):
            result = runner.run("echo hi", 30, False)
            assert result.exit_code == 1

    def test_all_error_always_returns_two(self) -> None:
        runner = self._make_runner("all-error")
        for _ in range(3):
            result = runner.run("echo hi", 30, False)
            assert result.exit_code == 2

    def test_first_fail_first_call_fails(self) -> None:
        runner = self._make_runner("first-fail")
        result = runner.run("echo hi", 30, False)
        assert result.exit_code == 1

    def test_first_fail_subsequent_calls_pass(self) -> None:
        runner = self._make_runner("first-fail")
        runner.run("echo hi", 30, False)  # call 1 — fails
        result2 = runner.run("echo hi", 30, False)
        assert result2.exit_code == 0
        result3 = runner.run("echo hi", 30, False)
        assert result3.exit_code == 0

    def test_alternating_odd_calls_fail(self) -> None:
        runner = self._make_runner("alternating")
        result1 = runner.run("a", 30, False)  # call 1 (odd) — fail
        result2 = runner.run("b", 30, False)  # call 2 (even) — pass
        result3 = runner.run("c", 30, False)  # call 3 (odd) — fail
        assert result1.exit_code == 1
        assert result2.exit_code == 0
        assert result3.exit_code == 1

    def test_call_count_tracks_invocations(self) -> None:
        runner = self._make_runner("all-pass")
        assert runner.call_count == 0
        runner.run("a", 30, False)
        runner.run("b", 30, False)
        assert runner.call_count == 2

    def test_calls_list_records_actions(self) -> None:
        runner = self._make_runner("all-pass")
        runner.run("action-one", 30, False)
        runner.run("action-two", 30, True)
        assert runner.calls == ["action-one", "action-two"]

    def test_action_result_contains_simulated_output(self) -> None:
        runner = self._make_runner("all-pass")
        result = runner.run("my-action", 30, False)
        assert isinstance(result, ActionResult)
        assert "my-action" in result.output
        assert result.stderr == ""
        assert result.duration_ms == 0

    def test_unknown_scenario_returns_zero(self) -> None:
        runner = SimulationActionRunner(scenario="nonexistent-scenario")
        result = runner.run("x", 30, False)
        assert result.exit_code == 0


class TestSimulationActionRunnerPromptResult:
    """Test interactive _prompt_result() input handling."""

    def _run_with_stdin(self, input_text: str) -> int:
        runner = SimulationActionRunner()
        with patch("sys.stdin", StringIO(input_text)):
            return runner._prompt_result()

    def test_choice_1_returns_success(self) -> None:
        assert self._run_with_stdin("1\n") == 0

    def test_choice_2_returns_failure(self) -> None:
        assert self._run_with_stdin("2\n") == 1

    def test_choice_3_returns_error(self) -> None:
        assert self._run_with_stdin("3\n") == 2

    def test_empty_input_defaults_to_success(self) -> None:
        assert self._run_with_stdin("\n") == 0

    def test_eof_returns_success(self) -> None:
        runner = SimulationActionRunner()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.side_effect = EOFError
            result = runner._prompt_result()
        assert result == 0

    def test_keyboard_interrupt_returns_success(self) -> None:
        runner = SimulationActionRunner()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.readline.side_effect = KeyboardInterrupt
            result = runner._prompt_result()
        assert result == 0

    def test_invalid_then_valid_retries(self) -> None:
        runner = SimulationActionRunner()
        with patch("sys.stdin", StringIO("bad\n2\n")):
            result = runner._prompt_result()
        assert result == 1


class TestDefaultActionRunnerShellPath:
    """Test DefaultActionRunner executing shell commands via subprocess.Popen."""

    def _make_mock_process(
        self,
        stdout_lines: list[str],
        stderr_lines: list[str],
        returncode: int = 0,
    ) -> MagicMock:
        proc = MagicMock()
        proc.stdout = iter(stdout_lines)
        proc.stderr = iter(stderr_lines)
        proc.returncode = returncode
        proc.wait.return_value = None
        proc.kill.return_value = None
        return proc

    def test_on_output_line_called_for_each_line(self) -> None:
        lines_received: list[str] = []
        proc = self._make_mock_process(["line1\n", "line2\n"], [])
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            runner.run("echo hi", 30, False, on_output_line=lines_received.append)

        assert "line1" in lines_received
        assert "line2" in lines_received

    def test_exit_code_propagated(self) -> None:
        proc = self._make_mock_process([], [], returncode=42)
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            result = runner.run("exit 42", 30, False)

        assert result.exit_code == 42

    def test_stdout_captured(self) -> None:
        proc = self._make_mock_process(["hello\n", "world\n"], [])
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            result = runner.run("echo", 30, False)

        assert "hello\n" in result.output
        assert "world\n" in result.output

    def test_stderr_captured(self) -> None:
        proc = self._make_mock_process([], ["err line\n"], returncode=1)
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            result = runner.run("cmd", 30, False)

        assert "err line" in result.stderr

    def test_timeout_returns_exit_code_124(self) -> None:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.stderr = iter([])
        proc.returncode = -9
        # First wait() (with timeout) raises; second wait() (in except) succeeds
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        proc.kill.return_value = None
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            result = runner.run("sleep 100", 5, False)

        assert result.exit_code == 124

    def test_timeout_stderr_contains_message(self) -> None:
        proc = MagicMock()
        proc.stdout = iter([])
        proc.stderr = iter([])
        # First wait() raises; second wait() in except block succeeds
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        proc.kill.return_value = None
        runner = DefaultActionRunner()

        with patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc):
            result = runner.run("sleep 100", 5, False)

        assert "timed out" in result.stderr.lower() or result.exit_code == 124


class TestDefaultActionRunnerSlashPath:
    """Test DefaultActionRunner executing slash commands via run_claude_command."""

    def _make_completed_process(
        self, stdout: str = "", stderr: str = "", returncode: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_run_claude_command_called_for_slash_commands(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process(stdout="output", returncode=0)

        with patch(
            "little_loops.fsm.runners.run_claude_command", return_value=completed
        ) as mock_fn:
            runner.run("/ll:my-skill arg", 60, True)

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args
        assert "/ll:my-skill arg" in str(call_kwargs)

    def test_slash_result_maps_to_action_result(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process(stdout="hello", stderr="warn", returncode=0)

        with patch("little_loops.fsm.runners.run_claude_command", return_value=completed):
            result = runner.run("/ll:check", 60, True)

        assert result.output == "hello"
        assert result.stderr == "warn"
        assert result.exit_code == 0

    def test_slash_timeout_returns_exit_code_124(self) -> None:
        runner = DefaultActionRunner()

        with patch(
            "little_loops.fsm.runners.run_claude_command",
            side_effect=subprocess.TimeoutExpired("cmd", 60),
        ):
            result = runner.run("/ll:slow-skill", 60, True)

        assert result.exit_code == 124
        assert result.duration_ms == 60 * 1000

    def test_on_usage_detailed_forwarded_to_run_claude_command(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process()
        received_kwargs: dict = {}

        def capture(**kwargs: object) -> subprocess.CompletedProcess[str]:
            received_kwargs.update(kwargs)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=capture):
            runner.run("/ll:skill", 60, True, on_usage_detailed=lambda u: None)

        assert "on_usage_detailed" in received_kwargs

    def test_stream_callback_fires_on_non_stderr_lines(self) -> None:
        runner = DefaultActionRunner()
        lines_seen: list[str] = []
        completed = self._make_completed_process(stdout="streamed")

        def fake_run(**kwargs: object) -> subprocess.CompletedProcess[str]:
            cb = kwargs.get("stream_callback")
            if cb:
                cb("streamed line", False)
                cb("stderr line", True)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=fake_run):
            runner.run("/ll:skill", 60, True, on_output_line=lines_seen.append)

        assert "streamed line" in lines_seen
        assert "stderr line" not in lines_seen

    def test_agent_kwarg_forwarded(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process()
        captured_kwargs: dict = {}

        def capture(**kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=capture):
            runner.run("/ll:skill", 60, True, agent="my-agent")

        assert captured_kwargs.get("agent") == "my-agent"

    def test_tools_kwarg_forwarded(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process()
        captured_kwargs: dict = {}

        def capture(**kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=capture):
            runner.run("/ll:skill", 60, True, tools=["Read", "Grep"])

        assert captured_kwargs.get("tools") == ["Read", "Grep"]
