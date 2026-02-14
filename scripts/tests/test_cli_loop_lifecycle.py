"""Tests for cli/loop/lifecycle.py - status, stop, resume commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

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
