"""Tests for ll-loop background/daemon mode (FEAT-487)."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLoopSignalHandler:
    """Tests for loop signal handler (state lives in _helpers since BUG-600)."""

    @classmethod
    def setup_class(cls) -> None:
        """Import module for signal handler access."""
        import little_loops.cli.loop._helpers as helpers_module

        cls.helpers = helpers_module

    def setup_method(self) -> None:
        """Reset global state before each test."""
        self.helpers._loop_shutdown_requested = False
        self.helpers._loop_executor = None
        self.helpers._loop_pid_file = None
        self.helpers._using_alt_screen = False

    def teardown_method(self) -> None:
        """Reset global state after each test."""
        self.helpers._loop_shutdown_requested = False
        self.helpers._loop_executor = None
        self.helpers._loop_pid_file = None
        self.helpers._using_alt_screen = False

    def test_first_signal_sets_flag(self) -> None:
        """First signal sets shutdown flag without exiting."""
        self.helpers._loop_signal_handler(signal.SIGINT, None)
        assert self.helpers._loop_shutdown_requested is True

    def test_first_signal_calls_request_shutdown(self) -> None:
        """First signal calls executor.request_shutdown() if set."""
        mock_executor = MagicMock()
        self.helpers._loop_executor = mock_executor

        self.helpers._loop_signal_handler(signal.SIGTERM, None)

        assert self.helpers._loop_shutdown_requested is True
        mock_executor.request_shutdown.assert_called_once()

    def test_second_signal_forces_exit(self) -> None:
        """Second signal forces immediate exit with code 1."""
        self.helpers._loop_signal_handler(signal.SIGINT, None)
        assert self.helpers._loop_shutdown_requested is True

        with pytest.raises(SystemExit) as exc_info:
            self.helpers._loop_signal_handler(signal.SIGTERM, None)

        assert exc_info.value.code == 1

    def test_signal_handler_kills_current_process(self) -> None:
        """Signal handler kills _current_process on the action runner (BUG-592)."""
        mock_process = MagicMock()
        mock_inner = MagicMock()
        mock_inner.action_runner._current_process = mock_process
        mock_executor = MagicMock()
        mock_executor._executor = mock_inner
        self.helpers._loop_executor = mock_executor

        self.helpers._loop_signal_handler(signal.SIGTERM, None)

        mock_process.kill.assert_called_once()

    def test_signal_handler_kills_fsm_executor_current_process(self) -> None:
        """Signal handler kills _current_process on FSMExecutor for MCP path (BUG-818)."""
        mock_fsm_process = MagicMock()
        mock_inner = MagicMock()
        mock_inner.action_runner._current_process = None
        mock_inner._current_process = mock_fsm_process
        mock_executor = MagicMock()
        mock_executor._executor = mock_inner
        self.helpers._loop_executor = mock_executor

        self.helpers._loop_signal_handler(signal.SIGTERM, None)

        mock_fsm_process.kill.assert_called_once()

    def test_signal_handler_no_current_process_is_safe(self) -> None:
        """Signal handler doesn't crash when _current_process is None (BUG-592)."""
        mock_inner = MagicMock()
        mock_inner.action_runner._current_process = None
        mock_inner._current_process = None
        mock_executor = MagicMock()
        mock_executor._executor = mock_inner
        self.helpers._loop_executor = mock_executor

        # Should not raise
        self.helpers._loop_signal_handler(signal.SIGTERM, None)
        assert self.helpers._loop_shutdown_requested is True

    def test_second_signal_cleans_pid_file(self, tmp_path: Path) -> None:
        """Second signal cleans up PID file before exiting."""
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("12345")
        self.helpers._loop_pid_file = pid_file

        self.helpers._loop_signal_handler(signal.SIGINT, None)

        with pytest.raises(SystemExit):
            self.helpers._loop_signal_handler(signal.SIGINT, None)

        assert not pid_file.exists()

    def test_signal_handler_second_signal_emits_alt_screen_exit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Second signal emits alt-screen exit sequence to stderr when alt screen is active."""
        self.helpers._using_alt_screen = True

        self.helpers._loop_signal_handler(signal.SIGINT, None)

        with pytest.raises(SystemExit):
            self.helpers._loop_signal_handler(signal.SIGINT, None)

        assert "\033[?1049l" in capsys.readouterr().err


class TestRunBackground:
    """Tests for run_background() helper."""

    def test_spawns_detached_process(self, tmp_path: Path) -> None:
        """Spawns process with start_new_session=True."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 42
            from little_loops.cli.loop._helpers import run_background

            result = run_background("my-loop", args, loops_dir)

        assert result == 0
        mock_popen.assert_called_once()
        kwargs = mock_popen.call_args[1]
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL

    def test_writes_pid_file(self, tmp_path: Path) -> None:
        """PID file written to .loops/.running/<name>.pid."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 99
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        pid_files = list((loops_dir / ".running").glob("my-loop-*.pid"))
        assert len(pid_files) == 1
        assert pid_files[0].read_text() == "99"

    def test_creates_log_file(self, tmp_path: Path) -> None:
        """Log file created at .loops/.running/<name>.log."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 99
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        log_files = list((loops_dir / ".running").glob("my-loop-*.log"))
        assert len(log_files) == 1

    def test_forwards_max_iterations(self, tmp_path: Path) -> None:
        """Forwards --max-iterations to child process."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=10, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--max-iterations" in cmd
        assert "10" in cmd

    def test_forwards_no_llm(self, tmp_path: Path) -> None:
        """Forwards --no-llm to child process."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=True, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--no-llm" in cmd

    def test_command_includes_foreground_internal(self, tmp_path: Path) -> None:
        """Child command uses --foreground-internal flag."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--foreground-internal" in cmd
        assert "--background" not in cmd

    def test_resume_subcommand_spawns_resume(self, tmp_path: Path) -> None:
        """subcommand='resume' spawns ll-loop resume instead of ll-loop run."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 7
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir, subcommand="resume")

        cmd = mock_popen.call_args[0][0]
        assert "resume" in cmd
        assert "run" not in cmd

    def test_forwards_verbose(self, tmp_path: Path) -> None:
        """Forwards --verbose to child process (BUG-621)."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            verbose=True,
            quiet=False,
            queue=False,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--verbose" in cmd

    def test_verbose_not_forwarded_when_false(self, tmp_path: Path) -> None:
        """Does not forward --verbose when not set."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            verbose=False,
            quiet=False,
            queue=False,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--verbose" not in cmd

    def test_forwards_context_flags(self, tmp_path: Path) -> None:
        """Forwards --context KEY=VALUE flags to child process."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            context=["issue_id=042", "mode=fast"],
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--context" in cmd
        assert "issue_id=042" in cmd
        assert "mode=fast" in cmd

    def test_context_not_forwarded_when_empty(self, tmp_path: Path) -> None:
        """Does not add --context to child command when list is empty."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False, context=[]
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--context" not in cmd

    def test_prints_confirmation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Prints launch confirmation with PID and help commands."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 555
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        captured = capsys.readouterr()
        assert "started in background" in captured.out
        assert "555" in captured.out
        assert "ll-loop status my-loop" in captured.out
        assert "ll-loop stop my-loop" in captured.out

    def test_forwards_handoff_threshold(self, tmp_path: Path) -> None:
        """Forwards --handoff-threshold to child process."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            handoff_threshold=40,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--handoff-threshold" in cmd
        assert "40" in cmd

    def test_handoff_threshold_not_forwarded_when_none(self, tmp_path: Path) -> None:
        """Does not add --handoff-threshold to child command when not set."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            handoff_threshold=None,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--handoff-threshold" not in cmd

    def test_forwards_program_md(self, tmp_path: Path) -> None:
        """Forwards --program-md PATH to child process when set (ENH-1121)."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        program_md_path = tmp_path / ".ll" / "program.md"
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            handoff_threshold=None,
            program_md=program_md_path,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--program-md" in cmd
        assert str(program_md_path) in cmd

    def test_forwards_positional_input(self, tmp_path: Path) -> None:
        """Forwards positional input arg to child process when set."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            input="ENH-571",
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "ENH-571" in cmd
        loop_idx = cmd.index("my-loop")
        input_idx = cmd.index("ENH-571")
        assert input_idx == loop_idx + 1, "input must immediately follow loop_name"

    def test_input_not_forwarded_when_none(self, tmp_path: Path) -> None:
        """Does not add positional input to child command when not set."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            input=None,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        loop_idx = cmd.index("my-loop")
        next_token = cmd[loop_idx + 1]
        assert next_token.startswith("--"), "nothing between loop_name and first flag when input=None"

    def test_program_md_not_forwarded_when_none(self, tmp_path: Path) -> None:
        """Does not add --program-md to child command when not set (ENH-1121)."""
        import argparse

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        args = argparse.Namespace(
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            quiet=False,
            queue=False,
            handoff_threshold=None,
            program_md=None,
        )

        with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 1
            from little_loops.cli.loop._helpers import run_background

            run_background("my-loop", args, loops_dir)

        cmd = mock_popen.call_args[0][0]
        assert "--program-md" not in cmd


class TestCmdStopWithPid:
    """Tests for cmd_stop with PID-based process termination."""

    def test_stop_sends_sigterm_to_background(self, tmp_path: Path) -> None:
        """Sends SIGTERM when PID file exists and process exits gracefully (BUG-592)."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")

        # Alive on initial check, exits after SIGTERM on first poll
        alive_seq = [True, False]

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.fsm.persistence.StatePersistence"),
            patch("little_loops.cli.loop.lifecycle._process_alive", side_effect=alive_seq),
            patch("little_loops.cli.loop.lifecycle.os.kill") as mock_kill,
            patch("little_loops.cli.loop.lifecycle.time.sleep"),
        ):
            from little_loops.cli.loop.lifecycle import cmd_stop

            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        assert mock_state.status == "interrupted"
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_stop_cleans_stale_pid(self, tmp_path: Path) -> None:
        """Cleans up PID file when process is not alive."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("99999")

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.cli.loop.lifecycle._process_alive", return_value=False),
        ):
            from little_loops.cli.loop.lifecycle import cmd_stop

            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        assert not pid_file.exists()

    def test_stop_without_pid_file(self, tmp_path: Path) -> None:
        """Falls back to state-only stop when no PID file."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.fsm.persistence.StatePersistence"),
        ):
            from little_loops.cli.loop.lifecycle import cmd_stop

            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        assert mock_state.status == "interrupted"
        logger.success.assert_called_once()

    def test_stop_dead_process_preserves_state(self, tmp_path: Path) -> None:
        """Does not overwrite state when process already exited (stale PID).

        Regression test for BUG-529: cmd_stop previously wrote 'interrupted'
        before checking liveness, overwriting the process's own final status.
        """
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.status = "running"

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("99999")

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.fsm.persistence.StatePersistence") as mock_cls,
            patch("little_loops.cli.loop.lifecycle._process_alive", return_value=False),
        ):
            mock_persistence = mock_cls.return_value
            from little_loops.cli.loop.lifecycle import cmd_stop

            result = cmd_stop("test-loop", tmp_path, logger)

        assert result == 0
        assert not pid_file.exists()
        mock_persistence.save_state.assert_not_called()


