"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import yaml

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


class TestHistoryTail:
    """Integration tests for history --tail flag truncation behavior."""

    @pytest.fixture
    def many_events_file(self, tmp_path: Path) -> Path:
        """Create an events file with 10 events for tail testing."""
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"

        # Create 10 events with unique identifiers
        events = [
            {
                "event": "transition",
                "ts": f"2026-01-15T10:00:{i:02d}",
                "from": f"state{i}",
                "to": f"state{i + 1}",
            }
            for i in range(10)
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_history_tail_limits_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N should show only last N events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "3"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Verify only last 3 events appear (state7, state8, state9)
        assert "'from': 'state7'" in captured.out
        assert "'from': 'state8'" in captured.out
        assert "'from': 'state9'" in captured.out
        # First events should NOT appear (use exact match to avoid state10 matching state1)
        assert "'from': 'state0'" not in captured.out
        assert "'from': 'state1'" not in captured.out
        assert "'from': 'state5'" not in captured.out

    def test_history_tail_zero_shows_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail 0 shows all events (Python list[-0:] returns full list)."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "0"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Due to Python slicing behavior, list[-0:] returns all items
        # All 10 events should appear
        for i in range(10):
            assert f"'from': 'state{i}'" in captured.out

    def test_history_tail_exceeds_events_shows_all(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """--tail N where N > total events shows all events."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "100"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear
        for i in range(10):
            assert f"'from': 'state{i}'" in captured.out

    def test_history_default_tail_shows_all_small(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Without --tail (default 50), all events shown when < 50."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 10 events should appear (10 < 50 default)
        for i in range(10):
            assert f"'from': 'state{i}'" in captured.out

    def test_history_tail_preserves_chronological_order(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        many_events_file: Path,
    ) -> None:
        """Tail should show events in chronological order."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "3"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Verify chronological order: state7 before state8 before state9
        state7_pos = captured.out.find("state7")
        state8_pos = captured.out.find("state8")
        state9_pos = captured.out.find("state9")
        assert state7_pos < state8_pos < state9_pos

    def test_history_tail_with_empty_events(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tail with empty events file handles gracefully."""
        # Create empty events file
        running_dir = tmp_path / ".loops" / ".running"
        running_dir.mkdir(parents=True)
        events_file = running_dir / "test-loop.events.jsonl"
        events_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "--tail", "5"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "No history" in captured.out


class TestStateToDict:
    """Tests for _state_to_dict helper function using real StateConfig objects."""

    def _state_to_dict(self, state: StateConfig) -> dict[str, Any]:
        """Re-implement _state_to_dict logic for testing.

        This mirrors the implementation in cli.py to verify behavior.
        The actual function is nested inside main_loop() so cannot be imported.
        """
        d: dict[str, Any] = {}
        if state.action:
            d["action"] = state.action
        if state.evaluate:
            d["evaluate"] = {"type": state.evaluate.type}
            if state.evaluate.target is not None:
                d["evaluate"]["target"] = state.evaluate.target
            if state.evaluate.tolerance is not None:
                d["evaluate"]["tolerance"] = state.evaluate.tolerance
            if state.evaluate.previous is not None:
                d["evaluate"]["previous"] = state.evaluate.previous
            if state.evaluate.operator is not None:
                d["evaluate"]["operator"] = state.evaluate.operator
            if state.evaluate.pattern is not None:
                d["evaluate"]["pattern"] = state.evaluate.pattern
            if state.evaluate.path is not None:
                d["evaluate"]["path"] = state.evaluate.path
        if state.on_success:
            d["on_success"] = state.on_success
        if state.on_failure:
            d["on_failure"] = state.on_failure
        if state.on_error:
            d["on_error"] = state.on_error
        if state.next:
            d["next"] = state.next
        if state.route:
            d["route"] = dict(state.route.routes)
            if state.route.default:
                d["route"]["_"] = state.route.default
        if state.terminal:
            d["terminal"] = True
        if state.capture:
            d["capture"] = state.capture
        if state.timeout:
            d["timeout"] = state.timeout
        if state.on_maintain:
            d["on_maintain"] = state.on_maintain
        return d

    def test_simple_state_with_action(self) -> None:
        """Convert state with action and on_success."""
        state = make_test_state(action="echo hello", on_success="done")
        result = self._state_to_dict(state)
        assert result == {"action": "echo hello", "on_success": "done"}

    def test_terminal_state(self) -> None:
        """Convert terminal state to dict."""
        state = make_test_state(terminal=True)
        result = self._state_to_dict(state)
        assert result == {"terminal": True}

    def test_state_with_failure_routing(self) -> None:
        """Convert state with on_failure."""
        state = make_test_state(
            action="pytest",
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "pytest",
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_on_error(self) -> None:
        """Convert state with on_error."""
        state = make_test_state(
            action="risky_command",
            on_success="done",
            on_error="handle_error",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "risky_command",
            "on_success": "done",
            "on_error": "handle_error",
        }

    def test_state_with_next(self) -> None:
        """Convert state with unconditional next."""
        state = make_test_state(action="echo step", next="next_state")
        result = self._state_to_dict(state)
        assert result == {"action": "echo step", "next": "next_state"}

    def test_state_with_evaluate_exit_code(self) -> None:
        """Convert state with exit_code evaluator."""
        state = make_test_state(
            action="pytest",
            evaluate=EvaluateConfig(type="exit_code"),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "pytest",
            "evaluate": {"type": "exit_code"},
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_evaluate_numeric(self) -> None:
        """Convert state with output_numeric evaluator."""
        state = make_test_state(
            action="wc -l errors.log",
            evaluate=EvaluateConfig(
                type="output_numeric",
                operator="le",
                target=5,
            ),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "wc -l errors.log",
            "evaluate": {
                "type": "output_numeric",
                "operator": "le",
                "target": 5,
            },
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_evaluate_convergence(self) -> None:
        """Convert state with convergence evaluator."""
        state = make_test_state(
            action="count_errors",
            evaluate=EvaluateConfig(
                type="convergence",
                target=0,
                tolerance=0.1,
                previous="${captured.last_count}",
            ),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "convergence"
        assert result["evaluate"]["target"] == 0
        assert result["evaluate"]["tolerance"] == 0.1
        assert result["evaluate"]["previous"] == "${captured.last_count}"

    def test_state_with_evaluate_pattern(self) -> None:
        """Convert state with output_contains evaluator."""
        state = make_test_state(
            action="grep ERROR log.txt",
            evaluate=EvaluateConfig(
                type="output_contains",
                pattern="ERROR",
            ),
            on_success="fix",
            on_failure="done",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "output_contains"
        assert result["evaluate"]["pattern"] == "ERROR"

    def test_state_with_evaluate_json_path(self) -> None:
        """Convert state with output_json evaluator."""
        state = make_test_state(
            action="curl api/status",
            evaluate=EvaluateConfig(
                type="output_json",
                path=".status",
                target="healthy",
            ),
            on_success="done",
            on_failure="retry",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "output_json"
        assert result["evaluate"]["path"] == ".status"
        assert result["evaluate"]["target"] == "healthy"

    def test_state_with_route_table(self) -> None:
        """Convert state with route table."""
        state = make_test_state(
            action="analyze",
            evaluate=EvaluateConfig(type="llm_structured"),
            route=RouteConfig(
                routes={"success": "done", "failure": "retry", "blocked": "escalate"},
                default="error_state",
            ),
        )
        result = self._state_to_dict(state)
        assert result["route"] == {
            "success": "done",
            "failure": "retry",
            "blocked": "escalate",
            "_": "error_state",
        }

    def test_state_with_route_no_default(self) -> None:
        """Convert state with route table but no default."""
        state = make_test_state(
            action="check",
            route=RouteConfig(routes={"pass": "done", "fail": "fix"}),
        )
        result = self._state_to_dict(state)
        assert result["route"] == {"pass": "done", "fail": "fix"}
        assert "_" not in result["route"]

    def test_state_with_capture(self) -> None:
        """Convert state with capture variable."""
        state = make_test_state(
            action="wc -l errors.log",
            capture="error_count",
            on_success="check",
        )
        result = self._state_to_dict(state)
        assert result["capture"] == "error_count"

    def test_state_with_timeout(self) -> None:
        """Convert state with timeout."""
        state = make_test_state(
            action="slow_command",
            timeout=300,
            on_success="done",
        )
        result = self._state_to_dict(state)
        assert result["timeout"] == 300

    def test_state_with_on_maintain(self) -> None:
        """Convert state with on_maintain."""
        state = make_test_state(
            action="monitor",
            on_maintain="monitor",
            on_success="done",
        )
        result = self._state_to_dict(state)
        assert result["on_maintain"] == "monitor"

    def test_all_fields_populated(self) -> None:
        """Convert state with all optional fields populated."""
        state = make_test_state(
            action="full_test",
            evaluate=EvaluateConfig(
                type="output_numeric",
                operator="eq",
                target=0,
            ),
            on_success="done",
            on_failure="fix",
            on_error="error_handler",
            capture="result",
            timeout=60,
        )
        result = self._state_to_dict(state)
        assert "action" in result
        assert "evaluate" in result
        assert "on_success" in result
        assert "on_failure" in result
        assert "on_error" in result
        assert "capture" in result
        assert "timeout" in result


class TestPrintExecutionPlan:
    """Tests for print_execution_plan output formatting.

    Note: print_execution_plan is a nested function in main_loop(), so we test
    via the CLI's --dry-run flag which calls it.
    """

    def test_basic_plan_shows_states(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan output shows all states."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: start
states:
  start:
    action: "echo start"
    on_success: done
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "[start]" in captured.out
        assert "[done]" in captured.out

    def test_terminal_state_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Terminal states marked with [TERMINAL]."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: done
states:
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "[TERMINAL]" in captured.out

    def test_long_action_truncated(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Actions over 70 chars are truncated with ..."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_action = "echo " + "x" * 100  # 105 chars total
        (loops_dir / "test.yaml").write_text(f"""
name: test
initial: start
states:
  start:
    action: "{long_action}"
    on_success: done
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        # Should be truncated at 70 chars with ...
        assert "..." in captured.out
        # Full action should NOT appear
        assert long_action not in captured.out

    def test_evaluate_type_shown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate type is displayed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: check
states:
  check:
    action: "pytest"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: fix
  fix:
    action: "fix.sh"
    next: check
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "evaluate: exit_code" in captured.out

    def test_route_mappings_displayed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Route mappings are displayed correctly."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: analyze
states:
  analyze:
    action: "check status"
    route:
      success: done
      failure: retry
      _: error
  done:
    terminal: true
  retry:
    action: "retry"
    next: analyze
  error:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "route:" in captured.out
        assert "success -> done" in captured.out
        assert "failure -> retry" in captured.out
        assert "_ -> error" in captured.out

    def test_metadata_shown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop metadata (initial, max_iterations, timeout) shown."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: start
max_iterations: 25
timeout: 3600
states:
  start:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "Initial state: start" in captured.out
        assert "Max iterations: 25" in captured.out
        assert "Timeout: 3600s" in captured.out


class TestProgressDisplay:
    """Tests for progress display formatting."""

    @pytest.mark.parametrize(
        "duration_ms,expected",
        [
            (5200, "5.2s"),
            (30000, "30.0s"),
            (59900, "59.9s"),
        ],
    )
    def test_duration_seconds(self, duration_ms: int, expected: str) -> None:
        """Duration under 60s formatted as seconds."""
        duration_sec = duration_ms / 1000
        assert duration_sec < 60
        duration_str = f"{duration_sec:.1f}s"
        assert duration_str == expected

    @pytest.mark.parametrize(
        "duration_ms,expected",
        [
            (60000, "1m 0s"),
            (90000, "1m 30s"),
            (150000, "2m 30s"),
            (3600000, "60m 0s"),
        ],
    )
    def test_duration_minutes(self, duration_ms: int, expected: str) -> None:
        """Duration over 60s formatted as minutes."""
        duration_sec = duration_ms / 1000
        assert duration_sec >= 60
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:.0f}s"
        assert duration_str == expected

    @pytest.mark.parametrize(
        "verdict,expected_symbol",
        [
            ("success", "\u2713"),
            ("target", "\u2713"),
            ("progress", "\u2713"),
            ("failure", "\u2717"),
            ("stall", "\u2717"),
            ("error", "\u2717"),
            ("blocked", "\u2717"),
        ],
    )
    def test_verdict_symbols(self, verdict: str, expected_symbol: str) -> None:
        """Correct symbols for success/failure verdicts."""
        success_verdicts = ("success", "target", "progress")
        symbol = "\u2713" if verdict in success_verdicts else "\u2717"
        assert symbol == expected_symbol

    @pytest.mark.parametrize(
        "action_length,expect_truncation",
        [
            (50, False),
            (60, False),
            (61, True),
            (70, True),
            (100, True),
        ],
    )
    def test_action_truncation(self, action_length: int, expect_truncation: bool) -> None:
        """Actions over 60 chars are truncated with ellipsis."""
        action = "x" * action_length
        action_display = action[:60] + "..." if len(action) > 60 else action
        if expect_truncation:
            assert len(action_display) == 63  # 60 chars + "..."
            assert action_display.endswith("...")
        else:
            assert action_display == action
            assert "..." not in action_display

    def test_confidence_formatting(self) -> None:
        """Confidence value formatted to 2 decimal places."""
        confidence = 0.875
        formatted = f"(confidence: {confidence:.2f})"
        assert formatted == "(confidence: 0.88)"

    def test_iteration_progress_format(self) -> None:
        """Iteration progress shows [current/max] format."""
        current = 5
        max_iter = 50
        progress = f"[{current}/{max_iter}]"
        assert progress == "[5/50]"


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
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "-n", "20", "--dry-run"]):
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

    def test_list_no_loops_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """list with missing .loops/ directory handles gracefully."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()

        # Should handle missing .loops/ gracefully
        assert result == 0

    def test_list_running_shows_status_info(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running shows running loops with status info."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create state files
        (running_dir / "loop-a.state.json").write_text(
            json.dumps(
                {
                    "loop_name": "loop-a",
                    "current_state": "check-errors",
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
        (running_dir / "loop-b.state.json").write_text(
            json.dumps(
                {
                    "loop_name": "loop-b",
                    "current_state": "fix-types",
                    "iteration": 1,
                    "captured": {},
                    "prev_result": None,
                    "last_result": None,
                    "started_at": "2026-01-15T10:00:00Z",
                    "updated_at": "2026-01-15T10:00:30Z",
                    "status": "running",
                }
            )
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "Running loops:" in captured.out
        assert "loop-a" in captured.out
        assert "check-errors" in captured.out
        assert "iteration 3" in captured.out
        assert "loop-b" in captured.out
        assert "fix-types" in captured.out
        assert "iteration 1" in captured.out

    def test_list_running_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running with no running loops shows appropriate message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()
        # Empty .running directory - no state files

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list", "--running"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "No running loops" in captured.out

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
        with patch.object(sys, "argv", ["ll-loop", "compile", str(tmp_path / "nonexistent.yaml")]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_unknown_command_shows_help(self) -> None:
        """No command shows help and returns error."""
        with patch.object(sys, "argv", ["ll-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_run_quiet_flag_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--quiet", "--dry-run"]):
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

    def test_resume_continues_running_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Resume should continue from saved running state to completion."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        running_dir = loops_dir / ".running"
        running_dir.mkdir()

        # Create loop definition with multiple states
        loop_content = """
