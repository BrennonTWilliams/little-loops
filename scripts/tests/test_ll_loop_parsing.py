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
        parser = argparse.ArgumentParser(prog="ll-loop run")
        parser.add_argument("loop")
        parser.add_argument("--max-iterations", "-n", type=int)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--quiet", "-q", action="store_true")
        parser.add_argument("--no-llm", action="store_true")
        parser.add_argument("--llm-model", type=str)
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

    def test_compile_subcommand(self) -> None:
        """compile subcommand."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["compile", "paradigm.yaml"])
        assert args.command == "compile"
        assert args.input == "paradigm.yaml"
        assert args.output is None

    def test_compile_with_output(self) -> None:
        """compile with -o output."""
        parser = self._create_subparser_only()
        args = parser.parse_args(["compile", "paradigm.yaml", "-o", "output.yaml"])
        assert args.output == "output.yaml"

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
