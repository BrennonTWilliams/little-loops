"""Tests for little_loops.testing.LLTestBus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops import LLTestBus
from little_loops.events import LLEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def events_jsonl(tmp_path: Path) -> Path:
    """Write a minimal LLEvent wire-format JSONL fixture file."""
    events_file = tmp_path / "test-loop.events.jsonl"
    events = [
        {"event": "loop_start", "ts": "2025-01-01T00:00:00", "loop": "test-loop"},
        {"event": "state_enter", "ts": "2025-01-01T00:00:01", "state": "check", "iteration": 1},
        {"event": "action_start", "ts": "2025-01-01T00:00:02", "action": "echo hello"},
        {"event": "issue.closed", "ts": "2025-01-01T00:00:03", "issue": "BUG-001"},
        {"event": "loop_complete", "ts": "2025-01-01T00:00:04", "loop": "test-loop"},
    ]
    with open(events_file, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return events_file


# ---------------------------------------------------------------------------
# Helper extension classes
# ---------------------------------------------------------------------------


class _RecordingExtension:
    """Captures all events it receives."""

    def __init__(self) -> None:
        self.received: list[LLEvent] = []

    def on_event(self, event: LLEvent) -> None:
        self.received.append(event)


class _FilteredExtension:
    """Only receives events matching event_filter."""

    event_filter = "issue.*"

    def __init__(self) -> None:
        self.received: list[LLEvent] = []

    def on_event(self, event: LLEvent) -> None:
        self.received.append(event)


class _MultiFilterExtension:
    """Receives events matching any of several patterns."""

    event_filter = ["loop_*", "issue.*"]

    def __init__(self) -> None:
        self.received: list[LLEvent] = []

    def on_event(self, event: LLEvent) -> None:
        self.received.append(event)


# ---------------------------------------------------------------------------
# from_jsonl tests
# ---------------------------------------------------------------------------


class TestFromJsonl:
    def test_loads_events_from_existing_file(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        # 5 events defined in fixture
        assert len(bus._events) == 5

    def test_accepts_str_path(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(str(events_jsonl))
        assert len(bus._events) == 5

    def test_returns_empty_bus_for_missing_file(self, tmp_path: Path) -> None:
        bus = LLTestBus.from_jsonl(tmp_path / "nonexistent.events.jsonl")
        assert bus._events == []

    def test_event_types_parsed_correctly(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        types = [e.type for e in bus._events]
        assert types == [
            "loop_start",
            "state_enter",
            "action_start",
            "issue.closed",
            "loop_complete",
        ]


# ---------------------------------------------------------------------------
# replay tests
# ---------------------------------------------------------------------------


class TestReplay:
    def test_replay_with_no_extensions_does_nothing(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        bus.replay()  # must not raise
        assert bus.delivered_events == []

    def test_unfiltered_extension_receives_all_events(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _RecordingExtension()
        bus.register(ext)
        bus.replay()

        assert len(ext.received) == 5
        assert ext.received[0].type == "loop_start"

    def test_delivered_events_matches_extension_received(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _RecordingExtension()
        bus.register(ext)
        bus.replay()

        assert bus.delivered_events == ext.received

    def test_filtered_extension_receives_only_matching_events(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _FilteredExtension()
        bus.register(ext)
        bus.replay()

        # Only "issue.closed" matches "issue.*"
        assert len(ext.received) == 1
        assert ext.received[0].type == "issue.closed"

    def test_delivered_events_contains_only_filtered_matches(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _FilteredExtension()
        bus.register(ext)
        bus.replay()

        assert len(bus.delivered_events) == 1
        assert bus.delivered_events[0].type == "issue.closed"

    def test_multi_pattern_filter_matches_multiple_types(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _MultiFilterExtension()
        bus.register(ext)
        bus.replay()

        # "loop_*" matches loop_start, loop_complete; "issue.*" matches issue.closed
        received_types = [e.type for e in ext.received]
        assert "loop_start" in received_types
        assert "loop_complete" in received_types
        assert "issue.closed" in received_types
        assert "state_enter" not in received_types
        assert "action_start" not in received_types
        assert len(ext.received) == 3

    def test_multiple_extensions_receive_independently(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        unfiltered = _RecordingExtension()
        filtered = _FilteredExtension()
        bus.register(unfiltered)
        bus.register(filtered)
        bus.replay()

        assert len(unfiltered.received) == 5
        assert len(filtered.received) == 1
        # All 5 events delivered (unfiltered extension gets them all)
        assert len(bus.delivered_events) == 5

    def test_replay_resets_delivered_events_on_second_call(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _RecordingExtension()
        bus.register(ext)
        bus.replay()
        first_count = len(bus.delivered_events)
        bus.replay()
        # delivered_events is reset, not accumulated
        assert len(bus.delivered_events) == first_count

    def test_event_payload_preserved(self, events_jsonl: Path) -> None:
        bus = LLTestBus.from_jsonl(events_jsonl)
        ext = _RecordingExtension()
        bus.register(ext)
        bus.replay()

        loop_start = next(e for e in ext.received if e.type == "loop_start")
        assert loop_start.payload.get("loop") == "test-loop"

    def test_empty_bus_replay_is_noop(self, tmp_path: Path) -> None:
        bus = LLTestBus.from_jsonl(tmp_path / "missing.events.jsonl")
        ext = _RecordingExtension()
        bus.register(ext)
        bus.replay()

        assert ext.received == []
        assert bus.delivered_events == []

    def test_string_event_filter_normalization(self, tmp_path: Path) -> None:
        """A str event_filter is treated as a single glob pattern."""
        events_file = tmp_path / "e.jsonl"
        with open(events_file, "w") as f:
            f.write(json.dumps({"event": "state_enter", "ts": "2025-01-01T00:00:00"}) + "\n")
            f.write(json.dumps({"event": "state_exit", "ts": "2025-01-01T00:00:01"}) + "\n")

        class StateExtension:
            event_filter = "state_*"

            def __init__(self) -> None:
                self.received: list[LLEvent] = []

            def on_event(self, event: LLEvent) -> None:
                self.received.append(event)

        bus = LLTestBus.from_jsonl(events_file)
        ext = StateExtension()
        bus.register(ext)
        bus.replay()

        assert len(ext.received) == 2