name: test-loop
initial: step1
max_iterations: 5
states:
  step1:
    action: "echo step1"
    evaluate:
      type: exit_code
    on_success: step2
    on_failure: step1
  step2:
    action: "echo step2"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: step2
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        # Create state file showing loop paused at step2 (not initial)
        state_file = running_dir / "test-loop.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "test-loop",
                    "current_state": "step2",
                    "iteration": 2,
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo step2"],
                returncode=0,
                stdout="step2",
                stderr="",
            )

            with patch.object(sys, "argv", ["ll-loop", "resume", "test-loop"]):
                from little_loops.cli import main_loop

                result = main_loop()

        # Verify successful completion
        assert result == 0
        captured = capsys.readouterr()
        assert "Resumed and completed: done" in captured.out

        # Verify loop_resume event was emitted
        events_file = running_dir / "test-loop.events.jsonl"
        assert events_file.exists()

        with open(events_file) as f:
            events = [json.loads(line) for line in f if line.strip()]

        event_types = [e["event"] for e in events]
        assert "loop_resume" in event_types

        # Verify resume started from step2
        resume_event = next(e for e in events if e["event"] == "loop_resume")
        assert resume_event["from_state"] == "step2"
        assert resume_event["iteration"] == 2


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


class TestErrorMessages:
    """Tests that verify error message content, not just return codes."""

    def test_missing_loop_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Missing loop shows helpful error message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""  # Error message is not empty
        assert "nonexistent" in captured.err  # Mentions the loop name
        assert "not found" in captured.err.lower()  # Helpful error indication

    def test_validation_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Validation error shows what's wrong."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "invalid.yaml").write_text(
            """
name: invalid
initial: nonexistent
states:
  start:
    action: "echo test"
    terminal: true
"""
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "validate", "invalid"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "validation" in captured.err.lower() or "invalid" in captured.err.lower()
        assert "nonexistent" in captured.err  # Mentions the invalid state

    def test_yaml_parse_error_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Invalid YAML shows parsing error."""
        # Use compile command which properly catches yaml.YAMLError
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("invalid: yaml: content: [broken")

        with patch.object(sys, "argv", ["ll-loop", "compile", str(bad_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "yaml" in captured.err.lower() or "parse" in captured.err.lower()

    def test_compile_missing_input_error_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Compile with missing file shows helpful error."""
        missing_path = tmp_path / "nonexistent.yaml"
        with patch.object(sys, "argv", ["ll-loop", "compile", str(missing_path)]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "not found" in captured.err.lower()
        assert str(missing_path) in captured.err or "nonexistent" in captured.err

    def test_status_no_state_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Status with no state shows helpful message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""
        assert "test-loop" in captured.err  # Mentions loop name
        assert "not found" in captured.err.lower() or "no state" in captured.err.lower()

    def test_resume_no_state_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Resume with no state shows helpful message."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text(
            """
name: test
initial: start
states:
  start:
    action: "echo test"
    terminal: true
"""
        )

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "resume", "test"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        # Note: resume with nothing uses logger.warning() which goes to stdout
        combined = captured.out + captured.err
        assert "test" in combined  # Mentions loop name
        assert "nothing" in combined.lower() or "resume" in combined.lower()

    def test_error_messages_go_to_stderr(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error messages go to stderr, not stdout."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        captured = capsys.readouterr()
        assert result == 1
        assert captured.err != ""  # Error in stderr

    def test_error_messages_not_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error conditions produce non-empty error output."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        error_scenarios = [
            (["ll-loop", "run", "missing"], "missing loop"),
            (["ll-loop", "validate", "missing"], "missing loop validation"),
            (["ll-loop", "status", "missing"], "missing status"),
        ]

        for argv, scenario in error_scenarios:
            monkeypatch.chdir(tmp_path)
            with patch.object(sys, "argv", argv):
                from little_loops.cli import main_loop

                result = main_loop()

            captured = capsys.readouterr()
            assert result == 1, f"Expected error for {scenario}"
            combined = captured.out + captured.err
            assert combined.strip() != "", f"Empty output for {scenario}"