class TestCmdStatusWithPid:
    """Tests for cmd_status with PID liveness display."""

    def test_status_shows_running_pid(self, tmp_path: Path) -> None:
        """Shows PID with (running) when process is alive."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.loop_name = "test-loop"
        mock_state.status = "running"
        mock_state.current_state = "check"
        mock_state.iteration = 5
        mock_state.started_at = "2026-02-27T10:00:00"
        mock_state.updated_at = "2026-02-27T10:05:00"
        mock_state.continuation_prompt = None

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("12345")

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.cli.loop.lifecycle._process_alive", return_value=True),
            patch("builtins.print") as mock_print,
        ):
            from little_loops.cli.loop.lifecycle import cmd_status

            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "12345" in print_text
        assert "running" in print_text

    def test_status_shows_stale_pid(self, tmp_path: Path) -> None:
        """Shows PID with (not running) when process is dead."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.loop_name = "test-loop"
        mock_state.status = "running"
        mock_state.current_state = "check"
        mock_state.iteration = 5
        mock_state.started_at = "2026-02-27T10:00:00"
        mock_state.updated_at = "2026-02-27T10:05:00"
        mock_state.continuation_prompt = None

        running_dir = tmp_path / ".running"
        running_dir.mkdir(parents=True)
        pid_file = running_dir / "test-loop.pid"
        pid_file.write_text("99999")

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("little_loops.cli.loop.lifecycle._process_alive", return_value=False),
            patch("builtins.print") as mock_print,
        ):
            from little_loops.cli.loop.lifecycle import cmd_status

            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "99999" in print_text
        assert "stale" in print_text

    def test_status_without_pid_file(self, tmp_path: Path) -> None:
        """Works normally when no PID file exists (foreground mode)."""
        logger = MagicMock()
        mock_state = MagicMock()
        mock_state.loop_name = "test-loop"
        mock_state.status = "running"
        mock_state.current_state = "check"
        mock_state.iteration = 5
        mock_state.started_at = "2026-02-27T10:00:00"
        mock_state.updated_at = "2026-02-27T10:05:00"
        mock_state.continuation_prompt = None

        with (
            patch("little_loops.cli.loop.lifecycle._find_instances", return_value=[(None, mock_state)]),
            patch("builtins.print") as mock_print,
        ):
            from little_loops.cli.loop.lifecycle import cmd_status

            result = cmd_status("test-loop", tmp_path, logger)

        assert result == 0
        print_calls = [str(c) for c in mock_print.call_args_list]
        print_text = " ".join(print_calls)
        assert "PID" not in print_text


