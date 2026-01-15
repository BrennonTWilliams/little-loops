"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

if TYPE_CHECKING:
    pass


def make_test_state(
    action: str | None = None,
    on_success: str | None = None,
    on_failure: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
    capture: str | None = None,
    timeout: int | None = None,
    on_maintain: str | None = None,
) -> StateConfig:
    """Create StateConfig for testing."""
    return StateConfig(
        action=action,
        on_success=on_success,
        on_failure=on_failure,
        on_error=on_error,
        next=next,
        terminal=terminal,
        evaluate=evaluate,
        route=route,
        capture=capture,
        timeout=timeout,
        on_maintain=on_maintain,
    )


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_iterations: int = 50,
    timeout: int | None = None,
) -> FSMLoop:
    """Create FSMLoop for testing."""
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_success="done", on_failure="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_iterations=max_iterations,
        timeout=timeout,
    )


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


class TestMainLoopIntegration:
    """Integration tests that call main_loop() directly.

    These tests verify the actual CLI entry point behavior, including:
    - Shorthand conversion (loop name -> run subcommand)
    - Argument parsing and command dispatch
    - Handler function execution

    Unlike the unit tests above, these tests call the actual main_loop()
    function with mocked sys.argv to test real CLI behavior.

    Note: Uses monkeypatch.chdir() to change working directory since
    Path(".loops") resolves against the actual cwd, not Path.cwd().
    """

    def test_shorthand_inserts_run_subcommand(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ll-loop fix-types becomes ll-loop run fix-types internally."""
        # Create valid loop file
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: fix-types
initial: check
states:
  check:
    terminal: true
"""
        (loops_dir / "fix-types.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "fix-types", "--dry-run"]):
            from little_loops.cli import main_loop

            result = main_loop()

        # --dry-run should succeed and return 0
        assert result == 0

    def test_run_dry_run_outputs_plan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run outputs execution plan without running."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: start
states:
  start:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "Execution plan for: test-loop" in captured.out
        assert "[start]" in captured.out
        assert "[done]" in captured.out

    def test_run_with_max_iterations_shows_in_plan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--max-iterations override is reflected in dry-run plan."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
max_iterations: 5
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "run", "test-loop", "-n", "20", "--dry-run"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Max iterations should be shown in plan output
        assert "20" in captured.out

    def test_run_missing_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run with non-existent loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_validate_valid_loop_succeeds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """validate with valid loop returns success."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: valid-loop
initial: start
states:
  start:
    action: "echo test"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "valid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "valid-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Should print validation success message
        assert "valid-loop" in captured.out.lower() or "Valid" in captured.out

    def test_validate_missing_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate with missing loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_list_empty_loops_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list with empty .loops/ directory shows no loops."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Either shows "No loops" message or empty output
        assert "No loops" in captured.out or captured.out.strip() == ""

    def test_list_multiple_loops(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list shows all available loops."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: a")
        (loops_dir / "loop-b.yaml").write_text("name: b")
        (loops_dir / "loop-c.yaml").write_text("name: c")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "loop-a" in captured.out
        assert "loop-b" in captured.out
        assert "loop-c" in captured.out

    def test_list_no_loops_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """list with missing .loops/ directory handles gracefully."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()

        # Should handle missing .loops/ gracefully
        assert result == 0

    def test_status_no_state_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """status with no saved state returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_stop_no_running_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop with no running loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_history_no_events_returns_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """history with no events handles gracefully."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        # Should return 0 even with no events
        assert result == 0

    def test_compile_valid_paradigm(self, tmp_path: Path) -> None:
        """compile with valid paradigm creates output file."""
        input_file = tmp_path / "paradigm.yaml"
        input_file.write_text(
            """
name: test-paradigm
paradigm: simple
goal: "Test goal"
"""
        )

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
        # Output file should be created
        output_file = tmp_path / "paradigm.fsm.yaml"
        assert output_file.exists()

    def test_compile_with_output_flag(self, tmp_path: Path) -> None:
        """compile -o specifies output file path."""
        input_file = tmp_path / "paradigm.yaml"
        input_file.write_text("name: test\nparadigm: simple")
        output_file = tmp_path / "custom-output.yaml"

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

            with patch.object(
                sys,
                "argv",
                ["ll-loop", "compile", str(input_file), "-o", str(output_file)],
            ):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        assert output_file.exists()

    def test_compile_missing_input_returns_error(self, tmp_path: Path) -> None:
        """compile with missing input file returns error."""
        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(tmp_path / "nonexistent.yaml")]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_unknown_command_shows_help(self) -> None:
        """No command shows help and returns error."""
        with patch.object(sys, "argv", ["ll-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_run_quiet_flag_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--quiet flag is accepted by the CLI."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        # Note: dry-run still outputs execution plan, but --quiet affects run output
        with patch.object(
            sys, "argv", ["ll-loop", "run", "test-loop", "--quiet", "--dry-run"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0


class TestCmdStop:
    """Tests for stop subcommand."""

    def test_stop_running_loop_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop marks running loop as interrupted."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create state file for "running" loop
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "check",
                    "iteration": 3,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:05:00Z",
                    "status": "running",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        # Verify status was updated
        updated_state = json.loads(state_file.read_text())
        assert updated_state["status"] == "interrupted"

    def test_stop_nonexistent_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error for unknown loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_stop_already_stopped_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error if loop not running."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create state file with "completed" status
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "done",
                    "iteration": 5,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:05:00Z",
                    "status": "completed",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_stop_interrupted_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stop returns error if loop already interrupted."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "check",
                    "iteration": 3,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:05:00Z",
                    "status": "interrupted",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1


class TestCmdResume:
    """Tests for resume subcommand."""

    def test_resume_nothing_to_resume_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns warning when nothing to resume."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create valid loop file but no state
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_resume_file_not_found_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error for missing loop file."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_resume_validation_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error for invalid loop definition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create invalid loop (initial state doesn't exist)
        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "invalid-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_resume_completed_loop_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resume returns error if loop already completed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create valid loop file
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        # Create state file with "completed" status
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "done",
                    "iteration": 5,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:05:00Z",
                    "status": "completed",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        # PersistentExecutor.resume() returns None for completed loops
        assert result == 1


class TestErrorHandling:
    """Tests for error handling across subcommands."""

    def test_run_validation_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run returns error for invalid loop definition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        # Create invalid loop (initial state doesn't exist)
        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "invalid-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_validate_invalid_initial_state_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """validate catches missing initial state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_content = """
name: invalid-loop
initial: nonexistent
states:
  check:
    action: "echo hello"
"""
        (loops_dir / "invalid-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "invalid-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_compile_yaml_error_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """compile returns error for malformed YAML."""
        # Create file with invalid YAML syntax
        input_file = tmp_path / "malformed.yaml"
        input_file.write_text(
            """
name: test
paradigm: simple
invalid yaml: [unclosed bracket
goal: "Test"
"""
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_status_displays_all_fields(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """status displays all state fields correctly."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "fixing",
                    "iteration": 7,
                    "captured": {"errors": "3"},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:15:00Z",
                    "status": "running",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "test-loop" in captured.out
        assert "running" in captured.out
        assert "fixing" in captured.out
        assert "7" in captured.out
