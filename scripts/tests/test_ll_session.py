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

    def test_path_subcommand(self) -> None:
        with patch("sys.argv", ["ll-session", "path", "abc123"]):
            args = _parse_args()
        assert args.command == "path"
        assert args.session_id == "abc123"

    def test_recent_rejects_invalid_kind(self) -> None:
        with patch("sys.argv", ["ll-session", "recent", "--kind", "bogus"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_recent_issue_arg_accepted(self) -> None:
        with patch("sys.argv", ["ll-session", "recent", "--issue", "ENH-1710"]):
            args = _parse_args()
        assert args.command == "recent"
        assert args.issue == "ENH-1710"
        assert args.kind is None

    def test_recent_subcommand_skill_accepted(self) -> None:
        """ENH-1833: --kind skill must be a valid choice for both recent and search."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "skill"]):
            args = _parse_args()
        assert args.kind == "skill"

        with patch("sys.argv", ["ll-session", "search", "--fts", "refine", "--kind", "skill"]):
            args = _parse_args()
        assert args.kind == "skill"

    def test_recent_subcommand_cli_accepted(self) -> None:
        """ENH-1849: --kind cli must be a valid choice for both recent and search."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "cli"]):
            args = _parse_args()
        assert args.kind == "cli"

        with patch("sys.argv", ["ll-session", "search", "--fts", "my-cmd", "--kind", "cli"]):
            args = _parse_args()
        assert args.kind == "cli"


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
                    "sessions": 0,
                }
                assert main_session() == 0
        assert "Backfilled" in capsys.readouterr().out

    def test_backfill_reports_messages_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """backfill success line includes messages= and sessions= counts (ENH-1621, ENH-1710)."""
        db = tmp_path / "session.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 2,
                    "loops": 0,
                    "tools": 3,
                    "messages": 5,
                    "sessions": 2,
                    "corrections": 0,
                }
                assert main_session() == 0
        out = capsys.readouterr().out
        assert "messages=5" in out
        assert "sessions=2" in out
        assert "corrections=0" in out
        assert "Backfilled 12" in out

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

    def test_search_with_kind_filter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "deploy", "state": "wait"})
        transport.close()
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "search", "--fts", "deploy", "--kind", "loop"],
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
            [
                "ll-session",
                "--db",
                str(db),
                "search",
                "--fts",
                "deploy",
                "--kind",
                "loop",
                "--json",
            ],
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

    def test_related_outputs_events(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
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
        with patch("sys.argv", ["ll-session", "--db", str(db), "related", "BUG-789", "--json"]):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["issue_id"] == "BUG-789"

    # --- path (ENH-1710) ---

    def test_path_found(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        from little_loops.session_store import connect as ss_connect

        ensure_db(db)
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sid-xyz", "/path/to/sid-xyz.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()
        with patch("sys.argv", ["ll-session", "--db", str(db), "path", "sid-xyz"]):
            assert main_session() == 0
        assert "/path/to/sid-xyz.jsonl" in capsys.readouterr().out

    def test_path_not_found(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "path", "NOPE"]):
            assert main_session() == 1
        assert "not found" in capsys.readouterr().out.lower()

    # --- recent --issue (ENH-1711) ---

    def test_recent_no_kind_no_issue_returns_1(self) -> None:
        with patch("sys.argv", ["ll-session", "recent"]):
            assert main_session() == 1

    def test_recent_filtered_by_issue(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import connect as ss_connect

        db = tmp_path / "session.db"
        ensure_db(db)
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-42", "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T10:00:00Z", "sess-42", "hello"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-42", "/path/sess-42.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--issue", "ENH-42"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "sess-42" in out

    def test_recent_filtered_by_issue_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import json as json_mod

        from little_loops.session_store import connect as ss_connect

        db = tmp_path / "session.db"
        ensure_db(db)
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-43", "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T10:00:00Z", "sess-43", "work"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-43", "/path/sess-43.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "recent", "--issue", "ENH-43", "--json"],
        ):
            assert main_session() == 0
        data = json_mod.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["session_id"] == "sess-43"

    def test_recent_correction_kind(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1831: recent --kind correction returns captured rows."""
        from little_loops.session_store import record_correction

        db = tmp_path / "session.db"
        record_correction(db, "sess-corr1", "no, don't do that", "user_prompt_submit")
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "correction"]):
            assert main_session() == 0
        assert "don't do that" in capsys.readouterr().out

    def test_recent_correction_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1831: recent --kind correction with no rows emits 'No correction events'."""
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "correction"]):
            assert main_session() == 0
        assert "No correction events" in capsys.readouterr().out

    def test_recent_skill_kind(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """ENH-1833: recent --kind skill returns captured skill rows."""
        from little_loops.session_store import record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-sk1", "refine-issue", "ENH-1833")
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "skill"]):
            assert main_session() == 0
        assert "refine-issue" in capsys.readouterr().out

    def test_recent_skill_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """ENH-1833: recent --kind skill with no rows emits 'No skill events'."""
        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "skill"]):
            assert main_session() == 0
        assert "No skill events" in capsys.readouterr().out

    def test_recent_cli_kind(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """ENH-1849: recent --kind cli returns captured CLI event rows."""
        from little_loops.session_store import cli_event_context

        db = tmp_path / "session.db"
        with cli_event_context(db, "ll-test", ["--dry-run"]):
            pass
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "cli"]):
            assert main_session() == 0
        assert "ll-test" in capsys.readouterr().out

    def test_recent_cli_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """ENH-1849: recent --kind cli with no rows emits 'No cli events'."""
        from little_loops.session_store import ensure_db

        db = tmp_path / "session.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "cli"]):
            assert main_session() == 0
        assert "No cli events" in capsys.readouterr().out