class TestMainModuleEntryPoint:
    """Tests that __main__.py enables `python -m little_loops.cli.loop` invocation (BUG-891)."""

    def test_main_module_is_importable(self) -> None:
        """__main__.py must exist so `python -m little_loops.cli.loop` works."""
        import importlib.util

        spec = importlib.util.find_spec("little_loops.cli.loop.__main__")
        assert spec is not None, (
            "__main__.py is missing from little_loops/cli/loop/; "
            "background mode spawns 'python -m little_loops.cli.loop' which requires it"
        )

    def test_module_entry_point_exits_cleanly(self) -> None:
        """python -m little_loops.cli.loop --help must exit 0, not raise No module named error."""
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "little_loops.cli.loop", "--help"],
            capture_output=True,
            text=True,
        )
        assert "No module named little_loops.cli.loop.__main__" not in result.stderr, (
            f"__main__.py is missing; got stderr: {result.stderr}"
        )
        assert result.returncode == 0, (
            f"Expected exit 0 from --help, got {result.returncode}\nstderr: {result.stderr}"
        )


class TestMakeInstanceId:
    """Tests for _make_instance_id() helper (ENH-1354)."""

    def test_format_matches_pattern(self) -> None:
        """Instance ID must match <loop_name>-YYYYMMDDTHHMMSS format."""
        import re

        from little_loops.cli.loop._helpers import _make_instance_id

        result = _make_instance_id("autodev")
        assert re.match(r"^autodev-\d{8}T\d{6}$", result), f"Unexpected format: {result!r}"

    def test_embeds_loop_name_prefix(self) -> None:
        """Instance ID must begin with the loop name."""
        from little_loops.cli.loop._helpers import _make_instance_id

        result = _make_instance_id("my-loop")
        assert result.startswith("my-loop-")

    def test_successive_calls_are_unique(self) -> None:
        """Two successive calls return distinct values (timestamp resolution is 1 second)."""
        import time

        from little_loops.cli.loop._helpers import _make_instance_id

        id1 = _make_instance_id("test")
        time.sleep(1.05)
        id2 = _make_instance_id("test")
        assert id1 != id2, "Expected distinct instance IDs across second boundary"
