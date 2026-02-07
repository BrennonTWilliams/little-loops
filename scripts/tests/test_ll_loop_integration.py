"""Tests for ll-loop CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

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
        """list with empty .loops/ directory shows built-in loops only."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Built-in loops are shown when no project loops exist
        if "[built-in]" in captured.out:
            assert "Available loops:" in captured.out
        else:
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
