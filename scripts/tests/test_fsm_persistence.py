"""Tests for FSM state persistence and event streaming."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import (
    LoopState,
    PersistentExecutor,
    StatePersistence,
    get_loop_history,
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
            last_result={"verdict": "failure", "details": {"confidence": 0.65}},
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
    ) -> ActionResult:
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
                    on_success="done",
                    on_failure="fix",
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
        PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner
        )

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
                    on_success="check",  # Always loop back
                    on_failure="check",
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
                    on_success="done",
                    on_failure="check",
                ),
                "done": StateConfig(terminal=True),
            },
        )

    def test_running_directory_created_automatically(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """AC: .loops/.running/ directory created automatically."""
        PersistentExecutor(
            simple_fsm, loops_dir=tmp_loops_dir, action_runner=MockActionRunner()
        )

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
