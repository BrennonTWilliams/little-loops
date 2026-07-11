"""Tests for FSM action runner implementations (runners.py).

Covers SimulationActionRunner scenarios, _prompt_result() inputs, and
DefaultActionRunner shell/slash paths. Skips _current_process lifecycle
(already tested in test_fsm_executor.py:TestDefaultActionRunnerProcessTracking).
"""

from __future__ import annotations

import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import ActionResult, DefaultActionRunner, SimulationActionRunner


class _MockFileObj:
    """File-like object supporting fileno() and readline() for selector tests."""

    def __init__(self, lines: list[str] | None = None):
        self._lines = list(lines) if lines else []
        self._pos = 0
        self._closed = False

    def fileno(self) -> int:
        return id(self) % 65536

    def readline(self) -> str:
        if self._closed:
            return ""
        if self._pos < len(self._lines):
            line = self._lines[self._pos]
            self._pos += 1
            return line
        return ""  # EOF

    def close(self) -> None:
        self._closed = True


def _make_selector_mock_process(
    stdout_lines: list[str] | None = None,
    stderr_lines: list[str] | None = None,
    returncode: int = 0,
) -> MagicMock:
    """Create a mock Popen process compatible with the selector-based runner.

    Returns a MagicMock whose stdout/stderr are _MockFileObj instances
    that support fileno() and readline().
    """
    proc = MagicMock()
    proc.stdout = _MockFileObj(stdout_lines or [])
    proc.stderr = _MockFileObj(stderr_lines or [])
    proc.returncode = returncode
    proc.pid = 12345
    proc.wait.return_value = None
    proc.kill.return_value = None
    return proc


