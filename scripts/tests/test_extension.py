"""Tests for LLExtension Protocol, NoopLoggerExtension, ExtensionLoader, and wire_extensions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.events import EventBus, LLEvent
from little_loops.extension import (
    ExtensionLoader,
    LLExtension,
    NoopLoggerExtension,
    wire_extensions,
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


class TestWireExtensions:
    """Tests for wire_extensions() helper."""

    def test_wire_extensions_registers_on_bus(self) -> None:
        """wire_extensions loads extensions and registers them on EventBus."""
        received: list[LLEvent] = []

        class RecordingExtension:
            def on_event(self, event: LLEvent) -> None:
                received.append(event)

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[RecordingExtension()]):
            extensions = wire_extensions(bus, config_paths=["fake:Extension"])

        assert len(extensions) == 1

        # Emit a raw dict event (as EventBus normally does)
        bus.emit({"event": "fsm.state_enter", "ts": "2026-04-02T12:00:00Z", "state": "build"})

        assert len(received) == 1
        assert isinstance(received[0], LLEvent)
        assert received[0].type == "fsm.state_enter"
        assert received[0].timestamp == "2026-04-02T12:00:00Z"
        assert received[0].payload == {"state": "build"}

    def test_wire_extensions_no_extensions(self) -> None:
        """wire_extensions with no config and no entry points returns empty list."""
        bus = EventBus()
        with patch("little_loops.extension.entry_points", return_value=[]):
            extensions = wire_extensions(bus)

        assert extensions == []
        # Bus should still work normally
        received: list[dict[str, Any]] = []
        bus.register(lambda e: received.append(e))
        bus.emit({"event": "test", "ts": "now"})
        assert len(received) == 1

    def test_wire_extensions_failed_load_doesnt_crash(self) -> None:
        """wire_extensions handles failed extension loads gracefully."""
        bus = EventBus()
        with patch("little_loops.extension.entry_points", return_value=[]):
            extensions = wire_extensions(bus, config_paths=["nonexistent.module:FakeExtension"])

        assert extensions == []

    def test_wire_extensions_preserves_original_event(self) -> None:
        """wire_extensions wrapper uses from_raw_event to avoid mutating the shared dict."""
        received_events: list[LLEvent] = []

        class RecordingExtension:
            def on_event(self, event: LLEvent) -> None:
                received_events.append(event)

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[RecordingExtension()]):
            wire_extensions(bus, config_paths=["fake:Extension"])

        raw = {"event": "state_enter", "ts": "2026-04-02T12:00:00Z", "state": "build"}
        bus.emit(raw)

        # Original dict should not be mutated
        assert "event" in raw
        assert "ts" in raw
        assert len(received_events) == 1

    def test_wire_extensions_multiple_extensions(self) -> None:
        """wire_extensions registers multiple extensions on the same bus."""
        received_a: list[LLEvent] = []
        received_b: list[LLEvent] = []

        class ExtA:
            def on_event(self, event: LLEvent) -> None:
                received_a.append(event)

        class ExtB:
            def on_event(self, event: LLEvent) -> None:
                received_b.append(event)

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[ExtA(), ExtB()]):
            extensions = wire_extensions(bus)

        assert len(extensions) == 2

        bus.emit({"event": "test", "ts": "now", "data": 1})

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0].type == "test"
        assert received_b[0].type == "test"

    def test_wire_extensions_passes_event_filter(self) -> None:
        """wire_extensions forwards event_filter from extension to bus.register()."""
        received: list[LLEvent] = []

        class FilteredExtension:
            event_filter = "issue.*"

            def on_event(self, event: LLEvent) -> None:
                received.append(event)

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[FilteredExtension()]):
            wire_extensions(bus, config_paths=["fake:Extension"])

        bus.emit({"event": "issue.closed", "ts": "now"})
        bus.emit({"event": "state_enter", "ts": "now"})

        assert len(received) == 1
        assert received[0].type == "issue.closed"

    def test_wire_extensions_no_event_filter_receives_all(self) -> None:
        """wire_extensions without event_filter on extension receives all events."""
        received: list[LLEvent] = []

        class UnfilteredExtension:
            def on_event(self, event: LLEvent) -> None:
                received.append(event)

        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[UnfilteredExtension()]):
            wire_extensions(bus, config_paths=["fake:Extension"])

        bus.emit({"event": "issue.closed", "ts": "now"})
        bus.emit({"event": "state_enter", "ts": "now"})

        assert len(received) == 2


class TestNewProtocols:
    """Structural compliance tests for InterceptorExtension, ActionProviderExtension,
    EvaluatorProviderExtension, and the IssueInfo import smoke test."""

    def test_smoke_import_interceptor_extension(self) -> None:
        """Importing InterceptorExtension from public API succeeds (no circular import)."""
        from little_loops import InterceptorExtension  # noqa: F401 — import is the test

        assert InterceptorExtension is not None

    def test_smoke_import_action_provider_extension(self) -> None:
        """Importing ActionProviderExtension from public API succeeds."""
        from little_loops import ActionProviderExtension  # noqa: F401

        assert ActionProviderExtension is not None

    def test_smoke_import_evaluator_provider_extension(self) -> None:
        """Importing EvaluatorProviderExtension from public API succeeds."""
        from little_loops import EvaluatorProviderExtension  # noqa: F401

        assert EvaluatorProviderExtension is not None

    def test_smoke_import_route_context(self) -> None:
        """Importing RouteContext from public API succeeds (no circular import)."""
        from little_loops import RouteContext  # noqa: F401

        assert RouteContext is not None

    def test_smoke_import_route_decision(self) -> None:
        """Importing RouteDecision from public API succeeds (no circular import)."""
        from little_loops import RouteDecision  # noqa: F401

        assert RouteDecision is not None

    def test_interceptor_extension_protocol_satisfied(self) -> None:
        """A class with before_route, after_route, before_issue_close satisfies the protocol."""
        from little_loops.extension import InterceptorExtension

        class MyInterceptor:
            def before_route(self, context: object) -> object:
                return None

            def after_route(self, context: object) -> None:
                pass

            def before_issue_close(self, info: object) -> None:
                return None

        interceptor = MyInterceptor()
        # Structural typing: instance should be usable as the protocol type
        _: InterceptorExtension = interceptor  # type: ignore[assignment]

    def test_action_provider_extension_protocol_satisfied(self) -> None:
        """A class with provided_actions() satisfies ActionProviderExtension."""
        from little_loops.extension import ActionProviderExtension

        class MyActionProvider:
            def provided_actions(self) -> dict:
                return {}

        provider = MyActionProvider()
        _: ActionProviderExtension = provider  # type: ignore[assignment]

    def test_evaluator_provider_extension_protocol_satisfied(self) -> None:
        """A class with provided_evaluators() satisfies EvaluatorProviderExtension."""
        from little_loops.extension import EvaluatorProviderExtension

        class MyEvaluatorProvider:
            def provided_evaluators(self) -> dict:
                return {}

        provider = MyEvaluatorProvider()
        _: EvaluatorProviderExtension = provider  # type: ignore[assignment]
