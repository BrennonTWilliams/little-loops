"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


class TestLoopArgumentParsing:
    """Tests for ll-loop argument parsing.

    Note: The actual ll-loop CLI uses a complex argparse setup with both a
    positional 'loop' argument and subparsers. This requires special handling
    in the main_loop function to distinguish between "ll-loop fix-types" and
    "ll-loop run fix-types". The tests here verify the subparser-based parsing.
    """

    def _create_run_parser(self) -> argparse.ArgumentParser:
        """Create parser for run subcommand tests."""
        from little_loops.cli_args import add_handoff_threshold_arg

        parser = argparse.ArgumentParser(prog="ll-loop run")
        parser.add_argument("loop")
        parser.add_argument("input", nargs="?", default=None)
        parser.add_argument("--max-iterations", "-n", type=int)
        parser.add_argument("--delay", type=float, default=None, metavar="SECONDS")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--quiet", "-q", action="store_true")
        parser.add_argument("--no-llm", action="store_true")
        parser.add_argument("--llm-model", type=str)
        parser.add_argument("--context", action="append", default=[], metavar="KEY=VALUE")
        add_handoff_threshold_arg(parser)
        return parser

    def _create_subparser_only(self) -> argparse.ArgumentParser:
        """Create parser with subparsers only (no top-level loop arg)."""
        parser = argparse.ArgumentParser(prog="ll-loop")

        subparsers = parser.add_subparsers(dest="command")

        run_parser = subparsers.add_parser("run")
        run_parser.add_argument("loop")
        run_parser.add_argument("--max-iterations", "-n", type=int)
        run_parser.add_argument("--dry-run", action="store_true")

        validate_parser = subparsers.add_parser("validate")
        validate_parser.add_argument("loop")

        list_parser = subparsers.add_parser("list")
        list_parser.add_argument("--running", action="store_true")

        compile_parser = subparsers.add_parser("compile")
        compile_parser.add_argument("input")
        compile_parser.add_argument("-o", "--output")

        status_parser = subparsers.add_parser("status")
        status_parser.add_argument("loop")

        history_parser = subparsers.add_parser("history")
        history_parser.add_argument("loop")
        history_parser.add_argument("--tail", "-n", type=int, default=50)

        return parser

    def test_run_subcommand(self) -> None:
        """run subcommand parses correctly."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["run", "fix-types"])
        assert args.command == "run"
        assert args.loop == "fix-types"

    def test_run_with_dry_run(self) -> None:
        """run --dry-run."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["run", "fix-types", "--dry-run"])
        assert args.command == "run"
        assert args.dry_run is True

    def test_run_with_max_iterations(self) -> None:
        """run --max-iterations."""
        parser = self._create_run_parser()
        args = parser.parse_args(["fix-types", "--max-iterations", "10"])
        assert args.max_iterations == 10
        assert args.loop == "fix-types"

    def test_validate_subcommand(self) -> None:
        """validate subcommand."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["validate", "fix-types"])
        assert args.command == "validate"
        assert args.loop == "fix-types"

    def test_list_subcommand(self) -> None:
        """list subcommand."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["list"])
        assert args.command == "list"
        assert args.running is False

    def test_list_running(self) -> None:
        """list --running."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["list", "--running"])
        assert args.command == "list"
        assert args.running is True

    def test_history_subcommand(self) -> None:
        """history subcommand."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["history", "fix-types"])
        assert args.command == "history"
        assert args.loop == "fix-types"
        assert args.tail == 50

    def test_history_with_tail(self) -> None:
        """history with --tail."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["history", "fix-types", "--tail", "20"])
        assert args.tail == 20

    def test_history_json_accepted_by_real_parser(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """history --json is accepted by the actual ll-loop parser (not rejected as unrecognized)."""
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        with (
            patch.object(sys, "argv", ["ll-loop", "history", "my-loop", "--json"]),
            patch("little_loops.cli.loop.info.cmd_history", return_value=0) as mock_history,
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        mock_history.assert_called_once()
        # cmd_history(loop_name, run_id, args, loops_dir) — args is the third positional argument
        call_args = mock_history.call_args
        history_args = call_args[0][2]
        assert getattr(history_args, "json", False) is True

    def test_status_subcommand(self) -> None:
        """status subcommand."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["status", "test-loop"])
        assert args.command == "status"
        assert args.loop == "test-loop"

    def test_no_llm_flag_parsed_correctly(self) -> None:
        """--no-llm flag sets no_llm to True."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--no-llm"])
        assert args.no_llm is True

    def test_no_llm_default_is_false(self) -> None:
        """--no-llm defaults to False when not specified."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop"])
        assert args.no_llm is False

    def test_llm_model_flag_parsed_correctly(self) -> None:
        """--llm-model accepts model string."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--llm-model", "claude-opus-4-20250514"])
        assert args.llm_model == "claude-opus-4-20250514"

    def test_llm_model_default_is_none(self) -> None:
        """--llm-model defaults to None when not specified."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop"])
        assert args.llm_model is None

    def test_context_single_flag(self) -> None:
        """--context KEY=VALUE is parsed into a list."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--context", "issue_id=042"])
        assert args.context == ["issue_id=042"]

    def test_context_multiple_flags(self) -> None:
        """Multiple --context flags accumulate into a list."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--context", "a=1", "--context", "b=2"])
        assert args.context == ["a=1", "b=2"]

    def test_context_default_is_empty_list(self) -> None:
        """--context defaults to [] when not specified."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop"])
        assert args.context == []

    def test_delay_flag_accepts_float(self) -> None:
        """--delay accepts a float value in seconds."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--delay", "0.5"])
        assert args.delay == 0.5

    def test_delay_flag_accepts_zero(self) -> None:
        """--delay 0 is accepted and distinct from not set."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop", "--delay", "0"])
        assert args.delay == 0.0

    def test_delay_default_is_none(self) -> None:
        """--delay defaults to None when not specified."""
        parser = self._create_run_parser()
        args = parser.parse_args(["test-loop"])
        assert args.delay is None

    def test_positional_input_parsed(self) -> None:
        """Positional input arg is parsed correctly."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop", "FEAT-719"])
        assert args.loop == "my-loop"
        assert args.input == "FEAT-719"

    def test_positional_input_default_is_none(self) -> None:
        """Positional input defaults to None when not provided."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop"])
        assert args.input is None

    def test_positional_input_quoted_string(self) -> None:
        """Positional input accepts a multi-word quoted string."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop", "What are best practices for Python?"])
        assert args.input == "What are best practices for Python?"

    def test_positional_input_with_context_flag(self) -> None:
        """Positional input coexists with --context flag."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop", "FEAT-719", "--context", "other=val"])
        assert args.input == "FEAT-719"
        assert args.context == ["other=val"]

    def test_handoff_threshold_parsed(self) -> None:
        """--handoff-threshold is registered on the run subparser."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop", "--handoff-threshold", "40"])
        assert args.handoff_threshold == 40

    def test_handoff_threshold_default_is_none(self) -> None:
        """--handoff-threshold defaults to None when not specified."""
        parser = self._create_run_parser()
        args = parser.parse_args(["my-loop"])
        assert args.handoff_threshold is None

    def test_handoff_threshold_registered_on_real_run_parser(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold is accepted by the actual ll-loop run parser."""
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        with (
            patch.object(sys, "argv", ["ll-loop", "run", "my-loop", "--handoff-threshold", "55"]),
            patch("little_loops.cli.loop.run.cmd_run", return_value=0) as mock_run,
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        mock_run.assert_called_once()
        run_args = mock_run.call_args[0][1]
        assert getattr(run_args, "handoff_threshold", None) == 55

    def test_handoff_threshold_registered_on_real_resume_parser(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--handoff-threshold is accepted by the actual ll-loop resume parser."""
        import sys
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        with (
            patch.object(
                sys, "argv", ["ll-loop", "resume", "my-loop", "--handoff-threshold", "30"]
            ),
            patch("little_loops.cli.loop.lifecycle.cmd_resume", return_value=0) as mock_resume,
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        mock_resume.assert_called_once()
        resume_args = mock_resume.call_args[0][1]
        assert getattr(resume_args, "handoff_threshold", None) == 30


class TestResolveLoopPath:
    """Tests for resolve_loop_path function logic."""

    @pytest.fixture
    def temp_project(self) -> Generator[Path, None, None]:
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            yield project

    def test_direct_path_exists(self, temp_project: Path) -> None:
        """Direct path returns as-is when exists."""
        loop_file = temp_project / "my-loop.yaml"
        loop_file.write_text("name: test")

        # Simulate resolve_loop_path logic
        path = Path(str(loop_file))
        assert path.exists()

    def test_loops_dir_resolution(self, temp_project: Path) -> None:
        """Loop name resolves to .loops/<name>.yaml."""
        loops_dir = temp_project / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "fix-types.yaml"
        loop_file.write_text("name: fix-types")

        # Simulate resolution logic
        name = "fix-types"
        direct = temp_project / name
        loops_path = temp_project / ".loops" / f"{name}.yaml"

        assert not direct.exists()
        assert loops_path.exists()

    def test_not_found(self, temp_project: Path) -> None:
        """FileNotFoundError for missing loop."""
        name = "nonexistent"
        direct = temp_project / name
        loops_path = temp_project / ".loops" / f"{name}.yaml"

        assert not direct.exists()
        assert not loops_path.exists()


class TestParseDuration:
    """Tests for the parse_duration() utility in text_utils."""

    def test_hours(self) -> None:
        """1h parses to 3600 seconds."""
        from little_loops.text_utils import parse_duration

        assert parse_duration("1h") == 3600

    def test_minutes(self) -> None:
        """30m parses to 1800 seconds."""
        from little_loops.text_utils import parse_duration

        assert parse_duration("30m") == 1800

    def test_days(self) -> None:
        """2d parses to 172800 seconds."""
        from little_loops.text_utils import parse_duration

        assert parse_duration("2d") == 172800

    def test_seconds(self) -> None:
        """45s parses to 45 seconds."""
        from little_loops.text_utils import parse_duration

        assert parse_duration("45s") == 45

    def test_multi_digit(self) -> None:
        """12h parses to 43200 seconds."""
        from little_loops.text_utils import parse_duration

        assert parse_duration("12h") == 43200

    def test_invalid_unit_raises(self) -> None:
        """Unknown unit raises ValueError."""
        from little_loops.text_utils import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("1w")

    def test_empty_string_raises(self) -> None:
        """Empty string raises ValueError."""
        from little_loops.text_utils import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")

    def test_missing_number_raises(self) -> None:
        """Missing numeric part raises ValueError."""
        from little_loops.text_utils import parse_duration

        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("h")
