"""State persistence and event streaming for FSM loops.

This module provides persistence capabilities for FSM loop execution:
- LoopState: Dataclass representing loop execution state
- StatePersistence: File I/O for state and events
- PersistentExecutor: Wrapper that persists state during execution
- Utility functions for listing running loops and reading history

File structure:
    .loops/
    ├── fix-types.yaml          # Loop definition
    └── .running/               # Runtime state (auto-managed)
        ├── fix-types.state.json
        └── fix-types.events.jsonl
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.fsm.executor import EventCallback, ExecutionResult, FSMExecutor
from little_loops.fsm.schema import FSMLoop

RUNNING_DIR = ".running"


def _iso_now() -> str:
    """Return current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class LoopState:
    """Persistent state for an FSM loop execution.

    This captures all runtime state needed to resume a loop:
    - Current state and iteration
    - Captured variables and previous result
    - Last evaluation result
    - Timestamps and status

    Attributes:
        loop_name: Name of the loop
        current_state: Current FSM state name
        iteration: Current iteration count (1-based)
        captured: Captured action outputs by variable name
        prev_result: Previous state's result (output, exit_code, state)
        last_result: Last evaluation result (verdict, details)
        started_at: ISO timestamp when loop started
        updated_at: ISO timestamp when state was last saved
        status: Execution status (running, completed, failed, interrupted, awaiting_continuation)
        continuation_prompt: Continuation context from handoff signal (if status is awaiting_continuation)
    """

    loop_name: str
    current_state: str
    iteration: int
    captured: dict[str, dict[str, Any]]
    prev_result: dict[str, Any] | None
    last_result: dict[str, Any] | None
    started_at: str
    updated_at: str
    status: str  # "running", "completed", "failed", "interrupted", "awaiting_continuation"
    continuation_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
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
        if self.continuation_prompt is not None:
            result["continuation_prompt"] = self.continuation_prompt
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopState:
        """Create LoopState from dictionary.

        Args:
            data: Dictionary with loop state fields

        Returns:
            LoopState instance
        """
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
            continuation_prompt=data.get("continuation_prompt"),
        )


class StatePersistence:
    """Manage loop state persistence and event streaming.

    Handles file I/O for:
    - State file: JSON file with current execution state
    - Events file: JSONL file with execution events (append-only)

    Files are stored in .loops/.running/<loop_name>.*
    """

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
        """Save current state to file.

        Updates the updated_at timestamp before saving.

        Args:
            state: LoopState to save
        """
        state.updated_at = _iso_now()
        self.state_file.write_text(json.dumps(state.to_dict(), indent=2))

    def load_state(self) -> LoopState | None:
        """Load state from file, or None if not exists.

        Returns:
            LoopState if file exists and is valid, None otherwise
        """
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
        """Append event to JSONL file.

        Args:
            event: Event dictionary to append
        """
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        """Read all events from file.

        Returns:
            List of event dictionaries, empty if file doesn't exist
        """
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


class PersistentExecutor:
    """FSM Executor with state persistence and event streaming.

    Wraps FSMExecutor to:
    - Save state after each state transition
    - Append events to JSONL file as they occur
    - Support resuming from saved state
    - Support graceful shutdown via signal handling
    """

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
        from little_loops.fsm.handoff_handler import HandoffBehavior, HandoffHandler
        from little_loops.fsm.signal_detector import SignalDetector

        self.fsm = fsm
        self.persistence = persistence or StatePersistence(fsm.name, loops_dir or Path(".loops"))
        self.persistence.initialize()

        # Create signal detector and handler based on FSM config
        signal_detector = SignalDetector()
        handoff_handler = HandoffHandler(HandoffBehavior(fsm.on_handoff))

        # Create base executor with event callback that persists
        self._executor = FSMExecutor(
            fsm,
            event_callback=self._handle_event,
            signal_detector=signal_detector,
            handoff_handler=handoff_handler,
            **executor_kwargs,
        )
        self._last_result: dict[str, Any] | None = None
        self._continuation_prompt: str | None = None
        self._on_event: EventCallback | None = None

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the executor.

        Delegates to the underlying FSMExecutor's request_shutdown method.
        The loop will exit cleanly after the current state completes,
        saving state as "interrupted" so it can be resumed later.
        """
        self._executor.request_shutdown()

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Handle event: persist to file and save state.

        Args:
            event: Event dictionary from executor
        """
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
                    k: v for k, v in event.items() if k not in ("event", "ts", "type", "verdict")
                },
            }

        # Track handoff events for continuation prompt
        if event_type == "handoff_detected":
            self._continuation_prompt = event.get("continuation")

        # Delegate to secondary observer (e.g. progress display)
        if self._on_event is not None:
            self._on_event(event)

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
        if result.terminated_by in ("max_iterations", "signal"):
            final_status = "interrupted"
        if result.terminated_by == "handoff":
            final_status = "awaiting_continuation"

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
            continuation_prompt=self._continuation_prompt,
        )
        self.persistence.save_state(final_state)

        return result

    def resume(self) -> ExecutionResult | None:
        """Resume from saved state, or None if no resumable state.

        Resumable states are: "running" and "awaiting_continuation".

        Returns:
            ExecutionResult if resumed and completed, None if no resumable state
        """
        state = self.persistence.load_state()
        if state is None:
            return None

        if state.status not in ("running", "awaiting_continuation"):
            return None  # Already completed/failed

        # Restore executor state
        self._executor.current_state = state.current_state
        self._executor.iteration = state.iteration
        self._executor.captured = state.captured
        self._executor.prev_result = state.prev_result
        self._executor.started_at = state.started_at
        self._last_result = state.last_result

        # Clear any pending handoff from previous run
        self._executor._pending_handoff = None

        # Emit resume event with continuation context if available
        resume_event: dict[str, Any] = {
            "event": "loop_resume",
            "ts": _iso_now(),
            "loop": self.fsm.name,
            "from_state": state.current_state,
            "iteration": state.iteration,
        }
        if state.status == "awaiting_continuation" and state.continuation_prompt:
            resume_event["from_handoff"] = True
            resume_event["continuation_prompt"] = state.continuation_prompt
        self.persistence.append_event(resume_event)

        # Continue execution (don't clear previous events)
        return self.run(clear_previous=False)


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
