"""Tests for cli/ctx_stats.py - ll-ctx-stats CLI entry point."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.ctx_stats import (
    _aggregate_tool_events,
    _build_parser,
    _parse_args,
    _progress_bar,
    _time_gained,
    main_ctx_stats,
)
from little_loops.session_store import connect, ensure_db


def _capture_print() -> tuple[list[str], object]:
    """Return (lines, side_effect) for capturing print() calls including no-arg ones."""
    lines: list[str] = []
    return lines, lambda *a, **_kw: lines.append(str(a[0]) if a else "")


def _populate_tool_events(
    db_path: Path,
    rows: list[tuple[str, int | None, int | None, int | None]],
) -> None:
    """Insert ``(tool, bytes_in, bytes_out, cache_hit)`` rows into tool_events."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for tool, b_in, b_out, hit in rows:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, "
                "result_size, bytes_in, bytes_out, cache_hit) "
                "VALUES('2026-05-22T00:00:00Z', 's1', ?, 'h', ?, ?, ?, ?)",
                (tool, b_out, b_in, b_out, hit),
            )
        conn.commit()
    finally:
        conn.close()


class TestParser:
    """Argument parser shape."""

    def test_build_parser_returns_argument_parser(self) -> None:
        parser = _build_parser()
        assert parser.prog == "ll-ctx-stats"

    def test_default_args(self) -> None:
        args = _parse_args([])
        assert args.db is None
        assert args.json_mode is False

    def test_db_flag(self) -> None:
        args = _parse_args(["--db", "/tmp/x.db"])
        assert args.db == Path("/tmp/x.db")

    def test_json_short_flag(self) -> None:
        args = _parse_args(["-j"])
        assert args.json_mode is True


class TestProgressBar:
    """Inline progress-bar formatter."""

    def test_full_bar(self) -> None:
        bar = _progress_bar(100, 100, 12)
        assert bar.startswith("|") and bar.endswith("|")
        assert "#" * 10 in bar

    def test_half_bar(self) -> None:
        bar = _progress_bar(50, 100, 12)
        assert bar.count("#") == 5
        assert bar.count(" ") == 5

    def test_zero_ceiling(self) -> None:
        bar = _progress_bar(0, 0, 8)
        assert bar == "|" + " " * 6 + "|"


class TestTimeGained:
    """Positive-tense formatter wrapping format_relative_time."""

    def test_strips_ago_suffix(self) -> None:
        # 6m worth of seconds -> "+6m"
        assert _time_gained(360).startswith("+")
        assert " ago" not in _time_gained(360)

    def test_seconds(self) -> None:
        assert _time_gained(45) == "+45s"


class TestAggregateToolEvents:
    """SQLite aggregation helper."""

    def test_missing_db_returns_none(self, tmp_path: Path) -> None:
        assert _aggregate_tool_events(tmp_path / "nope.db") is None

    def test_filters_null_byte_rows(self, tmp_path: Path) -> None:
        """Backfilled rows with NULL bytes_in/bytes_out must not be aggregated."""
        db = tmp_path / "session.db"
        _populate_tool_events(
            db,
            [
                ("Read", 100, 200, 0),
                ("Bash", None, None, None),  # backfilled — should be skipped
                ("Read", 50, 150, 1),
            ],
        )
        summary = _aggregate_tool_events(db)
        assert summary is not None
        assert summary["total_in"] == 150
        assert summary["total_out"] == 350
        assert summary["cache_hits"] == 1
        assert summary["cache_bytes"] == 150
        assert summary["per_tool"]["read"]["calls"] == 2
        assert "bash" not in summary["per_tool"]

    def test_empty_db_returns_zero_summary(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        summary = _aggregate_tool_events(db)
        assert summary is not None
        assert summary["total_out"] == 0


class TestMainCtxStats:
    """End-to-end CLI behavior."""

    def test_returns_zero_when_data_present(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "session.db"
        db.parent.mkdir()
        _populate_tool_events(
            db,
            [
                ("Read", 200, 1024, 0),
                ("Bash", 50, 512, 1),
                ("Read", 100, 2048, 0),
            ],
        )
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "Without savings" in output
        assert "With savings" in output
        assert "%" in output  # percentage reduction line
        assert "session time gained" in output
        assert "read" in output  # per-tool breakdown
        assert "Cache:" in output  # cache metrics line

    def test_falls_back_to_state_file(self, tmp_path: Path, monkeypatch) -> None:
        """When .ll/session.db is absent, render the ll-context-state.json fallback."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "ll-context-state.json").write_text(
            json.dumps(
                {
                    "estimated_tokens": 12345,
                    "tool_calls": 7,
                    "breakdown": {"read": 1000, "bash": 500},
                }
            ),
            encoding="utf-8",
        )
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        output = "\n".join(lines)
        assert "12,345" in output or "12345" in output
        assert "read" in output

    def test_returns_one_when_no_data(self, tmp_path: Path, monkeypatch) -> None:
        """Exit 1 when neither the SQLite store nor the fallback file is present."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.argv", ["ll-ctx-stats"]),
            patch("builtins.print"),
        ):
            result = main_ctx_stats()
        assert result == 1

    def test_json_mode(self, tmp_path: Path, monkeypatch) -> None:
        """--json emits parseable JSON with bytes_processed/reduction_pct."""
        monkeypatch.chdir(tmp_path)
        db = tmp_path / ".ll" / "session.db"
        db.parent.mkdir()
        _populate_tool_events(db, [("Read", 100, 900, 0)])
        lines, side_effect = _capture_print()
        with (
            patch("sys.argv", ["ll-ctx-stats", "--json"]),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_ctx_stats()
        assert result == 0
        data = json.loads("\n".join(lines))
        assert data["source"] == "sqlite"
        assert data["bytes_processed"] == 1000
        assert "reduction_pct" in data
        assert "per_tool" in data

    def test_db_flag_uses_explicit_path(self, tmp_path: Path, monkeypatch) -> None:
        """--db PATH overrides the default .ll/session.db location."""
        monkeypatch.chdir(tmp_path)
        custom = tmp_path / "elsewhere" / "alt.db"
        custom.parent.mkdir()
        _populate_tool_events(custom, [("Read", 1, 99, 0)])
        with (
            patch("sys.argv", ["ll-ctx-stats", "--db", str(custom), "--json"]),
            patch("builtins.print") as printed,
        ):
            result = main_ctx_stats()
        assert result == 0
        rendered = "".join(
            str(call.args[0]) for call in printed.call_args_list if call.args
        )
        assert "sqlite" in rendered


class TestToolEventsRoundtrip:
    """Cross-module sanity: connect() round-trips the FEAT-1623 byte columns."""

    def test_recent_tool_rows_carry_byte_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        _populate_tool_events(db, [("Read", 7, 42, 1)])
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT bytes_in, bytes_out, cache_hit FROM tool_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["bytes_in"] == 7
        assert row["bytes_out"] == 42
        assert row["cache_hit"] == 1


@pytest.fixture(autouse=True)
def _isolate_terminal_width(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin terminal width so progress-bar output stays stable across CI shells."""
    monkeypatch.setattr(
        "little_loops.cli.ctx_stats.terminal_width", lambda _default=80: 100
    )
