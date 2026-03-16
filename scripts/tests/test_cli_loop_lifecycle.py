"""Tests for cli/loop/lifecycle.py - status, stop, resume commands."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.loop.lifecycle import cmd_resume, cmd_status, cmd_stop


class TestCmdStatus:
    """Tests for cmd_status."""

    def test_no_state_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when no state found."""
        logger = MagicMock()

        with patch("little_loops.fsm.persistence.StatePersistence") as mock_cls:
            mock_cls.return_value.load_state.return_value = None
            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 1
        logger.error.assert_called_once()

    def test_status_prints_state(self, tmp_path: Path) -> None:
        """Prints state information when found."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.loop_name = "test-loop"
        mock_state.status = "running"
        mock_state.current_state = "check"
        mock_state.iteration = 5
        mock_state.started_at = "2026-02-14T10:00:00"
        mock_state.updated_at = "2026-02-14T10:05:00"
        mock_state.continuation_prompt = None

        with (
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("builtins.print") as mock_print,
        ):
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "test-loop" in print_text
        assert "running" in print_text

    def test_status_with_continuation_prompt(self, tmp_path: Path) -> None:
        """Shows truncated continuation prompt when present."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.loop_name = "test-loop"
        mock_state.status = "awaiting_continuation"
        mock_state.current_state = "check"
        mock_state.iteration = 3
        mock_state.started_at = "2026-02-14T10:00:00"
        mock_state.updated_at = "2026-02-14T10:05:00"
        mock_state.continuation_prompt = "A" * 300  # Long prompt

        with (
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("builtins.print") as mock_print,
        ):
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "..." in print_text  # Truncated


