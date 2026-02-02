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