class TestCompileEndToEnd:
    """End-to-end tests for paradigm compilation without mocking."""

    def test_compile_goal_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Goal paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: goal
goal: "No errors"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "goal.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "goal.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        assert output_file.exists()

        # Verify output structure
        fsm_data = yaml.safe_load(output_file.read_text())
        assert "states" in fsm_data
        assert "initial" in fsm_data
        assert fsm_data["initial"] == "evaluate"
        assert "evaluate" in fsm_data["states"]
        assert "fix" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_convergence_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Convergence paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: convergence
name: "reduce-errors"
check: "echo 5"
toward: 0
using: "echo fix"
"""
        input_file = tmp_path / "convergence.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "convergence.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "measure"
        assert "measure" in fsm_data["states"]
        assert "apply" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_invariants_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Invariants paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: invariants
name: "quality-checks"
constraints:
  - name: "tests"
    check: "echo test"
    fix: "echo fix-tests"
  - name: "lint"
    check: "echo lint"
    fix: "echo fix-lint"
"""
        input_file = tmp_path / "invariants.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "invariants.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "check_tests"
        assert "check_tests" in fsm_data["states"]
        assert "fix_tests" in fsm_data["states"]
        assert "check_lint" in fsm_data["states"]
        assert "fix_lint" in fsm_data["states"]
        assert "all_valid" in fsm_data["states"]

    def test_compile_imperative_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Imperative paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: imperative
