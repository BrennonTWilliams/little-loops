"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
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

    def test_validate_with_unreachable_state_prints_warning(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop with unreachable state is valid but prints ⚠ warning to stdout."""
        from little_loops.cli.loop.config_cmds import cmd_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text(
            "name: test-loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: test\n"
            "    on_success: done\n"
            "    on_failure: done\n"
            "  done:\n"
            "    terminal: true\n"
            "  orphan:\n"
            "    action: unreachable\n"
            "    next: done\n"
        )

        logger = Logger(use_color=False)
        result = cmd_validate("test-loop", loops_dir, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "⚠" in captured.out


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

    def test_list_shows_paradigm_and_description(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Available loops display paradigm type and description."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text(
            "name: my-loop\nparadigm: goal\ndescription: Ensure tests pass\n"
        )
        (loops_dir / "bare-loop.yaml").write_text("name: bare\n")

        args = argparse.Namespace(running=False, status=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "[goal]" in captured
        assert "Ensure tests pass" in captured
        assert "my-loop" in captured
        assert "bare-loop" in captured

    def test_running_shows_status_and_elapsed(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--running output includes state.status and elapsed time."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"
        state = LoopState(
            loop_name="my-loop",
            current_state="check_types",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:02:15",
            status="running",
            accumulated_ms=135_000,  # 2m 15s
        )

        args = argparse.Namespace(running=True, status=None)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "[running]" in captured
        assert "2m 15s" in captured
        assert "iteration 3" in captured

    def test_status_filter_matches(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--status filters running loops by status."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        loops_dir = tmp_path / ".loops"

        def make_state(name: str, s: str) -> LoopState:
            return LoopState(
                loop_name=name,
                current_state="check",
                iteration=1,
                captured={},
                prev_result=None,
                last_result=None,
                started_at="2026-01-01T00:00:00",
                updated_at="2026-01-01T00:00:01",
                status=s,
                accumulated_ms=5_000,
            )

        states = [make_state("loop-a", "interrupted"), make_state("loop-b", "running")]

        args = argparse.Namespace(running=False, status="interrupted")
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=states):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
        assert "loop-a" in captured
        assert "loop-b" not in captured

    def test_status_filter_no_match_returns_1(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--status returns exit code 1 when no loops match."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        args = argparse.Namespace(running=False, status="interrupted")
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[]):
            result = cmd_list(args, loops_dir)

        assert result == 1
        captured = capsys.readouterr().out
        assert "No loops with status: interrupted" in captured


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
        assert "from=state7" in captured.out
        assert "from=state8" in captured.out
        assert "from=state9" in captured.out
        # First events should NOT appear (use exact match to avoid state10 matching state1)
        assert "from=state0" not in captured.out
        assert "from=state1" not in captured.out
        assert "from=state5" not in captured.out

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
            assert f"from=state{i}" in captured.out

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
            assert f"from=state{i}" in captured.out

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
            assert f"from=state{i}" in captured.out

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
        assert "handoff: pause" in out
        assert "check" in out
        assert "done" in out
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
        assert "handoff: spawn" in out

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
        assert "check" in out
        assert "done" in out

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
        assert "evaluate: LLM (structured)" in out
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
        assert "maintain \u2500\u2500\u2192 check" in out

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
        assert "llm:" in out
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
            if line.rstrip() == "    action:":
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
        # The state header for an initial state shows "── run ── INITIAL · shell ──"
        assert "shell" in out
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


class TestCmdCompile:
    """Tests for cmd_compile round-trip serialization (BUG-601)."""

    def test_compile_preserves_llm_scope_on_handoff(self, tmp_path: Path) -> None:
        """Compiled .fsm.yaml retains llm, scope, and on_handoff fields (BUG-601)."""
        from little_loops.cli.loop.config_cmds import cmd_compile
        from little_loops.logger import Logger

        input_file = tmp_path / "my-loop.yaml"
        input_file.write_text(
            "name: my-loop\n"
            "initial: check\n"
            "on_handoff: spawn\n"
            "scope:\n"
            "  - src/\n"
            "llm:\n"
            "  model: claude-opus-4-6\n"
            "  max_tokens: 1024\n"
            "states:\n"
            "  check:\n"
            '    action: "echo hello"\n'
            "    on_success: done\n"
            "    on_failure: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        output_file = tmp_path / "my-loop.fsm.yaml"
        args = argparse.Namespace(input=str(input_file), output=str(output_file))
        logger = Logger(use_color=False)

        result = cmd_compile(args, logger)

        assert result == 0
        assert output_file.exists()
        with open(output_file) as f:
            compiled = yaml.safe_load(f)

        assert compiled.get("on_handoff") == "spawn", "on_handoff dropped during compilation"
        assert compiled.get("scope") == ["src/"], "scope dropped during compilation"
        assert "llm" in compiled, "llm block dropped during compilation"
        assert compiled["llm"].get("model") == "claude-opus-4-6"
        assert compiled["llm"].get("max_tokens") == 1024


class TestCmdTest:
    """Tests for cmd_test --state flag (FEAT-609)."""

    @pytest.fixture
    def multi_state_loop(self, tmp_path: Path) -> Path:
        """Create a multi-state loop with distinct states."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "multi-state.yaml"
        loop_file.write_text(
            "name: multi-state\n"
            "initial: check_types\n"
            "states:\n"
            "  check_types:\n"
            '    action: "echo checking types"\n'
            "    on_success: done\n"
            "    on_failure: fix_types\n"
            "  fix_types:\n"
            '    action: "echo fixing types"\n'
            "    on_success: done\n"
            "    on_failure: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_default_behavior_uses_initial_state(
        self,
        multi_state_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --state, cmd_test uses the initial state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state=None)
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "State: check_types" in captured.out

    def test_state_flag_tests_specified_state(
        self,
        multi_state_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--state <name> tests the specified state instead of the initial one."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="fix_types")
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "State: fix_types" in captured.out

    def test_invalid_state_returns_error(
        self,
        multi_state_loop: Path,
    ) -> None:
        """--state with a nonexistent state logs an error and returns 1."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="nonexistent_state")
        logger = Logger(use_color=False)
        result = cmd_test("multi-state", args, multi_state_loop, logger)

        assert result == 1

    @pytest.fixture
    def slash_command_loop(self, tmp_path: Path) -> Path:
        """Create a loop with a slash-command evaluate state."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "slash-loop.yaml"
        loop_file.write_text(
            "name: slash-loop\n"
            "initial: evaluate\n"
            "states:\n"
            "  evaluate:\n"
            '    action: "/ll:check-code"\n'
            "    on_success: done\n"
            "    on_failure: fix\n"
            "  fix:\n"
            '    action: "/ll:manage-issue bug fix"\n'
            "    on_success: done\n"
            "    on_failure: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_slash_command_with_exit_code_0_traces_success_route(
        self,
        slash_command_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exit-code 0 simulates success and traces transition to on_success state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="evaluate", exit_code=0)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATED" in captured.out
        assert "Exit code: 0" in captured.out
        assert "done" in captured.out  # routes to done on success

    def test_slash_command_with_exit_code_1_traces_failure_route(
        self,
        slash_command_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exit-code 1 simulates failure and traces transition to on_failure state."""
        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        args = argparse.Namespace(state="evaluate", exit_code=1)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATED" in captured.out
        assert "Exit code: 1" in captured.out
        assert "fix" in captured.out  # routes to fix on failure

    def test_slash_command_no_exit_code_uses_interactive_prompt(
        self,
        slash_command_loop: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --exit-code, slash-command state falls back to interactive prompt."""
        import io

        from little_loops.cli.loop.testing import cmd_test
        from little_loops.logger import Logger

        monkeypatch.setattr("sys.stdin", io.StringIO("1\n"))  # select Success (exit 0)
        args = argparse.Namespace(state="evaluate", exit_code=None)
        logger = Logger(use_color=False)
        result = cmd_test("slash-loop", args, slash_command_loop, logger)

        assert result == 0
        captured = capsys.readouterr()
        assert "Exit code: 0" in captured.out
        assert "done" in captured.out
