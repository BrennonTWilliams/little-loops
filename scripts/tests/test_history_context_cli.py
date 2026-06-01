"""Tests for cli/history_context.py - ll-history-context CLI entry point."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.history_context import main_history_context
from little_loops.session_store import connect, ensure_db, record_correction


class TestArgumentParsing:
    """Argparse unit tests via sys.argv, no filesystem."""

    def test_missing_issue_id_exits(self) -> None:
        with patch("sys.argv", ["ll-history-context"]):
            with pytest.raises(SystemExit):
                main_history_context()

    def test_issue_id_accepted(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            assert main_history_context() == 0

    def test_file_arg_is_optional(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            assert main_history_context() == 0


class TestHistoryContextWithMatches:
    """DB seeded with correction rows; assert ## Historical Context in stdout."""

    def test_outputs_historical_context_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "Fix ENH-1708 by wiring corrections into refine", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert "## Historical Context" in out

    def test_outputs_correction_content(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        record_correction(db, "sess-1", "Fix ENH-1708 by wiring corrections into refine", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        assert "wiring corrections into refine" in out

    def test_caps_at_five_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        for i in range(10):
            record_correction(db, f"sess-{i}", f"correction ENH-1708 unique item {i}", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        bullet_lines = [line for line in out.splitlines() if line.startswith("- ")]
        assert len(bullet_lines) <= 5


class TestHistoryContextNoMatches:
    """DB present but empty; assert empty stdout."""

    def test_empty_stdout_on_no_matches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-9999"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestHistoryContextDBMissing:
    """No DB file; assert empty stdout, exit 0."""

    def test_missing_db_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "nonexistent.db"
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestHistoryContextStaleRows:
    """All rows older than 30 days; assert empty stdout."""

    def _insert_old_correction(self, db: Path, topic: str, days_old: int) -> None:
        conn = connect(db)
        try:
            ts = (datetime.now(UTC) - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) "
                "VALUES(?, ?, ?, ?)",
                (ts, "sess-1", f"correction for {topic}", "user"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_stale_rows_produce_empty_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._insert_old_correction(db, "ENH-1708", days_old=31)
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            result = main_history_context()
        out = capsys.readouterr().out
        assert result == 0
        assert out.strip() == ""


class TestDeduplication:
    """Same content from two queries; assert deduped in output."""

    def test_duplicate_content_appears_once(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        # record_correction writes to both user_corrections AND search_index,
        # so the same row appears in both find_user_corrections() and search() results.
        record_correction(db, "sess-1", "Fix ENH-1708 dedup test content", "user")
        with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1708"]):
            main_history_context()
        out = capsys.readouterr().out
        count = out.count("dedup test content")
        assert count == 1, f"Expected 1 occurrence of deduped content, got {count}"
