"""Tests for LLEvent dataclass and EventBus multi-observer dispatcher."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from little_loops.events import EventBus, LLEvent


class TestLLEvent:
    """Tests for the LLEvent dataclass."""

    def test_creation(self) -> None:
        """LLEvent can be constructed with type, timestamp, payload."""
        event = LLEvent(
            type="fsm.state_enter", timestamp="2026-04-02T12:00:00Z", payload={"state": "build"}
        )
        assert event.type == "fsm.state_enter"
        assert event.timestamp == "2026-04-02T12:00:00Z"
        assert event.payload == {"state": "build"}

    def test_to_dict(self) -> None:
        """to_dict produces flat dict with event/ts keys plus payload spread."""
        event = LLEvent(
            type="fsm.loop_complete",
            timestamp="2026-04-02T12:05:00Z",
            payload={"final_state": "done", "iterations": 3},
        )
        d = event.to_dict()
        assert d["event"] == "fsm.loop_complete"
        assert d["ts"] == "2026-04-02T12:05:00Z"
        assert d["final_state"] == "done"
        assert d["iterations"] == 3
        # Should not have nested "payload" key
        assert "payload" not in d
        assert "type" not in d
        assert "timestamp" not in d

    def test_to_dict_json_serializable(self) -> None:
        """to_dict output is JSON serializable."""
        event = LLEvent(type="test", timestamp="2026-01-01T00:00:00Z", payload={"x": 1})
        json.dumps(event.to_dict())  # Should not raise

    def test_from_dict(self) -> None:
        """from_dict reconstructs LLEvent from a flat dict."""
        raw = {"event": "fsm.route", "ts": "2026-04-02T12:00:00Z", "from": "check", "to": "fix"}
        event = LLEvent.from_dict(raw)
        assert event.type == "fsm.route"
        assert event.timestamp == "2026-04-02T12:00:00Z"
        assert event.payload == {"from": "check", "to": "fix"}

    def test_from_dict_missing_fields(self) -> None:
        """from_dict handles missing event/ts with defaults."""
        raw = {"some_key": "some_value"}
        event = LLEvent.from_dict(raw)
        assert event.type == "unknown"
        assert event.timestamp == ""
        assert event.payload == {"some_key": "some_value"}

    def test_roundtrip(self) -> None:
        """to_dict -> from_dict roundtrip preserves data."""
        original = LLEvent(
            type="fsm.evaluate",
            timestamp="2026-04-02T12:00:00Z",
            payload={"verdict": "yes", "confidence": 0.95},
        )
        restored = LLEvent.from_dict(original.to_dict())
        assert restored.type == original.type
        assert restored.timestamp == original.timestamp
        assert restored.payload == original.payload

    def test_from_raw_event(self) -> None:
        """from_raw_event converts existing executor event dict format."""
        raw = {
            "event": "state_enter",
            "ts": "2026-04-02T12:00:00Z",
            "state": "build",
            "iteration": 1,
        }
        event = LLEvent.from_raw_event(raw)
        assert event.type == "state_enter"
        assert event.timestamp == "2026-04-02T12:00:00Z"
        assert event.payload == {"state": "build", "iteration": 1}
        # Original dict should not be mutated
        assert "event" in raw
        assert "ts" in raw


class TestEventBus:
    """Tests for EventBus multi-observer dispatcher."""

    def test_register_and_emit(self) -> None:
        """Registered callback receives emitted events."""
        received: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received.append(e))

        bus.emit({"event": "test", "ts": "now", "data": 1})

        assert len(received) == 1
        assert received[0]["event"] == "test"
        assert received[0]["data"] == 1

    def test_multiple_observers(self) -> None:
        """All registered observers receive each event."""
        received_a: list[dict[str, Any]] = []
        received_b: list[dict[str, Any]] = []
        bus = EventBus()
        bus.register(lambda e: received_a.append(e))
        bus.register(lambda e: received_b.append(e))

        bus.emit({"event": "test", "ts": "now"})

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_unregister(self) -> None:
        """Unregistered observer stops receiving events."""
        received: list[dict[str, Any]] = []
        callback = lambda e: received.append(e)  # noqa: E731
        bus = EventBus()
        bus.register(callback)
        bus.emit({"event": "first", "ts": "now"})
        bus.unregister(callback)
        bus.emit({"event": "second", "ts": "now"})

        assert len(received) == 1
        assert received[0]["event"] == "first"

    def test_emit_no_observers(self) -> None:
        """Emit with no observers does not raise."""
        bus = EventBus()
        bus.emit({"event": "test", "ts": "now"})  # Should not raise

    def test_observer_exception_isolated(self) -> None:
        """One observer's exception does not block others."""
        received: list[dict[str, Any]] = []

        def bad_observer(event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        bus = EventBus()
        bus.register(bad_observer)
        bus.register(lambda e: received.append(e))

        bus.emit({"event": "test", "ts": "now"})

        # Second observer still received the event
        assert len(received) == 1

    def test_observer_exception_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Observer exceptions are logged."""

        def bad_observer(event: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        bus = EventBus()
        bus.register(bad_observer)

        with caplog.at_level(logging.WARNING):
            bus.emit({"event": "test", "ts": "now"})

        assert any("observer raised an exception" in record.message for record in caplog.records)

    def test_file_sink(self, tmp_path: Path) -> None:
        """EventBus can write events to a JSONL file sink."""
        log_file = tmp_path / "events.jsonl"
        bus = EventBus()
        bus.add_file_sink(log_file)

        bus.emit({"event": "first", "ts": "t1", "x": 1})
        bus.emit({"event": "second", "ts": "t2", "x": 2})

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    def test_file_sink_reads_back(self, tmp_path: Path) -> None:
        """Events written to file sink can be read back as LLEvents."""
        log_file = tmp_path / "events.jsonl"
        bus = EventBus()
        bus.add_file_sink(log_file)

        bus.emit({"event": "fsm.state_enter", "ts": "2026-04-02T12:00:00Z", "state": "build"})

        events = EventBus.read_events(log_file)
        assert len(events) == 1
        assert events[0].type == "fsm.state_enter"
        assert events[0].payload["state"] == "build"

    def test_read_events_nonexistent_file(self, tmp_path: Path) -> None:
        """read_events returns empty list for nonexistent file."""
        events = EventBus.read_events(tmp_path / "missing.jsonl")
        assert events == []

    def test_read_events_skips_malformed(self, tmp_path: Path) -> None:
        """read_events skips malformed JSON lines."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            '{"event": "good", "ts": "t1"}\nnot-json\n{"event": "also_good", "ts": "t2"}\n'
        )

        events = EventBus.read_events(log_file)
        assert len(events) == 2
        assert events[0].type == "good"
        assert events[1].type == "also_good"
