"""Tests for ll-loop CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from tests.helpers import make_test_fsm, make_test_state

if TYPE_CHECKING:
    pass


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
    on_yes: done
    on_no: done
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
    on_yes: done
    on_no: done
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
        # Built-in loops are shown when no project loops exist, grouped by category
        if "[built-in]" in captured.out:
            assert any(kw in captured.out for kw in ["(", "uncategorized", "No loops"])
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
        runnable_tail = "\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        (loops_dir / "loop-a.yaml").write_text("name: a" + runnable_tail)
        (loops_dir / "loop-b.yaml").write_text("name: b" + runnable_tail)
        (loops_dir / "loop-c.yaml").write_text("name: c" + runnable_tail)

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

    def test_list_running_reconciles_dead_pid_entries(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running flips stale running entries to interrupted and excludes them from output.

        BUG-1731: list --running must apply the same dead-PID reconciliation as
        ll-loop status, so both commands report identical state counts.
        """
        loops_dir = tmp_path / ".loops"
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True)

        # Live loop: has a real (current) PID
        live_state = {
            "loop_name": "live-loop",
            "current_state": "work",
            "iteration": 1,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T10:00:00Z",
            "updated_at": "2026-01-15T10:01:00Z",
            "status": "running",
            "pid": 11111,
        }
        (running_dir / "live-loop.state.json").write_text(json.dumps(live_state))

        # Stale loop: status=running but PID is dead
        stale_state = {
            "loop_name": "stale-loop",
            "current_state": "check",
            "iteration": 7,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2026-01-15T09:00:00Z",
            "updated_at": "2026-01-15T09:30:00Z",
            "status": "running",
            "pid": 99999,
        }
        stale_file = running_dir / "stale-loop.state.json"
        stale_file.write_text(json.dumps(stale_state))

        monkeypatch.chdir(tmp_path)

        def _mock_alive(pid: int) -> bool:
            return pid == 11111

        with (
            patch("little_loops.fsm.persistence._process_alive", side_effect=_mock_alive),
            patch.object(sys, "argv", ["ll-loop", "list", "--running"]),
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # Stale loop on-disk file must have been rewritten to interrupted
        written = json.loads(stale_file.read_text())
        assert written["status"] == "interrupted", "Stale entry must be reconciled to interrupted"
        assert "reconciled_at" in written

        # live-loop still running; stale-loop reconciled to [paused] (interrupted), not [running]
        assert "live-loop" in captured.out
        assert "[running]" in captured.out  # live-loop is still shown as running
        assert "stale-loop" in captured.out  # stale entry still shown but reconciled
        # Stale entry must appear as [paused] (the display label for interrupted), not [running]
        out_lines = captured.out.splitlines()
        stale_line = next((ln for ln in out_lines if "stale-loop" in ln), None)
        assert stale_line is not None
        assert "[paused]" in stale_line, (
            f"Expected [paused] for reconciled stale entry, got: {stale_line}"
        )
        assert "[running]" not in stale_line

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

    def test_diagnose_evaluators_no_history(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """diagnose-evaluators with no history prints no-history message."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".loops").mkdir()
        with patch.object(sys, "argv", ["ll-loop", "diagnose-evaluators", "no-such-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "No history" in captured.out

    def test_promote_baseline_no_runs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """promote-baseline with no history exits 1 with informative message."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".loops").mkdir()
        with patch.object(sys, "argv", ["ll-loop", "promote-baseline", "no-such-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        assert "No history" in captured.out
