"""BUG-3755: live FSM events reach the sqlite and otel transports with their loop identity.

``FSMExecutor._emit`` stamps every event with ``loop`` (ENH-3345), but both
transports read ``loop_name``. The transport tests hand-fed ``{"loop_name": ...}``
dicts, a shape the executor never emits, so the suites stayed green while every
live ``loop_events`` row had a NULL loop name and every OTel loop span was named
``ll-loop``. These tests drive a real executor through its event bus instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from little_loops.events import event_loop_name
from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import PersistentExecutor
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig
from little_loops.session_store import SQLiteTransport, recent

try:
    import opentelemetry.sdk.trace  # noqa: F401

    _HAS_OTEL_SDK = True
except ImportError:
    _HAS_OTEL_SDK = False

LOOP = "bug3755-loop"


class _Runner:
    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=1)


def _run_loop(tmp_path: Path, *transports: Any) -> None:
    fsm = FSMLoop(
        name=LOOP,
        initial="work",
        states={
            "work": StateConfig(
                action="echo work",
                action_type="shell",
                evaluate=EvaluateConfig(type="exit_code"),
                on_yes="done",
                on_no="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )
    executor = PersistentExecutor(fsm, loops_dir=tmp_path / ".loops", action_runner=_Runner())
    for transport in transports:
        executor.event_bus.add_transport(transport)
    executor.run()
    executor.event_bus.close_transports()


class TestEventLoopName:
    def test_prefers_executor_stamped_loop(self) -> None:
        assert event_loop_name({"loop": "a", "loop_name": "b"}) == "a"

    def test_falls_back_to_legacy_loop_name(self) -> None:
        assert event_loop_name({"loop_name": "b"}) == "b"

    def test_missing_is_none(self) -> None:
        assert event_loop_name({"event": "state_enter"}) is None


class TestSQLiteTransportLiveLoop:
    def test_live_rows_carry_loop_name_and_route_source_state(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _run_loop(tmp_path, SQLiteTransport(db))
        rows = recent(db, kind="loop", limit=100)
        assert rows, "the executor emitted no recognised loop events"
        assert {row["loop_name"] for row in rows} == {LOOP}
        routes = [row for row in rows if row["transition"] == "route"]
        assert routes, "the loop emitted no route event"
        assert all(row["state"] == "work" for row in routes)


@pytest.mark.skipif(not _HAS_OTEL_SDK, reason="opentelemetry-sdk not installed")
class TestOTelTransportLiveLoop:
    def test_loop_span_is_named_after_the_loop(self, tmp_path: Path) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        from little_loops.transport import OTelTransport

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        _run_loop(tmp_path, OTelTransport(_tracer_provider=provider))
        names = [span.name for span in exporter.get_finished_spans()]
        assert LOOP in names
        assert "ll-loop" not in names
