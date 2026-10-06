"""BUG-3755: live FSM events reach the sqlite and otel transports with their loop identity.

``FSMExecutor._emit`` stamps every event with ``loop`` (ENH-3345), but both
transports read ``loop_name``. The transport tests hand-fed ``{"loop_name": ...}``
dicts, a shape the executor never emits, so the suites stayed green while every
live ``loop_events`` row had a NULL loop name and every OTel loop span was named
``ll-loop``. These tests drive a real executor through its event bus instead.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from little_loops.events import event_loop_name
from little_loops.fsm.executor import ActionResult
from little_loops.fsm.persistence import LoopState, PersistentExecutor
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig
from little_loops.session_store import SQLiteTransport, recent, search

try:
    import opentelemetry.sdk.trace  # noqa: F401

    _HAS_OTEL_SDK = True
except ImportError:
    _HAS_OTEL_SDK = False

LOOP = "bug3755-loop"


class _Runner:
    def run(self, action: str, timeout: int, is_slash_command: bool, **kwargs: Any) -> ActionResult:
        return ActionResult(output="ok", stderr="", exit_code=0, duration_ms=1)


def _run_loop(
    tmp_path: Path,
    *transports: Any,
    resume: bool = False,
    before_close: Callable[[list[dict[str, Any]]], None] | None = None,
) -> None:
    """Drive a real executor; ``resume`` restarts a saved interrupted state.

    ``before_close`` receives every bus event after the run, before transports close.
    """
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
    bus_events: list[dict[str, Any]] = []
    executor.event_bus.register(bus_events.append)
    try:
        if resume:
            executor.persistence.initialize()
            executor.persistence.save_state(
                LoopState(
                    loop_name=LOOP,
                    current_state="work",
                    iteration=1,
                    captured={},
                    prev_result=None,
                    last_result=None,
                    started_at="2024-01-15T10:30:00Z",
                    updated_at="",
                    status="interrupted",
                )
            )
            assert executor.resume() is not None
        else:
            executor.run()
        if before_close is not None:
            before_close(bus_events)
    finally:
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

    def test_route_rows_record_the_target_state(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _run_loop(tmp_path, SQLiteTransport(db))
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT transition, state, to_state FROM loop_events ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert ("route", "work", "done") in rows
        assert all(to_state is None for transition, _, to_state in rows if transition != "route")

    def test_route_is_searchable_by_destination(self, tmp_path: Path) -> None:
        """BUG-3758: the real work -> done route's FTS content carries both endpoints."""
        db = tmp_path / "history.db"
        _run_loop(tmp_path, SQLiteTransport(db))
        expected = f"{LOOP} work route done"
        for query in ("work route done", "work route"):
            hits = [r for r in search(db, query=query) if r["content"] == expected]
            assert len(hits) == 1, query
            assert hits[0]["kind"] == "loop"
            assert hits[0]["ref"] == LOOP
            assert hits[0]["anchor"] == f".loops/{LOOP}.yaml"
        rows = recent(db, kind="loop", limit=100)
        route = [r for r in rows if r["transition"] == "route"]
        assert [(r["state"], r["to_state"]) for r in route] == [("work", "done")]


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

    def test_resume_exports_both_roots_before_close(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """BUG-3759: loop_resume then loop_start each open a root; both are ended and exported."""
        pytest.importorskip("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
        from opentelemetry import context as otel_context
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON
        from opentelemetry.trace import StatusCode

        from little_loops.transport import OTelTransport

        exporter = InMemorySpanExporter()
        provider = TracerProvider(sampler=ALWAYS_ON)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        observed: dict[str, Any] = {}

        def observe(events: list[dict[str, Any]]) -> None:
            observed["types"] = [e["event"] for e in events]
            observed["finished"] = list(exporter.get_finished_spans())

        token = otel_context.attach(otel_context.Context())
        try:
            with caplog.at_level(logging.WARNING):
                _run_loop(
                    tmp_path,
                    OTelTransport(_tracer_provider=provider),
                    resume=True,
                    before_close=observe,
                )
        finally:
            otel_context.detach(token)
            provider.shutdown()

        types = observed["types"]
        assert types.index("loop_resume") < types.index("loop_start") < types.index("state_enter")
        opening = {"loop_resume", "loop_start", "state_enter", "action_start"}
        finished = observed["finished"]
        assert len(finished) == sum(1 for t in types if t in opening)

        roots = [s for s in finished if s.parent is None]
        assert [s.name for s in roots] == [LOOP, LOOP]
        assert roots[0].context.span_id != roots[1].context.span_id
        resume_root, start_root = roots
        assert resume_root.status.status_code == StatusCode.UNSET
        assert "ll.terminated_by" not in resume_root.attributes
        assert "ll.final_status" not in resume_root.attributes
        assert start_root.status.status_code == StatusCode.OK
        assert start_root.attributes["ll.final_status"] == "completed"
        children = [s for s in finished if s.parent is not None]
        assert children
        assert {s.parent.span_id for s in children if s.name == "work"} == {
            start_root.context.span_id
        }
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
