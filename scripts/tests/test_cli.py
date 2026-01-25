"""Tests for CLI argument parsing.

Tests the argument parsing logic for ll-auto and ll-parallel commands
without executing the actual managers.
"""

from __future__ import annotations

import argparse
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
        create.add_argument("--mode", choices=["auto", "parallel"], default="auto")
        create.add_argument("--max-workers", type=int, default=4)
        create.add_argument("--timeout", type=int, default=3600)

        # run
        run = subparsers.add_parser("run")
        run.add_argument("sprint")
        run.add_argument("--parallel", action="store_true")
        run.add_argument("--dry-run", "-n", action="store_true")
        run.add_argument("--max-workers", type=int)
        run.add_argument("--timeout", type=int)
        run.add_argument("--config", type=Path)

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
                "--mode",
                "parallel",
                "--max-workers",
                "8",
            ]
        )
        assert args.command == "create"
        assert args.name == "sprint-1"
        assert args.issues == "BUG-001,FEAT-010"
        assert args.description == "Q1 fixes"
        assert args.mode == "parallel"
        assert args.max_workers == 8

    def test_run_command(self) -> None:
        """run subcommand parses correctly."""
        args = self._parse_sprint_args(
            ["run", "sprint-1", "--parallel", "--dry-run", "--max-workers", "8"]
        )
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.parallel is True
        assert args.dry_run is True
        assert args.max_workers == 8

    def test_run_sequential(self) -> None:
        """run without --parallel flag."""
        args = self._parse_sprint_args(["run", "sprint-1"])
        assert args.command == "run"
        assert args.sprint == "sprint-1"
        assert args.parallel is False

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
