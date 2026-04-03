"""Extension system for little-loops.

Provides the extension Protocol, a reference implementation, and discovery/loading
utilities for external packages to hook into little-loops via structured events.

Public exports:
    LLExtension: Protocol that extensions must satisfy
    NoopLoggerExtension: Reference extension that logs events to a JSONL file
    ExtensionLoader: Discovers and loads extensions from config and entry points
"""

from __future__ import annotations

import importlib
import json
import logging
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from little_loops.events import EventBus, EventCallback, LLEvent

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "little_loops.extensions"


@runtime_checkable
class LLExtension(Protocol):
    """Protocol for little-loops extensions.

    Any class with an ``on_event`` method matching this signature is a valid
    extension. Extensions receive structured events from the EventBus.

    Optionally, an extension may declare ``event_filter`` to subscribe only to
    specific event namespaces via glob patterns (e.g. ``"issue.*"`` or
    ``["issue.*", "parallel.*"]``).  ``None`` (the default) means the extension
    receives every event.
    """

    event_filter: str | list[str] | None

    def on_event(self, event: LLEvent) -> None:
        """Handle an event from little-loops.

        Args:
            event: Structured event with type, timestamp, and payload
        """
        ...


class NoopLoggerExtension:
    """Reference extension that logs events to a JSONL file.

    Demonstrates the extension API by writing each event as a JSON line
    to a specified log file. Useful for debugging and as a template for
    building custom extensions.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path or Path(".ll/extension-events.jsonl")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def on_event(self, event: LLEvent) -> None:
        """Append event to JSONL log file."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")


class ExtensionLoader:
    """Discover and load extensions from config paths and entry points."""

    @staticmethod
    def from_config(extension_paths: list[str]) -> list[LLExtension]:
        """Load extensions from dotted module paths.

        Each path should be in the format "module.path:ClassName".
        Extensions that fail to load are skipped with a warning.

        Args:
            extension_paths: List of "module:Class" strings

        Returns:
            List of successfully loaded extension instances
        """
        extensions: list[Any] = []
        for path in extension_paths:
            try:
                module_path, class_name = path.rsplit(":", 1)
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                extensions.append(cls())
            except Exception:
                logger.warning("Failed to load extension from config: %s", path, exc_info=True)
        return extensions

    @staticmethod
    def from_entry_points() -> list[LLExtension]:
        """Discover extensions via importlib.metadata entry points.

        Looks for entry points in the "little_loops.extensions" group.

        Returns:
            List of successfully loaded extension instances
        """
        extensions: list[Any] = []
        try:
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:
            # Python 3.11 compatibility: entry_points() may not support group kwarg
            eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined, assignment]
        for ep in eps:
            try:
                cls = ep.load()
                extensions.append(cls())
            except Exception:
                logger.warning("Failed to load extension entry point: %s", ep.name, exc_info=True)
        return extensions

    @staticmethod
    def load_all(config_paths: list[str] | None = None) -> list[LLExtension]:
        """Load extensions from all discovery sources.

        Combines extensions from config paths and entry points.

        Args:
            config_paths: Optional list of "module:Class" strings from config

        Returns:
            Combined list of all loaded extensions
        """
        extensions: list[Any] = []
        if config_paths:
            extensions.extend(ExtensionLoader.from_config(config_paths))
        extensions.extend(ExtensionLoader.from_entry_points())
        return extensions


def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
) -> list[LLExtension]:
    """Load extensions and register them on an EventBus.

    Each extension's ``on_event`` callback is wrapped to convert the raw
    ``dict[str, Any]`` dispatched by ``EventBus.emit()`` into an ``LLEvent``
    using ``from_raw_event()`` (which copies the dict to avoid mutation).

    Args:
        bus: EventBus to register extension callbacks on
        config_paths: Optional list of "module:Class" strings from config

    Returns:
        List of loaded extension instances
    """
    extensions = ExtensionLoader.load_all(config_paths)
    for ext in extensions:

        def _make_callback(e: LLExtension) -> EventCallback:
            def _cb(event: dict[str, Any]) -> None:
                e.on_event(LLEvent.from_raw_event(event))

            return _cb

        bus.register(_make_callback(ext), filter=getattr(ext, "event_filter", None))
    if extensions:
        logger.info("Wired %d extension(s) to EventBus", len(extensions))
    return extensions
