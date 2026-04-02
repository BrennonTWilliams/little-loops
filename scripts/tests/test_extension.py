"""Tests for LLExtension Protocol, NoopLoggerExtension, and ExtensionLoader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from little_loops.events import LLEvent
from little_loops.extension import (
    ExtensionLoader,
    LLExtension,
    NoopLoggerExtension,
)


class TestLLExtensionProtocol:
    """Tests for the LLExtension Protocol."""

    def test_protocol_satisfied(self) -> None:
        """A class with on_event(LLEvent) satisfies the Protocol."""

        class MyExtension:
            def on_event(self, event: LLEvent) -> None:
                pass

        ext = MyExtension()
        # Should be usable as LLExtension without error
        _: LLExtension = ext
        ext.on_event(LLEvent(type="test", timestamp="now", payload={}))

    def test_protocol_callable(self) -> None:
        """Extension can receive events through on_event."""
        received: list[LLEvent] = []

        class RecordingExtension:
            def on_event(self, event: LLEvent) -> None:
                received.append(event)

        ext = RecordingExtension()
        event = LLEvent(
            type="fsm.state_enter", timestamp="2026-04-02T12:00:00Z", payload={"state": "build"}
        )
        ext.on_event(event)

        assert len(received) == 1
        assert received[0].type == "fsm.state_enter"


class TestNoopLoggerExtension:
    """Tests for the reference NoopLoggerExtension."""

    def test_logs_events_to_file(self, tmp_path: Path) -> None:
        """NoopLoggerExtension writes events to a JSONL log file."""
        log_file = tmp_path / "extension.log.jsonl"
        ext = NoopLoggerExtension(log_path=log_file)

        ext.on_event(LLEvent(type="fsm.state_enter", timestamp="t1", payload={"state": "check"}))
        ext.on_event(
            LLEvent(type="fsm.loop_complete", timestamp="t2", payload={"final_state": "done"})
        )

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["event"] == "fsm.state_enter"
        assert first["state"] == "check"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """NoopLoggerExtension creates parent directories if needed."""
        log_file = tmp_path / "nested" / "dir" / "extension.log.jsonl"
        ext = NoopLoggerExtension(log_path=log_file)
        ext.on_event(LLEvent(type="test", timestamp="now", payload={}))
        assert log_file.exists()

    def test_satisfies_protocol(self) -> None:
        """NoopLoggerExtension satisfies the LLExtension Protocol."""
        ext = NoopLoggerExtension(log_path=Path("/dev/null"))
        _: LLExtension = ext  # type check


class TestExtensionLoader:
    """Tests for ExtensionLoader discovery and loading."""

    def test_from_config_empty(self) -> None:
        """Empty config list returns empty extensions."""
        extensions = ExtensionLoader.from_config([])
        assert extensions == []

    def test_from_config_loads_valid_path(self) -> None:
        """Loads extension from a valid dotted module path."""
        # Use the reference extension as the test target
        extensions = ExtensionLoader.from_config(["little_loops.extension:NoopLoggerExtension"])
        assert len(extensions) == 1
        assert isinstance(extensions[0], NoopLoggerExtension)

    def test_from_config_invalid_path_skips(self) -> None:
        """Invalid module path is skipped with a warning, not an exception."""
        extensions = ExtensionLoader.from_config(["nonexistent.module:FakeExtension"])
        assert extensions == []

    def test_from_config_multiple(self) -> None:
        """Multiple valid paths load multiple extensions."""
        extensions = ExtensionLoader.from_config(
            [
                "little_loops.extension:NoopLoggerExtension",
                "little_loops.extension:NoopLoggerExtension",
            ]
        )
        assert len(extensions) == 2

    def test_from_entry_points_empty(self) -> None:
        """No installed entry points returns empty list."""
        with patch("little_loops.extension.entry_points", return_value=[]):
            extensions = ExtensionLoader.from_entry_points()
        assert extensions == []

    def test_load_all_combines_sources(self) -> None:
        """load_all combines config and entry point extensions."""
        with patch("little_loops.extension.entry_points", return_value=[]):
            extensions = ExtensionLoader.load_all(
                config_paths=["little_loops.extension:NoopLoggerExtension"]
            )
        assert len(extensions) == 1

    def test_load_all_no_config(self) -> None:
        """load_all with no config only uses entry points."""
        with patch("little_loops.extension.entry_points", return_value=[]):
            extensions = ExtensionLoader.load_all()
        assert extensions == []
