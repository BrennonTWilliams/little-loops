"""Event system for little-loops extension architecture.

Provides structured event types and a multi-observer event bus that extensions
can subscribe to for receiving lifecycle events from FSM loops, issue management,
and automation workflows.

Public exports:
    LLEvent: Structured event dataclass with type, timestamp, and payload
    EventBus: Multi-observer event dispatcher with pluggable transports
"""

from __future__ import annotations

import fnmatch
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.transport import Transport

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
        self._observers: list[tuple[EventCallback, list[str] | None]] = []
        self._transports: list[Transport] = []

    def register(self, callback: EventCallback, filter: str | list[str] | None = None) -> None:
        """Register an observer to receive events.

        Args:
            callback: Callable that receives raw event dicts.
            filter: Optional glob pattern(s) to match against the event's ``"event"`` key.
                A single string (e.g. ``"issue.*"``) or a list of strings
                (e.g. ``["issue.*", "parallel.*"]``).  ``None`` (default) means
                the observer receives every event — preserving existing behaviour.
                FSM executor events use bare names (``"state_enter"``, ``"loop_*"``);
                other subsystems use dotted namespaces (``"issue.*"``, ``"parallel.*"``).
        """
        patterns: list[str] | None = None
        if filter is not None:
            patterns = [filter] if isinstance(filter, str) else list(filter)
        self._observers.append((callback, patterns))

    def unregister(self, callback: EventCallback) -> None:
        """Remove an observer. No-op if not registered."""
        for i, (cb, _) in enumerate(self._observers):
            if cb is callback:
                del self._observers[i]
                return

    def add_transport(self, transport: Transport) -> None:
        """Register a Transport to receive every emitted event."""
        self._transports.append(transport)

    def close_transports(self) -> None:
        """Call ``close()`` on every registered transport, isolating exceptions."""
        for transport in self._transports:
            try:
                transport.close()
            except Exception:
                logger.warning("EventBus transport close raised an exception", exc_info=True)

    def emit(self, event: dict[str, Any]) -> None:
        """Dispatch event to all observers and transports.

        Observer and transport exceptions are caught and logged to prevent one
        sink from blocking others.
        """
        event_type = event.get("event", "")
        for observer, filter_patterns in self._observers:
            if filter_patterns is not None and not any(
                fnmatch.fnmatch(event_type, p) for p in filter_patterns
            ):
                continue
            try:
                observer(event)
            except Exception:
                logger.warning("EventBus observer raised an exception", exc_info=True)

        for transport in self._transports:
            try:
                transport.send(event)
            except Exception:
                logger.warning("EventBus transport raised an exception", exc_info=True)

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