class TestCmdStop:
    """Tests for cmd_stop."""

    def test_no_state_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when no state found."""
        logger = MagicMock()

        with patch("little_loops.fsm.persistence.StatePersistence") as mock_cls:
            mock_cls.return_value.load_state.return_value = None
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 1

    def test_not_running_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when loop is not running."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "completed"

        with patch("little_loops.fsm.persistence.StatePersistence") as mock_cls:
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 1
        logger.error.assert_called_once()

    def test_running_loop_stopped(self, tmp_path: Path) -> None:
        """Successfully stops a running loop."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        with patch("little_loops.fsm.persistence.StatePersistence") as mock_cls:
            mock_persistence = mock_cls.return_value
            mock_persistence.load_state.return_value = mock_state
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        assert mock_state.status == "interrupted"
        mock_persistence.save_state.assert_called_once_with(mock_state)

    def test_stop_with_pid_sends_sigterm_and_waits(self, tmp_path: Path) -> None:
        """Sends SIGTERM and polls for exit when PID file exists (BUG-592)."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir()
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")

        # Process alive on first check, dead after SIGTERM poll
        alive_seq = [True, True, False]

        with (
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("little_loops.cli.loop.lifecycle._process_alive", side_effect=alive_seq),
            patch("little_loops.cli.loop.lifecycle.os.kill") as mock_kill,
            patch("little_loops.cli.loop.lifecycle.time.sleep"),
        ):
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        mock_kill.assert_any_call(12345, signal.SIGTERM)
        assert mock_state.status == "interrupted"
        mock_cls.return_value.save_state.assert_called_once_with(mock_state)
        assert not pid_file.exists(), "PID file should be removed after SIGTERM stop"

    def test_stop_sends_sigkill_if_process_does_not_exit(self, tmp_path: Path) -> None:
        """Escalates to SIGKILL after grace period if process does not exit (BUG-592)."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir()
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")

        # Process stays alive through all polls: first check (alive) + 10 poll iterations
        alive_seq = [True] + [True] * 10

        with (
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("little_loops.cli.loop.lifecycle._process_alive", side_effect=alive_seq),
            patch("little_loops.cli.loop.lifecycle.os.kill") as mock_kill,
            patch("little_loops.cli.loop.lifecycle.time.sleep"),
        ):
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        mock_kill.assert_any_call(12345, signal.SIGTERM)
        mock_kill.assert_any_call(12345, signal.SIGKILL)
        logger.warning.assert_called_once()
        assert mock_state.status == "interrupted"
        assert not pid_file.exists(), "PID file should be removed after SIGKILL stop"

    def test_stop_sigkill_handles_race_if_process_exits_between_poll_and_kill(
        self, tmp_path: Path
    ) -> None:
        """OSError on SIGKILL is swallowed when process exits just before the kill (BUG-592)."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir()
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")

        alive_seq = [True] + [True] * 10

        def kill_side_effect(pid: int, sig: int) -> None:
            if sig == signal.SIGKILL:
                raise OSError("No such process")

        with (
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("little_loops.cli.loop.lifecycle._process_alive", side_effect=alive_seq),
            patch("little_loops.cli.loop.lifecycle.os.kill", side_effect=kill_side_effect),
            patch("little_loops.cli.loop.lifecycle.time.sleep"),
        ):
            mock_cls.return_value.load_state.return_value = mock_state
            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0  # No exception propagated
        assert mock_state.status == "interrupted"
        assert not pid_file.exists(), "PID file should be removed even when SIGKILL raises OSError"


class TestCmdResume:
    """Tests for cmd_resume."""

    def test_file_not_found_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when loop file not found."""
        logger = MagicMock()
        args = argparse.Namespace()

        with patch(
            "little_loops.cli.loop.lifecycle.load_loop",
            side_effect=FileNotFoundError("Not found"),
        ):
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 1
        logger.error.assert_called_once()

    def test_validation_error_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when loop has validation errors."""
        logger = MagicMock()
        args = argparse.Namespace()

        with patch(
            "little_loops.cli.loop.lifecycle.load_loop",
            side_effect=ValueError("Invalid FSM"),
        ):
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 1

    def test_nothing_to_resume_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when nothing to resume."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = None
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 1

    def test_resume_success(self, tmp_path: Path) -> None:
        """Returns 0 on successful terminal resume."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 5
        mock_result.duration_ms = 30000  # 30 seconds
        mock_result.terminated_by = "terminal"

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0

    def test_resume_with_minutes_duration(self, tmp_path: Path) -> None:
        """Duration is formatted in minutes when >= 60s."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 10
        mock_result.duration_ms = 120000  # 2 minutes
        mock_result.terminated_by = "terminal"

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        # Check logger was called with duration in minutes format
        success_text = str(logger.success.call_args)
        assert "2m" in success_text

    def test_resume_awaiting_continuation(self, tmp_path: Path) -> None:
        """Shows context when resuming from awaiting_continuation."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_state = MagicMock()
        mock_state.status = "awaiting_continuation"
        mock_state.iteration = 5
        mock_state.continuation_prompt = "A" * 600  # Long prompt

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 8
        mock_result.duration_ms = 5000
        mock_result.terminated_by = "terminal"

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("builtins.print") as mock_print,
        ):
            mock_persist_cls.return_value.load_state.return_value = mock_state
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "..." in print_text  # Truncated prompt
        assert "Resuming from context handoff" in print_text

    def test_resume_non_terminal_returns_1(self, tmp_path: Path) -> None:
        """Returns 1 when resumed loop didn't reach terminal state."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_result = MagicMock()
        mock_result.final_state = "error"
        mock_result.iterations = 5
        mock_result.duration_ms = 10000
        mock_result.terminated_by = "max_iterations"

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 1

    def test_resume_registers_signal_handlers(self, tmp_path: Path) -> None:
        """cmd_resume registers SIGINT/SIGTERM handlers before calling resume (BUG-600)."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 3
        mock_result.duration_ms = 5000
        mock_result.terminated_by = "terminal"

        with (
            patch(
                "little_loops.cli.loop.lifecycle.load_loop",
                return_value=mock_fsm,
            ),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.register_loop_signal_handlers") as mock_register,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        expected_pid_file = tmp_path / ".running" / "test-loop.pid"
        mock_register.assert_called_once_with(
            mock_exec_cls.return_value, pid_file=expected_pid_file
        )

    def test_context_overrides_applied_to_fsm(self, tmp_path: Path) -> None:
        """--context KEY=VALUE overrides are applied to fsm.context before execution."""
        logger = MagicMock()
        args = argparse.Namespace(context=["issue_id=042", "mode=fast"])
        mock_fsm = MagicMock()
        mock_fsm.context = {"issue_id": "001"}

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        assert mock_fsm.context["issue_id"] == "042"
        assert mock_fsm.context["mode"] == "fast"

    def test_context_invalid_format_raises_system_exit(self, tmp_path: Path) -> None:
        """--context value missing '=' raises SystemExit with clear message."""
        logger = MagicMock()
        args = argparse.Namespace(context=["badvalue"])
        mock_fsm = MagicMock()
        mock_fsm.context = {}

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            with pytest.raises(SystemExit) as exc_info:
                cmd_resume("test-loop", args, tmp_path, logger)

        assert "KEY=VALUE" in str(exc_info.value)

    def test_resume_signal_handler_triggers_graceful_shutdown(self, tmp_path: Path) -> None:
        """Ctrl-C during resume calls request_shutdown() instead of raising KeyboardInterrupt."""
        from little_loops.cli.loop._helpers import _loop_signal_handler

        mock_executor = MagicMock()

        import little_loops.cli.loop._helpers as _h

        _h._loop_shutdown_requested = False
        _h._loop_executor = mock_executor
        _h._loop_pid_file = None

        # Simulate first Ctrl-C (SIGINT)
        _loop_signal_handler(signal.SIGINT, None)

        mock_executor.request_shutdown.assert_called_once()


class TestCmdResumeBackground:
    """Tests for cmd_resume --background flag (FEAT-608)."""

    def test_background_flag_calls_run_background(self, tmp_path: Path) -> None:
        """--background flag delegates to run_background() with subcommand='resume'."""
        logger = MagicMock()
        args = argparse.Namespace(background=True)

        with patch("little_loops.cli.loop.lifecycle.run_background") as mock_rb:
            mock_rb.return_value = 0
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        mock_rb.assert_called_once_with("test-loop", args, tmp_path, subcommand="resume")

    def test_background_skips_foreground_execution(self, tmp_path: Path) -> None:
        """--background flag returns before calling executor.resume()."""
        logger = MagicMock()
        args = argparse.Namespace(background=True)

        with (
            patch("little_loops.cli.loop.lifecycle.run_background", return_value=0),
            patch("little_loops.cli.loop.lifecycle.load_loop") as mock_load,
        ):
            cmd_resume("test-loop", args, tmp_path, logger)

        mock_load.assert_not_called()

    def test_no_background_flag_runs_foreground(self, tmp_path: Path) -> None:
        """Without --background, resume runs in foreground (default unchanged)."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()
        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.run_background") as mock_rb,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        mock_rb.assert_not_called()

    def test_foreground_internal_registers_pid_cleanup(self, tmp_path: Path) -> None:
        """--foreground-internal registers atexit PID cleanup for background-resumed process."""

        logger = MagicMock()
        args = argparse.Namespace(foreground_internal=True)
        mock_fsm = MagicMock()
        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("123")

        registered: list = []

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.atexit.register", side_effect=registered.append),
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        assert len(registered) == 1  # PID cleanup was registered

    def test_plain_foreground_resume_writes_pid_file(self, tmp_path: Path) -> None:
        """Plain foreground resume writes a PID file so cmd_stop can send SIGTERM (BUG-639)."""
        logger = MagicMock()
        args = argparse.Namespace()  # no background, no foreground_internal
        mock_fsm = MagicMock()
        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.os.getpid", return_value=99999),
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            result = cmd_resume("test-loop", args, tmp_path, logger)

        assert result == 0
        pid_file = tmp_path / ".running" / "test-loop.pid"
        assert pid_file.exists(), "PID file should be written for plain foreground resume (BUG-639)"
        assert pid_file.read_text() == "99999"

    def test_plain_foreground_resume_pid_passed_to_signal_handler(self, tmp_path: Path) -> None:
        """Signal handler receives the PID file so force-exit cleans it up (BUG-639)."""
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()
        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.register_loop_signal_handlers") as mock_reg,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            cmd_resume("test-loop", args, tmp_path, logger)

        expected_pid_file = tmp_path / ".running" / "test-loop.pid"
        mock_reg.assert_called_once_with(mock_exec_cls.return_value, pid_file=expected_pid_file)

    def test_foreground_internal_does_not_overwrite_parent_pid(self, tmp_path: Path) -> None:
        """--foreground-internal skips writing PID (parent wrote it); existing PID preserved (BUG-639)."""
        logger = MagicMock()
        args = argparse.Namespace(foreground_internal=True)
        mock_fsm = MagicMock()
        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = "terminal"

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")  # Parent-written PID

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
            patch("little_loops.cli.loop.lifecycle.atexit.register"),
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            cmd_resume("test-loop", args, tmp_path, logger)

        assert pid_file.read_text() == "12345", "Parent-written PID should not be overwritten"


class TestCmdResumeExitCodes:
    """Tests for cmd_resume exit code mapping per terminated_by value (BUG-605)."""

    def _resume_with_terminated_by(self, tmp_path: Path, terminated_by: str) -> int:
        logger = MagicMock()
        args = argparse.Namespace()
        mock_fsm = MagicMock()

        mock_result = MagicMock()
        mock_result.final_state = "done"
        mock_result.iterations = 1
        mock_result.duration_ms = 1000
        mock_result.terminated_by = terminated_by

        with (
            patch("little_loops.cli.loop.lifecycle.load_loop", return_value=mock_fsm),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_persist_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor") as mock_exec_cls,
        ):
            mock_persist_cls.return_value.load_state.return_value = None
            mock_exec_cls.return_value.resume.return_value = mock_result
            return cmd_resume("test-loop", args, tmp_path, logger)

    @pytest.mark.parametrize("terminated_by", ["terminal", "signal", "handoff"])
    def test_zero_exit_for_graceful_termination(self, tmp_path: Path, terminated_by: str) -> None:
        """terminal, signal, and handoff all return exit code 0."""
        assert self._resume_with_terminated_by(tmp_path, terminated_by) == 0

    @pytest.mark.parametrize("terminated_by", ["max_iterations", "timeout"])
    def test_nonzero_exit_for_limit_termination(self, tmp_path: Path, terminated_by: str) -> None:
        """max_iterations and timeout return exit code 1."""
        assert self._resume_with_terminated_by(tmp_path, terminated_by) == 1

    def test_unknown_terminated_by_returns_1(self, tmp_path: Path) -> None:
        """Unknown terminated_by values fall back to exit code 1."""
        assert self._resume_with_terminated_by(tmp_path, "unexpected") == 1


class TestCmdRunHandoffThreshold:
    """Tests for --handoff-threshold handling in cmd_run (ENH-768)."""

    def _make_args(
        self, handoff_threshold: int | None = None, **kwargs: object
    ) -> argparse.Namespace:
        defaults = {
            "input": None,
            "context": [],
            "max_iterations": None,
            "delay": None,
            "no_llm": False,
            "llm_model": None,
            "dry_run": True,
            "background": False,
            "foreground_internal": False,
            "quiet": False,
            "verbose": False,
            "show_diagrams": False,
            "clear": False,
            "queue": False,
            "handoff_threshold": handoff_threshold,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _make_loop(self, tmp_path: Path) -> Path:
        """Create a minimal loop YAML in tmp_path."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        return loops_dir

    def test_handoff_threshold_sets_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting --handoff-threshold writes LL_HANDOFF_THRESHOLD to env."""
        import os

        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        monkeypatch.delenv("LL_HANDOFF_THRESHOLD", raising=False)
        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(handoff_threshold=40)
        logger = Logger(use_color=False)

        result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 0
        assert os.environ.get("LL_HANDOFF_THRESHOLD") == "40"

    def test_handoff_threshold_none_does_not_set_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When --handoff-threshold is not set, LL_HANDOFF_THRESHOLD is left alone."""
        import os

        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        monkeypatch.delenv("LL_HANDOFF_THRESHOLD", raising=False)
        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(handoff_threshold=None)
        logger = Logger(use_color=False)

        cmd_run("test-loop", args, loops_dir, logger)

        assert "LL_HANDOFF_THRESHOLD" not in os.environ

    def test_handoff_threshold_out_of_range_raises(self, tmp_path: Path) -> None:
        """--handoff-threshold outside 1-100 raises SystemExit."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        logger = Logger(use_color=False)

        with pytest.raises(SystemExit):
            cmd_run("test-loop", self._make_args(handoff_threshold=0), loops_dir, logger)

        with pytest.raises(SystemExit):
            cmd_run("test-loop", self._make_args(handoff_threshold=101), loops_dir, logger)
