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
    on_yes: done
    on_no: done
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
            "    on_yes: done\n"
            "    on_no: done\n"
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

    def test_list_shows_description(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Available loops display description."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text("name: my-loop\ndescription: Ensure tests pass\n")
        (loops_dir / "bare-loop.yaml").write_text("name: bare\n")

        args = argparse.Namespace(running=False, status=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr().out
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

    def test_list_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a valid JSON array with name and path fields."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: loop-a\n")
        (loops_dir / "loop-b.yaml").write_text("name: loop-b\n")

        args = argparse.Namespace(running=False, status=None, json=True)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {item["name"] for item in data}
        assert names == {"loop-a", "loop-b"}
        for item in data:
            assert "name" in item
            assert "path" in item

    def test_list_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no loops outputs an empty JSON array."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(running=False, status=None, json=True)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_list_without_json_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output groups loops by category (uncategorized when none set)."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "my-loop.yaml").write_text("name: my-loop\n")

        args = argparse.Namespace(running=False, status=None, json=False)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "uncategorized" in out
        assert "my-loop" in out


class TestLoopListCategoryFilter:
    """Tests for --category and --label filtering in cmd_list."""

    def test_category_filter_shows_only_matching(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--category shows only loops in that category."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-apo.yaml").write_text("name: loop-apo\ncategory: apo\n")
        (loops_dir / "loop-meta.yaml").write_text("name: loop-meta\ncategory: meta\n")

        args = argparse.Namespace(running=False, status=None, json=False, category="apo", label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "loop-apo" in out
        assert "loop-meta" not in out

    def test_label_filter_shows_only_matching(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--label shows only loops with that label."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(
            "name: loop-a\ncategory: apo\nlabels:\n  - optimize\n  - prompt\n"
        )
        (loops_dir / "loop-b.yaml").write_text(
            "name: loop-b\ncategory: meta\nlabels:\n  - health\n"
        )

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=["optimize"])
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "loop-a" in out
        assert "loop-b" not in out

    def test_grouped_display_by_category(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without filters, loops are grouped by category with headers."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-apo.yaml").write_text("name: loop-apo\ncategory: apo\n")
        (loops_dir / "loop-meta.yaml").write_text("name: loop-meta\ncategory: meta\n")
        (loops_dir / "loop-bare.yaml").write_text("name: loop-bare\n")

        args = argparse.Namespace(running=False, status=None, json=False, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "apo" in out
        assert "meta" in out
        assert "uncategorized" in out
        assert "loop-apo" in out
        assert "loop-meta" in out
        assert "loop-bare" in out
        # apo and meta headers should appear before uncategorized
        assert out.index("apo") < out.index("uncategorized")
        assert out.index("meta") < out.index("uncategorized")

    def test_json_output_includes_category_and_labels(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """JSON output includes category and labels fields."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text(
            "name: loop-a\ncategory: apo\nlabels:\n  - optimize\n"
        )

        args = argparse.Namespace(running=False, status=None, json=True, category=None, label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["category"] == "apo"
        assert data[0]["labels"] == ["optimize"]

    def test_no_match_filter_returns_message(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Filters with no match print a message and return 0."""
        from little_loops.cli.loop.info import cmd_list

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: loop-a\ncategory: apo\n")

        args = argparse.Namespace(running=False, status=None, json=False, category="data", label=None)
        with patch(
            "little_loops.cli.loop.info.get_builtin_loops_dir",
            return_value=tmp_path / "nonexistent",
        ):
            result = cmd_list(args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "No loops match" in out


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
            {"event": "evaluate", "ts": "2026-01-13T10:00:03", "verdict": "yes"},
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
        assert events[-1]["verdict"] == "yes"

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
        """Create an archived events file with 10 events for tail testing."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

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
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3"]
        ):
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
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "0"]
        ):
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
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "100"]
        ):
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
        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id"]):
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
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3"]
        ):
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
        # Create empty archived events file
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events_file.write_text("")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "5"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        assert "No events found" in captured.out

    def test_history_tail_excludes_action_output_from_count(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """action_output events should not count toward --tail in non-verbose mode.

        Regression test for BUG-657: when a shell action produces many output lines,
        those action_output events should not consume the tail budget, hiding earlier
        iterations from the user.
        """
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        # Simulate 3 iterations, each with 1 visible event + 10 action_output events.
        # Total raw events: 3 * 11 = 33. With --tail 5 applied to raw events (old bug),
        # only the last 5 raw events (all action_output from iter 3) would be kept,
        # hiding iter 1 and iter 2. With the fix, tail applies to visible events only.
        events = []
        for i in range(1, 4):
            events.append(
                {
                    "event": "state_enter",
                    "ts": f"2026-01-15T10:00:{i:02d}",
                    "state": f"iter{i}",
                    "iteration": i,
                }
            )
            for j in range(10):
                events.append(
                    {
                        "event": "action_output",
                        "ts": f"2026-01-15T10:00:{i:02d}",
                        "line": f"output line {j}",
                    }
                )

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "5"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # All 3 iterations should be visible (3 visible events <= tail 5)
        assert "iter1" in captured.out
        assert "iter2" in captured.out
        assert "iter3" in captured.out
        # action_output lines should NOT appear in non-verbose mode
        assert "output line" not in captured.out

    def test_history_tail_verbose_counts_action_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """In verbose mode, action_output events count toward --tail as before."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        # 2 iterations: 1 state_enter + 3 action_output each = 8 raw events total
        events = []
        for i in range(1, 3):
            events.append(
                {
                    "event": "state_enter",
                    "ts": f"2026-01-15T10:00:{i:02d}",
                    "state": f"iter{i}",
                    "iteration": i,
                }
            )
            for j in range(3):
                events.append(
                    {
                        "event": "action_output",
                        "ts": f"2026-01-15T10:00:{i:02d}",
                        "line": f"line{i}-{j}",
                    }
                )

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        monkeypatch.chdir(tmp_path)
        # --tail 3 in verbose mode: only last 3 raw events (all action_output from iter2)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "history", "test-loop", "test-run-id", "--tail", "3", "--verbose"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()

        # iter1 should NOT appear (its events are beyond tail=3 in verbose/raw mode)
        assert "iter1" not in captured.out
        # action_output lines from iter2 should appear
        assert "line2-0" in captured.out
        assert "line2-1" in captured.out
        assert "line2-2" in captured.out

    def test_history_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs a valid JSON array of events."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events = [
            {"event": "loop_start", "ts": "2026-01-13T10:00:00", "loop": "test-loop"},
            {"event": "state_enter", "ts": "2026-01-13T10:00:01", "state": "check", "iteration": 1},
        ]
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        args = argparse.Namespace(tail=50, verbose=False, json=True)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["event"] == "loop_start"
        assert data[1]["event"] == "state_enter"

    def test_history_json_respects_tail(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with --tail N returns only the last N events."""
        from little_loops.cli.loop.info import cmd_history

        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events = [{"event": f"evt_{i}", "ts": f"2026-01-13T10:00:{i:02d}"} for i in range(5)]
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        args = argparse.Namespace(tail=2, verbose=False, json=True)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        assert data[0]["event"] == "evt_3"
        assert data[1]["event"] == "evt_4"

    def test_history_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no history outputs nothing (no history message, exit 0)."""
        from little_loops.cli.loop.info import cmd_history

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        args = argparse.Namespace(tail=50, verbose=False, json=True)
        result = cmd_history("nonexistent", None, args, loops_dir)

        assert result == 0
        out = capsys.readouterr().out
        assert "No history" in out


class TestHistoryVerboseLLM:
    """Tests for --verbose LLM call details rendering in ll-loop history."""

    def _write_events(self, tmp_path: Path, events: list[dict[str, Any]]) -> None:
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def test_verbose_evaluate_shows_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose shows LLM call block (model, latency, prompt, response) for evaluate events."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "confidence": 0.9,
                    "reason": "Looks good",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 1234,
                    "llm_prompt": "Evaluate this output",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" in out
        assert "1234ms" in out
        assert "Evaluate this output" in out
        assert '{"verdict":"yes"}' in out

    def test_non_verbose_evaluate_hides_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --verbose, LLM call details are not shown."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 1234,
                    "llm_prompt": "Evaluate this output",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" not in out
        assert "1234ms" not in out
        assert "Evaluate this output" not in out

    def test_verbose_action_complete_shows_output_preview(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--verbose shows output_preview for action_complete events."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "action_complete",
                    "ts": "2026-01-13T10:00:02",
                    "exit_code": 0,
                    "duration_ms": 500,
                    "output_preview": "All tests passed",
                    "is_prompt": False,
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "All tests passed" in out

    def test_non_verbose_action_complete_hides_output_preview(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --verbose, output_preview is not shown in action_complete."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "action_complete",
                    "ts": "2026-01-13T10:00:02",
                    "exit_code": 0,
                    "duration_ms": 500,
                    "output_preview": "All tests passed",
                    "is_prompt": False,
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "All tests passed" not in out

    def test_full_implies_verbose_and_shows_llm_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--full implies --verbose and shows LLM call details."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_latency_ms": 800,
                    "llm_prompt": "Evaluate this",
                    "llm_raw_output": '{"verdict":"yes"}',
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=False, full=True, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "claude-sonnet-4-6" in out
        assert "800ms" in out

    def test_evaluate_without_llm_fields_no_extra_block(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """evaluate events without llm_model/llm_prompt don't render LLM block."""
        from little_loops.cli.loop.info import cmd_history

        self._write_events(
            tmp_path,
            [
                {
                    "event": "evaluate",
                    "ts": "2026-01-13T10:00:03",
                    "verdict": "yes",
                    "confidence": 0.9,
                    "reason": "exit code 0",
                }
            ],
        )

        args = argparse.Namespace(tail=50, verbose=True, full=False, json=False)
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")
        assert result == 0

        out = capsys.readouterr().out
        assert "LLM Call" not in out
        assert "Prompt:" not in out


class TestCmdListRunningJson:
    """Tests for list --running --json."""

    def test_list_running_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running --json outputs a JSON array of running loop states."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:00:01",
            status="running",
        )

        args = argparse.Namespace(running=True, status=None, json=True)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["loop_name"] == "my-loop"
        assert data[0]["current_state"] == "run_tests"
        assert data[0]["iteration"] == 3

    def test_list_running_json_empty(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running --json with no running loops exits 0 with 'No running loops' message."""
        from little_loops.cli.loop.info import cmd_list

        args = argparse.Namespace(running=True, status=None, json=True)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "No running loops" in out

    def test_list_running_without_json_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """list --running without --json still outputs human-readable text."""
        from little_loops.cli.loop.info import cmd_list
        from little_loops.fsm.persistence import LoopState

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:00:01",
            status="running",
            accumulated_ms=42000,
        )

        args = argparse.Namespace(running=True, status=None, json=False)
        with patch("little_loops.fsm.persistence.list_running_loops", return_value=[state]):
            result = cmd_list(args, tmp_path / ".loops")

        assert result == 0
        out = capsys.readouterr().out
        assert "Running loops:" in out
        assert "my-loop" in out


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
            "    on_yes: done\n"
            "    on_no: check\n"
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
            "    on_yes: done\n"
            "    on_no: check\n"
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

    def test_show_states_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """States section is hidden when --verbose is not passed."""
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "States:" not in out
        assert "action:" not in out
        # Overview table and other sections still present
        assert "Diagram:" in out
        assert "Commands:" in out

    def test_show_shell_action_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Shell action is hidden when --verbose is not passed."""
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "States:" not in out
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
            "    on_yes: done\n"
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
            "    on_yes: done\n"
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

    def test_show_evaluate_hidden_without_verbose(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate section is hidden when --verbose is not passed."""
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert "evaluate:" not in out
        assert "Examine the output carefully" not in out

    def test_show_evaluate_prompt_truncated_at_100_chars(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate prompt is hidden without --verbose; shown fully with it."""
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        out = capsys.readouterr().out
        assert long_prompt not in out
        assert "States:" not in out

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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "show", "my-loop", "--verbose"]):
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
            "    on_yes: done\n"
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
            "    on_yes: done\n"
            "    on_no: fix_types\n"
            "  fix_types:\n"
            '    action: "echo fixing types"\n'
            "    on_yes: done\n"
            "    on_no: done\n"
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
            "    on_yes: done\n"
            "    on_no: fix\n"
            "  fix:\n"
            '    action: "/ll:manage-issue bug fix"\n'
            "    on_yes: done\n"
            "    on_no: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        return loops_dir

    def test_slash_command_with_exit_code_0_traces_success_route(
        self,
        slash_command_loop: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--exit-code 0 simulates yes verdict and traces transition to on_yes state."""
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
        """--exit-code 1 simulates no verdict and traces transition to on_no state."""
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


class TestCmdRunContextInjection:
    """Tests for cmd_run positional input injection into fsm.context."""

    @pytest.fixture
    def simple_loop(self, tmp_path: Path) -> Path:
        """Create a minimal loop that accepts a runtime input."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "input-loop.yaml"
        loop_file.write_text("""
name: input-loop
initial: init
context:
  input: null
states:
  init:
    action: "echo {{context.input}}"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loops_dir

    @pytest.fixture
    def custom_key_loop(self, tmp_path: Path) -> Path:
        """Create a loop that uses a non-default input_key."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_file = loops_dir / "keyed-loop.yaml"
        loop_file.write_text("""
name: keyed-loop
initial: init
input_key: issue_id
context:
  issue_id: null
states:
  init:
    action: "echo {{context.issue_id}}"
    on_yes: done
    on_no: done
  done:
    terminal: true
""")
        return loops_dir

    def test_positional_input_injected_into_context(self, simple_loop: Path) -> None:
        """Positional input arg is injected as context['input'] before execution."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        args = argparse.Namespace(
            input="FEAT-719",
            context=[],
            max_iterations=None,
            delay=None,
            no_llm=False,
            llm_model=None,
            dry_run=True,
            background=False,
            foreground_internal=False,
            quiet=False,
            verbose=False,
            show_diagrams=False,
            clear=False,
            queue=False,
        )
        logger = Logger(use_color=False)
        result = cmd_run("input-loop", args, simple_loop, logger)
        assert result == 0

        # Verify injection directly via load_and_validate + manual injection
        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)
        fsm.context[fsm.input_key] = "FEAT-719"
        assert fsm.context["input"] == "FEAT-719"

    def test_no_positional_input_leaves_context_unchanged(self, simple_loop: Path) -> None:
        """When no positional input is given, context['input'] retains its YAML default."""
        from little_loops.fsm.validation import load_and_validate

        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)
        # No injection; context retains the null declared in YAML
        assert fsm.context.get("input") is None

    def test_context_flag_overrides_positional_input(self, simple_loop: Path) -> None:
        """--context input=X overrides a positional input since it runs after injection."""
        from little_loops.fsm.validation import load_and_validate

        path = simple_loop / "input-loop.yaml"
        fsm, _ = load_and_validate(path)

        # Simulate cmd_run injection order: positional first, then --context
        positional_input = "FEAT-719"
        fsm.context[fsm.input_key] = positional_input
        # --context override
        for kv in ["input=OVERRIDE"]:
            key, _, value = kv.partition("=")
            fsm.context[key.strip()] = value.strip()

        assert fsm.context["input"] == "OVERRIDE"

    def test_custom_input_key_loaded_from_yaml(self, custom_key_loop: Path) -> None:
        """input_key declared in YAML is respected by the FSMLoop dataclass."""
        from little_loops.fsm.validation import load_and_validate

        path = custom_key_loop / "keyed-loop.yaml"
        fsm, _ = load_and_validate(path)

        assert fsm.input_key == "issue_id"
        # Simulate positional injection using custom key
        fsm.context[fsm.input_key] = "FEAT-100"


class TestCmdStatusJson:
    """Tests for ll-loop status --json."""

    def test_status_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs loop state as a JSON object."""
        from little_loops.cli.loop.lifecycle import cmd_status
        from little_loops.fsm.persistence import LoopState, StatePersistence

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:05:00",
            status="running",
        )

        with patch.object(StatePersistence, "load_state", return_value=state):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=True)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["loop_name"] == "my-loop"
        assert data["current_state"] == "run_tests"
        assert data["iteration"] == 5
        assert data["status"] == "running"
        assert "pid" in data

    def test_status_json_no_state(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with no state returns exit code 1."""
        from little_loops.cli.loop.lifecycle import cmd_status
        from little_loops.fsm.persistence import StatePersistence

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(StatePersistence, "load_state", return_value=None):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=True)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 1

    def test_status_human_readable_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output is unchanged human-readable format."""
        from little_loops.cli.loop.lifecycle import cmd_status
        from little_loops.fsm.persistence import LoopState, StatePersistence

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        state = LoopState(
            loop_name="my-loop",
            current_state="run_tests",
            iteration=2,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2026-01-13T10:00:00",
            updated_at="2026-01-13T10:01:00",
            status="interrupted",
        )

        with patch.object(StatePersistence, "load_state", return_value=state):
            from little_loops.logger import Logger

            logger = Logger(verbose=False)
            args = argparse.Namespace(json=False)
            result = cmd_status("my-loop", loops_dir, logger, args)

        assert result == 0
        out = capsys.readouterr().out
        assert "Loop: my-loop" in out
        assert "Status: interrupted" in out
        assert out.strip()[0] != "{"  # Not JSON


class TestCmdShowJson:
    """Tests for ll-loop show --json."""

    def test_show_json_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json outputs FSM config as a JSON object."""
        from little_loops.cli.loop.info import cmd_show

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\n"
            "description: Test loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: echo hello\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        from little_loops.logger import Logger

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False)
        result = cmd_show("my-loop", args, loops_dir, logger)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "name" in data or "states" in data  # FSMLoop.to_dict() includes these
        assert isinstance(data, dict)

    def test_show_json_invalid_loop(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json with missing loop returns exit code 1."""
        from little_loops.cli.loop.info import cmd_show
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=True, verbose=False)
        result = cmd_show("nonexistent-loop", args, loops_dir, logger)

        assert result == 1

    def test_show_human_readable_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --json, output contains the expected human-readable sections."""
        from little_loops.cli.loop.info import cmd_show

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = loops_dir / "my-loop.yaml"
        loop_yaml.write_text(
            "name: my-loop\n"
            "initial: start\n"
            "states:\n"
            "  start:\n"
            "    action: echo hello\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )

        from little_loops.logger import Logger

        logger = Logger(verbose=False)
        args = argparse.Namespace(json=False, verbose=False)
        result = cmd_show("my-loop", args, loops_dir, logger)

        assert result == 0
        out = capsys.readouterr().out
        assert "my-loop" in out
        assert "Diagram:" in out


class TestHistoryFiltering:
    """Tests for --event, --state, --since filtering in ll-loop history."""

    @pytest.fixture
    def mixed_events_file(self, tmp_path: Path) -> Path:
        """Create an archived events file with a variety of event types and states."""
        from datetime import datetime, timedelta

        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"

        now = datetime.now()
        old_ts = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        recent_ts = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")

        events = [
            {"event": "state_enter", "ts": old_ts, "state": "check", "iteration": 1},
            {"event": "action_start", "ts": old_ts, "state": "check", "action": "echo hi"},
            {"event": "evaluate", "ts": old_ts, "state": "check", "verdict": "no"},
            {"event": "route", "ts": old_ts, "from": "check", "to": "fix"},
            {"event": "state_enter", "ts": recent_ts, "state": "fix", "iteration": 2},
            {"event": "evaluate", "ts": recent_ts, "state": "fix", "verdict": "yes"},
            {"event": "route", "ts": recent_ts, "from": "fix", "to": "done"},
            {"event": "loop_complete", "ts": recent_ts, "final_state": "done"},
        ]

        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return events_file

    def test_event_filter_evaluate(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--event evaluate returns only evaluate events."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event="evaluate",
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert all(e["event"] == "evaluate" for e in data)
        assert len(data) == 2

    def test_state_filter_check(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--state check returns events where state, from, or to field equals 'check'."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state="check",
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # state_enter(check), action_start(check), evaluate(check), route(from=check)
        assert len(data) == 4
        for e in data:
            matches = (
                e.get("state") == "check" or e.get("from") == "check" or e.get("to") == "check"
            )
            assert matches, f"Event {e} does not match --state check"

    def test_since_filter_excludes_old_events(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--since 1h excludes events older than 1 hour."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state=None,
            since="1h",
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # Only the 4 recent events (30m old) should survive; old events (3h old) excluded
        assert len(data) == 4

    def test_combined_event_and_state_filter(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--event route --state check returns only route events touching state 'check'."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event="route",
            state="check",
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["event"] == "route"
        assert data[0]["from"] == "check"

    def test_tail_applied_after_filter(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tail applies as the final limit after --event filter."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=1,
            verbose=False,
            json=True,
            full=False,
            event="state_enter",
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        # 2 state_enter events exist, but --tail 1 limits to last 1
        assert len(data) == 1
        assert data[0]["state"] == "fix"

    def test_no_filter_behavior_unchanged(
        self,
        tmp_path: Path,
        mixed_events_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No filter flags: shows all non-action_output events (existing behavior)."""
        from little_loops.cli.loop.info import cmd_history

        args = argparse.Namespace(
            tail=50,
            verbose=False,
            json=True,
            full=False,
            event=None,
            state=None,
            since=None,
        )
        result = cmd_history("test-loop", "test-run-id", args, tmp_path / ".loops")

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 8


class TestHistorySinceShortForm:
    """Tests for -S short form of --since in ll-loop history (ENH-910)."""

    @pytest.fixture
    def loop_archive(self, tmp_path: Path) -> Path:
        """Create an archived events file for history testing."""
        archive_dir = tmp_path / ".loops" / ".history" / "test-loop" / "test-run-id"
        archive_dir.mkdir(parents=True)
        events_file = archive_dir / "events.jsonl"
        events = [
            {"event": "transition", "ts": "2026-01-15T10:00:00", "from": "idle", "to": "check"},
        ]
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        return tmp_path

    def test_history_since_short_form(
        self,
        loop_archive: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """-S is accepted as --since in ll-loop history (ENH-910)."""
        monkeypatch.chdir(loop_archive)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "history", "test-loop", "test-run-id", "-S", "1h"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
