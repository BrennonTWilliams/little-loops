"""Tests for --queue retry behavior in cmd_run (BUG-1281)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.fsm.concurrency import ScopeLock


def _make_args(**kwargs: object) -> argparse.Namespace:
    defaults = {
        "input": None,
        "context": [],
        "max_iterations": None,
        "delay": None,
        "no_llm": False,
        "llm_model": None,
        "dry_run": False,
        "background": False,
        "foreground_internal": False,
        "quiet": False,
        "verbose": False,
        "show_diagrams": False,
        "clear": False,
        "queue": True,
        "handoff_threshold": None,
        "program_md": None,
        "worktree": False,
        "context_limit": None,
        "builtin": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_loop(tmp_path: Path) -> Path:
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "test-loop.yaml").write_text(
        "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
    )
    return loops_dir


def _conflict() -> ScopeLock:
    return ScopeLock(
        loop_name="other-loop", scope=["."], pid=99999, started_at="2026-01-01T00:00:00Z"
    )


class TestQueueRetryOnRace:
    """cmd_run retries acquire when it loses the post-wait race (BUG-1281)."""

    def test_retries_acquire_after_losing_race(self, tmp_path: Path) -> None:
        """cmd_run with --queue retries acquire if it loses the post-wait race."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args()

        with (
            patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls,
            patch("little_loops.fsm.persistence.PersistentExecutor"),
            patch("little_loops.cli.loop.run.register_loop_signal_handlers"),
            patch("little_loops.cli.loop.run.run_foreground", return_value=0),
            patch("little_loops.extension.wire_extensions"),
        ):
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            # 1st: initial check fails (conflict exists)
            # 2nd: retry loop, loses the race
            # 3rd: retry loop, wins the race
            mock_lm.acquire.side_effect = [False, False, True]
            mock_lm.find_conflict.return_value = _conflict()
            mock_lm.wait_for_scope.return_value = True

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 0
        assert mock_lm.acquire.call_count == 3
        assert mock_lm.wait_for_scope.call_count == 2

    def test_exits_when_scope_never_becomes_available(self, tmp_path: Path) -> None:
        """cmd_run exits with code 1 when wait_for_scope times out."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args()

        with patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls:
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = False
            mock_lm.find_conflict.return_value = _conflict()
            mock_lm.wait_for_scope.return_value = False  # timeout — never free

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 1

    def test_without_queue_flag_exits_immediately_on_conflict(self, tmp_path: Path) -> None:
        """Without --queue, a scope conflict exits with code 1 and makes no retry."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = _make_loop(tmp_path)
        logger = Logger(use_color=False)
        args = _make_args(queue=False)

        with patch("little_loops.fsm.concurrency.LockManager") as mock_lm_cls:
            mock_lm = MagicMock()
            mock_lm_cls.return_value = mock_lm
            mock_lm.acquire.return_value = False
            mock_lm.find_conflict.return_value = _conflict()

            result = cmd_run("test-loop", args, loops_dir, logger)

        assert result == 1
        assert mock_lm.acquire.call_count == 1
        mock_lm.wait_for_scope.assert_not_called()
