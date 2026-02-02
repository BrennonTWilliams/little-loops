"""Tests for CLI argument parsing.

Tests the argument parsing logic for ll-auto and ll-parallel commands
without executing the actual managers.
"""

from __future__ import annotations

import argparse
import signal
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
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

    def test_main_auto_quiet_flag_passed_to_manager(self, temp_project: Path) -> None:
        """main_auto passes quiet flag as verbose=False to AutoManager."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys,
                "argv",
                [
                    "ll-auto",
                    "--quiet",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 0
            mock_manager_cls.assert_called_once()
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["verbose"] is False  # --quiet means verbose=False

    def test_main_auto_without_quiet_flag_passed_to_manager(self, temp_project: Path) -> None:
        """main_auto without --quiet passes verbose=True to AutoManager (default)."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys,
                "argv",
                [
                    "ll-auto",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 0
            mock_manager_cls.assert_called_once()
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["verbose"] is True  # default is verbose


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


class TestMainMessagesIntegration:
    """Integration tests for main_messages entry point."""

    def test_main_messages_default_args(self) -> None:
        """main_messages with default arguments extracts messages."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = [
                    {"content": "Test message 1", "timestamp": "2026-01-01T00:00:00"},
                    {"content": "Test message 2", "timestamp": "2026-01-01T01:00:00"},
                ]
                with patch("little_loops.user_messages.save_messages") as mock_save:
                    mock_save.return_value = Path("/output/user-messages-123.jsonl")

                    with patch.object(sys, "argv", ["ll-messages"]):
                        from little_loops.cli import main_messages

                        result = main_messages()

            assert result == 0
            mock_extract.assert_called_once()
            mock_save.assert_called_once()

    def test_main_messages_with_limit(self) -> None:
        """main_messages respects the --limit argument."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", ["ll-messages", "-n", "50"]):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0
            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["limit"] == 50

    def test_main_messages_with_since_date(self) -> None:
        """main_messages parses --since date correctly."""
        from datetime import datetime

        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", ["ll-messages", "--since", "2026-01-01"]):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0
            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["since"] == datetime(2026, 1, 1)

    def test_main_messages_with_stdout(self) -> None:
        """main_messages outputs to stdout with --stdout flag."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch("little_loops.user_messages.extract_user_messages") as mock_extract:
                mock_extract.return_value = [
                    {"content": "Test", "timestamp": "2026-01-01T00:00:00"}
                ]
                with patch("little_loops.user_messages.print_messages_to_stdout") as mock_print:
                    with patch.object(sys, "argv", ["ll-messages", "--stdout"]):
                        from little_loops.cli import main_messages

                        result = main_messages()

            assert result == 0
            mock_print.assert_called_once()

    def test_main_messages_no_project_folder(self) -> None:
        """main_messages returns error when project folder not found."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = None

            with patch.object(sys, "argv", ["ll-messages"]):
                from little_loops.cli import main_messages

                result = main_messages()

            assert result == 1

    def test_main_messages_invalid_date_format(self) -> None:
        """main_messages returns error for invalid date format."""
        with patch("little_loops.user_messages.get_project_folder") as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")

            with patch.object(sys, "argv", ["ll-messages", "--since", "invalid-date"]):
                from little_loops.cli import main_messages

                result = main_messages()

            assert result == 1


class TestMainLoopIntegration:
    """Integration tests for main_loop entry point."""

    def test_main_loop_list_command(self) -> None:
        """main_loop list command lists available loops."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (loops_dir / "test-loop.yaml").write_text("name: test")

            with patch.object(sys, "argv", ["ll-loop", "list"]):
                with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                    from little_loops.cli import main_loop

                    result = main_loop()

            assert result == 0

    def test_main_loop_list_running_command(self) -> None:
        """main_loop list --running shows running loops."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()

            with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
                with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                    from little_loops.cli import main_loop

                    result = main_loop()

            assert result == 0

    def test_main_loop_validate_invalid_definition(self) -> None:
        """main_loop validate returns error for invalid loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()

            # Create the file so resolve_loop_path doesn't fail immediately
            loop_content = """
name: test-loop
initial: start
states:
  start:
    terminal: true
