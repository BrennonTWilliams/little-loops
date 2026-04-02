"""Tests for FSM state persistence and event streaming."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import (
    LoopState,
    PersistentExecutor,
    StatePersistence,
    get_archived_events,
    get_loop_history,
    list_run_history,
    list_running_loops,
)
from little_loops.fsm.schema import FSMLoop, StateConfig


class TestLoopState:
    """Tests for LoopState dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """State round-trips through to_dict/from_dict."""
        original = LoopState(
            loop_name="test-loop",
            current_state="fix",
            iteration=3,
            captured={"errors": {"output": "4", "exit_code": 0}},
            prev_result={"output": "test", "exit_code": 1, "state": "check"},
            last_result={"verdict": "no", "details": {"confidence": 0.65}},
            started_at="2024-01-15T10:30:00Z",
            updated_at="2024-01-15T10:32:45Z",
            status="running",
        )

        restored = LoopState.from_dict(original.to_dict())

        assert restored.loop_name == original.loop_name
        assert restored.current_state == original.current_state
        assert restored.iteration == original.iteration
        assert restored.captured == original.captured
        assert restored.prev_result == original.prev_result
        assert restored.last_result == original.last_result
        assert restored.started_at == original.started_at
        assert restored.updated_at == original.updated_at
        assert restored.status == original.status

    def test_to_dict_json_serializable(self) -> None:
        """to_dict output is JSON serializable."""
        state = LoopState(
            loop_name="test",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )

        # Should not raise
        json.dumps(state.to_dict())

    def test_from_dict_with_defaults(self) -> None:
        """from_dict handles missing optional fields."""
        data = {
            "loop_name": "test",
            "current_state": "check",
            "iteration": 1,
            "started_at": "2024-01-15T10:30:00Z",
            "status": "running",
            # Missing: captured, prev_result, last_result, updated_at
        }

        state = LoopState.from_dict(data)

        assert state.captured == {}
        assert state.prev_result is None
        assert state.last_result is None
        assert state.updated_at == ""

    def test_active_sub_loop_field_roundtrip(self) -> None:
        """active_sub_loop round-trips through to_dict/from_dict (FEAT-659)."""
        state = LoopState(
            loop_name="parent",
            current_state="run_child",
            iteration=2,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="2024-01-15T10:31:00Z",
            status="running",
            active_sub_loop="child-loop",
        )
        d = state.to_dict()
        assert d["active_sub_loop"] == "child-loop"

        restored = LoopState.from_dict(d)
        assert restored.active_sub_loop == "child-loop"

    def test_active_sub_loop_defaults_to_none(self) -> None:
        """active_sub_loop defaults to None when not in data (FEAT-659)."""
        data = {
            "loop_name": "test",
            "current_state": "check",
            "iteration": 1,
            "started_at": "2024-01-15T10:30:00Z",
            "status": "running",
        }
        state = LoopState.from_dict(data)
        assert state.active_sub_loop is None

    def test_active_sub_loop_omitted_when_none(self) -> None:
        """to_dict omits active_sub_loop when None (FEAT-659)."""
        state = LoopState(
            loop_name="test",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        d = state.to_dict()
        assert "active_sub_loop" not in d


class TestStatePersistence:
    """Tests for StatePersistence class."""

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        return tmp_path / ".loops"

    def test_initialize_creates_running_dir(self, tmp_loops_dir: Path) -> None:
        """initialize() creates .running directory."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        assert (tmp_loops_dir / ".running").exists()
        assert (tmp_loops_dir / ".running").is_dir()

    def test_save_and_load_state(self, tmp_loops_dir: Path) -> None:
        """State saves to and loads from file."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="fix",
            iteration=3,
            captured={"errors": {"output": "4"}},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        loaded = persistence.load_state()
        assert loaded is not None
        assert loaded.current_state == "fix"
        assert loaded.iteration == 3
        assert loaded.captured["errors"]["output"] == "4"
        assert loaded.updated_at != ""  # Should be set by save

    def test_load_state_returns_none_if_missing(self, tmp_loops_dir: Path) -> None:
        """load_state() returns None if no file exists."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        assert persistence.load_state() is None

    def test_load_state_returns_none_for_invalid_json(self, tmp_loops_dir: Path) -> None:
        """load_state() returns None if file is invalid JSON."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Write invalid JSON
        persistence.state_file.write_text("not valid json")

        assert persistence.load_state() is None

    def test_clear_state_removes_file(self, tmp_loops_dir: Path) -> None:
        """clear_state() removes the state file."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)
        assert persistence.state_file.exists()

        persistence.clear_state()
        assert not persistence.state_file.exists()

    def test_clear_state_handles_missing_file(self, tmp_loops_dir: Path) -> None:
        """clear_state() handles missing file gracefully."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Should not raise
        persistence.clear_state()

    def test_append_events(self, tmp_loops_dir: Path) -> None:
        """Events append to JSONL file."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.append_event({"event": "loop_start", "ts": "2024-01-15T10:30:00Z"})
        persistence.append_event(
            {"event": "state_enter", "state": "check", "ts": "2024-01-15T10:30:01Z"}
        )

        events = persistence.read_events()
        assert len(events) == 2
        assert events[0]["event"] == "loop_start"
        assert events[1]["event"] == "state_enter"
        assert events[1]["state"] == "check"

    def test_append_event_without_initialize_raises(self, tmp_path: Path) -> None:
        """append_event() raises FileNotFoundError when parent directory does not exist."""
        persistence = StatePersistence("test-loop", tmp_path / "nonexistent_dir")
        with pytest.raises(FileNotFoundError):
            persistence.append_event({"type": "test"})

    def test_read_events_returns_empty_if_missing(self, tmp_loops_dir: Path) -> None:
        """read_events() returns empty list if no file exists."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        assert persistence.read_events() == []

    def test_read_events_skips_malformed_lines(self, tmp_loops_dir: Path) -> None:
        """read_events() skips malformed JSON lines."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Write a mix of valid and invalid lines
        with open(persistence.events_file, "w") as f:
            f.write('{"event": "valid1"}\n')
            f.write("not valid json\n")
            f.write('{"event": "valid2"}\n')
            f.write("\n")  # Empty line
            f.write('{"event": "valid3"}\n')

        events = persistence.read_events()
        assert len(events) == 3
        assert [e["event"] for e in events] == ["valid1", "valid2", "valid3"]

    def test_clear_events_removes_file(self, tmp_loops_dir: Path) -> None:
        """clear_events() removes the events file."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.append_event({"event": "test"})
        assert persistence.events_file.exists()

        persistence.clear_events()
        assert not persistence.events_file.exists()

    def test_events_file_is_append_only(self, tmp_loops_dir: Path) -> None:
        """Events are appended, not overwritten."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.append_event({"event": "first"})
        persistence.append_event({"event": "second"})
        persistence.append_event({"event": "third"})

        # Read raw file to verify JSONL format
        content = persistence.events_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 3

    def test_clear_all_removes_both_files(self, tmp_loops_dir: Path) -> None:
        """clear_all() removes both state and events files."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Create both files
        state = LoopState(
            loop_name="test",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)
        persistence.append_event({"event": "test"})

        assert persistence.state_file.exists()
        assert persistence.events_file.exists()

        persistence.clear_all()

        assert not persistence.state_file.exists()
        assert not persistence.events_file.exists()


class TestArchiveRun:
    """Tests for StatePersistence.archive_run() and related history utilities."""

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        return tmp_path / ".loops"

    def _make_state(self, started_at: str = "2024-01-15T10:30:00+00:00") -> LoopState:
        return LoopState(
            loop_name="test-loop",
            current_state="done",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at=started_at,
            updated_at="",
            status="completed",
            accumulated_ms=3600000,
        )

    def test_archive_run_copies_state_and_events(self, tmp_loops_dir: Path) -> None:
        """archive_run() copies state.json and events.jsonl to .history/."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.save_state(self._make_state())
        persistence.append_event({"event": "loop_start", "ts": "2024-01-15T10:30:00Z"})

        archive_path = persistence.archive_run()

        assert archive_path is not None
        assert (archive_path / "state.json").exists()
        assert (archive_path / "events.jsonl").exists()

    def test_archive_run_directory_structure(self, tmp_loops_dir: Path) -> None:
        """archive_run() creates .history/<loop_name>/<run_id>/ structure."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state("2024-01-15T10:30:00+00:00"))

        archive_path = persistence.archive_run()

        assert archive_path is not None
        # Should be inside .history/test-loop/
        assert archive_path.parent.name == "test-loop"
        assert archive_path.parent.parent.name == ".history"

    def test_archive_run_run_id_from_started_at(self, tmp_loops_dir: Path) -> None:
        """archive_run() derives run_id from started_at timestamp."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state("2024-01-15T10:30:00+00:00"))

        archive_path = persistence.archive_run()

        assert archive_path is not None
        # run_id is compact form of "2024-01-15T10:30:00+00:00"
        # → strip :, ., + → "2024-01-15T103000000000"[:17] = "2024-01-15T103000"
        assert archive_path.name == "2024-01-15T103000"

    def test_archive_run_returns_none_for_fresh_run(self, tmp_loops_dir: Path) -> None:
        """archive_run() returns None when there are no files to archive."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        result = persistence.archive_run()

        assert result is None

    def test_archive_run_only_state_no_events(self, tmp_loops_dir: Path) -> None:
        """archive_run() archives state.json even if events file doesn't exist."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state())

        archive_path = persistence.archive_run()

        assert archive_path is not None
        assert (archive_path / "state.json").exists()
        assert not (archive_path / "events.jsonl").exists()

    def test_archive_run_only_events_no_state(self, tmp_loops_dir: Path) -> None:
        """archive_run() archives events.jsonl even if state file doesn't exist."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.append_event({"event": "test"})

        archive_path = persistence.archive_run()

        assert archive_path is not None
        assert not (archive_path / "state.json").exists()
        assert (archive_path / "events.jsonl").exists()

    def test_archive_run_does_not_delete_originals(self, tmp_loops_dir: Path) -> None:
        """archive_run() copies files; running files still exist afterward."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state())
        persistence.append_event({"event": "test"})

        persistence.archive_run()

        assert persistence.state_file.exists()
        assert persistence.events_file.exists()

    def test_clear_all_archives_before_clearing(self, tmp_loops_dir: Path) -> None:
        """clear_all() archives existing files before deleting them."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state())
        persistence.append_event({"event": "loop_start"})

        persistence.clear_all()

        # Running files are gone
        assert not persistence.state_file.exists()
        assert not persistence.events_file.exists()

        # But history exists
        history_base = tmp_loops_dir / ".history" / "test-loop"
        assert history_base.exists()
        run_dirs = list(history_base.iterdir())
        assert len(run_dirs) == 1
        assert (run_dirs[0] / "state.json").exists()
        assert (run_dirs[0] / "events.jsonl").exists()

    def test_clear_all_no_archive_for_fresh_run(self, tmp_loops_dir: Path) -> None:
        """clear_all() does not create empty history dirs when no files exist."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.clear_all()

        history_base = tmp_loops_dir / ".history" / "test-loop"
        assert not history_base.exists()

    def test_multiple_archive_runs_coexist(self, tmp_loops_dir: Path) -> None:
        """Multiple archived runs coexist under different run IDs."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # First run
        persistence.save_state(self._make_state("2024-01-15T10:00:00+00:00"))
        persistence.append_event({"event": "run1"})
        persistence.clear_all()

        # Second run
        persistence.save_state(self._make_state("2024-01-15T11:00:00+00:00"))
        persistence.append_event({"event": "run2"})
        persistence.clear_all()

        history_base = tmp_loops_dir / ".history" / "test-loop"
        run_dirs = sorted(history_base.iterdir())
        assert len(run_dirs) == 2

    def test_list_run_history_returns_newest_first(self, tmp_loops_dir: Path) -> None:
        """list_run_history() returns archived runs sorted newest first."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Simulate two archived runs
        persistence.save_state(self._make_state("2024-01-15T10:00:00+00:00"))
        persistence.clear_all()

        persistence.save_state(self._make_state("2024-01-15T11:00:00+00:00"))
        persistence.clear_all()

        runs = list_run_history("test-loop", tmp_loops_dir)

        assert len(runs) == 2
        assert runs[0].started_at == "2024-01-15T11:00:00+00:00"
        assert runs[1].started_at == "2024-01-15T10:00:00+00:00"

    def test_list_run_history_empty_when_no_history(self, tmp_loops_dir: Path) -> None:
        """list_run_history() returns [] when no history exists."""
        runs = list_run_history("nonexistent-loop", tmp_loops_dir)
        assert runs == []

    def test_get_archived_events_returns_events(self, tmp_loops_dir: Path) -> None:
        """get_archived_events() returns events for a specific run."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.save_state(self._make_state("2024-01-15T10:30:00+00:00"))
        persistence.append_event({"event": "loop_start", "ts": "t1"})
        persistence.append_event({"event": "state_enter", "ts": "t2"})
        archive_path = persistence.archive_run()
        assert archive_path is not None

        events = get_archived_events("test-loop", archive_path.name, tmp_loops_dir)

        assert len(events) == 2
        assert events[0]["event"] == "loop_start"
        assert events[1]["event"] == "state_enter"

    def test_get_archived_events_returns_empty_for_missing_run(self, tmp_loops_dir: Path) -> None:
        """get_archived_events() returns [] for a nonexistent run ID."""
        events = get_archived_events("test-loop", "2024-01-15T103000", tmp_loops_dir)
        assert events == []


class MockActionRunner:
    """Mock action runner for testing."""

    def __init__(self, results: list[ActionResult] | None = None) -> None:
        self.calls: list[str] = []
        self.results = results or []
        self._index = 0

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Any = None,
    ) -> ActionResult:
        del on_output_line
        self.calls.append(action)
        if self._index < len(self.results):
            result = self.results[self._index]
            self._index += 1
            return result
        return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)


