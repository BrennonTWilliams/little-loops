"""Event system for little-loops extension architecture.

Provides structured event types and a multi-observer event bus that extensions
can subscribe to for receiving lifecycle events from FSM loops, issue management,
and automation workflows.

Public exports:
    LLEvent: Structured event dataclass with type, timestamp, and payload
    EventBus: Multi-observer event dispatcher with optional JSONL file sink
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Type for event callback (matches existing EventCallback in fsm/executor.py)
EventCallback = Callable[[dict[str, Any]], None]


@dataclass
class LLEvent:
    """Structured event emitted by little-loops subsystems.

    Attributes:
        type: Event type identifier (e.g. "fsm.state_enter", "fsm.loop_complete")
        timestamp: ISO 8601 timestamp string
        payload: Type-specific event data
    """

    type: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Produces a flat dict compatible with the existing FSM event format:
        {"event": type, "ts": timestamp, ...payload}
        """
        return {"event": self.type, "ts": self.timestamp, **self.payload}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLEvent:
        """Create from dictionary (JSON deserialization).

        Accepts the flat dict format: {"event": ..., "ts": ..., ...payload}
        """
        copy = dict(data)
        event_type = copy.pop("event", copy.pop("type", "unknown"))
        ts = copy.pop("ts", copy.pop("timestamp", ""))
        return cls(type=event_type, timestamp=ts, payload=copy)

    @classmethod
    def from_raw_event(cls, raw: dict[str, Any]) -> LLEvent:
        """Convert existing executor event dict to LLEvent without mutating the original."""
        return cls.from_dict(dict(raw))


class EventBus:
    """Multi-observer event dispatcher.

    Dispatches event dicts to all registered observers. Exceptions in individual
    observers are caught and logged, not propagated.
    """

    def __init__(self) -> None:
        self._observers: list[EventCallback] = []
        self._file_sinks: list[Path] = []

    def register(self, callback: EventCallback) -> None:
        """Register an observer to receive events."""
        self._observers.append(callback)

    def unregister(self, callback: EventCallback) -> None:
        """Remove an observer. No-op if not registered."""
        try:
            self._observers.remove(callback)
        except ValueError:
            pass

    def add_file_sink(self, path: Path) -> None:
        """Add a JSONL file sink. Events will be appended to this file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file_sinks.append(path)

    def emit(self, event: dict[str, Any]) -> None:
        """Dispatch event to all observers and file sinks.

        Observer exceptions are caught and logged to prevent one observer
        from blocking others.
        """
        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                logger.warning("EventBus observer raised an exception", exc_info=True)

        for sink_path in self._file_sinks:
            try:
                with open(sink_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception:
                logger.warning("EventBus file sink write failed: %s", sink_path, exc_info=True)

    @staticmethod
    def read_events(path: Path) -> list[LLEvent]:
        """Read events from a JSONL file.

        Returns:
            List of LLEvent instances, empty if file doesn't exist.
            Malformed lines are silently skipped.
        """
        if not path.exists():
            return []
        events: list[LLEvent] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(LLEvent.from_dict(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        return events