name: "fix-cycle"
steps:
  - "echo step1"
  - "echo step2"
until:
  check: "echo done"
"""
        input_file = tmp_path / "imperative.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "imperative.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "step_0"
        assert "step_0" in fsm_data["states"]
        assert "step_1" in fsm_data["states"]
        assert "check_done" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compiled_output_passes_validation(self, tmp_path: Path) -> None:
        """Compiled FSM passes validate_fsm() check."""
        paradigm_yaml = """
paradigm: goal
goal: "Test validation"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "validate-test.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "validate-test.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        # Load and validate the FSM
        from little_loops.fsm.schema import FSMLoop
        from little_loops.fsm.validation import validate_fsm

        fsm_data = yaml.safe_load(output_file.read_text())
        fsm = FSMLoop.from_dict(fsm_data)
        errors = validate_fsm(fsm)

        # No error-level validation issues
        assert not any(e.severity.value == "error" for e in errors)

    def test_compile_unknown_paradigm_returns_error(self, tmp_path: Path) -> None:
        """Unknown paradigm type returns error."""
        paradigm_yaml = """
paradigm: nonexistent-type
name: "test"
"""
        input_file = tmp_path / "unknown.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_compile_goal_missing_required_field_returns_error(self, tmp_path: Path) -> None:
        """Goal paradigm missing 'goal' field returns error."""
        paradigm_yaml = """
paradigm: goal
tools:
  - "echo check"
"""
        input_file = tmp_path / "incomplete.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_compile_default_output_path(self, tmp_path: Path) -> None:
        """Without -o flag, output uses input filename with .fsm.yaml extension."""
        paradigm_yaml = """
paradigm: goal
goal: "Test"
tools:
  - "echo check"
"""
        input_file = tmp_path / "my-paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        # Default output replaces .yaml with .fsm.yaml
        default_output = tmp_path / "my-paradigm.fsm.yaml"
        assert default_output.exists()