class TestBackfillSinceFlag:
    """--since flag for ll-session backfill (ENH-1830)."""

    def test_since_flag_parsed_from_argv(self) -> None:
        with patch("sys.argv", ["ll-session", "backfill", "--since", "2026-01-01"]):
            args = _parse_args()
        assert args.command == "backfill"
        assert args.since == "2026-01-01"

    def test_backfill_without_since_has_none_default(self) -> None:
        with patch("sys.argv", ["ll-session", "backfill"]):
            args = _parse_args()
        assert getattr(args, "since", None) is None

    def test_since_calls_backfill_incremental(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "backfill", "--since", "2026-01-01"]
        ):
            with patch("little_loops.cli.session.backfill_incremental") as mock_inc:
                with patch("little_loops.cli.session.get_project_folder") as mock_folder:
                    mock_folder.return_value = tmp_path
                    mock_inc.return_value = {"tools": 2, "messages": 3, "sessions": 1}
                    result = main_session()
        assert result == 0
        assert mock_inc.called
        out = capsys.readouterr().out
        assert "incremental" in out
        assert "2026-01-01" in out

    def test_since_invalid_date_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "backfill", "--since", "not-a-date"]
        ):
            result = main_session()
        assert result == 1

    def test_backfill_without_since_still_calls_full_backfill(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 0,
                    "loops": 0,
                    "tools": 0,
                    "messages": 0,
                    "sessions": 0,
                }
                result = main_session()
        assert result == 0
        assert mock_backfill.called


class TestGrepExpandDescribe:
    """Tests for the grep, expand, and describe subcommands (FEAT-1712)."""

    def _make_db_with_summary(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with one message + one summary node; returns (db_path, node_id)."""
        from little_loops.session_store import compact_session, connect

        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-1", str(tmp_path / "sess-1.jsonl")),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:00Z", "sess-1", "auth middleware test message"),
            )
            conn.commit()
        finally:
            conn.close()
        compact_session("sess-1", db)
        conn = connect(db)
        try:
            node_id = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='leaf' AND session_id='sess-1'"
            ).fetchone()["id"]
        finally:
            conn.close()
        return db, node_id

    def test_grep_argument_parsing(self) -> None:
        with patch("sys.argv", ["ll-session", "grep", "auth middleware"]):
            args = _parse_args()
        assert args.command == "grep"
        assert args.pattern == "auth middleware"
        assert args.summary_id is None
        assert args.limit == 50

    def test_grep_with_summary_id_flag(self) -> None:
        with patch("sys.argv", ["ll-session", "grep", "auth", "--summary-id", "7"]):
            args = _parse_args()
        assert args.summary_id == 7

    def test_expand_argument_parsing(self) -> None:
        with patch("sys.argv", ["ll-session", "expand", "42"]):
            args = _parse_args()
        assert args.command == "expand"
        assert args.summary_id == 42

    def test_describe_argument_parsing(self) -> None:
        with patch("sys.argv", ["ll-session", "describe", "99"]):
            args = _parse_args()
        assert args.command == "describe"
        assert args.node_id == 99

    def test_grep_finds_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db, _ = self._make_db_with_summary(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "grep", "auth"]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "auth" in out

    def test_grep_no_match(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db, _ = self._make_db_with_summary(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "grep", "ZZZNOMATCH"]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "No matches" in out

    def test_expand_returns_messages(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, node_id = self._make_db_with_summary(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "expand", str(node_id)]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "auth" in out

    def test_expand_missing_node(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "expand", "99999"]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "No messages" in out

    def test_describe_returns_node_metadata(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, node_id = self._make_db_with_summary(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "describe", str(node_id)]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "leaf" in out

    def test_describe_missing_node(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "describe", "99999"]):
            result = main_session()
        assert result == 1

    # -- helpers for condensed-node CLI tests ----------------------------------

    def _make_db_with_condensed_node(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with 30 messages compacted into ≥ 2 leaves + 1 condensed node."""
        from little_loops.session_store import compact_session, connect

        session_id = "sess-condensed"
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            for i in range(30):
                ts = f"2026-01-01T00:{i:02d}:00Z"
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (ts, session_id, f"Message number {i}. auth middleware FSM test."),
                )
            conn.commit()
        finally:
            conn.close()
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        compact_session(session_id, db, config=config)
        conn = connect(db)
        try:
            condensed_id = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='condensed' AND session_id=?",
                (session_id,),
            ).fetchone()["id"]
        finally:
            conn.close()
        return db, condensed_id

    def test_expand_condensed_node_returns_messages_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, condensed_id = self._make_db_with_condensed_node(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "expand", str(condensed_id)]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "auth" in out

    def test_grep_with_condensed_summary_id_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, condensed_id = self._make_db_with_condensed_node(tmp_path)
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "grep", "--summary-id", str(condensed_id), "auth"],
        ):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "auth" in out
