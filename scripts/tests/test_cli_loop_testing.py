"""Tests for cmd_simulate scenario-based simulation.

Fills the gap left by TestCmdSimulateCircuit in test_ll_loop_commands.py
which only tests RateLimitCircuit forwarding — not scenario modes or
max-iterations behavior.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from little_loops.cli.loop.testing import cmd_simulate, cmd_test
from little_loops.logger import Logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_loop(loops_dir: Path, name: str = "test-loop") -> Path:
    """Create a minimal 2-state loop for simulation testing."""
    loop_file = loops_dir / f"{name}.yaml"
    loop_file.write_text(
        f"""name: {name}
initial: start
max_iterations: 5
states:
  start:
    action: echo "hello"
    on_yes: done
  done:
    terminal: true
"""
    )
    return loop_file


def _make_multi_state_loop(loops_dir: Path) -> Path:
    """Create a 3-state loop with yes/no routing for scenario testing."""
    loop_file = loops_dir / "multi.yaml"
    loop_file.write_text("""name: multi
initial: step1
max_iterations: 10
states:
  step1:
    action: echo "step1"
    on_yes: step2
    on_no: done
  step2:
    action: echo "step2"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
    return loop_file


def _make_args(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with defaults for cmd_simulate."""
    defaults: dict = {
        "max_iterations": None,
        "scenario": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# cmd_simulate — Scenario Tests
# ---------------------------------------------------------------------------


class TestCmdSimulateScenarios:
    """Tests for cmd_simulate --scenario flag behavior."""

    def test_all_pass_scenario_completes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--scenario all-pass makes all exit codes 0, reaching terminal state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_minimal_loop(loops_dir)

        args = _make_args(scenario="all-pass")
        logger = Logger()

        result = cmd_simulate("test-loop", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION" in captured.out
        assert "done" in captured.out  # reached terminal state
        assert "Terminated by: terminal" in captured.out

    def test_all_fail_scenario(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--scenario all-fail makes all exit codes 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_multi_state_loop(loops_dir)

        args = _make_args(scenario="all-fail")
        logger = Logger()

        result = cmd_simulate("multi", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        # With all-fail, step1's on_no → done should trigger
        assert "done" in captured.out

    def test_all_error_scenario(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--scenario all-error makes all exit codes 2."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_minimal_loop(loops_dir)

        args = _make_args(scenario="all-error")
        logger = Logger()

        result = cmd_simulate("test-loop", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION" in captured.out

    def test_first_fail_scenario(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--scenario first-fail makes first exit code 1, rest 0."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_multi_state_loop(loops_dir)

        args = _make_args(scenario="first-fail")
        logger = Logger()

        result = cmd_simulate("multi", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION" in captured.out

    def test_alternating_scenario(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--scenario alternating toggles between 0 and 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_multi_state_loop(loops_dir)

        args = _make_args(scenario="alternating")
        logger = Logger()

        result = cmd_simulate("multi", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION" in captured.out

    def test_no_scenario_uses_interactive_mode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without --scenario, mode string shows 'interactive'."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_minimal_loop(loops_dir)

        args = _make_args(scenario=None)
        logger = Logger()

        result = cmd_simulate("test-loop", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "interactive" in captured.out

    def test_simulation_shows_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Simulation output includes a summary section."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_minimal_loop(loops_dir)

        args = _make_args(scenario="all-pass")
        logger = Logger()

        result = cmd_simulate("test-loop", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "Summary" in captured.out
        assert "States visited:" in captured.out
        assert "Iterations:" in captured.out
        assert "Would have executed" in captured.out
        assert "Terminated by:" in captured.out


class TestCmdSimulateMaxIterations:
    """Tests for --max-iterations flag in cmd_simulate."""

    def test_max_iterations_applied(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--max-iterations overrides the FSM's max_iterations."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        _make_minimal_loop(loops_dir)

        args = _make_args(max_iterations=3, scenario="all-pass")
        logger = Logger()

        result = cmd_simulate("test-loop", args, loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        # Should complete within the specified max_iterations
        assert "Terminated by:" in captured.out


class TestCmdSimulateErrors:
    """Tests for cmd_simulate error handling."""

    def test_nonexistent_loop_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Simulating a nonexistent loop returns exit code 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = _make_args()
        logger = Logger()

        result = cmd_simulate("nonexistent", args, loops_dir, logger)
        assert result == 1

    def test_invalid_yaml_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invalid loop YAML (missing required fields) returns exit code 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Valid YAML but missing required FSM fields (no states, no initial)
        (loops_dir / "bad.yaml").write_text("name: incomplete")

        args = _make_args()
        logger = Logger()

        result = cmd_simulate("bad", args, loops_dir, logger)
        assert result == 1


# ---------------------------------------------------------------------------
# cmd_test — Additional Coverage
# ---------------------------------------------------------------------------


class TestCmdTestAdditional:
    """Additional tests for cmd_test beyond what TestCmdTest covers."""

    def test_state_with_no_action_reports_valid(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A state with no action reports as valid structure."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "noop.yaml").write_text("""name: noop
initial: idle
states:
  idle:
    terminal: true
""")

        args = argparse.Namespace(state=None, exit_code=None)
        logger = Logger()

        result = cmd_test("noop", args, loops_dir, logger)
        assert result == 0
        captured = capsys.readouterr()
        assert "has no action to test" in captured.out

    def test_file_not_found_returns_1(self, tmp_path: Path) -> None:
        """Non-existent loop returns exit code 1."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(state=None, exit_code=None)
        logger = Logger()

        result = cmd_test("nonexistent", args, loops_dir, logger)
        assert result == 1