class TestEndToEndExecution:
    """Tests for actual loop execution through PersistentExecutor.run().

    These tests verify the core execution path that --dry-run mode skips:
    - PersistentExecutor.run() is called and executes the loop
    - Correct exit codes are returned (0 for terminal, 1 for non-terminal)
    - State and events files are created during execution
    - Completion messages display correct final state and iteration count

    All tests mock subprocess.run() at the executor level to avoid actual
    shell execution while still exercising the full execution path.

    Note: These tests verify event generation via the events file rather than
    display output, as the display callback mechanism requires separate testing.
    """

    def test_executes_loop_to_terminal_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop executes to terminal state and returns 0."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-exec
initial: check
max_iterations: 3
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-exec.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-exec"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        assert mock_run.called

        captured = capsys.readouterr()
        # Verify loop header displayed
        assert "Running loop: test-exec" in captured.out
        assert "Max iterations: 3" in captured.out
        # Verify completion message shows correct final state
        assert "Loop completed: done" in captured.out
        assert "1 iterations" in captured.out

    def test_exits_on_max_iterations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop exits with code 1 when max_iterations reached."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-max
initial: check
max_iterations: 2
states:
  check:
    action: "echo fail"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-max.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            # Always return failure so loop keeps iterating
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo fail"],
                returncode=1,
                stdout="",
                stderr="error",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-max"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 1  # Non-terminal exit
        assert mock_run.call_count == 2  # Ran exactly max_iterations times

        captured = capsys.readouterr()
        # Verify loop header and completion message
        assert "Running loop: test-max" in captured.out
        assert "Max iterations: 2" in captured.out
        # Final state is check (not done) because max_iterations reached
        assert "Loop completed: check" in captured.out
        assert "2 iterations" in captured.out

    def test_reports_final_state_on_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop reports correct final state when action fails."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-fail
