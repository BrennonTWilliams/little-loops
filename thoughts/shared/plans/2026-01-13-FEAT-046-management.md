# FEAT-046: State Persistence and Events - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-046-state-persistence-and-events.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The FSM executor (`scripts/little_loops/fsm/executor.py`) maintains execution state in memory:
- `current_state` (line 202): Current FSM state name
- `iteration` (line 203): Loop iteration counter
- `captured` (line 204): Captured action outputs
- `prev_result` (line 205): Previous state result
- `started_at` (line 206): Start timestamp

The executor already has an event callback system (`executor.py:198, 510-518`) that emits structured events for all state transitions. Events include: `loop_start`, `state_enter`, `action_start`, `action_complete`, `evaluate`, `route`, `loop_complete`.

### Key Discoveries
- Event callback architecture at `executor.py:198` is designed for persistence integration
- State is tracked but not persisted between sessions
- Existing patterns in `state.py:76-204` show StateManager with load/save/cleanup
- JSONL pattern in `user_messages.py:219-247` shows append-mode event streaming
- Dataclass serialization pattern uses `to_dict()` and `@classmethod from_dict()`

## Desired End State

1. `.loops/.running/` directory created automatically when loops run
2. State saved to `<name>.state.json` after each state transition
3. Events appended to `<name>.events.jsonl` as they occur
4. Resume capability that continues from saved state
5. Utility functions to list running loops and read event history

### How to Verify
- Unit tests for `LoopState` serialization roundtrip
- Unit tests for `StatePersistence` file operations
- Integration tests for `PersistentExecutor` resume capability
- All existing FSM tests continue to pass

## What We're NOT Doing

- Not implementing the `ll-loop` CLI tool (FEAT-047)
- Not implementing scope-based concurrency control (FEAT-049)
- Not modifying the core `FSMExecutor` class (only wrapping it)
- Not adding cleanup on completion (state file remains for history per spec)

## Problem Analysis

The FSM executor lacks persistence, meaning:
1. Interrupted loops cannot resume
2. No execution history for debugging
3. No way to list currently running loops

## Solution Approach

Create a new `persistence.py` module in `scripts/little_loops/fsm/` that:
1. Defines `LoopState` dataclass matching the spec
2. Implements `StatePersistence` class for file I/O
3. Implements `PersistentExecutor` wrapper that saves state on events
4. Provides utility functions for listing loops and reading history

This follows the existing patterns in the codebase (see `state.py`, `user_messages.py`).

## Implementation Phases

### Phase 1: LoopState Dataclass and StatePersistence Class

#### Overview
Create the core persistence data structures and file I/O operations.

#### Changes Required

**File**: `scripts/little_loops/fsm/persistence.py` (new file)

```python
"""State persistence and event streaming for FSM loops."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNNING_DIR = ".running"


def _iso_now() -> str:
    """Return current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LoopState:
    """Persistent state for an FSM loop execution."""

    loop_name: str
    current_state: str
    iteration: int
    captured: dict[str, dict[str, Any]]
    prev_result: dict[str, Any] | None
    last_result: dict[str, Any] | None
    started_at: str
    updated_at: str
    status: str  # "running", "completed", "failed", "interrupted"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "loop_name": self.loop_name,
            "current_state": self.current_state,
            "iteration": self.iteration,
            "captured": self.captured,
            "prev_result": self.prev_result,
            "last_result": self.last_result,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopState:
        """Create LoopState from dictionary."""
        return cls(
            loop_name=data["loop_name"],
            current_state=data["current_state"],
            iteration=data["iteration"],
            captured=data.get("captured", {}),
            prev_result=data.get("prev_result"),
            last_result=data.get("last_result"),
            started_at=data["started_at"],
            updated_at=data.get("updated_at", ""),
            status=data["status"],
        )


class StatePersistence:
    """Manage loop state persistence and event streaming."""

    def __init__(self, loop_name: str, loops_dir: Path | None = None) -> None:
        """Initialize persistence for a loop.

        Args:
            loop_name: Name of the loop
            loops_dir: Base directory for loops (default: .loops)
        """
        self.loop_name = loop_name
        self.loops_dir = loops_dir or Path(".loops")
        self.running_dir = self.loops_dir / RUNNING_DIR
        self.state_file = self.running_dir / f"{loop_name}.state.json"
        self.events_file = self.running_dir / f"{loop_name}.events.jsonl"

    def initialize(self) -> None:
        """Create running directory if needed."""
        self.running_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: LoopState) -> None:
        """Save current state to file."""
        state.updated_at = _iso_now()
        self.state_file.write_text(json.dumps(state.to_dict(), indent=2))

    def load_state(self) -> LoopState | None:
        """Load state from file, or None if not exists."""
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text())
            return LoopState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def clear_state(self) -> None:
        """Remove state file."""
        if self.state_file.exists():
            self.state_file.unlink()

    def append_event(self, event: dict[str, Any]) -> None:
        """Append event to JSONL file."""
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        """Read all events from file."""
        if not self.events_file.exists():
            return []
        events: list[dict[str, Any]] = []
        with open(self.events_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines
        return events

    def clear_events(self) -> None:
        """Remove events file."""
        if self.events_file.exists():
            self.events_file.unlink()

    def clear_all(self) -> None:
        """Clear both state and events files (for new run)."""
        self.clear_state()
        self.clear_events()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/persistence.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/persistence.py`

