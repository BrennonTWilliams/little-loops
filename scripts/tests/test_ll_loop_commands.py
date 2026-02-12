"""Tests for ll-loop CLI command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import yaml

if TYPE_CHECKING:
    pass


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

        with open(valid_loop_file) as f:
            data = yaml.safe_load(f)

        assert "name" in data
        assert "initial" in data
        assert "states" in data
        assert data["initial"] in data["states"]

    def test_invalid_loop_structure(self, invalid_loop_file: Path) -> None:
        """Invalid loop file has missing initial state."""

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


class TestCmdShow:
    """Tests for show command."""

    @pytest.fixture
    def valid_loop_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory with a valid loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "    on_failure: check\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_show_displays_metadata(
        self,
        valid_loop_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays loop metadata."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Loop: my-loop" in out
        assert "[check]" in out
        assert "[done]" in out
        assert "ll-loop run my-loop" in out

    def test_show_displays_diagram(
        self,
        valid_loop_dir: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays FSM diagram."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Diagram:" in out
        assert "[check]" in out
        assert "[done]" in out

    def test_show_nonexistent_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Show command returns error for missing loop."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