initial: check
max_iterations: 1
states:
  check:
    action: "echo fail"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-fail.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo fail"],
                returncode=1,
                stdout="",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-fail"]):
                from little_loops.cli import main_loop

                main_loop()

        captured = capsys.readouterr()
        # Verify completion message - final state is check (stayed there after failure)
        assert "Loop completed: check" in captured.out
        assert "1 iterations" in captured.out

    def test_successful_route_to_terminal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop with multiple states routes successfully to terminal."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-route
initial: check
max_iterations: 3
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: retry
  retry:
    action: "echo retry"
    next: check
  done:
    terminal: true
"""
        (loops_dir / "test-route.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-route"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Verify successful completion
        assert "Loop completed: done" in captured.out
        assert "1 iterations" in captured.out

    def test_quiet_mode_suppresses_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet flag suppresses progress display."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-quiet
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-quiet.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        # Note: Won't actually call subprocess.run for terminal-only loop
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Output should be minimal/empty in quiet mode
            assert "Running loop" not in captured.out
            assert "Loop completed" not in captured.out

    def test_quiet_mode_suppresses_logo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet flag suppresses logo display."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-quiet-logo
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-quiet-logo.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet-logo", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Logo should not be displayed in quiet mode
            assert "little loops" not in captured.out

    def test_background_flag_shows_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--background flag shows warning that it's not implemented."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-background
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-background.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-background", "--background"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Warning should appear about background mode
            assert "Background mode not yet implemented" in captured.out
            assert "running in foreground" in captured.out

    def test_creates_state_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Execution creates state and events files."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-state
initial: check
max_iterations: 2
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-state.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-state"]):
                from little_loops.cli import main_loop

                main_loop()

        # Verify state files created
        running_dir = loops_dir / ".running"
        assert running_dir.exists()
        state_file = running_dir / "test-state.state.json"
        assert state_file.exists()
        events_file = running_dir / "test-state.events.jsonl"
        assert events_file.exists()

        # Verify events file has content
        with open(events_file) as f:
            events = [json.loads(line) for line in f if line.strip()]
        event_types = [e["event"] for e in events]
        # Verify all expected event types were emitted
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "action_start" in event_types
        assert "action_complete" in event_types
        assert "evaluate" in event_types
        assert "route" in event_types
        assert "loop_complete" in event_types


class TestLLMFlags:
    """Tests for --no-llm and --llm-model CLI flags.

    These tests verify that the LLM-related CLI flags are correctly parsed
    and their values are properly passed through to the FSM configuration.
    """

    def test_no_llm_flag_accepted_with_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm flag is accepted by the CLI with --dry-run."""
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
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm", "--dry-run"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_llm_model_flag_accepted_with_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model flag is accepted by the CLI with --dry-run."""
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
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514", "--dry-run"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_no_llm_and_llm_model_combined(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both --no-llm and --llm-model flags can be used together."""
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
        with patch.object(
            sys,
            "argv",
            [
                "ll-loop",
                "run",
                "test-loop",
                "--no-llm",
                "--llm-model",
                "claude-opus-4-20250514",
                "--dry-run",
            ],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_no_llm_sets_fsm_llm_enabled_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm sets fsm.llm.enabled to False before execution."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            # Call original init
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.enabled is False

    def test_llm_model_sets_fsm_llm_model(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model sets fsm.llm.model to the specified value."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514"],
                ):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.model == "claude-opus-4-20250514"

    def test_llm_model_overrides_default_model(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model overrides the default model value."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Loop with custom llm config that will be overridden
        loop_content = """
name: test-loop
initial: check
llm:
  model: "claude-sonnet-4-20250514"
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514"],
                ):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        # CLI flag should override the YAML-specified model
        assert captured_fsm.llm.model == "claude-opus-4-20250514"

    def test_no_llm_preserves_other_llm_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm only changes enabled, preserving other LLM settings."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
llm:
  model: "claude-opus-4-20250514"
  max_tokens: 512
  timeout: 60
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.enabled is False
        # Other settings should be preserved from YAML
        assert captured_fsm.llm.model == "claude-opus-4-20250514"
        assert captured_fsm.llm.max_tokens == 512
        assert captured_fsm.llm.timeout == 60


class TestCmdTest:
    """Tests for ll-loop test subcommand."""

    def test_test_nonexistent_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with non-existent loop shows error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "not found" in captured.err.lower()

    def test_test_shell_action_success(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with successful shell command shows success verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-echo
goal: echo works
tools:
  - "echo hello"
  - "echo fixed"
max_iterations: 5
"""
        (loops_dir / "test-echo.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-echo"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
        assert "evaluate → done" in captured.out or "evaluate" in captured.out
        assert "configured correctly" in captured.out

    def test_test_shell_action_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with failing shell command shows failure verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-fail
goal: exit with error
tools:
  - "exit 1"
  - "echo fixed"
max_iterations: 5
"""
        (loops_dir / "test-fail.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-fail"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0  # Test succeeds even if loop would fail
        captured = capsys.readouterr()
        assert "FAILURE" in captured.out
        assert "evaluate → fix" in captured.out or "fix" in captured.out
        assert "configured correctly" in captured.out

    def test_test_slash_command_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with slash command action is skipped."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-slash
goal: slash command works
tools:
  - "/ll:check_code"
  - "/ll:check_code fix"
max_iterations: 5
"""
        (loops_dir / "test-slash.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-slash"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0  # Should succeed but skip execution
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.out
        assert "slash command" in captured.out.lower()
        assert "valid" in captured.out

    def test_test_parse_error_in_evaluator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with evaluator that can't parse output shows error verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
name: test-parse-error
initial: check
states:
  check:
    action: "echo 'not a number'"
    evaluate:
      type: output_numeric
      operator: eq
      target: 0
    on_success: done
    on_failure: fix
    on_error: done
  fix:
    action: "echo fixing"
    next: check
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-parse-error.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-parse-error"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1  # Test fails due to evaluator error
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "output_numeric" in captured.out
        assert "issues" in captured.out.lower()

    def test_test_no_action_initial_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with initial state having no action shows no action to test."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
name: test-no-action
initial: start
states:
  start:
    next: done
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-no-action.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-no-action"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "no action" in captured.out.lower()
        assert "valid" in captured.out.lower()

    def test_test_subcommand_registered(self) -> None:
        """Test subcommand is registered in known_subcommands."""
        # This verifies the subcommand won't be treated as a loop name
        import sys as _sys
        from unittest.mock import patch as mock_patch

        with mock_patch.object(_sys, "argv", ["ll-loop", "test", "--help"]):
            # If test is not a known subcommand, it would be parsed as a loop name
            # and "run" would be inserted, causing different behavior
            from little_loops.cli import main_loop

            # Should not raise SystemExit for unrecognized subcommand
            # (--help will cause SystemExit 0, which is expected)
            try:
                main_loop()
            except SystemExit as e:
                # --help causes exit 0
                assert e.code == 0
