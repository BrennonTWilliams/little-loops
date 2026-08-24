"""Tests for little_loops.session_store — queries module."""

from __future__ import annotations

import argparse
import itertools
import re
from pathlib import Path

import pytest

from little_loops.session_store import (
    SQLiteTransport,
    connect,
    ensure_db,
    recent,
    record_correction,
    search,
)

# ENH-2529: consolidate per-test temp dirs under one module-scoped parent to cut
# macOS launchservicesd/mds re-indexing churn during full-suite runs. Each test
# still gets a fresh, unique directory; only the parent dir consolidates.
_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("session_store")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


class TestSearch:
    """FTS5 full-text search."""

    def test_search_returns_ranked_match(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "rate-limit-loop", "state": "wait"})
        transport.close()
        results = search(db, query="rate")
        assert results
        assert results[0]["kind"] == "loop"
        assert "score" in results[0]

    def test_search_no_match_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        assert search(db, query="nonexistentterm") == []

    def test_search_respects_limit(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        for i in range(5):
            transport.send({"event": "state_enter", "loop_name": "loopname", "state": f"s{i}"})
        transport.close()
        assert len(search(db, query="loopname", limit=2)) == 2

    def test_search_hyphenated_id_matches(self, tmp_path: Path) -> None:
        """Hyphenated issue IDs must match literally, not raise ValueError
        via FTS operator parsing (BUG-2651)."""
        db = tmp_path / "session.db"
        record_correction(db, "sess-h1", "Fixed BUG-490 in the parser", "user")
        results = search(db, query="BUG-490")
        assert results
        assert "BUG-490" in results[0]["content"]


class TestRecent:
    """The recent() query helper."""

    def test_unknown_kind_raises(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        try:
            recent(db, kind="bogus")
        except ValueError as exc:
            assert "bogus" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")

    def test_recent_orders_newest_first(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "first", "state": "a"})
        transport.send({"event": "state_enter", "loop_name": "second", "state": "b"})
        transport.close()
        rows = recent(db, kind="loop")
        assert rows[0]["loop_name"] == "second"


class TestToolEventsByteColumns:
    """FEAT-1624: read-side verification of the FEAT-1623 byte columns.

    ``test_hook_post_tool_use.py::TestPostToolUseWithSessionStore`` covers the
    write side (hook handler populates ``bytes_in``/``bytes_out``/``cache_hit``).
    These tests confirm the values survive a ``connect()`` + ``recent(kind=
    "tool")`` round-trip — what the ``ll-ctx-stats`` aggregator depends on.
    """

    def test_recent_tool_returns_byte_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit) "
                "VALUES('2026-05-22T00:00:00Z', 's1', 'Read', 'h', 42, 7, 42, 1)"
            )
            conn.commit()
        finally:
            conn.close()
        rows = recent(db, kind="tool")
        assert len(rows) == 1
        row = rows[0]
        assert row["tool_name"] == "Read"
        assert row["bytes_in"] == 7
        assert row["bytes_out"] == 42
        assert row["cache_hit"] == 1

    def test_recent_tool_preserves_null_byte_columns(self, tmp_path: Path) -> None:
        """Backfilled rows have NULL bytes_in/bytes_out — ``recent()`` must surface that."""
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit) "
                "VALUES('2026-05-22T00:00:00Z', 's1', 'Bash', 'h', NULL, NULL, NULL, NULL)"
            )
            conn.commit()
        finally:
            conn.close()
        rows = recent(db, kind="tool")
        assert rows[0]["bytes_in"] is None
        assert rows[0]["bytes_out"] is None
        assert rows[0]["cache_hit"] is None


class TestExportContextPressureEvent:
    """ENH-2507 wiring: context_pressure_event participates in export_history()."""

    def test_included_in_default_export(self, tmp_path: Path) -> None:
        from little_loops.session_store import export_history, record_context_pressure_event

        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="s1", used_pct=10.0, used_tokens_est=1000)
        types = {row["type"] for row in export_history(db)}
        assert "context_pressure_event" in types

    def test_explicit_table_selection(self, tmp_path: Path) -> None:
        from little_loops.session_store import export_history, record_context_pressure_event

        db = tmp_path / "history.db"
        record_context_pressure_event(db, session_id="s1", used_pct=10.0, used_tokens_est=1000)
        rows = list(export_history(db, tables=["context_pressure_event"]))
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"


class TestExportAdvisorConsultEvent:
    """FEAT-3300 wiring: advisor_consult_event participates in export_history()."""

    def test_included_in_default_export(self, tmp_path: Path) -> None:
        from little_loops.session_store import export_history, write_advisor_consult

        db = tmp_path / "history.db"
        write_advisor_consult(
            db,
            session_id="s1",
            task_key="session:abc",
            signal="pre_done",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
        )
        types = {row["type"] for row in export_history(db)}
        assert "advisor_consult_event" in types

    def test_explicit_table_selection(self, tmp_path: Path) -> None:
        from little_loops.session_store import export_history, write_advisor_consult

        db = tmp_path / "history.db"
        write_advisor_consult(
            db,
            session_id="s1",
            task_key="session:abc",
            signal="pre_done",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
        )
        rows = list(export_history(db, tables=["advisor_consult_event"]))
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s1"


class TestExportTableRegistration:
    """BUG-3197: the advertised table set must not drift from the accepted one."""

    def test_message_event_is_the_only_non_default_table(self) -> None:
        """Pins the invariant ENH-2463 silently broke by adding loop_run to the
        map but not the defaults. A new table added to only one list fails here.
        """
        from little_loops.session_store.queries import (
            _EXPORT_DEFAULT_TABLES,
            _EXPORT_TABLE_MAP,
        )

        assert set(_EXPORT_TABLE_MAP) - set(_EXPORT_DEFAULT_TABLES) == {"message_event"}
        # Defaults must not name a type the map cannot resolve.
        assert set(_EXPORT_DEFAULT_TABLES) <= set(_EXPORT_TABLE_MAP)

    def test_help_text_advertises_every_map_key(self) -> None:
        from little_loops.session_store import export_tables_help
        from little_loops.session_store.queries import _EXPORT_TABLE_MAP

        text = export_tables_help()
        advertised = {t.strip() for t in text.split("Choices:")[1].split(",")}
        assert advertised == set(_EXPORT_TABLE_MAP)

    def test_help_text_derives_the_excluded_set(self) -> None:
        from little_loops.session_store import export_tables_help

        assert "default: all types except message_event" in export_tables_help()

    def test_parser_uses_the_derived_help(self) -> None:
        """Assert on the action's help attribute, not rendered --help output —
        argparse line-wraps to terminal width, which makes scraping brittle.
        """
        from little_loops.cli.session import _build_parser
        from little_loops.session_store import export_tables_help

        subparsers = next(
            a for a in _build_parser()._actions if isinstance(a, argparse._SubParsersAction)
        )
        tables = next(a for a in subparsers.choices["export"]._actions if a.dest == "tables")
        assert tables.help == export_tables_help()

    def test_loop_run_included_in_default_export(self, tmp_path: Path) -> None:
        from little_loops.session_store import export_history, record_loop_run_summary

        db = tmp_path / "history.db"
        record_loop_run_summary(db, run_id="r1", loop_name="demo", final_state="done")
        types = {row["type"] for row in export_history(db)}
        assert "loop_run" in types
