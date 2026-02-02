"""Tests for ll-loop CLI command."""

from __future__ import annotations

import json
import subprocess
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