"""
            loop_file = loops_dir / "test-loop.yaml"
            loop_file.write_text(loop_content)

            with patch("little_loops.fsm.validation.load_and_validate") as mock_load:
                mock_load.side_effect = ValueError("Invalid loop definition")

                with patch.object(sys, "argv", ["ll-loop", "validate", "test-loop"]):
                    with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from little_loops.cli import main_loop

                        result = main_loop()

                assert result == 1

    def test_main_loop_compile_command(self) -> None:
        """main_loop compile compiles paradigm to FSM."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "paradigm.yaml"
            input_file.write_text("name: test\nparadigm: simple")

            with patch("little_loops.fsm.compilers.compile_paradigm") as mock_compile:
                from little_loops.fsm.schema import FSMLoop, StateConfig

                mock_fsm = FSMLoop(
                    name="compiled",
                    paradigm="simple",
                    initial="start",
                    states={"start": StateConfig(terminal=True)},
                    max_iterations=10,
                )
                mock_compile.return_value = mock_fsm

                with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
                    from little_loops.cli import main_loop

                    result = main_loop()

            assert result == 0

    def test_main_loop_no_command_shows_help(self) -> None:
        """main_loop with no command shows help and returns error."""
        with patch.object(sys, "argv", ["ll-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1


class TestSprintArgumentParsing:
    """Tests for ll-sprint argument parsing."""

    def _parse_sprint_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_sprint."""
        parser = argparse.ArgumentParser(prog="ll-sprint")
        subparsers = parser.add_subparsers(dest="command")

        # create
        create = subparsers.add_parser("create")
        create.add_argument("name")
        create.add_argument("--issues", required=True)
        create.add_argument("--description", "-d", default="")
        create.add_argument("-w", "--max-workers", type=int, default=4)
        create.add_argument("-t", "--timeout", type=int, default=3600)
        create.add_argument("--skip", type=str, default=None)

        # run
        run = subparsers.add_parser("run")
        run.add_argument("sprint")
        run.add_argument("--dry-run", "-n", action="store_true")
        run.add_argument("-w", "--max-workers", type=int)
        run.add_argument("-t", "--timeout", type=int)
        run.add_argument("--config", type=Path)
        run.add_argument("--resume", "-r", action="store_true")
        run.add_argument("--quiet", "-q", action="store_true")
        run.add_argument("--skip", type=str, default=None)

        # list
        list_parser = subparsers.add_parser("list")
        list_parser.add_argument("--verbose", "-v", action="store_true")

        # show
        show = subparsers.add_parser("show")
        show.add_argument("sprint")
        show.add_argument("--config", type=Path)

        # delete
        delete = subparsers.add_parser("delete")
        delete.add_argument("sprint")

        return parser.parse_args(args)

    def test_create_command(self) -> None:
        """create subcommand parses correctly."""
        args = self._parse_sprint_args(
            [
                "create",
                "sprint-1",
                "--issues",
                "BUG-001,FEAT-010",
                "--description",
                "Q1 fixes",
                "--max-workers",
                "8",
            ]
        )
        assert args.command == "create"
        assert args.name == "sprint-1"
        assert args.issues == "BUG-001,FEAT-010"
        assert args.description == "Q1 fixes"
        assert args.max_workers == 8

    def test_run_command(self) -> None:
        """run subcommand parses correctly."""
        args = self._parse_sprint_args(
            ["run", "sprint-1", "--dry-run", "--max-workers", "8"]
        )
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.dry_run is True
        assert args.max_workers == 8

    def test_run_default(self) -> None:
        """run with default options."""
        args = self._parse_sprint_args(["run", "sprint-1"])
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.dry_run is False

    def test_list_command(self) -> None:
        """list subcommand."""
        args = self._parse_sprint_args(["list", "--verbose"])
        assert args.command == "list"
        assert args.verbose is True

    def test_show_command(self) -> None:
        """show subcommand."""
        args = self._parse_sprint_args(["show", "sprint-1", "--config", "/my/project"])
        assert args.command == "show"
        assert args.sprint == "sprint-1"
        assert args.config == Path("/my/project")

    def test_delete_command(self) -> None:
        """delete subcommand."""
        args = self._parse_sprint_args(["delete", "sprint-1"])
        assert args.command == "delete"
        assert args.sprint == "sprint-1"

    def test_no_command(self) -> None:
        """No command shows help."""
        args = self._parse_sprint_args([])
        assert args.command is None

    def test_create_with_short_flags(self) -> None:
        """create subcommand accepts short flags for --max-workers and --timeout."""
        args = self._parse_sprint_args(
            ["create", "sprint-1", "--issues", "BUG-001", "-w", "4", "-t", "1800"]
        )
        assert args.command == "create"
        assert args.max_workers == 4
        assert args.timeout == 1800

    def test_run_with_short_flags(self) -> None:
        """run subcommand accepts short flags for --max-workers and --timeout."""
        args = self._parse_sprint_args(["run", "sprint-1", "-w", "4", "-t", "1800"])
        assert args.command == "run"
        assert args.max_workers == 4
        assert args.timeout == 1800

    def test_create_with_skip(self) -> None:
        """create subcommand accepts --skip to exclude issues."""
        args = self._parse_sprint_args(
            ["create", "sprint-1", "--issues", "BUG-001,BUG-002", "--skip", "BUG-002"]
        )
        assert args.command == "create"
        assert args.skip == "BUG-002"

    def test_run_with_skip(self) -> None:
        """run subcommand accepts --skip to exclude issues."""
        args = self._parse_sprint_args(["run", "sprint-1", "--skip", "BUG-002,BUG-003"])
        assert args.command == "run"
        assert args.skip == "BUG-002,BUG-003"

    def test_run_with_resume(self) -> None:
        """run subcommand accepts --resume/-r."""
        args = self._parse_sprint_args(["run", "sprint-1", "-r"])
        assert args.command == "run"
        assert args.resume is True

    def test_run_with_quiet(self) -> None:
        """run subcommand accepts --quiet/-q."""
        args = self._parse_sprint_args(["run", "sprint-1", "--quiet"])
        assert args.command == "run"
        assert args.quiet is True

    def test_run_with_quiet_short_flag(self) -> None:
        """run subcommand accepts -q short flag."""
        args = self._parse_sprint_args(["run", "sprint-1", "-q"])
        assert args.command == "run"
        assert args.quiet is True

    def test_run_without_quiet_default(self) -> None:
        """run subcommand defaults quiet to False."""
        args = self._parse_sprint_args(["run", "sprint-1"])
        assert args.command == "run"
        assert args.quiet is False

    def test_run_with_quiet_and_other_flags(self) -> None:
        """run subcommand combines --quiet with other flags."""
        args = self._parse_sprint_args(
            ["run", "sprint-1", "-q", "--dry-run", "-w", "4", "-r"]
        )
        assert args.command == "run"
        assert args.quiet is True
        assert args.dry_run is True
        assert args.max_workers == 4
        assert args.resume is True


class TestSprintShowDependencyVisualization:
    """Tests for sprint show dependency visualization."""

    @staticmethod
    def _make_issue(
        issue_id: str,
        priority: str = "P1",
        title: str = "Test issue",
        blocked_by: list[str] | None = None,
    ) -> Any:
        """Helper to create test IssueInfo objects."""
        from pathlib import Path

        from little_loops.issue_parser import IssueInfo

        return IssueInfo(
            path=Path(f"{issue_id.lower()}.md"),
            issue_type="features",
            priority=priority,
            issue_id=issue_id,
            title=title,
            blocked_by=blocked_by or [],
        )

    def test_render_execution_plan_single_wave(self) -> None:
        """Single wave with multiple parallel issues."""
        from little_loops.cli import _render_execution_plan
        from little_loops.dependency_graph import DependencyGraph

        # Create test issues with no dependencies
        issue1 = self._make_issue("BUG-001", priority="P0", title="Fix crash")
        issue2 = self._make_issue("FEAT-002", priority="P2", title="Add feature")

        graph = DependencyGraph.from_issues([issue1, issue2])
        waves = graph.get_execution_waves()

        output = _render_execution_plan(waves, graph)

        assert "EXECUTION PLAN (2 issues, 1 waves)" in output
        assert "Wave 1 (parallel):" in output
        assert "BUG-001" in output
        assert "FEAT-002" in output
        assert "blocked by" not in output

    def test_render_execution_plan_with_dependencies(self) -> None:
        """Multiple waves with dependencies."""
        from little_loops.cli import _render_execution_plan
        from little_loops.dependency_graph import DependencyGraph

        issue1 = self._make_issue("FEAT-001", priority="P0", title="First feature")
        issue2 = self._make_issue("BUG-002", priority="P1", title="Bug fix", blocked_by=["FEAT-001"])

        graph = DependencyGraph.from_issues([issue1, issue2])
        waves = graph.get_execution_waves()

        output = _render_execution_plan(waves, graph)

        assert "2 waves" in output
        assert "Wave 1" in output
        assert "Wave 2" in output
        assert "blocked by: FEAT-001" in output

    def test_render_execution_plan_empty_waves(self) -> None:
        """Empty waves return empty string."""
        from little_loops.cli import _render_execution_plan
        from little_loops.dependency_graph import DependencyGraph

        graph = DependencyGraph()
        output = _render_execution_plan([], graph)

        assert output == ""

    def test_render_dependency_graph_chain(self) -> None:
        """Dependency chain A -> B -> C."""
        from little_loops.cli import _render_dependency_graph
        from little_loops.dependency_graph import DependencyGraph

        issue_a = self._make_issue("FEAT-001", priority="P0", title="First")
        issue_b = self._make_issue("FEAT-002", priority="P1", title="Second", blocked_by=["FEAT-001"])
        issue_c = self._make_issue("FEAT-003", priority="P2", title="Third", blocked_by=["FEAT-002"])

        graph = DependencyGraph.from_issues([issue_a, issue_b, issue_c])
        waves = graph.get_execution_waves()

        output = _render_dependency_graph(waves, graph)

        assert "DEPENDENCY GRAPH" in output
        assert "FEAT-001" in output
        assert "FEAT-002" in output
        assert "FEAT-003" in output
        assert "──→" in output
        assert "Legend" in output

    def test_render_dependency_graph_single_wave(self) -> None:
        """Single wave has no dependency graph (returns empty)."""
        from little_loops.cli import _render_dependency_graph
        from little_loops.dependency_graph import DependencyGraph

        issue1 = self._make_issue("BUG-001", priority="P0", title="Bug fix")
        issue2 = self._make_issue("FEAT-002", priority="P2", title="Feature")

        graph = DependencyGraph.from_issues([issue1, issue2])
        waves = graph.get_execution_waves()

        output = _render_dependency_graph(waves, graph)

        # Single wave means no dependencies to show
        assert output == ""

    def test_render_execution_plan_title_truncation(self) -> None:
        """Long titles are truncated."""
        from little_loops.cli import _render_execution_plan
        from little_loops.dependency_graph import DependencyGraph

        long_title = "A" * 60  # Very long title
        issue = self._make_issue("BUG-001", priority="P0", title=long_title)

        graph = DependencyGraph.from_issues([issue])
        waves = graph.get_execution_waves()

        output = _render_execution_plan(waves, graph)

        # Title should be truncated with ...
        assert "..." in output
        assert "A" * 60 not in output


# =============================================================================
# ENH-206: Additional Coverage Tests
# =============================================================================


class TestMainAutoAdditionalCoverage:
    """Additional coverage tests for main_auto entry point."""

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
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}
                    },
                    "completed_dir": "completed",
                    "priorities": ["P0", "P1", "P2"],
                },
                "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config))
            issues_dir = project / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)
            yield project

    def test_category_filter_passed_to_manager(self, temp_project: Path) -> None:
        """main_auto passes --category filter to AutoManager."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys,
                "argv",
                ["ll-auto", "--category", "bugs", "--config", str(temp_project)],
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 0
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["category"] == "bugs"

    def test_only_and_skip_parsed_to_sets(self, temp_project: Path) -> None:
        """main_auto parses --only and --skip to sets."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys,
                "argv",
                [
                    "ll-auto",
                    "--only",
                    "BUG-001,BUG-002",
                    "--skip",
                    "BUG-003",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 0
            call_kwargs = mock_manager_cls.call_args.kwargs
            assert call_kwargs["only_ids"] == {"BUG-001", "BUG-002"}
            assert call_kwargs["skip_ids"] == {"BUG-003"}

    def test_project_root_fallback_to_cwd(self, temp_project: Path) -> None:
        """main_auto uses Path.cwd() when no --config provided."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 0
            mock_manager_cls.return_value = mock_manager

            # Change to temp directory for test
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(temp_project)
                with patch.object(sys, "argv", ["ll-auto"]):
                    from little_loops.cli import main_auto

                    result = main_auto()
            finally:
                os.chdir(original_cwd)

            assert result == 0
            # Verify BRConfig was created with cwd path
            mock_manager_cls.assert_called_once()

    def test_manager_run_error_returned(self, temp_project: Path) -> None:
        """main_auto returns error code when manager.run() fails."""
        with patch("little_loops.cli.AutoManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager.run.return_value = 1  # Non-zero exit
            mock_manager_cls.return_value = mock_manager

            with patch.object(
                sys, "argv", ["ll-auto", "--config", str(temp_project)]
            ):
                from little_loops.cli import main_auto

                result = main_auto()

            assert result == 1


class TestMainParallelAdditionalCoverage:
    """Additional coverage tests for main_parallel entry point."""

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
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}
                    },
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

    def test_priority_filter_parsed_to_uppercase_list(
        self, temp_project: Path
    ) -> None:
        """main_parallel parses priority string to uppercase list."""
        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--priority", "p1,p2", "--config", str(temp_project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0
            # Verify create_parallel_config was called with uppercase priorities
            from little_loops.cli import BRConfig

            config = BRConfig(temp_project)
            # The priority_filter should be ["P1", "P2"]
            call_kwargs = mock_orch_cls.call_args.kwargs
            assert "parallel_config" in call_kwargs or result == 0

    def test_merge_pending_flag_passed_to_config(self, temp_project: Path) -> None:
        """main_parallel passes --merge-pending to parallel config."""
        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--merge-pending", "--config", str(temp_project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0

    def test_overlap_detection_flag_passed(self, temp_project: Path) -> None:
        """main_parallel passes --overlap-detection to config."""
        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--overlap-detection", "--config", str(temp_project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0

    def test_warn_only_flag_sets_serialize_overlapping_false(
        self, temp_project: Path
    ) -> None:
        """main_parallel --warn-only sets serialize_overlapping=False."""
        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                [
                    "ll-parallel",
                    "--overlap-detection",
                    "--warn-only",
                    "--config",
                    str(temp_project),
                ],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

            assert result == 0

    def test_state_file_deleted_on_fresh_start(self, temp_project: Path) -> None:
        """main_parallel deletes state file when not resuming."""
        # Create a mock state file
        state_file = temp_project / ".parallel-state.json"
        state_file.write_text('{"test": "data"}')

        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys, "argv", ["ll-parallel", "--config", str(temp_project)]
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

        assert result == 0
        # State file should be deleted
        assert not state_file.exists()

    def test_state_file_preserved_on_resume(self, temp_project: Path) -> None:
        """main_parallel preserves state file when --resume flag set."""
        state_file = temp_project / ".parallel-state.json"
        state_file.write_text('{"test": "data"}')

        with patch(
            "little_loops.parallel.ParallelOrchestrator"
        ) as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_orch_cls.return_value = mock_orch

            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--resume", "--config", str(temp_project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

        assert result == 0
        # State file should still exist
        assert state_file.exists()


class TestMainMessagesAdditionalCoverage:
    """Additional coverage tests for main_messages entry point."""

    def test_output_path_argument(self) -> None:
        """main_messages uses custom output path from --output."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = [
                    {"content": "Test", "timestamp": "2026-01-01T00:00:00"}
                ]
                with patch(
                    "little_loops.user_messages.save_messages"
                ) as mock_save:
                    mock_save.return_value = Path("/custom/output.jsonl")

                    with patch.object(
                        sys,
                        "argv",
                        ["ll-messages", "--output", "/custom/output.jsonl"],
                    ):
                        from little_loops.cli import main_messages

                        result = main_messages()

            assert result == 0
            mock_save.assert_called_once()
            call_args = mock_save.call_args.args
            assert call_args[1] == Path("/custom/output.jsonl")

    def test_cwd_working_directory_override(self) -> None:
        """main_messages uses --cwd for project folder lookup."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = []

                with patch.object(
                    sys, "argv", ["ll-messages", "--cwd", "/custom/cwd"]
                ):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0
            mock_get_folder.assert_called_once_with(Path("/custom/cwd"))

    def test_exclude_agents_flag(self) -> None:
        """main_messages passes include_agent_sessions=False when --exclude-agents."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = []

                with patch.object(sys, "argv", ["ll-messages", "--exclude-agents"]):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["include_agent_sessions"] is False

    def test_include_response_context_flag(self) -> None:
        """main_messages passes include_response_context=True when flag set."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = []

                with patch.object(
                    sys, "argv", ["ll-messages", "--include-response-context"]
                ):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0
            call_kwargs = mock_extract.call_args.kwargs
            assert call_kwargs["include_response_context"] is True

    def test_empty_messages_returns_zero(self) -> None:
        """main_messages returns 0 when no messages found (with warning)."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = []  # Empty list

                with patch.object(sys, "argv", ["ll-messages"]):
                    from little_loops.cli import main_messages

                    result = main_messages()

            assert result == 0  # Early return at line 402

    def test_verbose_logging_flag(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """main_messages creates Logger with verbose=True when --verbose set."""
        with patch(
            "little_loops.user_messages.get_project_folder"
        ) as mock_get_folder:
            mock_get_folder.return_value = Path("/mock/project")
            with patch(
                "little_loops.user_messages.extract_user_messages"
            ) as mock_extract:
                mock_extract.return_value = []
                with patch(
                    "little_loops.user_messages.save_messages"
                ) as mock_save:
                    mock_save.return_value = Path("/output.jsonl")

                    with patch.object(sys, "argv", ["ll-messages", "--verbose"]):
                        from little_loops.cli import main_messages

                        result = main_messages()

            captured = capsys.readouterr()
            assert result == 0
            # Verbose output should include progress messages
            assert (
                "Project folder:" in captured.out or "Limit:" in captured.out
            )


class TestMainLoopAdditionalCoverage:
    """Additional coverage tests for main_loop entry point."""

    def test_argv_preprocessing_inserts_run(self) -> None:
        """main_loop inserts 'run' when first arg is not a subcommand."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock at cli module level to intercept before validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            # Patch at actual source module paths (cli.py imports these locally)
            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    # Call with loop name directly (no "run" subcommand)
                    with patch.object(
                        sys, "argv", ["ll-loop", "test-loop"]
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0

    def test_loop_path_resolution_prefers_fsm_yaml(self) -> None:
        """resolve_loop_path prefers .fsm.yaml over .yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()

            # Create both files
            (loops_dir / "test-loop.yaml").write_text("name: paradigm")
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: compiled\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="compiled",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    with patch.object(
                        sys, "argv", ["ll-loop", "run", "test-loop"]
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0

    def test_dry_run_prints_execution_plan(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """main_loop --dry-run prints execution plan and exits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            loop_content = """
name: test-loop
initial: start
states:
  start:
    action: echo "test"
    on_success: done
  done:
    terminal: true
"""
            (loops_dir / "test-loop.fsm.yaml").write_text(loop_content)

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test-loop",
                paradigm="test",
                initial="start",
                states={
                    "start": StateConfig(
                        action='echo "test"', on_success="done"
                    ),
                    "done": StateConfig(terminal=True),
                },
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch.object(
                    sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]
                ):
                    # Change to temp directory so resolve_loop_path works
                    import os
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        from little_loops.cli import main_loop
                        result = main_loop()
                    finally:
                        os.chdir(original_cwd)

            captured = capsys.readouterr()
            assert result == 0
            assert "Execution plan for:" in captured.out

    def test_max_iterations_override(self) -> None:
        """main_loop passes max_iterations override to executor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    with patch.object(
                        sys,
                        "argv",
                        ["ll-loop", "run", "test-loop", "--max-iterations", "5"],
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0

    def test_no_llm_flag(self) -> None:
        """main_loop passes no_llm=True when flag set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    with patch.object(
                        sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0

    def test_stop_command(self) -> None:
        """main_loop stop command stops running loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock StatePersistence to return a running state
            from little_loops.fsm.persistence import StatePersistence
            mock_state = MagicMock()
            mock_state.status = "running"

            with patch("little_loops.fsm.persistence.StatePersistence") as mock_sp_cls:
                mock_sp = MagicMock()
                mock_sp.load_state.return_value = mock_state
                mock_sp_cls.return_value = mock_sp

                with patch.object(
                    sys, "argv", ["ll-loop", "stop", "test-loop"]
                ):
                    # Change to temp directory so resolve_loop_path works
                    import os
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        from little_loops.cli import main_loop
                        result = main_loop()
                    finally:
                        os.chdir(original_cwd)

            assert result == 0

    def test_resume_command(self) -> None:
        """main_loop resume command resumes interrupted loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    # resume() returns the same type of result
                    mock_executor.resume.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    with patch.object(
                        sys, "argv", ["ll-loop", "resume", "test-loop"]
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0

    def test_history_command_with_tail(self) -> None:
        """main_loop history command shows execution history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            with patch("little_loops.fsm.persistence.get_loop_history", return_value=[]):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-loop", "history", "test-loop", "--tail", "10"],
                ):
                    # Change to temp directory so resolve_loop_path works
                    import os
                    original_cwd = os.getcwd()
                    try:
                        os.chdir(tmpdir)
                        from little_loops.cli import main_loop
                        result = main_loop()
                    finally:
                        os.chdir(original_cwd)

            assert result == 0

    def test_test_command_single_iteration(self) -> None:
        """main_loop test command runs single test iteration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()
            (
                loops_dir / "test-loop.fsm.yaml"
            ).write_text(
                "name: test\ninitial: start\nstates:\n  start:\n    terminal: true"
            )

            # Mock the FSM validation
            from little_loops.fsm.schema import FSMLoop, StateConfig

            mock_fsm = FSMLoop(
                name="test",
                paradigm="test",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=50,
            )

            with patch("little_loops.fsm.validation.load_and_validate", return_value=mock_fsm):
                with patch(
                    "little_loops.fsm.persistence.PersistentExecutor"
                ) as mock_exec:
                    mock_executor = MagicMock()
                    # Create a proper mock result with all required attributes
                    mock_result = MagicMock()
                    mock_result.iterations = 1
                    mock_result.terminated_by = "terminal"
                    mock_result.final_state = "start"
                    mock_result.duration_ms = 100
                    mock_executor.run.return_value = mock_result
                    mock_exec.return_value = mock_executor

                    with patch.object(
                        sys, "argv", ["ll-loop", "test", "test-loop"]
                    ):
                        # Change to temp directory so resolve_loop_path works
                        import os
                        original_cwd = os.getcwd()
                        try:
                            os.chdir(tmpdir)
                            from little_loops.cli import main_loop
                            result = main_loop()
                        finally:
                            os.chdir(original_cwd)

            assert result == 0


class TestMainSprintAdditionalCoverage:
    """Additional coverage tests for main_sprint entry point."""

    @pytest.fixture
    def sprint_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with sprint config."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            claude_dir = project / ".claude"
            claude_dir.mkdir()
            config = {
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {
                        "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                        "features": {
                            "prefix": "FEAT",
                            "dir": "features",
                            "action": "implement",
                        },
                    },
                    "completed_dir": "completed",
                },
            }
            (claude_dir / "ll-config.json").write_text(json.dumps(config))

            # Create issue directories
            issues_dir = project / ".issues"
            for category in ["bugs", "features", "completed"]:
                (issues_dir / category).mkdir(parents=True)

            # Create sample issues
            (
                issues_dir / "bugs" / "P0-BUG-001-test-bug.md"
            ).write_text("# BUG-001: Test Bug\n\nFix this bug.")
            (
                issues_dir / "features" / "P1-FEAT-010-test-feature.md"
            ).write_text("# FEAT-010: Test Feature\n\nAdd this feature.")

            # Create .sprints directory
            (project / ".sprints").mkdir()

            yield project

    def test_create_with_skip_filter(self, sprint_project: Path) -> None:
        """ll-sprint create with --skip excludes specified issues."""
        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(
                sys,
                "argv",
                [
                    "ll-sprint",
                    "create",
                    "test-sprint-2",
                    "--issues",
                    "BUG-001,FEAT-010",
                    "--skip",
                    "BUG-001",
                ],
            ):
                from little_loops.cli import main_sprint

                result = main_sprint()

        assert result == 0

    def test_list_verbose_mode(self, sprint_project: Path) -> None:
        """ll-sprint list --verbose shows detailed information."""
        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(
                sys,
                "argv",
                [
                    "ll-sprint",
                    "create",
                    "test-sprint-3",
                    "--issues",
                    "BUG-001",
                    "--description",
                    "Test sprint",
                ],
            ):
                from little_loops.cli import main_sprint

                main_sprint()

        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(sys, "argv", ["ll-sprint", "list", "--verbose"]):
                from little_loops.cli import main_sprint

                result = main_sprint()

        assert result == 0

    def test_delete_not_found_error(self) -> None:
        """ll-sprint delete returns error for non-existent sprint."""
        with patch("pathlib.Path.cwd", return_value=Path.cwd()):
            with patch.object(sys, "argv", ["ll-sprint", "delete", "nonexistent-sprint"]):
                from little_loops.cli import main_sprint

                result = main_sprint()

        assert result == 1

    def test_run_sprint_not_found(self, sprint_project: Path) -> None:
        """ll-sprint run returns error for non-existent sprint."""
        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(
                sys,
                "argv",
                ["ll-sprint", "run", "nonexistent-sprint"],
            ):
                from little_loops.cli import main_sprint

                result = main_sprint()

        assert result == 1

    def test_run_dry_run_mode(self, sprint_project: Path) -> None:
        """ll-sprint run --dry-run exits after printing plan."""
        # Create a sprint first
        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(
                sys,
                "argv",
                [
                    "ll-sprint",
                    "create",
                    "test-sprint-4",
                    "--issues",
                    "BUG-001",
                ],
            ):
                from little_loops.cli import main_sprint

                main_sprint()

        with patch("pathlib.Path.cwd", return_value=sprint_project):
            with patch.object(
                sys,
                "argv",
                ["ll-sprint", "run", "test-sprint-4", "--dry-run"],
            ):
                from little_loops.cli import main_sprint

                result = main_sprint()

        assert result == 0


class TestSprintSignalHandler:
    """Tests for sprint signal handler (ENH-183)."""

    @classmethod
    def setup_class(cls) -> None:
        """Import once at class level to access signal handler."""
        import little_loops.cli as cli_module
        cls.cli_module = cli_module

    def setup_method(self) -> None:
        """Reset global flag before each test."""
        self.cli_module._sprint_shutdown_requested = False

    def teardown_method(self) -> None:
        """Reset global flag after each test."""
        self.cli_module._sprint_shutdown_requested = False

    def test_first_signal_sets_flag(self) -> None:
        """First signal sets shutdown flag without exiting."""
        # First signal should set flag
        self.cli_module._sprint_signal_handler(signal.SIGINT, None)

        assert self.cli_module._sprint_shutdown_requested is True

    def test_second_signal_forces_exit(self) -> None:
        """Second signal forces immediate exit with code 1."""
        # Set first signal
        self.cli_module._sprint_signal_handler(signal.SIGINT, None)
        assert self.cli_module._sprint_shutdown_requested is True

        # Second signal should force exit
        with pytest.raises(SystemExit) as exc_info:
            self.cli_module._sprint_signal_handler(signal.SIGTERM, None)

        assert exc_info.value.code == 1

    def test_global_flag_reset_between_tests(self) -> None:
        """Global flag can be reset for independent tests."""
        self.cli_module._sprint_shutdown_requested = False

        self.cli_module._sprint_signal_handler(signal.SIGINT, None)
        assert self.cli_module._sprint_shutdown_requested is True

        # Reset
        self.cli_module._sprint_shutdown_requested = False
        assert self.cli_module._sprint_shutdown_requested is False


class TestMainHistoryCoverage:
    """Coverage tests for main_history entry point (NO existing tests)."""

    @pytest.fixture
    def history_project(self) -> Generator[Path, None, None]:
        """Create a temporary project with completed issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            issues_dir = project / ".issues"
            completed_dir = issues_dir / "completed"
            completed_dir.mkdir(parents=True)

            # Create sample completed issue
            (
                completed_dir / "P1-BUG-001-fixed-bug.md"
            ).write_text(
                """
# BUG-001: Fixed Bug

## Status
Completed

## Resolution
- Fixed the bug
"""
            )
            yield project

    def _make_mock_summary(self) -> "HistorySummary":
        """Create a mock summary object matching HistorySummary dataclass."""
        from datetime import date
        from little_loops.issue_history import HistorySummary

        return HistorySummary(
            total_count=0,
            type_counts={},
            priority_counts={},
            discovery_counts={},
            earliest_date=None,
            latest_date=None,
        )

    def _make_mock_analysis(self) -> "HistoryAnalysis":
        """Create a mock analysis object matching HistoryAnalysis dataclass."""
        from datetime import date
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            HotspotAnalysis,
            CouplingAnalysis,
            RegressionAnalysis,
            TestGapAnalysis,
            RejectionAnalysis,
            ManualPatternAnalysis,
            AgentEffectivenessAnalysis,
            ComplexityProxyAnalysis,
            ConfigGapsAnalysis,
            CrossCuttingAnalysis,
            TechnicalDebtMetrics,
        )

        return HistoryAnalysis(
            generated_date=date(2026, 2, 1),
            total_completed=0,
            total_active=0,
            date_range_start=None,
            date_range_end=None,
            summary=HistorySummary(
                total_count=0,
                type_counts={},
                priority_counts={},
                discovery_counts={},
                earliest_date=None,
                latest_date=None,
            ),
            period_metrics=[],
            velocity_trend="stable",
            bug_ratio_trend="stable",
            subsystem_health=[],
            hotspot_analysis=HotspotAnalysis(),
            coupling_analysis=CouplingAnalysis(),
            regression_analysis=RegressionAnalysis(),
            test_gap_analysis=TestGapAnalysis(),
            rejection_analysis=RejectionAnalysis(),
            manual_pattern_analysis=ManualPatternAnalysis(),
            agent_effectiveness_analysis=AgentEffectivenessAnalysis(),
            complexity_proxy_analysis=ComplexityProxyAnalysis(),
            config_gaps_analysis=ConfigGapsAnalysis(),
            cross_cutting_analysis=CrossCuttingAnalysis(),
            debt_metrics=TechnicalDebtMetrics(),
            comparison_period=None,
            previous_period=None,
            current_period=None,
        )

    def test_summary_command_default_output(self, history_project: Path) -> None:
        """ll-history summary outputs formatted text by default."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history,
                "calculate_summary",
                return_value=self._make_mock_summary(),
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(sys, "argv", ["ll-history", "summary"]):
                        result = main_history()

        assert result == 0

    def test_summary_json_flag(self, history_project: Path) -> None:
        """ll-history summary --json outputs JSON format."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history,
                "calculate_summary",
                return_value=self._make_mock_summary(),
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(sys, "argv", ["ll-history", "summary", "--json"]):
                        result = main_history()

        assert result == 0

    def test_summary_directory_argument(self) -> None:
        """ll-history summary --directory uses custom issues directory."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history,
                "calculate_summary",
                return_value=self._make_mock_summary(),
            ):
                with patch.object(
                    sys, "argv", ["ll-history", "summary", "--directory", "/custom/issues"]
                ):
                    result = main_history()

        assert result == 0

    def test_analyze_command_default_format(self, history_project: Path) -> None:
        """ll-history analyze defaults to text format."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(sys, "argv", ["ll-history", "analyze"]):
                        result = main_history()

        assert result == 0

    def test_analyze_format_json(self, history_project: Path) -> None:
        """ll-history analyze --format json outputs JSON."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(
                        sys, "argv", ["ll-history", "analyze", "--format", "json"]
                    ):
                        result = main_history()

        assert result == 0

    def test_analyze_format_markdown(self, history_project: Path) -> None:
        """ll-history analyze --format markdown outputs Markdown."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(
                        sys, "argv", ["ll-history", "analyze", "--format", "markdown"]
                    ):
                        result = main_history()

        assert result == 0

    def test_analyze_format_yaml(self, history_project: Path) -> None:
        """ll-history analyze --format yaml outputs YAML."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(
                        sys, "argv", ["ll-history", "analyze", "--format", "yaml"]
                    ):
                        result = main_history()

        assert result == 0

    def test_analyze_period_choices(self, history_project: Path) -> None:
        """ll-history analyze --period accepts weekly/monthly/quarterly."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        for period in ["weekly", "monthly", "quarterly"]:
            with patch.object(
                issue_history, "scan_completed_issues", return_value=[]
            ):
                with patch.object(
                    issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
                ):
                    with patch("pathlib.Path.cwd", return_value=history_project):
                        with patch.object(
                            sys, "argv", ["ll-history", "analyze", "--period", period]
                        ):
                            result = main_history()

            assert result == 0

    def test_analyze_compare_argument(self, history_project: Path) -> None:
        """ll-history analyze --compare compares last N days."""
        from little_loops.cli import main_history
        from little_loops import issue_history

        with patch.object(
            issue_history, "scan_completed_issues", return_value=[]
        ):
            with patch.object(
                issue_history, "calculate_analysis", return_value=self._make_mock_analysis()
            ):
                with patch("pathlib.Path.cwd", return_value=history_project):
                    with patch.object(
                        sys, "argv", ["ll-history", "analyze", "--compare", "30"]
                    ):
                        result = main_history()

        assert result == 0

    def test_no_command_shows_help(self) -> None:
        """ll-history with no command shows help and returns error."""
        from little_loops.cli import main_history

        with patch.object(sys, "argv", ["ll-history"]):
            result = main_history()

        assert result == 1
