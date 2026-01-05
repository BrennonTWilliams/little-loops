"""Tests for CLI argument parsing.

Tests the argument parsing logic for ll-auto and ll-parallel commands
without executing the actual managers.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


class TestAutoArgumentParsing:
    """Tests for ll-auto (main_auto) argument parsing."""

    def _parse_auto_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_auto."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--resume", "-r", action="store_true")
        parser.add_argument("--dry-run", "-n", action="store_true")
        parser.add_argument("--max-issues", "-m", type=int, default=0)
        parser.add_argument("--category", "-c", type=str, default=None)
        parser.add_argument("--config", type=Path, default=None)
        return parser.parse_args(args)

    def test_default_args(self) -> None:
        """Default values when no arguments provided."""
        args = self._parse_auto_args([])
        assert args.resume is False
        assert args.dry_run is False
        assert args.max_issues == 0
        assert args.category is None
        assert args.config is None

    def test_resume_flag_long(self) -> None:
        """--resume flag sets resume=True."""
        args = self._parse_auto_args(["--resume"])
        assert args.resume is True

    def test_resume_flag_short(self) -> None:
        """-r flag sets resume=True."""
        args = self._parse_auto_args(["-r"])
        assert args.resume is True

    def test_dry_run_flag_long(self) -> None:
        """--dry-run flag sets dry_run=True."""
        args = self._parse_auto_args(["--dry-run"])
        assert args.dry_run is True

    def test_dry_run_flag_short(self) -> None:
        """-n flag sets dry_run=True."""
        args = self._parse_auto_args(["-n"])
        assert args.dry_run is True

    def test_max_issues_long(self) -> None:
        """--max-issues sets the issue limit."""
        args = self._parse_auto_args(["--max-issues", "5"])
        assert args.max_issues == 5

    def test_max_issues_short(self) -> None:
        """-m sets the issue limit."""
        args = self._parse_auto_args(["-m", "10"])
        assert args.max_issues == 10

    def test_category_filter_long(self) -> None:
        """--category sets the category filter."""
        args = self._parse_auto_args(["--category", "bugs"])
        assert args.category == "bugs"

    def test_category_filter_short(self) -> None:
        """-c sets the category filter."""
        args = self._parse_auto_args(["-c", "features"])
        assert args.category == "features"

    def test_config_path(self) -> None:
        """--config sets the project root path."""
        args = self._parse_auto_args(["--config", "/path/to/project"])
        assert args.config == Path("/path/to/project")

    def test_combined_args(self) -> None:
        """Multiple arguments work together correctly."""
        args = self._parse_auto_args(
            [
                "--resume",
                "--dry-run",
                "--max-issues",
                "3",
                "--category",
                "bugs",
                "--config",
                "/my/project",
            ]
        )
        assert args.resume is True
        assert args.dry_run is True
        assert args.max_issues == 3
        assert args.category == "bugs"
        assert args.config == Path("/my/project")

    def test_combined_short_args(self) -> None:
        """Short form arguments work together correctly."""
        args = self._parse_auto_args(["-r", "-n", "-m", "7", "-c", "enhancements"])
        assert args.resume is True
        assert args.dry_run is True
        assert args.max_issues == 7
        assert args.category == "enhancements"


class TestParallelArgumentParsing:
    """Tests for ll-parallel (main_parallel) argument parsing."""

    def _parse_parallel_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_parallel."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--workers", "-w", type=int, default=None)
        parser.add_argument("--priority", "-p", type=str, default=None)
        parser.add_argument("--max-issues", "-m", type=int, default=0)
        parser.add_argument("--worktree-base", type=Path, default=None)
        parser.add_argument("--dry-run", "-n", action="store_true")
        parser.add_argument("--resume", "-r", action="store_true")
        parser.add_argument("--timeout", "-t", type=int, default=None)
        parser.add_argument("--quiet", "-q", action="store_true")
        parser.add_argument("--cleanup", "-c", action="store_true")
        parser.add_argument("--stream-output", action="store_true")
        parser.add_argument("--show-model", action="store_true")
        parser.add_argument("--config", type=Path, default=None)
        return parser.parse_args(args)

    def test_default_args(self) -> None:
        """Default values when no arguments provided."""
        args = self._parse_parallel_args([])
        assert args.workers is None
        assert args.priority is None
        assert args.max_issues == 0
        assert args.worktree_base is None
        assert args.dry_run is False
        assert args.resume is False
        assert args.timeout is None
        assert args.quiet is False
        assert args.cleanup is False
        assert args.stream_output is False
        assert args.show_model is False
        assert args.config is None

    def test_workers_long(self) -> None:
        """--workers sets the number of parallel workers."""
        args = self._parse_parallel_args(["--workers", "3"])
        assert args.workers == 3

    def test_workers_short(self) -> None:
        """-w sets the number of parallel workers."""
        args = self._parse_parallel_args(["-w", "4"])
        assert args.workers == 4

    def test_priority_filter_long(self) -> None:
        """--priority sets the priority filter string."""
        args = self._parse_parallel_args(["--priority", "P1,P2"])
        assert args.priority == "P1,P2"

    def test_priority_filter_short(self) -> None:
        """-p sets the priority filter string."""
        args = self._parse_parallel_args(["-p", "P0,P1,P2"])
        assert args.priority == "P0,P1,P2"

    def test_max_issues_long(self) -> None:
        """--max-issues sets the issue limit."""
        args = self._parse_parallel_args(["--max-issues", "10"])
        assert args.max_issues == 10

    def test_max_issues_short(self) -> None:
        """-m sets the issue limit."""
        args = self._parse_parallel_args(["-m", "5"])
        assert args.max_issues == 5

    def test_worktree_base(self) -> None:
        """--worktree-base sets the worktree directory."""
        args = self._parse_parallel_args(["--worktree-base", "/tmp/worktrees"])
        assert args.worktree_base == Path("/tmp/worktrees")

    def test_dry_run_flag_long(self) -> None:
        """--dry-run enables dry run mode."""
        args = self._parse_parallel_args(["--dry-run"])
        assert args.dry_run is True

    def test_dry_run_flag_short(self) -> None:
        """-n enables dry run mode."""
        args = self._parse_parallel_args(["-n"])
        assert args.dry_run is True

    def test_resume_flag_long(self) -> None:
        """--resume enables resume mode."""
        args = self._parse_parallel_args(["--resume"])
        assert args.resume is True

    def test_resume_flag_short(self) -> None:
        """-r enables resume mode."""
        args = self._parse_parallel_args(["-r"])
        assert args.resume is True

    def test_timeout_long(self) -> None:
        """--timeout sets the per-issue timeout."""
        args = self._parse_parallel_args(["--timeout", "1800"])
        assert args.timeout == 1800

    def test_timeout_short(self) -> None:
        """-t sets the per-issue timeout."""
        args = self._parse_parallel_args(["-t", "3600"])
        assert args.timeout == 3600

    def test_quiet_flag_long(self) -> None:
        """--quiet suppresses output."""
        args = self._parse_parallel_args(["--quiet"])
        assert args.quiet is True

    def test_quiet_flag_short(self) -> None:
        """-q suppresses output."""
        args = self._parse_parallel_args(["-q"])
        assert args.quiet is True

    def test_cleanup_flag_long(self) -> None:
        """--cleanup enables cleanup mode."""
        args = self._parse_parallel_args(["--cleanup"])
        assert args.cleanup is True

    def test_cleanup_flag_short(self) -> None:
        """-c enables cleanup mode."""
        args = self._parse_parallel_args(["-c"])
        assert args.cleanup is True

    def test_stream_output_flag(self) -> None:
        """--stream-output enables output streaming."""
        args = self._parse_parallel_args(["--stream-output"])
        assert args.stream_output is True

    def test_show_model_flag(self) -> None:
        """--show-model enables model display."""
        args = self._parse_parallel_args(["--show-model"])
        assert args.show_model is True

    def test_config_path(self) -> None:
        """--config sets the project root path."""
        args = self._parse_parallel_args(["--config", "/path/to/project"])
        assert args.config == Path("/path/to/project")

    def test_combined_args(self) -> None:
        """Multiple arguments work together correctly."""
        args = self._parse_parallel_args(
            [
                "--workers",
                "4",
                "--priority",
                "P1,P2,P3",
                "--max-issues",
                "20",
                "--dry-run",
                "--resume",
                "--timeout",
                "2400",
                "--quiet",
                "--stream-output",
                "--show-model",
                "--config",
                "/my/project",
            ]
        )
        assert args.workers == 4
        assert args.priority == "P1,P2,P3"
        assert args.max_issues == 20
        assert args.dry_run is True
        assert args.resume is True
        assert args.timeout == 2400
        assert args.quiet is True
        assert args.stream_output is True
        assert args.show_model is True
        assert args.config == Path("/my/project")


class TestPriorityFilterParsing:
    """Tests for priority filter string parsing logic."""

    def test_parse_single_priority(self) -> None:
        """Single priority is parsed correctly."""
        priority_str = "P1"
        result = [p.strip().upper() for p in priority_str.split(",")]
        assert result == ["P1"]

    def test_parse_multiple_priorities(self) -> None:
        """Multiple priorities are parsed correctly."""
        priority_str = "P1,P2"
        result = [p.strip().upper() for p in priority_str.split(",")]
        assert result == ["P1", "P2"]

    def test_parse_priorities_with_spaces(self) -> None:
        """Priorities with surrounding spaces are trimmed."""
        priority_str = "P1, P2, P3"
        result = [p.strip().upper() for p in priority_str.split(",")]
        assert result == ["P1", "P2", "P3"]

    def test_parse_lowercase_priorities(self) -> None:
        """Lowercase priorities are converted to uppercase."""
        priority_str = "p1,p2"
        result = [p.strip().upper() for p in priority_str.split(",")]
        assert result == ["P1", "P2"]


class TestMainAutoIntegration:
    """Integration tests for main_auto entry point."""

    @pytest.fixture
    def temp_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with config."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            claude_dir = project / ".claude"
            claude_dir.mkdir()
            config = {
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "completed_dir": "completed",
                    "priorities": ["P0", "P1", "P2"],
                },
                "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config))
            issues_dir = project / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)
            yield project

    def test_main_auto_creates_manager_with_correct_args(self, temp_project: Path) -> None:
        """main_auto creates AutoManager with parsed arguments."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys,
                "argv",
                [
                    "ll-auto",
                    "--dry-run",
                    "--max-issues",
                    "5",
                    "--resume",
                    "--category",
                    "bugs",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 0
            mock_manager_cls.assert_called_once()
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["dry_run"] is True
            assert call_kwargs["max_issues"] == 5
            assert call_kwargs["resume"] is True
            assert call_kwargs["category"] == "bugs"


class TestMainParallelIntegration:
    """Integration tests for main_parallel entry point."""

    @pytest.fixture
    def temp_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with config."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            claude_dir = project / ".claude"
            claude_dir.mkdir()
            config = {
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "completed_dir": "completed",
                    "priorities": ["P0", "P1", "P2"],
                },
                "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
                "parallel": {
                    "max_workers": 2,
                    "state_file": ".parallel-state.json",
                    "timeout_seconds": 1800,
                },
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config))
            issues_dir = project / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)
            yield project

    def test_main_parallel_cleanup_mode(self, temp_project: Path) -> None:
        """main_parallel --cleanup calls cleanup and exits."""
        with patch("little_loops.parallel.WorkerPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value = mock_pool

            with patch.object(
                sys,
                "argv",
                [
                    "ll-parallel",
                    "--cleanup",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0
            mock_pool.cleanup_all_worktrees.assert_called_once()

    def test_main_parallel_creates_orchestrator_with_correct_args(self, temp_project: Path) -> None:
        """main_parallel creates ParallelOrchestrator with parsed arguments."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                [
                    "ll-parallel",
                    "--workers",
                    "3",
                    "--dry-run",
                    "--priority",
                    "P1,P2",
                    "--max-issues",
                    "10",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0
            mock_orch_cls.assert_called_once()
            call_kwargs = mock_orch_cls.call_args.kwargs
            assert call_kwargs["verbose"] is True  # default (not --quiet)
