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
        assert "On handoff: pause" in out
        assert "[check]" in out
        assert "[done]" in out
        assert "ll-loop run my-loop" in out

    def test_show_displays_on_handoff(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Show command displays on_handoff value when set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "spawn-loop.yaml").write_text(
            "name: spawn-loop\n"
            "initial: check\n"
            "on_handoff: spawn\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "    on_failure: check\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "spawn-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "On handoff: spawn" in out

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

    def test_show_prompt_action_shows_3_lines(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Prompt action type shows first 3 lines + ... not the full text."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_prompt = "\n".join(f"Line {i}: " + "x" * 50 for i in range(10))
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            + "\n".join(f"      {line}" for line in long_prompt.splitlines())
            + "\n"
            "    action_type: prompt\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "..." in out
        assert "Line 0" in out
        assert "Line 9" not in out

    def test_show_shell_action_truncated_at_70(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Shell action still truncates at 70 chars."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_shell = "echo " + "x" * 100
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: run\n"
            "states:\n"
            "  run:\n"
            f'    action: "{long_shell}"\n'
            "    action_type: shell\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "..." in out
        assert long_shell not in out

    def test_show_verbose_shows_full_action(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose flag shows full action text."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        full_prompt = "\n".join(f"Line {i}: " + "detail " * 10 for i in range(5))
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            + "\n".join(f"      {line}" for line in full_prompt.splitlines())
            + "\n"
            "    action_type: prompt\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Line 0" in out
        assert "Line 4" in out

    def test_show_verbose_shows_evaluate_prompt(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose flag shows evaluate.prompt."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm\n"
            "      prompt: Did the command succeed? Answer yes or no.\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "prompt:" in out
        assert "Did the command succeed" in out

    def test_show_evaluate_prompt_preview(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-verbose show displays truncated evaluate prompt preview."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "      prompt: |\n"
            "        Examine the output carefully.\n"
            "        Second line detail.\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "evaluate: llm_structured" in out
        assert "prompt: Examine the output carefully." in out
        assert " ..." in out  # truncated because multiple lines
        assert "Second line detail" not in out

    def test_show_evaluate_prompt_truncated_at_100_chars(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate prompt preview truncates long single lines at 100 chars."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_prompt = "x" * 120
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            f"      prompt: {long_prompt}\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert " ..." in out
        assert long_prompt not in out

    def test_show_evaluate_min_confidence_non_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Non-default min_confidence is shown in evaluate block."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "      min_confidence: 0.8\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "min_confidence: 0.8" in out

    def test_show_evaluate_min_confidence_default_hidden(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Default min_confidence (0.5) is not shown."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: llm_structured\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "min_confidence" not in out

    def test_show_evaluate_operator_and_target(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """operator and target shown for numeric evaluators."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo 5"\n'
            "    evaluate:\n"
            "      type: output_numeric\n"
            "      operator: gt\n"
            "      target: 3\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "operator: gt 3" in out

    def test_show_evaluate_pattern(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """pattern shown for output_contains evaluator."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    evaluate:\n"
            "      type: output_contains\n"
            "      pattern: ERROR\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "pattern: ERROR" in out

    def test_show_state_capture_timeout_on_maintain(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """State-level capture, timeout, and on_maintain are displayed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    capture: result\n"
            "    timeout: 60\n"
            "    on_maintain: check\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "capture: result" in out
        assert "timeout: 60s" in out
        assert "on_maintain \u2500\u2500\u2192 check" in out

    def test_show_state_optional_fields_absent_when_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """capture, timeout, on_maintain not shown when not configured."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "capture:" not in out
        assert "timeout:" not in out
        assert "on_maintain" not in out

    def test_show_llm_config_block_non_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """LLM config block shown when non-default values are set."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "llm:\n"
            "  model: opus\n"
            "  max_tokens: 512\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "LLM config:" in out
        assert "model=opus" in out
        assert "max_tokens=512" in out

    def test_show_llm_config_block_hidden_when_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """LLM config block not shown when all values are default."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "LLM config" not in out

    def test_show_verbose_multiline_action_all_lines_indented(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose: all continuation lines of a multiline action are indented."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: fix\n"
            "states:\n"
            "  fix:\n"
            "    action: |\n"
            "      First line of action.\n"
            "      Second line of action.\n"
            "      Third line of action.\n"
            "    action_type: prompt\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        # Collect lines that are part of the action block (6-space indented content)
        action_content_lines = []
        in_action = False
        for line in out.splitlines():
            if "action: |" in line:
                in_action = True
                continue
            if in_action:
                if line.startswith("      "):  # 6-space indent = action content
                    action_content_lines.append(line)
                else:
                    break
        assert len(action_content_lines) == 3, (
            f"Expected 3 action content lines, got {len(action_content_lines)}: {action_content_lines}"
        )
        for line in action_content_lines:
            assert line.startswith("      "), f"Action line not indented: {line!r}"

    def test_show_diagram_appears_before_states(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Diagram section appears before States section in output."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        diagram_pos = out.find("Diagram:")
        states_pos = out.find("States:")
        assert diagram_pos != -1
        assert states_pos != -1
        assert diagram_pos < states_pos, "Diagram: must appear before States:"

    def test_show_state_header_includes_type_badge(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """State header includes (action_type) badge; standalone type: line is absent."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: run\n"
            "states:\n"
            "  run:\n"
            '    action: "echo hello"\n'
            "    action_type: shell\n"
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        # The state header for an initial state shows "[run] [INITIAL] (shell)"
        assert "(shell)" in out
        assert "    type: shell" not in out

    def test_show_commands_section_lists_all_subcommands(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Commands section lists run, test, status, and history subcommands."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "ll-loop run my-loop" in out
        assert "ll-loop test my-loop" in out
        assert "ll-loop status my-loop" in out
        assert "ll-loop history my-loop" in out
