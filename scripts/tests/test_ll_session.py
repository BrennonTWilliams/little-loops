"""Tests for cli/session.py - ll-session CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.session import _parse_args, main_session
from little_loops.session_store import SQLiteTransport, ensure_db


class TestArgumentParsing:
    """Argparse unit tests via _parse_args(), no filesystem."""

    def test_no_args_command_is_none(self) -> None:
        with patch("sys.argv", ["ll-session"]):
            args = _parse_args()
        assert args.command is None

    def test_search_subcommand(self) -> None:
        with patch("sys.argv", ["ll-session", "search", "--fts", "rate limit"]):
            args = _parse_args()
        assert args.command == "search"
        assert args.fts == "rate limit"

    def test_recent_subcommand(self) -> None:
        with patch("sys.argv", ["ll-session", "recent", "--kind", "loop"]):
            args = _parse_args()
        assert args.command == "recent"
        assert args.kind == "loop"

    def test_backfill_subcommand(self) -> None:
        with patch("sys.argv", ["ll-session", "backfill"]):
            args = _parse_args()
        assert args.command == "backfill"

    def test_recent_rejects_invalid_kind(self) -> None:
        with patch("sys.argv", ["ll-session", "recent", "--kind", "bogus"]):
            with pytest.raises(SystemExit):
                _parse_args()


class TestMainSession:
    """Integration tests for main_session()."""

    def test_no_subcommand_returns_1(self) -> None:
        with patch("sys.argv", ["ll-session"]):
            assert main_session() == 1

    def test_search_outputs_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "ratelimit", "state": "wait"})
        transport.close()
        with patch("sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "ratelimit"]):
            assert main_session() == 0
        assert "ratelimit" in capsys.readouterr().out

    def test_search_no_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "zzznope"]):
            assert main_session() == 0
        assert "No matches" in capsys.readouterr().out

    def test_recent_loop(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "loop_start", "loop_name": "mine"})
        transport.close()
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "loop"]):
            assert main_session() == 0
        assert "mine" in capsys.readouterr().out

    def test_recent_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "tool"]):
            assert main_session() == 0
        assert "No tool events" in capsys.readouterr().out

    def test_backfill_runs(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        issues = tmp_path / ".issues"
        issues.mkdir()
        (issues / "P1-BUG-9-z.md").write_text(
            "---\nid: BUG-9\nstatus: done\n---\n", encoding="utf-8"
        )
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 1,
                    "loops": 0,
                    "tools": 0,
                    "messages": 0,
                }
                assert main_session() == 0
        assert "Backfilled" in capsys.readouterr().out

    def test_backfill_reports_messages_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """backfill success line includes the messages= count (ENH-1621)."""
        db = tmp_path / "session.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 2,
                    "loops": 0,
                    "tools": 3,
                    "messages": 5,
                }
                assert main_session() == 0
        out = capsys.readouterr().out
        assert "messages=5" in out
        assert "Backfilled 10" in out

    def test_recent_message_kind(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The recent CLI accepts --kind message after ENH-1621."""
        db = tmp_path / "session.db"
        from little_loops.session_store import ensure_db

        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "message"]):
            assert main_session() == 0
        assert "No message events" in capsys.readouterr().out
