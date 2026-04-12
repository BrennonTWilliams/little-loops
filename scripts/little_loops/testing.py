"""Offline test harness for little-loops extensions.

Provides :class:`LLTestBus` — a standalone replay engine that loads a recorded
``.events.jsonl`` file and dispatches events through registered
:class:`~little_loops.extension.LLExtension` instances without running a live loop.

Example usage::

    from little_loops.testing import LLTestBus

    bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
    bus.register(MyExtension())
    bus.replay()
    assert len(bus.delivered_events) == 15
    assert bus.delivered_events[0].type == "loop_start"
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.events import EventBus, LLEvent

if TYPE_CHECKING:
    from little_loops.extension import LLExtension


class LLTestBus:
    """Offline event replay harness for testing :class:`~little_loops.extension.LLExtension` handlers.

    Loads a pre-recorded ``.events.jsonl`` file, replays events through
    registered extensions offline (no live loop execution), and exposes
    :attr:`delivered_events` for assertions.

    Attributes:
        delivered_events: Events actually delivered to at least one extension
            (i.e. events that passed the ``event_filter`` of any registered extension).
    """

    def __init__(self, events: list[LLEvent]) -> None:
        self._events: list[LLEvent] = events
        self._extensions: list[LLExtension] = []
        self.delivered_events: list[LLEvent] = []

    @classmethod
    def from_jsonl(cls, path: str | Path) -> LLTestBus:
        """Create an :class:`LLTestBus` from a JSONL events file.

        Args:
            path: Path to the ``.events.jsonl`` file. If the file does not exist,
                an empty bus is returned (no events, no error).

        Returns:
            A new :class:`LLTestBus` instance loaded with events from the file.
        """
        events = EventBus.read_events(Path(path))
        return cls(events)

    def register(self, ext: LLExtension) -> None:
        """Register an extension to receive events during :meth:`replay`.

        Args:
            ext: An object implementing the :class:`~little_loops.extension.LLExtension`
                protocol (must have ``on_event`` and optionally ``event_filter``).
        """
        self._extensions.append(ext)

    def replay(self) -> None:
        """Replay all loaded events through registered extensions.

        For each event, applies each extension's ``event_filter`` (if set) using
        glob matching, then calls ``ext.on_event(event)`` for matching events.
        Events that pass the filter for at least one extension are appended to
        :attr:`delivered_events`.

        ``event_filter`` semantics mirror :class:`~little_loops.events.EventBus`:

        - ``None`` (or absent): the extension receives every event.
        - ``str``: a single glob pattern matched against ``event.type``.
        - ``list[str]``: any matching pattern causes delivery.
        """
        self.delivered_events = []

        for event in self._events:
            delivered = False
            for ext in self._extensions:
                ef = getattr(ext, "event_filter", None)
                patterns: list[str] | None = None
                if ef is not None:
                    patterns = [ef] if isinstance(ef, str) else list(ef)

                if patterns is not None and not any(
                    fnmatch.fnmatch(event.type, p) for p in patterns
                ):
                    continue

                ext.on_event(event)
                delivered = True

            if delivered:
                self.delivered_events.append(event)