def _make_ready_selector(fileobj_map: dict) -> MagicMock:
    """Create a mock DefaultSelector that simulates real selector behavior.

    Returns all registered keys as EVENT_READ on every select() call.
    The caller reads lines via key.fileobj.readline() and unregisters
    pipes when they return EOF (empty string). This mirrors how the
    real selector loop works.
    """
    sel = MagicMock()
    _registered: dict = {}

    def _register(fobj, events, data=None):
        _registered[fobj] = (events, data)

    def _unregister(fobj):
        _registered.pop(fobj, None)

    def _get_map():
        return dict(_registered)

    def _select(timeout=None):
        result = []
        for fobj, (events, data) in list(_registered.items()):
            key = MagicMock()
            key.fileobj = fobj
            key.data = data
            key.events = events
            result.append((key, events))
        return result

    sel.register.side_effect = _register
    sel.unregister.side_effect = _unregister
    sel.get_map.side_effect = _get_map
    sel.select.side_effect = _select
    sel.close.return_value = None
    return sel


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
    """Test DefaultActionRunner executing shell commands via subprocess.Popen.

    Uses selector-based I/O (mirrors the production code after the
    timeout dead-zone fix). Tests patch both subprocess.Popen and
    selectors.DefaultSelector to control pipe I/O and timeout behavior.
    """

    def test_on_output_line_called_for_each_line(self) -> None:
        lines_received: list[str] = []
        proc = _make_selector_mock_process(
            stdout_lines=["line1\n", "line2\n"],
        )
        sel = _make_ready_selector({})

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
        ):
            runner = DefaultActionRunner()
            runner.run("echo hi", 30, False, on_output_line=lines_received.append)

        assert "line1" in lines_received
        assert "line2" in lines_received

    def test_exit_code_propagated(self) -> None:
        proc = _make_selector_mock_process(returncode=42)
        sel = _make_ready_selector({})

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
        ):
            runner = DefaultActionRunner()
            result = runner.run("exit 42", 30, False)

        assert result.exit_code == 42

    def test_stdout_captured(self) -> None:
        proc = _make_selector_mock_process(
            stdout_lines=["hello\n", "world\n"],
        )
        sel = _make_ready_selector({})

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
        ):
            runner = DefaultActionRunner()
            result = runner.run("echo", 30, False)

        assert "hello\n" in result.output
        assert "world\n" in result.output

    def test_stderr_captured(self) -> None:
        proc = _make_selector_mock_process(
            stderr_lines=["err line\n"],
            returncode=1,
        )
        sel = _make_ready_selector({})

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
        ):
            runner = DefaultActionRunner()
            result = runner.run("cmd", 30, False)

        assert "err line" in result.stderr

    def test_timeout_returns_exit_code_124(self) -> None:
        """Timeout fires when wall-clock deadline passes before any data is read."""
        proc = _make_selector_mock_process()
        sel = MagicMock()
        sel.get_map.return_value = {"fake_key": "fake_val"}  # never empty → loop continues
        sel.select.return_value = []  # no data ever ready
        sel.close.return_value = None
        sel.register.return_value = None

        runner = DefaultActionRunner()

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group") as mock_killpg,
        ):
            result = runner.run("sleep 100", 0, False)  # timeout=0 → immediate deadline

        assert result.exit_code == 124
        assert "timed out" in result.stderr.lower()
        mock_killpg.assert_called_once_with(proc)

    def test_timeout_stderr_contains_message(self) -> None:
        """Timeout path produces a meaningful stderr message."""
        proc = _make_selector_mock_process()
        sel = MagicMock()
        sel.get_map.return_value = {"k": "v"}
        sel.select.return_value = []
        sel.close.return_value = None
        sel.register.return_value = None

        runner = DefaultActionRunner()

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group"),
        ):
            result = runner.run("sleep 100", 0, False)

        assert result.exit_code == 124
        assert "timed out" in result.stderr.lower()

    def test_hanging_process_timeout_fires_during_read(self) -> None:
        """Timeout fires even when selector returns no ready pipes.

        Simulates a process that registers pipes but never produces output.
        The wall-clock deadline passes and the timeout path is taken.
        """
        proc = _make_selector_mock_process()
        sel = MagicMock()
        # get_map() non-empty → loop body runs; select() empty → no data
        sel.get_map.return_value = {"pipe": "data"}
        sel.select.return_value = []
        sel.close.return_value = None
        sel.register.return_value = None

        runner = DefaultActionRunner()

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group") as mock_killpg,
        ):
            result = runner.run("hang forever", 0, False)

        assert result.exit_code == 124
        mock_killpg.assert_called_once_with(proc)

    def test_stderr_captured_when_stdout_empty(self) -> None:
        """Stderr output is captured correctly when stdout produces nothing."""
        proc = _make_selector_mock_process(
            stderr_lines=["error1\n", "error2\n"],
            returncode=1,
        )
        sel = _make_ready_selector({})

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
        ):
            runner = DefaultActionRunner()
            result = runner.run("failing-cmd", 30, False)

        assert "error1" in result.stderr
        assert "error2" in result.stderr
        assert result.exit_code == 1


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

    def test_model_kwarg_forwarded(self) -> None:
        runner = DefaultActionRunner()
        completed = self._make_completed_process()
        captured_kwargs: dict = {}

        def capture(**kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=capture):
            runner.run("/ll:skill", 60, True, model="claude-haiku-4-5-20251001")

        assert captured_kwargs.get("model") == "claude-haiku-4-5-20251001"

    def test_working_dir_kwarg_forwarded(self, tmp_path: Path) -> None:
        """working_dir threads through to run_claude_command (ENH-2609)."""
        runner = DefaultActionRunner()
        completed = self._make_completed_process()
        captured_kwargs: dict = {}

        def capture(**kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=capture):
            runner.run("/ll:skill", 60, True, working_dir=tmp_path)

        assert captured_kwargs.get("working_dir") == tmp_path


class TestDefaultActionRunnerWorkingDir:
    """ENH-2609: shell actions honor the working_dir override."""

    def test_shell_runs_in_working_dir(self, tmp_path: Path) -> None:
        runner = DefaultActionRunner()
        result = runner.run("pwd", 10, False, working_dir=tmp_path)
        assert result.exit_code == 0
        assert Path(result.output.strip()).resolve() == tmp_path.resolve()

    def test_shell_defaults_to_inherited_cwd(self) -> None:
        runner = DefaultActionRunner()
        result = runner.run("pwd", 10, False)
        assert result.exit_code == 0
        assert Path(result.output.strip()).resolve() == Path.cwd().resolve()
