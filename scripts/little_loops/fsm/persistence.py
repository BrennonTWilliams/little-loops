"""State persistence and event streaming for FSM loops.

This module provides persistence capabilities for FSM loop execution:
- LoopState: Dataclass representing loop execution state
- StatePersistence: File I/O for state and events
- PersistentExecutor: Wrapper that persists state during execution
- Utility functions for listing running loops and reading history

File structure:
    .loops/
    ├── fix-types.yaml          # Loop definition
    ├── .running/               # Runtime state (auto-managed)
    │   ├── fix-types.state.json
    │   └── fix-types.events.jsonl
    └── .history/               # Archived run logs (auto-populated)
        └── fix-types/
            └── 2024-01-15T103000/
                ├── state.json
                └── events.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.events import EventBus
from little_loops.fsm.concurrency import _process_alive
from little_loops.fsm.executor import EventCallback, ExecutionResult, FSMExecutor
from little_loops.fsm.schema import FSMLoop

RUNNING_DIR = ".running"
HISTORY_DIR = ".history"

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    """Return current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


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
        status: Execution status (running, completed, failed, interrupted, awaiting_continuation, timed_out)
        continuation_prompt: Continuation context from handoff signal (if status is awaiting_continuation)
        accumulated_ms: Total milliseconds elapsed across all segments up to this save (used to restore
            elapsed time correctly after resume, so duration_ms and ${loop.elapsed_ms} reflect the
            full loop lifetime rather than only the most recent segment)
    """

    loop_name: str
    current_state: str
    iteration: int
    captured: dict[str, dict[str, Any]]
    prev_result: dict[str, Any] | None
    last_result: dict[str, Any] | None
    started_at: str
    updated_at: str
    status: (
        str  # "running", "completed", "failed", "interrupted", "awaiting_continuation", "timed_out"
    )
    continuation_prompt: str | None = None
    accumulated_ms: int = 0  # total elapsed ms across all segments (for resume offset)
    retry_counts: dict[str, int] = field(default_factory=dict)  # per-state retry tracking
    active_sub_loop: str | None = None  # name of currently executing sub-loop (observability)

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
            "accumulated_ms": self.accumulated_ms,
        }
        if self.continuation_prompt is not None:
            result["continuation_prompt"] = self.continuation_prompt
        if self.retry_counts:
            result["retry_counts"] = self.retry_counts
        if self.active_sub_loop is not None:
            result["active_sub_loop"] = self.active_sub_loop
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
            accumulated_ms=data.get("accumulated_ms", 0),
            retry_counts=data.get("retry_counts", {}),
            active_sub_loop=data.get("active_sub_loop"),
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
        """Save current state to file using an atomic write.

        Updates the updated_at timestamp before saving.  Writes to a temporary
        file first, then renames it over the target to avoid leaving a corrupt
        or empty state file if the process is killed mid-write.

        Args:
            state: LoopState to save
        """
        state.updated_at = _iso_now()
        data = json.dumps(state.to_dict(), indent=2)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.state_file.parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(data)
            os.replace(tmp_path, self.state_file)
        except Exception:
            os.unlink(tmp_path)
            raise

    def load_state(self) -> LoopState | None:
        """Load state from file, or None if not exists.

        Returns:
            LoopState if file exists and is valid, None otherwise
        """
        if not self.state_file.exists():
            return None
        try:
            data = json.loads(self.state_file.read_text())
        except json.JSONDecodeError:
            return None
        try:
            return LoopState.from_dict(data)
        except KeyError as e:
            logger.warning("Corrupted state file %s: missing key %s", self.state_file, e)
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

    def archive_run(self) -> Path | None:
        """Archive current run files to .history/ before clearing.

        Reads the current state to derive the run timestamp, then copies
        both state.json and events.jsonl into:
            <loops_dir>/.history/<loop_name>/<run_id>/

        where run_id is a compact ISO timestamp derived from started_at
        (e.g. "2024-01-15T103000" from "2024-01-15T10:30:00.123456+00:00").

        Returns:
            Path to the archive directory if files were archived, None if
            there were no files to archive (fresh run).
        """
        has_state = self.state_file.exists()
        has_events = self.events_file.exists()
        if not has_state and not has_events:
            return None

        # Derive run ID from started_at in state file, or fall back to now
        state = self.load_state()
        if state is not None and state.started_at:
            # Compact ISO: strip colons, dots, plus signs; take first 19 chars
            # e.g. "2024-01-15T10:30:00.123+00:00" → "2024-01-15T103000"
            run_id = state.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]
        else:
            run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")

        archive_dir = self.loops_dir / HISTORY_DIR / self.loop_name / run_id
        archive_dir.mkdir(parents=True, exist_ok=True)

        if has_state:
            shutil.copy2(self.state_file, archive_dir / "state.json")
        if has_events:
            shutil.copy2(self.events_file, archive_dir / "events.jsonl")

        return archive_dir

    def clear_all(self) -> None:
        """Archive current run files then clear state and events (for new run)."""
        self.archive_run()
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
        self.loops_dir = loops_dir
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
            loops_dir=self.loops_dir,
            **executor_kwargs,
        )
        self._last_result: dict[str, Any] | None = None
        self._continuation_prompt: str | None = None
        self.event_bus = EventBus()

    @property
    def _on_event(self) -> EventCallback | None:
        """Backward-compatible access to the first observer on the event bus."""
        return self.event_bus._observers[0][0] if self.event_bus._observers else None

    @_on_event.setter
    def _on_event(self, callback: EventCallback | None) -> None:
        """Backward-compatible setter: replaces all observers with this one."""
        self.event_bus._observers.clear()
        if callback is not None:
            self.event_bus.register(callback)

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
        if event_type in ("state_enter", "loop_complete"):
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

        # Delegate to registered observers (e.g. progress display, extensions)
        self.event_bus.emit(event)

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
            accumulated_ms=_now_ms()
            - self._executor.start_time_ms
            + self._executor.elapsed_offset_ms,
            retry_counts=dict(self._executor._retry_counts),
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
        if result.terminated_by == "timeout":
            final_status = "timed_out"

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
            accumulated_ms=result.duration_ms,
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
        self._executor._retry_counts = dict(state.retry_counts)

        # Restore accumulated elapsed time so duration_ms and ${loop.elapsed_ms} reflect
        # the full loop lifetime (all segments), not just the resumed segment.
        # FSMExecutor.run() will reset start_time_ms to _now_ms(), so we use elapsed_offset_ms
        # to carry forward the time already spent before this resume.
        self._executor.elapsed_offset_ms = state.accumulated_ms

        # Clear any pending signals from previous run
        self._executor._pending_handoff = None
        self._executor._pending_error = None

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

    # Include loops that have a PID file but no state file yet (still starting up)
    known_names = {s.loop_name for s in states}
    for pid_file in running_dir.glob("*.pid"):
        if pid_file.stem in known_names:
            continue  # state file already covers this loop
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            continue
        if _process_alive(pid):
            states.append(
                LoopState(
                    loop_name=pid_file.stem,
                    current_state="(initializing)",
                    iteration=0,
                    captured={},
                    prev_result=None,
                    last_result=None,
                    started_at="",
                    updated_at="",
                    status="starting",
                )
            )

    return states


def list_run_history(loop_name: str, loops_dir: Path | None = None) -> list[LoopState]:
    """List archived runs for a loop, newest first.

    Reads state files from .loops/.history/<loop_name>/*/state.json and returns
    them sorted by started_at descending (most recent run first).

    Args:
        loop_name: Name of the loop
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of LoopState objects for all archived runs, newest first.
        Returns an empty list if no history exists.
    """
    base_dir = loops_dir or Path(".loops")
    history_loop_dir = base_dir / HISTORY_DIR / loop_name

    if not history_loop_dir.exists():
        return []

    states: list[LoopState] = []
    for state_file in history_loop_dir.glob("*/state.json"):
        try:
            data = json.loads(state_file.read_text())
            states.append(LoopState.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue

    states.sort(key=lambda s: s.started_at, reverse=True)
    return states


def get_archived_events(
    loop_name: str, run_id: str, loops_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Read events for a specific archived run.

    Args:
        loop_name: Name of the loop
        run_id: The run directory name (compact timestamp)
        loops_dir: Base directory for loops (default: .loops)

    Returns:
        List of event dictionaries, empty if not found.
    """
    base_dir = loops_dir or Path(".loops")
    events_file = base_dir / HISTORY_DIR / loop_name / run_id / "events.jsonl"

    if not events_file.exists():
        return []

    events: list[dict[str, Any]] = []
    with open(events_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


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