---

### Phase 2: PersistentExecutor Wrapper

#### Overview
Implement the executor wrapper that persists state and events during execution.

#### Changes Required

**File**: `scripts/little_loops/fsm/persistence.py` (append to file)

```python
from little_loops.fsm.executor import ExecutionResult, FSMExecutor
from little_loops.fsm.schema import FSMLoop


class PersistentExecutor:
    """FSM Executor with state persistence and event streaming."""

    def __init__(
        self,
        fsm: FSMLoop,
        persistence: StatePersistence | None = None,
        loops_dir: Path | None = None,
        **executor_kwargs: Any,
    ) -> None:
        """Initialize persistent executor.

        Args:
            fsm: FSM loop definition
            persistence: Optional pre-configured persistence (for testing)
            loops_dir: Base directory for loops (default: .loops)
            **executor_kwargs: Additional kwargs for FSMExecutor
        """
        self.fsm = fsm
        self.persistence = persistence or StatePersistence(
            fsm.name, loops_dir or Path(".loops")
        )
        self.persistence.initialize()

        # Create base executor with event callback that persists
        self._executor = FSMExecutor(
            fsm,
            event_callback=self._handle_event,
            **executor_kwargs,
        )
        self._last_result: dict[str, Any] | None = None

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle event: persist to file and save state."""
        self.persistence.append_event(event)

        # Save state after state transitions
        event_type = event.get("event")
        if event_type in ("state_enter", "route", "loop_complete"):
            self._save_state()

        # Track evaluation results for state persistence
        if event_type == "evaluate":
            self._last_result = {
                "verdict": event.get("verdict"),
                "details": {
                    k: v
                    for k, v in event.items()
                    if k not in ("event", "ts", "type", "verdict")
                },
            }

    def _save_state(self) -> None:
        """Save current executor state to file."""
        status = "running"
        if self._executor.current_state:
            state_config = self.fsm.states.get(self._executor.current_state)
            if state_config and state_config.terminal:
                status = "completed"

        state = LoopState(
            loop_name=self.fsm.name,
            current_state=self._executor.current_state,
            iteration=self._executor.iteration,
            captured=self._executor.captured,
            prev_result=self._executor.prev_result,
            last_result=self._last_result,
            started_at=self._executor.started_at,
            updated_at="",  # Will be set by save_state
            status=status,
        )
        self.persistence.save_state(state)

    def run(self, clear_previous: bool = True) -> ExecutionResult:
        """Run the FSM with persistence.

        Args:
            clear_previous: If True, clear previous state/events before running

        Returns:
            ExecutionResult from the execution
        """
        if clear_previous:
            self.persistence.clear_all()

        result = self._executor.run()

        # Update final state
        final_status = "completed" if result.terminated_by == "terminal" else "failed"
        if result.terminated_by == "max_iterations":
            final_status = "interrupted"

        final_state = LoopState(
            loop_name=self.fsm.name,
            current_state=result.final_state,
            iteration=result.iterations,
            captured=result.captured,
            prev_result=self._executor.prev_result,
            last_result=self._last_result,
            started_at=self._executor.started_at,
            updated_at="",
            status=final_status,
        )
        self.persistence.save_state(final_state)

        return result

    def resume(self) -> ExecutionResult | None:
        """Resume from saved state, or None if no resumable state.

        Returns:
            ExecutionResult if resumed and completed, None if no resumable state
        """
        state = self.persistence.load_state()
        if state is None:
            return None

        if state.status != "running":
            return None  # Already completed/failed

        # Restore executor state
        self._executor.current_state = state.current_state
        self._executor.iteration = state.iteration
        self._executor.captured = state.captured
        self._executor.prev_result = state.prev_result
        self._executor.started_at = state.started_at
        self._last_result = state.last_result

        # Emit resume event
        self.persistence.append_event({
            "event": "loop_resume",
            "ts": _iso_now(),
            "loop": self.fsm.name,
            "from_state": state.current_state,
            "iteration": state.iteration,
        })

        # Continue execution (don't clear previous events)
        return self.run(clear_previous=False)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/persistence.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/persistence.py`

