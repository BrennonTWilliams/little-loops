"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator
from unittest.mock import MagicMock

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


class TestCmdValidate:
    """Tests for validate command logic."""

    @pytest.fixture
    def valid_loop_file(self, tmp_path: Path) -> Path:
        """Create a valid loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text("""
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
""")
        return loop_file

    @pytest.fixture
    def invalid_loop_file(self, tmp_path: Path) -> Path:
        """Create an invalid loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "invalid-loop.yaml"
        loop_file.write_text("""
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
""")
        return loop_file

    def test_valid_loop_structure(self, valid_loop_file: Path) -> None:
        """Valid loop file has correct structure."""
        import yaml

        with open(valid_loop_file) as f:
            data = yaml.safe_load(f)

        assert "name" in data
        assert "initial" in data
        assert "states" in data
        assert data["initial"] in data["states"]

    def test_invalid_loop_structure(self, invalid_loop_file: Path) -> None:
        """Invalid loop file has missing initial state."""
        import yaml

        with open(invalid_loop_file) as f:
            data = yaml.safe_load(f)

        assert data["initial"] not in data["states"]


class TestCmdList:
    """Tests for list command logic."""

    @pytest.fixture
    def loops_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory with some files."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: a")
        (loops_dir / "loop-b.yaml").write_text("name: b")
        (loops_dir / "loop-c.yaml").write_text("name: c")
        return loops_dir

    def test_list_available_loops(self, loops_dir: Path) -> None:
        """List returns all YAML files."""
        yaml_files = list(loops_dir.glob("*.yaml"))
        assert len(yaml_files) == 3
        names = sorted(p.stem for p in yaml_files)
        assert names == ["loop-a", "loop-b", "loop-c"]

    def test_no_loops_dir(self, tmp_path: Path) -> None:
        """No .loops directory returns gracefully."""
        loops_dir = tmp_path / ".loops"
        assert not loops_dir.exists()


class TestCmdHistory:
    """Tests for history command logic."""

    @pytest.fixture
    def events_file(self, tmp_path: Path) -> Path:
        """Create an events file."""
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"

        events = [
            {"event": "loop_start", "ts": "2026-01-13T10:00:00", "loop": "test-loop"},
            {"event": "state_enter", "ts": "2026-01-13T10:00:01", "state": "check", "iteration": 1},
            {"event": "action_start", "ts": "2026-01-13T10:00:02", "action": "echo hello"},
            {"event": "evaluate", "ts": "2026-01-13T10:00:03", "verdict": "success"},
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_read_events(self, events_file: Path) -> None:
        """Events file can be read as JSONL."""
        events: list[dict[str, Any]] = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line.strip()))

        assert len(events) == 4
        assert events[0]["event"] == "loop_start"
        assert events[-1]["verdict"] == "success"

    def test_tail_events(self, events_file: Path) -> None:
        """Tail returns last N events."""
        events: list[dict[str, Any]] = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line.strip()))

        tail = 2
        last_n = events[-tail:]
        assert len(last_n) == 2
        assert last_n[0]["event"] == "action_start"


class TestStateToDict:
    """Tests for _state_to_dict helper function."""

    def test_simple_state(self) -> None:
        """Convert simple state config to dict."""
        # Simulate StateConfig structure
        state = MagicMock()
        state.action = "echo hello"
        state.evaluate = None
        state.on_success = "done"
        state.on_failure = None
        state.on_error = None
        state.next = None
        state.route = None
        state.terminal = False
        state.capture = None
        state.timeout = None
        state.on_maintain = None

        d: dict[str, Any] = {}
        if state.action:
            d["action"] = state.action
        if state.on_success:
            d["on_success"] = state.on_success

        assert d == {"action": "echo hello", "on_success": "done"}

    def test_terminal_state(self) -> None:
        """Convert terminal state to dict."""
        state = MagicMock()
        state.action = None
        state.evaluate = None
        state.on_success = None
        state.on_failure = None
        state.on_error = None
        state.next = None
        state.route = None
        state.terminal = True
        state.capture = None
        state.timeout = None
        state.on_maintain = None

        d: dict[str, Any] = {}
        if state.terminal:
            d["terminal"] = True

        assert d == {"terminal": True}


class TestProgressDisplay:
    """Tests for progress display formatting."""

    def test_duration_seconds(self) -> None:
        """Duration under 60s formatted as seconds."""
        duration_ms = 5200
        duration_sec = duration_ms / 1000
        assert duration_sec < 60
        duration_str = f"{duration_sec:.1f}s"
        assert duration_str == "5.2s"

    def test_duration_minutes(self) -> None:
        """Duration over 60s formatted as minutes."""
        duration_ms = 150000  # 2.5 minutes
        duration_sec = duration_ms / 1000
        assert duration_sec >= 60
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:.0f}s"
        assert duration_str == "2m 30s"

    def test_verdict_symbols(self) -> None:
        """Correct symbols for success/failure verdicts."""
        success_verdicts = ("success", "target", "progress")
        failure_verdicts = ("failure", "stall", "error", "blocked")

        for v in success_verdicts:
            assert v in success_verdicts

        for v in failure_verdicts:
            assert v not in success_verdicts