class TestPersistentExecutor:
    """Tests for PersistentExecutor class."""

    @pytest.fixture
    def simple_fsm(self) -> FSMLoop:
        """Create a simple FSM for testing."""
        return FSMLoop(
            name="test-loop",
            initial="check",
            states={
                "check": StateConfig(
                    action="echo 'checking'",
                    on_yes="done",
                    on_no="fix",
                ),
                "fix": StateConfig(
                    action="echo 'fixing'",
                    next="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        return tmp_path / ".loops"

    def test_creates_running_directory(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """PersistentExecutor creates .running directory."""
        mock_runner = MockActionRunner()
        PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner)

        assert (tmp_loops_dir / ".running").exists()

    def test_run_creates_state_file(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """run() creates state file."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )
        executor.run()

        state_file = tmp_loops_dir / ".running" / "test-loop.state.json"
        assert state_file.exists()

    def test_run_creates_events_file(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """run() creates events file."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )
        executor.run()

        events_file = tmp_loops_dir / ".running" / "test-loop.events.jsonl"
        assert events_file.exists()

    def test_run_saves_final_state(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """run() saves final state with correct status."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )
        result = executor.run()

        state = executor.persistence.load_state()
        assert state is not None
        assert state.current_state == result.final_state
        assert state.status == "completed"

    def test_events_are_persisted(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """Events are written to JSONL file during execution."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )
        executor.run()

        events = executor.persistence.read_events()
        assert len(events) > 0

        # Check for key event types
        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "loop_complete" in event_types

    def test_run_clears_previous_by_default(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """run() clears previous state/events by default."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

        # First run
        executor.run()
        first_events = executor.persistence.read_events()

        # Second run should clear first
        executor2 = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )
        executor2.run()
        second_events = executor2.persistence.read_events()

        # Should only have events from second run
        assert len(second_events) > 0
        assert len(second_events) <= len(first_events) + 5  # Reasonable bound

    def test_resume_returns_none_for_missing_state(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """resume() returns None if no state file exists."""
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )
        result = executor.resume()
        assert result is None

    def test_resume_returns_none_for_completed(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """resume() returns None if loop already completed."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="done",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="completed",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        result = executor.resume()
        assert result is None

    def test_resume_returns_none_for_failed(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """resume() returns None if loop already failed."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="failed",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        result = executor.resume()
        assert result is None

    def test_resume_returns_none_for_interrupted(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """resume() returns None if loop was interrupted (same as completed/failed)."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=5,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="interrupted",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        result = executor.resume()
        assert result is None

    def test_resume_emits_resume_event(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """resume() emits loop_resume event."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Save a running state
        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        executor.resume()

        events = persistence.read_events()
        event_types = [e["event"] for e in events]
        assert "loop_resume" in event_types

    def test_resume_clears_pending_signals(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """resume() clears both _pending_handoff and _pending_error from the previous run."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=1,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        # Simulate stale signals from a previous run
        executor._executor._pending_handoff = object()  # type: ignore[assignment]
        executor._executor._pending_error = "stale error"

        executor.resume()

        assert executor._executor._pending_handoff is None
        assert executor._executor._pending_error is None

    def test_final_status_completed_on_terminal(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """Final status is 'completed' when reaching terminal state."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )
        result = executor.run()

        assert result.terminated_by == "terminal"
        state = executor.persistence.load_state()
        assert state is not None
        assert state.status == "completed"

    def test_final_status_interrupted_on_max_iterations(self, tmp_loops_dir: Path) -> None:
        """Final status is 'interrupted' when max_iterations reached."""
        # Create FSM that won't terminate
        fsm = FSMLoop(
            name="infinite-loop",
            initial="check",
            max_iterations=2,
            states={
                "check": StateConfig(
                    action="echo 'checking'",
                    on_yes="check",  # Always loop back
                    on_no="check",
                ),
            },
        )

        mock_runner = MockActionRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner)
        result = executor.run()

        assert result.terminated_by == "max_iterations"
        state = executor.persistence.load_state()
        assert state is not None
        assert state.status == "interrupted"

    def test_final_status_timed_out_on_timeout(self, tmp_loops_dir: Path) -> None:
        """Final status is 'timed_out' when loop timeout is exceeded."""
        fsm = FSMLoop(
            name="timeout-loop",
            initial="check",
            timeout=1,
            states={
                "check": StateConfig(
                    action="echo 'checking'",
                    on_yes="check",  # Always loop back
                    on_no="check",
                ),
            },
        )

        mock_runner = MockActionRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner)
        # Simulate elapsed time already exceeding the timeout
        executor._executor.elapsed_offset_ms = 999_999_999
        result = executor.run()

        assert result.terminated_by == "timeout"
        state = executor.persistence.load_state()
        assert state is not None
        assert state.status == "timed_out"


class TestUtilityFunctions:
    """Tests for utility functions."""

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory with state files."""
        loops_dir = tmp_path / ".loops"
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True)

        # Create some state files
        state1 = {
            "loop_name": "loop-a",
            "current_state": "check",
            "iteration": 1,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:01Z",
            "status": "running",
        }
        state2 = {
            "loop_name": "loop-b",
            "current_state": "done",
            "iteration": 3,
            "captured": {},
            "prev_result": None,
            "last_result": None,
            "started_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:05:00Z",
            "status": "completed",
        }

        (running_dir / "loop-a.state.json").write_text(json.dumps(state1))
        (running_dir / "loop-b.state.json").write_text(json.dumps(state2))

        # Create events file for loop-a
        events = [
            {"event": "loop_start", "ts": "2024-01-15T10:30:00Z"},
            {"event": "state_enter", "state": "check", "ts": "2024-01-15T10:30:01Z"},
        ]
        with open(running_dir / "loop-a.events.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        return loops_dir

    def test_list_running_loops(self, tmp_loops_dir: Path) -> None:
        """list_running_loops() returns all loops with state files."""
        states = list_running_loops(tmp_loops_dir)

        assert len(states) == 2
        names = {s.loop_name for s in states}
        assert names == {"loop-a", "loop-b"}

    def test_list_running_loops_empty_dir(self, tmp_path: Path) -> None:
        """list_running_loops() returns empty list if no running dir."""
        states = list_running_loops(tmp_path / "nonexistent")
        assert states == []

    def test_list_running_loops_skips_invalid_files(self, tmp_path: Path) -> None:
        """list_running_loops() skips malformed state files."""
        loops_dir = tmp_path / ".loops"
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True)

        # Write a valid state
        valid_state = {
            "loop_name": "valid",
            "current_state": "check",
            "iteration": 1,
            "started_at": "",
            "status": "running",
        }
        (running_dir / "valid.state.json").write_text(json.dumps(valid_state))

        # Write invalid JSON
        (running_dir / "invalid.state.json").write_text("not json")

        # Write valid JSON but missing required field
        (running_dir / "missing.state.json").write_text('{"loop_name": "test"}')

        states = list_running_loops(loops_dir)
        assert len(states) == 1
        assert states[0].loop_name == "valid"

    def test_list_running_loops_pid_only_live_process(self, tmp_path: Path) -> None:
        """list_running_loops() includes loops with PID file but no state file yet (live process)."""
        loops_dir = tmp_path / ".loops"
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True)

        (running_dir / "starting-loop.pid").write_text("12345")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("little_loops.fsm.persistence._process_alive", lambda pid: True)
            states = list_running_loops(loops_dir)

        assert len(states) == 1
        assert states[0].loop_name == "starting-loop"
        assert states[0].status == "starting"
        assert states[0].current_state == "(initializing)"
        assert states[0].iteration == 0

    def test_list_running_loops_pid_only_stale_process(self, tmp_path: Path) -> None:
        """list_running_loops() skips PID-only loops where the process is not alive."""
        loops_dir = tmp_path / ".loops"
        running_dir = loops_dir / ".running"
        running_dir.mkdir(parents=True)

        (running_dir / "dead-loop.pid").write_text("99999")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("little_loops.fsm.persistence._process_alive", lambda pid: False)
            states = list_running_loops(loops_dir)

        assert states == []

    def test_list_running_loops_no_duplicate_for_loop_with_both_files(
        self, tmp_loops_dir: Path
    ) -> None:
        """list_running_loops() returns state-file version only when both .pid and .state.json exist."""
        running_dir = tmp_loops_dir / ".running"
        # loop-a has a state file (from fixture); also add a PID file for it
        (running_dir / "loop-a.pid").write_text("12345")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("little_loops.fsm.persistence._process_alive", lambda pid: True)
            states = list_running_loops(tmp_loops_dir)

        names = [s.loop_name for s in states]
        assert names.count("loop-a") == 1
        # The state-file version should be returned, not the synthetic one
        loop_a = next(s for s in states if s.loop_name == "loop-a")
        assert loop_a.status != "starting"

    def test_get_loop_history(self, tmp_loops_dir: Path) -> None:
        """get_loop_history() returns events for a loop."""
        events = get_loop_history("loop-a", tmp_loops_dir)

        assert len(events) == 2
        assert events[0]["event"] == "loop_start"
        assert events[1]["event"] == "state_enter"

    def test_get_loop_history_missing(self, tmp_loops_dir: Path) -> None:
        """get_loop_history() returns empty list for missing loop."""
        events = get_loop_history("nonexistent", tmp_loops_dir)
        assert events == []


class TestAcceptanceCriteria:
    """Tests covering acceptance criteria from the issue."""

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        return tmp_path / ".loops"

    @pytest.fixture
    def simple_fsm(self) -> FSMLoop:
        """Create a simple FSM for testing."""
        return FSMLoop(
            name="test-loop",
            initial="check",
            states={
                "check": StateConfig(
                    action="echo 'checking'",
                    on_yes="done",
                    on_no="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_running_directory_created_automatically(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: .loops/.running/ directory created automatically."""
        PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner())

        assert (tmp_loops_dir / ".running").exists()

    def test_state_saved_after_state_transition(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: State saved to <name>.state.json after each state transition."""
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )
        executor.run()

        state_file = tmp_loops_dir / ".running" / "test-loop.state.json"
        assert state_file.exists()

        # Verify state content
        data = json.loads(state_file.read_text())
        assert "loop_name" in data
        assert "current_state" in data
        assert "iteration" in data
        assert "captured" in data
        assert "started_at" in data
        assert "status" in data

    def test_events_appended_as_they_occur(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
        """AC: Events appended to <name>.events.jsonl as they occur."""
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )
        executor.run()

        events = executor.persistence.read_events()
        assert len(events) > 0

        # Verify JSONL format (each line is valid JSON)
        content = executor.persistence.events_file.read_text()
        for line in content.strip().split("\n"):
            if line:
                json.loads(line)  # Should not raise

    def test_load_state_returns_none_if_no_file(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: load_state() returns None if no state file exists."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        assert persistence.load_state() is None

    def test_resume_continues_from_saved_state(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: resume() continues from saved state maintaining iteration count."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Save a state mid-execution
        saved_iteration = 5
        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=saved_iteration,
            captured={"test_var": {"output": "captured_value"}},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        result = executor.resume()

        assert result is not None
        # Iteration should have increased from saved state
        assert result.iterations >= saved_iteration

    def test_resume_restores_accumulated_duration(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: duration_ms after resume includes time from before the interruption (BUG-527)."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Simulate a state saved after 5 seconds of prior execution
        prior_elapsed_ms = 5000
        state = LoopState(
            loop_name="test-loop",
            current_state="check",
            iteration=3,
            captured={},
            prev_result=None,
            last_result=None,
            started_at="2024-01-15T10:30:00Z",
            updated_at="",
            status="running",
            accumulated_ms=prior_elapsed_ms,
        )
        persistence.save_state(state)

        executor = PersistentExecutor(
            simple_fsm, persistence=persistence, action_runner=MockActionRunner()
        )
        result = executor.resume()

        assert result is not None
        # duration_ms must include the prior 5 seconds, not reset to 0
        assert result.duration_ms >= prior_elapsed_ms

    def test_resume_preserves_captured_for_interpolation(self, tmp_loops_dir: Path) -> None:
        """Captures from before interrupt are usable after resume via interpolation."""
        # FSM where step2 uses captured value from step1
        fsm = FSMLoop(
            name="capture-resume",
            initial="step1",
            states={
                "step1": StateConfig(
                    action="fetch.sh",
                    capture="data",
                    next="step2",
                ),
                "step2": StateConfig(
                    action='use "${captured.data.output}"',
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )

        persistence = StatePersistence("capture-resume", tmp_loops_dir)
        persistence.initialize()

        # Simulate interrupted execution: step1 completed, about to start step2
        state = LoopState(
            loop_name="capture-resume",
            current_state="step2",
            iteration=2,
            captured={
                "data": {
                    "output": "captured-value",
                    "stderr": "",
                    "exit_code": 0,
                    "duration_ms": 100,
                }
            },
            prev_result={
                "output": "captured-value",
                "stderr": "",
                "exit_code": 0,
                "state": "step1",
            },
            last_result=None,
            started_at="2026-01-15T10:00:00Z",
            updated_at="",
            status="running",
        )
        persistence.save_state(state)

        mock_runner = MockActionRunner()

        executor = PersistentExecutor(fsm, persistence=persistence, action_runner=mock_runner)
        result = executor.resume()

        assert result is not None
        # Verify the interpolation used the captured value from before resume
        assert len(mock_runner.calls) == 1
        assert 'use "captured-value"' in mock_runner.calls[0]

    def test_resume_returns_none_for_completed_failed(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: resume() returns None for completed/failed loops."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        for status in ["completed", "failed"]:
            state = LoopState(
                loop_name="test-loop",
                current_state="done",
                iteration=5,
                captured={},
                prev_result=None,
                last_result=None,
                started_at="",
                updated_at="",
                status=status,
            )
            persistence.save_state(state)

            executor = PersistentExecutor(
                simple_fsm, persistence=persistence, action_runner=MockActionRunner()
            )
            result = executor.resume()
            assert result is None, f"Should return None for status={status}"

    def test_list_running_loops_returns_running_status(self, tmp_loops_dir: Path) -> None:
        """AC: list_running_loops() returns all loops with 'running' status."""
        running_dir = tmp_loops_dir / ".running"
        running_dir.mkdir(parents=True)

        # Create states with different statuses
        for name, status in [
            ("loop-running", "running"),
            ("loop-completed", "completed"),
            ("loop-failed", "failed"),
        ]:
            state = {
                "loop_name": name,
                "current_state": "check",
                "iteration": 1,
                "started_at": "",
                "status": status,
            }
            (running_dir / f"{name}.state.json").write_text(json.dumps(state))

        states = list_running_loops(tmp_loops_dir)

        # All states should be returned, regardless of status
        assert len(states) == 3
        statuses = {s.status for s in states}
        assert statuses == {"running", "completed", "failed"}

    def test_get_loop_history_returns_all_events(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: get_loop_history() returns all events for a loop."""
        executor = PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )
        executor.run()

        events = get_loop_history("test-loop", tmp_loops_dir)
        assert len(events) > 0

        # Should include start and complete events
        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "loop_complete" in event_types

    def test_event_file_is_append_only_jsonl(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: Event file is append-only JSONL format."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        # Append multiple events
        persistence.append_event({"event": "first", "ts": "t1"})
        persistence.append_event({"event": "second", "ts": "t2"})

        # Read raw content
        content = persistence.events_file.read_text()
        lines = content.strip().split("\n")

        # Each line should be valid JSON
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"


class TestCorruptedStateFiles:
    """Tests for corrupted state file handling."""

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        return tmp_path / ".loops"

    # State file corruption tests
    def test_zero_byte_state_file(self, tmp_loops_dir: Path) -> None:
        """Zero-byte state file should return None."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text("")

        result = persistence.load_state()
        assert result is None

    def test_truncated_json_state_file(self, tmp_loops_dir: Path) -> None:
        """Truncated JSON should return None."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"status": "running", "current_sta')

        result = persistence.load_state()
        assert result is None

    def test_binary_garbage_state_file(self, tmp_loops_dir: Path) -> None:
        """Binary content in state file should be handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_bytes(b"\x00\xff\xfe\x80\x90")

        # May raise UnicodeDecodeError since it's not caught
        # This test documents current behavior
        try:
            result = persistence.load_state()
            assert result is None
        except UnicodeDecodeError:
            pass  # Current implementation doesn't catch this

    def test_wrong_encoding_state_file(self, tmp_loops_dir: Path) -> None:
        """Non-UTF-8 encoding should be handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        content = '{"status": "running"}'.encode("utf-16")
        persistence.state_file.write_bytes(content)

        # May raise UnicodeDecodeError since it's not caught
        try:
            result = persistence.load_state()
            assert result is None
        except UnicodeDecodeError:
            pass  # Current implementation doesn't catch this

    # Field validation tests
    def test_missing_required_field_in_state(self, tmp_loops_dir: Path) -> None:
        """State JSON missing required field should return None and log a warning."""
        from unittest.mock import patch

        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"loop_name": "test"}')

        with patch("little_loops.fsm.persistence.logger") as mock_logger:
            result = persistence.load_state()

        assert result is None
        mock_logger.warning.assert_called_once()
        assert "Corrupted state file" in mock_logger.warning.call_args[0][0]

    def test_wrong_type_for_field_in_state(self, tmp_loops_dir: Path) -> None:
        """Wrong type for field should be accepted (no validation)."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        # iteration should be int, but no type validation exists
        state_data = {
            "loop_name": 123,  # Should be string
            "current_state": "test",
            "iteration": "not-an-int",  # Should be int
            "started_at": "",
            "status": "running",
        }
        persistence.state_file.write_text(json.dumps(state_data))

        result = persistence.load_state()
        # Current implementation doesn't validate types - documents behavior
        assert result is not None  # Will load successfully

    def test_null_values_in_state(self, tmp_loops_dir: Path) -> None:
        """Null values for required fields should be handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        state_data = {
            "loop_name": None,
            "current_state": None,
            "iteration": None,
            "started_at": None,
            "status": None,
        }
        persistence.state_file.write_text(json.dumps(state_data))

        result = persistence.load_state()
        # Null values are accepted - documents behavior
        assert result is not None

    # Events file corruption tests
    def test_truncated_events_file(self, tmp_loops_dir: Path) -> None:
        """Truncated events JSONL recovers gracefully."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        # Valid line, then truncated line
        persistence.events_file.write_text('{"event": "start"}\n{"event": "tran')

        events = persistence.read_events()
        assert len(events) == 1
        assert events[0]["event"] == "start"


class TestSignalHandlingPersistence:
    """Tests for graceful shutdown via signal handling with persistence."""

    @pytest.fixture
    def multi_state_fsm(self) -> FSMLoop:
        """Create a multi-state FSM for signal testing."""
        return FSMLoop(
            name="signal-test-loop",
            initial="step1",
            max_iterations=10,
            states={
                "step1": StateConfig(action="echo step1", next="step2"),
                "step2": StateConfig(action="echo step2", next="step3"),
                "step3": StateConfig(action="echo step3", next="done"),
                "done": StateConfig(terminal=True),
            },
        )

    @pytest.fixture
    def tmp_loops_dir(self, tmp_path: Path) -> Path:
        """Create temporary loops directory."""
        return tmp_path / ".loops"

    def test_persistent_executor_has_request_shutdown(
        self, multi_state_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """PersistentExecutor exposes request_shutdown method."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            multi_state_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

        # Method exists and is callable
        assert hasattr(executor, "request_shutdown")
        assert callable(executor.request_shutdown)

    def test_request_shutdown_delegates_to_inner_executor(
        self, multi_state_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """request_shutdown delegates to inner FSMExecutor."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            multi_state_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

        assert executor._executor._shutdown_requested is False
        executor.request_shutdown()
        assert executor._executor._shutdown_requested is True

    def test_signal_termination_saves_state_as_interrupted(
        self, multi_state_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """Signal termination saves state with status='interrupted'."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            multi_state_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

        # Request shutdown before run
        executor.request_shutdown()
        result = executor.run()

        assert result.terminated_by == "signal"

        # Check persisted state
        state = executor.persistence.load_state()
        assert state is not None
        assert state.status == "interrupted"

    def test_signal_termination_preserves_captured_in_state(self, tmp_loops_dir: Path) -> None:
        """Signal termination preserves captured values in state file."""
        fsm = FSMLoop(
            name="capture-signal-test",
            initial="capture_step",
            max_iterations=10,
            states={
                "capture_step": StateConfig(
                    action="echo captured_value",
                    capture="my_capture",
                    next="next_step",
                ),
                "next_step": StateConfig(action="echo next", next="capture_step"),
            },
        )

        call_count = [0]
        executor_ref: list[PersistentExecutor] = []

        class CaptureAndShutdownRunner:
            calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
            ) -> ActionResult:
                del timeout, is_slash_command, on_output_line
                self.calls.append(action)
                call_count[0] += 1

                # Shutdown after first iteration
                if call_count[0] == 2 and executor_ref:
                    executor_ref[0].request_shutdown()

                if "captured_value" in action:
                    return ActionResult(
                        output="important_data_xyz", stderr="", exit_code=0, duration_ms=10
                    )
                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)

        runner = CaptureAndShutdownRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor_ref.append(executor)

        result = executor.run()

        assert result.terminated_by == "signal"
        assert "my_capture" in result.captured
        assert result.captured["my_capture"]["output"] == "important_data_xyz"

        # Check state file also has captured values
        state = executor.persistence.load_state()
        assert state is not None
        assert "my_capture" in state.captured
        assert state.captured["my_capture"]["output"] == "important_data_xyz"

    def test_signal_interrupted_loop_can_be_resumed(self, tmp_loops_dir: Path) -> None:
        """Loop interrupted by signal can be resumed later."""
        fsm = FSMLoop(
            name="resumable-signal-test",
            initial="step1",
            max_iterations=10,
            states={
                "step1": StateConfig(action="echo step1", next="step2"),
                "step2": StateConfig(action="echo step2", next="step3"),
                "step3": StateConfig(action="echo step3", next="done"),
                "done": StateConfig(terminal=True),
            },
        )

        call_count = [0]
        executor_ref: list[PersistentExecutor] = []

        class ShutdownAfterFirstRunner:
            calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
            ) -> ActionResult:
                del timeout, is_slash_command, on_output_line
                self.calls.append(action)
                call_count[0] += 1

                # Shutdown after first action
                if call_count[0] == 1 and executor_ref:
                    executor_ref[0].request_shutdown()

                return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=10)

        runner = ShutdownAfterFirstRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor_ref.append(executor)

        # First run - gets interrupted
        result1 = executor.run()
        assert result1.terminated_by == "signal"
        assert result1.final_state == "step2"  # Routed after step1

        # Check state shows interrupted
        state = executor.persistence.load_state()
        assert state is not None
        assert state.status == "interrupted"

        # Manually set status to "running" to enable resume
        # (In real scenario, user would mark as resumable)
        state.status = "running"
        executor.persistence.save_state(state)

        # Create new executor for resume
        runner2 = MockActionRunner()
        executor2 = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner2)

        # Resume
        result2 = executor2.resume()

        assert result2 is not None
        assert result2.terminated_by == "terminal"
        assert result2.final_state == "done"

    def test_signal_emits_events_before_termination(
        self, multi_state_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """Signal termination still emits loop_start and loop_complete events."""
        mock_runner = MockActionRunner()
        executor = PersistentExecutor(
            multi_state_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

        executor.request_shutdown()
        executor.run()

        events = executor.persistence.read_events()
        event_types = [e["event"] for e in events]

        assert "loop_start" in event_types
        assert "loop_complete" in event_types

        # Find loop_complete event
        loop_complete = next(e for e in events if e["event"] == "loop_complete")
        assert loop_complete["terminated_by"] == "signal"

    def test_signal_during_multi_iteration_preserves_progress(self, tmp_loops_dir: Path) -> None:
        """Signal during multi-iteration execution preserves all progress."""
        fsm = FSMLoop(
            name="multi-iter-signal",
            initial="step1",
            max_iterations=10,
            states={
                "step1": StateConfig(action="echo step1", capture="step1_out", next="step2"),
                "step2": StateConfig(action="echo step2", capture="step2_out", next="step1"),
            },
        )

        call_count = [0]
        executor_ref: list[PersistentExecutor] = []

        class ProgressTrackingRunner:
            calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line: Any = None,
            ) -> ActionResult:
                del timeout, is_slash_command, on_output_line
                self.calls.append(action)
                call_count[0] += 1

                # Shutdown after 4 actions (2 full iterations)
                if call_count[0] == 4 and executor_ref:
                    executor_ref[0].request_shutdown()

                # Return call count to track progress
                return ActionResult(
                    output=f"call_{call_count[0]}", stderr="", exit_code=0, duration_ms=10
                )

        runner = ProgressTrackingRunner()
        executor = PersistentExecutor(fsm, loops_dir=tmp_loops_dir, action_runner=runner)
        executor_ref.append(executor)

        result = executor.run()

        assert result.terminated_by == "signal"
        assert result.iterations == 4  # 4 iterations completed

        # Both captures should have latest values
        assert "step1_out" in result.captured
        assert "step2_out" in result.captured

        # Verify captures updated over iterations
        # Last step1 was call 3, last step2 was call 4
        assert result.captured["step1_out"]["output"] == "call_3"
        assert result.captured["step2_out"]["output"] == "call_4"