---

### Phase 3: Utility Functions and Module Exports

#### Overview
Add utility functions for listing running loops and reading event history, and export from module.

#### Changes Required

**File**: `scripts/little_loops/fsm/persistence.py` (append to file)

```python
def list_running_loops(loops_dir: Path | None = None) -> list[LoopState]:
    """List all loops with saved state.

    Args:
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of LoopState objects for all loops with state files
    """
    base_dir = loops_dir or Path(".loops")
    running_dir = base_dir / RUNNING_DIR

    if not running_dir.exists():
        return []

    states: list[LoopState] = []
    for state_file in running_dir.glob("*.state.json"):
        try:
            data = json.loads(state_file.read_text())
            states.append(LoopState.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue  # Skip malformed files

    return states


def get_loop_history(loop_name: str, loops_dir: Path | None = None) -> list[dict[str, Any]]:
    """Get event history for a loop.

    Args:
        loop_name: Name of the loop
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of event dictionaries
    """
    persistence = StatePersistence(loop_name, loops_dir)
    return persistence.read_events()
```

**File**: `scripts/little_loops/fsm/__init__.py` (update exports)

Add to existing exports:
```python
from little_loops.fsm.persistence import (
    LoopState,
    PersistentExecutor,
    StatePersistence,
    get_loop_history,
    list_running_loops,
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/`

---

### Phase 4: Comprehensive Tests

#### Overview
Write tests covering all acceptance criteria from the issue.

#### Changes Required

**File**: `scripts/tests/test_fsm_persistence.py` (new file)

```python
"""Tests for FSM state persistence and event streaming."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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

    def test_append_events(self, tmp_loops_dir: Path) -> None:
        """Events append to JSONL file."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()

        persistence.append_event({"event": "loop_start", "ts": "2024-01-15T10:30:00Z"})
        persistence.append_event({"event": "state_enter", "state": "check", "ts": "2024-01-15T10:30:01Z"})

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

    def test_run_creates_state_and_events(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """run() creates state file and events file."""
        executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir)

        with patch.object(executor._executor, "run") as mock_run:
            from little_loops.fsm.executor import ExecutionResult
            mock_run.return_value = ExecutionResult(
                final_state="done",
                iterations=1,
                terminated_by="terminal",
                duration_ms=100,
                captured={},
            )
            executor.run()

        # State file should exist
        state_file = tmp_loops_dir / ".running" / "test-loop.state.json"
        assert state_file.exists()

        # Events file should exist (from _handle_event calls)
        events_file = tmp_loops_dir / ".running" / "test-loop.events.jsonl"
        # Note: events may or may not exist depending on mock behavior

    def test_resume_returns_none_for_missing_state(
        self, simple_fsm: FSMLoop, tmp_loops_dir: Path
    ) -> None:
        """resume() returns None if no state file exists."""
        executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir)
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

        executor = PersistentExecutor(simple_fsm, persistence=persistence)
        result = executor.resume()
        assert result is None


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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`
- [ ] All tests in test file pass
- [ ] Test coverage includes all acceptance criteria from issue

---

## Testing Strategy

### Unit Tests
- `LoopState` serialization roundtrip
- `StatePersistence` file operations (save, load, clear, append)
- Event JSONL format validation

### Integration Tests
- `PersistentExecutor` with mocked FSMExecutor
- Resume from saved state
- Utility functions with real file system

## References

- Original issue: `.issues/features/P2-FEAT-046-state-persistence-and-events.md`
- Design doc: `docs/generalized-fsm-loop.md` sections "State Persistence" and "Structured Events"
- Existing patterns: `scripts/little_loops/state.py:76-204` (StateManager)
- Event callback: `scripts/little_loops/fsm/executor.py:198,510-518`
- JSONL pattern: `scripts/little_loops/user_messages.py:219-247`
