"""Tests for the Transport Protocol, JsonlTransport, and wire_transports()."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from little_loops.config.features import EventsConfig
from little_loops.events import EventBus
from little_loops.transport import JsonlTransport, Transport, wire_transports


class TestTransportProtocol:
    """Tests for the Transport Protocol."""

    def test_protocol_satisfied_by_class_with_send_and_close(self) -> None:
        """A class with send and close satisfies the Protocol via runtime_checkable."""

        class MyTransport:
            def send(self, event: dict[str, Any]) -> None:
                pass

            def close(self) -> None:
                pass

        t = MyTransport()
        assert isinstance(t, Transport)

    def test_jsonl_transport_satisfies_protocol(self, tmp_path: Path) -> None:
        """JsonlTransport instances satisfy the Transport Protocol."""
        t = JsonlTransport(tmp_path / "out.jsonl")
        assert isinstance(t, Transport)

    def test_protocol_rejects_class_without_send(self) -> None:
        """A class missing send is not a Transport."""

        class NotTransport:
            def close(self) -> None:
                pass

        assert not isinstance(NotTransport(), Transport)


class TestJsonlTransport:
    """Tests for JsonlTransport implementation."""

    def test_send_appends_jsonl(self, tmp_path: Path) -> None:
        """send() appends each event as a JSON line."""
        path = tmp_path / "events.jsonl"
        t = JsonlTransport(path)
        t.send({"event": "first", "ts": "t1", "x": 1})
        t.send({"event": "second", "ts": "t2", "x": 2})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    def test_init_creates_parent_directory(self, tmp_path: Path) -> None:
        """JsonlTransport.__init__ creates parent directories if missing."""
        path = tmp_path / "nested" / "deep" / "events.jsonl"
        JsonlTransport(path)
        assert path.parent.exists()

    def test_close_is_noop(self, tmp_path: Path) -> None:
        """close() is a no-op and may be called repeatedly."""
        t = JsonlTransport(tmp_path / "events.jsonl")
        t.close()
        t.close()  # Idempotent


class TestEventBusTransports:
    """Tests for EventBus transport fan-out."""

    def test_add_transport_and_emit(self, tmp_path: Path) -> None:
        """Events emitted on the bus are dispatched to registered transports."""
        path = tmp_path / "events.jsonl"
        bus = EventBus()
        bus.add_transport(JsonlTransport(path))

        bus.emit({"event": "first", "ts": "t1"})
        bus.emit({"event": "second", "ts": "t2"})

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_multiple_transports_each_receive_event(self, tmp_path: Path) -> None:
        """All registered transports receive each emitted event."""
        path_a = tmp_path / "a.jsonl"
        path_b = tmp_path / "b.jsonl"
        bus = EventBus()
        bus.add_transport(JsonlTransport(path_a))
        bus.add_transport(JsonlTransport(path_b))

        bus.emit({"event": "x", "ts": "t"})

        assert path_a.read_text().strip()
        assert path_b.read_text().strip()

    def test_transport_exception_isolated(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One transport's exception does not stop others or propagate."""
        captured: list[dict[str, Any]] = []

        class BadTransport:
            def send(self, event: dict[str, Any]) -> None:
                raise RuntimeError("boom")

            def close(self) -> None:
                pass

        class RecordingTransport:
            def send(self, event: dict[str, Any]) -> None:
                captured.append(event)

            def close(self) -> None:
                pass

        bus = EventBus()
        bus.add_transport(BadTransport())
        bus.add_transport(RecordingTransport())

        with caplog.at_level(logging.WARNING):
            bus.emit({"event": "test", "ts": "now"})

        # Second transport still received the event
        assert len(captured) == 1
        # And the exception was logged, not propagated
        assert any("transport" in record.message.lower() for record in caplog.records)

    def test_close_transports_calls_close_on_each(self) -> None:
        """close_transports() invokes close() on every registered transport."""
        closed: list[str] = []

        class CountingTransport:
            def __init__(self, name: str) -> None:
                self.name = name

            def send(self, event: dict[str, Any]) -> None:
                pass

            def close(self) -> None:
                closed.append(self.name)

        bus = EventBus()
        bus.add_transport(CountingTransport("a"))
        bus.add_transport(CountingTransport("b"))

        bus.close_transports()
        assert closed == ["a", "b"]


class TestWireTransports:
    """Tests for the wire_transports() registry helper."""

    def test_jsonl_registered_by_name(self, tmp_path: Path) -> None:
        """The jsonl transport is registered and wires up successfully."""
        bus = EventBus()
        config = EventsConfig(transports=["jsonl"])
        wire_transports(bus, config, log_dir=tmp_path)

        # After wiring, emitting should produce a file
        bus.emit({"event": "first", "ts": "t"})
        bus.close_transports()

        # JsonlTransport writes somewhere under tmp_path
        files = list(tmp_path.rglob("*.jsonl"))
        assert files, "expected JsonlTransport to write at least one file"

    def test_unknown_transport_warns_and_skips(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unknown transport names log a warning and are skipped."""
        bus = EventBus()
        config = EventsConfig(transports=["mystery"])

        with caplog.at_level(logging.WARNING):
            wire_transports(bus, config, log_dir=tmp_path)

        assert any("mystery" in record.message for record in caplog.records)

    def test_empty_transports_is_noop(self, tmp_path: Path) -> None:
        """Empty transports list does not register anything."""
        bus = EventBus()
        config = EventsConfig(transports=[])
        wire_transports(bus, config, log_dir=tmp_path)
        # No files produced
        bus.emit({"event": "x", "ts": "t"})
        assert not list(tmp_path.rglob("*.jsonl"))
