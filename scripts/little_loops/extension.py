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

from little_loops.events import LLEvent

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "little_loops.extensions"


@runtime_checkable
class LLExtension(Protocol):
    """Protocol for little-loops extensions.

    Any class with an ``on_event`` method matching this signature is a valid
    extension. Extensions receive structured events from the EventBus.
    """

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
