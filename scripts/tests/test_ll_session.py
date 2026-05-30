"""Tests for cli/session.py - ll-session CLI entry point."""

from __future__ import annotations

import json
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

    def test_search_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """search --json outputs valid JSON array."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "ratelimit", "state": "wait"})
        transport.close()
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "ratelimit", "--json"]
        ):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "content" in data[0]
        assert "kind" in data[0]
        assert "ratelimit" in data[0]["content"]

    def test_search_json_short_flag(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """search -j works equivalently to --json."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "ratelimit", "state": "wait"})
        transport.close()
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "ratelimit", "-j"]
        ):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "content" in data[0]

    def test_search_json_no_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """search --json with no matches outputs empty JSON array."""
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "zzznope", "--json"]
        ):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

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

    def test_recent_message_kind(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The recent CLI accepts --kind message after ENH-1621."""
        db = tmp_path / "session.db"
        from little_loops.session_store import ensure_db

        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "message"]):
            assert main_session() == 0
        assert "No message events" in capsys.readouterr().out

    # --- search --kind (ENH-1752) ---

    def test_search_kind_arg_accepted(self) -> None:
        with patch("sys.argv", ["ll-session", "search", "--fts", "x", "--kind", "loop"]):
            args = _parse_args()
        assert args.command == "search"
        assert args.kind == "loop"
        assert args.fts == "x"

    def test_search_kind_rejects_invalid(self) -> None:
        with patch("sys.argv", ["ll-session", "search", "--fts", "x", "--kind", "bogus"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_search_with_kind_filter(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "deploy", "state": "wait"})
        transport.close()
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "search", "--fts", "deploy", "--kind", "loop"]
        ):
            assert main_session() == 0
        assert "deploy" in capsys.readouterr().out

    def test_search_kind_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "deploy", "state": "wait"})
        transport.close()
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "search", "--fts", "deploy", "--kind", "loop", "--json"],
        ):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0

    # --- related (ENH-1752) ---

    def test_related_arg_parsing(self) -> None:
        with patch("sys.argv", ["ll-session", "related", "BUG-123"]):
            args = _parse_args()
        assert args.command == "related"
        assert args.issue_id == "BUG-123"

    def test_related_outputs_events(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "issue.completed", "issue_id": "BUG-456"})
        transport.close()
        with patch("sys.argv", ["ll-session", "--db", str(db), "related", "BUG-456"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "BUG-456" in out or "done" in out

    def test_related_no_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "related", "NOPE-000"]):
            assert main_session() == 0
        assert "No events for NOPE-000" in capsys.readouterr().out

    def test_related_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "issue.completed", "issue_id": "BUG-789"})
        transport.close()
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "related", "BUG-789", "--json"]
        ):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["issue_id"] == "BUG-789"
