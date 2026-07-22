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

    def test_recent_subcommand_commit_accepted(self) -> None:
        """ENH-2458: --kind commit must be a valid choice for both recent and search."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "commit"]):
            args = _parse_args()
        assert args.kind == "commit"

        with patch("sys.argv", ["ll-session", "search", "--fts", "fix", "--kind", "commit"]):
            args = _parse_args()
        assert args.kind == "commit"

    def test_recent_subcommand_test_run_accepted(self) -> None:
        """ENH-2459: --kind test_run must be a valid choice for both recent and search."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "test_run"]):
            args = _parse_args()
        assert args.kind == "test_run"

        with patch("sys.argv", ["ll-session", "search", "--fts", "test_x", "--kind", "test_run"]):
            args = _parse_args()
        assert args.kind == "test_run"

    def test_recent_subcommand_usage_accepted(self) -> None:
        """ENH-2461: --kind usage must be a valid choice for both recent and search."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "usage"]):
            args = _parse_args()
        assert args.kind == "usage"

        with patch("sys.argv", ["ll-session", "search", "--fts", "opus", "--kind", "usage"]):
            args = _parse_args()
        assert args.kind == "usage"

    def test_recent_subcommand_hook_event_accepted(self) -> None:
        """ENH-2506: --kind hook_event must be a valid choice for recent."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "hook_event"]):
            args = _parse_args()
        assert args.kind == "hook_event"

    def test_search_subcommand_hook_event_accepted(self) -> None:
        """ENH-2506: --kind hook_event must be a valid choice for search."""
        with patch(
            "sys.argv", ["ll-session", "search", "--fts", "PostToolUse", "--kind", "hook_event"]
        ):
            args = _parse_args()
        assert args.kind == "hook_event"

    def test_recent_subcommand_harness_accepted(self) -> None:
        """ENH-2741: --kind harness must be a valid choice for recent."""
        with patch("sys.argv", ["ll-session", "recent", "--kind", "harness"]):
            args = _parse_args()
        assert args.kind == "harness"

    def test_search_subcommand_harness_accepted(self) -> None:
        """ENH-2741: --kind harness must be a valid choice for search."""
        with patch("sys.argv", ["ll-session", "search", "--fts", "my-target", "--kind", "harness"]):
            args = _parse_args()
        assert args.kind == "harness"

    def test_recent_subcommand_orchestration_run_accepted(self) -> None:
        """ENH-2492: orchestration_run is valid for recent and search."""
        from little_loops.session_store import VALID_KINDS

        assert "orchestration_run" in VALID_KINDS
        with patch("sys.argv", ["ll-session", "recent", "--kind", "orchestration_run"]):
            args = _parse_args()
        assert args.kind == "orchestration_run"

        with patch(
            "sys.argv",
            ["ll-session", "search", "--fts", "ENH-2492", "--kind", "orchestration_run"],
        ):
            args = _parse_args()
        assert args.kind == "orchestration_run"

    def test_skill_stats_subcommand(self) -> None:
        """ENH-2460: skill-stats subcommand parses with optional --since."""
        with patch("sys.argv", ["ll-session", "skill-stats", "--since", "2026-01-01"]):
            args = _parse_args()
        assert args.command == "skill-stats"
        assert args.since == "2026-01-01"


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
        """backfill --rebuild success line includes messages= and sessions= counts
        (ENH-1621, ENH-1710, ENH-2581)."""
        db = tmp_path / "session.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill", "--rebuild"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 2,
                    "loops": 0,
                    "raw_events": 3,
                    "messages": 5,
                    "sessions": 2,
                    "corrections": 0,
                    "snapshots": 0,
                    "tools": 3,
                    "assistant_messages": 0,
                    "skill_events": 0,
                    "summaries": 0,
                    "commits": 0,
                }
                assert main_session() == 0
        out = capsys.readouterr().out
        assert "messages=5" in out
        assert "sessions=2" in out
        assert "corrections=0" in out
        assert "Backfilled 15" in out

    def test_backfill_reports_learning_tests_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """backfill success line includes learning_tests= count (ENH-2466)."""
        db = tmp_path / "session.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill"]):
            with patch("little_loops.cli.session.backfill") as mock_backfill:
                mock_backfill.return_value = {
                    "issues": 0,
                    "loops": 0,
                    "raw_events": 0,
                    "snapshots": 0,
                    "commits": 0,
                    "learning_tests": 4,
                }
                assert main_session() == 0
        assert "learning_tests=4" in capsys.readouterr().out

    def test_recent_kind_learning_test_accepted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """recent --kind learning_test is accepted (learning_test is in VALID_KINDS, ENH-2466)."""
        db = tmp_path / "session.db"
        from little_loops.session_store import ensure_db

        ensure_db(db)
        with patch(
            "sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "learning_test"]
        ):
            assert main_session() == 0
        assert "No learning_test events" in capsys.readouterr().out

    def test_search_kind_learning_test_accepted(self) -> None:
        with patch(
            "sys.argv", ["ll-session", "search", "--fts", "streaming", "--kind", "learning_test"]
        ):
            args = _parse_args()
        assert args.kind == "learning_test"

    def test_recent_kind_subagent_run_accepted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """recent --kind subagent_run is accepted (subagent_run is in VALID_KINDS, ENH-2505)."""
        db = tmp_path / "session.db"
        from little_loops.session_store import ensure_db

        ensure_db(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "subagent_run"]):
            assert main_session() == 0
        assert "No subagent_run events" in capsys.readouterr().out

    def test_search_kind_subagent_run_accepted(self) -> None:
        with patch(
            "sys.argv", ["ll-session", "search", "--fts", "Explore", "--kind", "subagent_run"]
        ):
            args = _parse_args()
        assert args.kind == "subagent_run"

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
                    mock_inc.return_value = {"raw_events": 6}
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

    # -- multi-level DAG CLI tests (ENH-1955) -----------------------------------

    def _make_db_with_multi_level_dag(self, tmp_path: Path) -> tuple[Path, int]:
        """Build a 3-level DAG and return (db_path, root_id)."""
        from datetime import UTC, datetime

        from little_loops.session_store import connect, ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            for sid in ("sess-a", "sess-b"):
                conn.execute(
                    "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                    (sid, str(tmp_path / f"{sid}.jsonl")),
                )
            for i in range(3):
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", "sess-a", f"CLI test A msg {i} FSM"),
                )
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", "sess-b", f"CLI test B msg {i} auth"),
                )

            # Leaf A
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('leaf', 'Leaf A', 50, 'sess-a', 0, ?)",
                (now,),
            )
            leaf_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for row in conn.execute(
                "SELECT id FROM message_events WHERE session_id='sess-a'"
            ).fetchall():
                conn.execute(
                    "INSERT INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                    (leaf_a, row["id"]),
                )

            # Leaf B
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('leaf', 'Leaf B', 50, 'sess-b', 0, ?)",
                (now,),
            )
            leaf_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for row in conn.execute(
                "SELECT id FROM message_events WHERE session_id='sess-b'"
            ).fetchall():
                conn.execute(
                    "INSERT INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                    (leaf_b, row["id"]),
                )

            # L1 condensed
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('condensed', 'L1 summary', 100, NULL, 1, ?)",
                (now,),
            )
            l1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (l1, leaf_a))
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (l1, leaf_b))

            # L2 root
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('condensed', 'Root summary', 150, NULL, 2, ?)",
                (now,),
            )
            root_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (root_id, l1))

            conn.commit()
        finally:
            conn.close()
        return db, root_id

    def test_expand_root_node_n_levels_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, root_id = self._make_db_with_multi_level_dag(tmp_path)
        with patch("sys.argv", ["ll-session", "--db", str(db), "expand", str(root_id)]):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "FSM" in out
        assert "auth" in out

    def test_grep_with_multi_level_summary_id_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db, root_id = self._make_db_with_multi_level_dag(tmp_path)
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "grep", "--summary-id", str(root_id), "FSM"],
        ):
            result = main_session()
        out = capsys.readouterr().out
        assert result == 0
        assert "FSM" in out


# =============================================================================
# TestExtractDecisionsFlag
# =============================================================================


class TestExtractDecisionsFlag:
    """--extract-decisions flag for ll-session backfill (ENH-2152)."""

    def test_extract_decisions_flag_parses_correctly(self) -> None:
        with patch("sys.argv", ["ll-session", "backfill", "--extract-decisions"]):
            args = _parse_args()
        assert args.command == "backfill"
        assert args.extract_decisions is True

    def test_extract_decisions_default_is_false(self) -> None:
        with patch("sys.argv", ["ll-session", "backfill"]):
            args = _parse_args()
        assert getattr(args, "extract_decisions", False) is False

    def test_extract_decisions_invokes_runner_after_backfill(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "session.db"
        with (
            patch(
                "sys.argv",
                ["ll-session", "--db", str(db), "backfill", "--extract-decisions"],
            ),
            patch("little_loops.cli.session.backfill") as mock_backfill,
            patch("little_loops.cli.session._run_extract_decisions") as mock_extract,
        ):
            mock_backfill.return_value = {
                "issues": 0,
                "loops": 0,
                "tools": 0,
                "messages": 0,
                "sessions": 0,
                "corrections": 0,
                "summaries": 0,
            }
            result = main_session()
        assert result == 0
        mock_extract.assert_called_once_with(since=None)


class TestBackfillSnapshotsFlag:
    """--snapshots flag for ll-session backfill (ENH-2151)."""

    def test_snapshots_flag_parsed_from_argv(self) -> None:
        from little_loops.cli.session import _parse_args

        with patch("sys.argv", ["ll-session", "backfill", "--snapshots"]):
            args = _parse_args()
        assert args.command == "backfill"
        assert args.snapshots is True

    def test_snapshots_flag_default_is_false(self) -> None:
        from little_loops.cli.session import _parse_args

        with patch("sys.argv", ["ll-session", "backfill"]):
            args = _parse_args()
        assert getattr(args, "snapshots", False) is False

    def test_snapshots_flag_calls_backfill_snapshots(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.cli.session import main_session

        db = tmp_path / "history.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "backfill", "--snapshots"]):
            with patch("little_loops.cli.session.backfill_snapshots") as mock_snap:
                mock_snap.return_value = 3
                result = main_session()
        assert result == 0
        assert mock_snap.called
        out = capsys.readouterr().out
        assert "3" in out
        assert "snapshot" in out.lower()


class TestRebuildSubcommand:
    """ll-session rebuild — materialize cache tables from raw_events (ENH-2581)."""

    def test_rebuild_parsed_from_argv(self) -> None:
        with patch("sys.argv", ["ll-session", "rebuild"]):
            args = _parse_args()
        assert args.command == "rebuild"

    def test_rebuild_invokes_session_store_rebuild(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "rebuild"]):
            with patch("little_loops.cli.session.rebuild") as mock_rebuild:
                mock_rebuild.return_value = {
                    "sessions": 1,
                    "tools": 2,
                    "messages": 3,
                    "assistant_messages": 0,
                    "skill_events": 0,
                    "corrections": 0,
                    "summaries": 0,
                }
                result = main_session()
        assert result == 0
        assert mock_rebuild.called
        out = capsys.readouterr().out
        assert "messages=3" in out

    def test_rebuild_json_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db = tmp_path / "history.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "rebuild", "--json"]):
            with patch("little_loops.cli.session.rebuild") as mock_rebuild:
                mock_rebuild.return_value = {"tools": 1}
                result = main_session()
        assert result == 0
        out = capsys.readouterr().out
        assert '"tools"' in out


class TestCompactSubcommand:
    """ll-session compact [--and-prune] — retention lifecycle (ENH-2581)."""

    def test_compact_parsed_from_argv(self) -> None:
        with patch("sys.argv", ["ll-session", "compact", "--and-prune"]):
            args = _parse_args()
        assert args.command == "compact"
        assert args.and_prune is True

    def test_compact_default_and_prune_is_false(self) -> None:
        with patch("sys.argv", ["ll-session", "compact"]):
            args = _parse_args()
        assert args.and_prune is False

    def test_compact_invokes_session_store_compact(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "compact", "--and-prune"]):
            with patch("little_loops.cli.session.compact") as mock_compact:
                mock_compact.return_value = {
                    "compacted_rows": 5,
                    "summary_nodes": 2,
                    "pruned_rows": 5,
                }
                result = main_session()
        assert result == 0
        assert mock_compact.called
        assert mock_compact.call_args.kwargs["and_prune"] is True
        out = capsys.readouterr().out
        assert "5" in out
        assert "pruned" in out.lower()


class TestRecompressSubcommand:
    """ll-session recompress — compress legacy raw_events payloads."""

    def test_recompress_parsed_from_argv(self) -> None:
        with patch("sys.argv", ["ll-session", "recompress", "--batch", "500"]):
            args = _parse_args()
        assert args.command == "recompress"
        assert args.batch == 500

    def test_recompress_default_batch(self) -> None:
        with patch("sys.argv", ["ll-session", "recompress"]):
            args = _parse_args()
        assert args.batch == 2000

    def test_recompress_invokes_session_store_recompress(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "history.db"
        with patch("sys.argv", ["ll-session", "--db", str(db), "recompress"]):
            with patch("little_loops.cli.session.recompress_raw_events") as mock_recompress:
                mock_recompress.return_value = {
                    "recompressed": 42,
                    "size_before_mb": 100.0,
                    "size_after_mb": 40.0,
                }
                result = main_session()
        assert result == 0
        assert mock_recompress.called
        assert mock_recompress.call_args.kwargs["batch_size"] == 2000
        out = capsys.readouterr().out
        assert "42" in out
        assert "60.0" in out  # saved MB


class TestSkillStatsAndNewKinds:
    """ENH-2458/2459/2460: skill-stats subcommand and commit/test_run kinds."""

    def test_skill_stats_outputs_rollup(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "refine-issue", "ENH-1"):
            pass
        with pytest.raises(ValueError):
            with skill_event_context(db, "s2", "refine-issue", "ENH-2"):
                raise ValueError("fail")
        with patch("sys.argv", ["ll-session", "--db", str(db), "skill-stats"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "refine-issue" in out
        assert "invocations=2" in out
        assert "success_rate=50%" in out

    def test_skill_stats_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "check-code", ""):
            pass
        with patch("sys.argv", ["ll-session", "--db", str(db), "skill-stats", "--json"]):
            assert main_session() == 0
        data = json.loads(capsys.readouterr().out)
        assert data[0]["skill_name"] == "check-code"
        assert data[0]["successes"] == 1

    def test_recent_kind_commit_outputs_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "abc123", "fix: repair the flux capacitor (BUG-88)")
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "commit"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "abc123" in out
        assert "BUG-88" in out

    def test_recent_kind_test_run_outputs_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(db, ts="2026-07-01T12:00:00Z", total=5, passed=5, env_label="local")
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "test_run"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "total=5" in out
        assert "env_label=local" in out

    def test_recent_kind_hook_event_outputs_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_hook_event

        db = tmp_path / "history.db"
        record_hook_event(
            db,
            session_id="s1",
            event_name="PostToolUse",
            matcher="Write|Edit",
            script="little_loops.hooks.post_tool_use",
            exit_code=0,
            duration_ms=12,
        )
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "hook_event"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "PostToolUse" in out

    def test_recent_kind_harness_outputs_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        record_harness_event(
            db, ts="2026-07-01T12:00:00Z", runner="cli", target="my-target", exit_code=0
        )
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "harness"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "my-target" in out

    def test_search_kind_harness_matches_indexed_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_harness_event

        db = tmp_path / "history.db"
        record_harness_event(
            db, ts="2026-07-01T12:00:00Z", runner="cli", target="my-target", exit_code=0
        )
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "search", "--fts", "my-target", "--kind", "harness"],
        ):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "my-target" in out

    def test_record_hook_event_subcommand_writes_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import recent

        db = tmp_path / "history.db"
        with patch(
            "sys.argv",
            [
                "ll-session",
                "--db",
                str(db),
                "record-hook-event",
                "--event-name",
                "Stop",
                "--exit-code",
                "0",
                "--duration-ms",
                "5",
            ],
        ):
            assert main_session() == 0
        rows = recent(db, kind="hook_event")
        assert len(rows) == 1
        assert rows[0]["event_name"] == "Stop"

    def test_recent_kind_usage_outputs_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-2461: usage rows are derived from raw_events via rebuild()."""
        import json as _json

        from little_loops.session_store import backfill_raw_events, ensure_db, rebuild

        db = tmp_path / "history.db"
        ensure_db(db)
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            _json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "sess-usage",
                    "timestamp": "2026-07-13T03:00:00Z",
                    "message": {
                        "model": "claude-opus-4-7",
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "cache_read_input_tokens": 50,
                            "cache_creation_input_tokens": 10,
                        },
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        rebuild(db)
        with patch("sys.argv", ["ll-session", "--db", str(db), "recent", "--kind", "usage"]):
            assert main_session() == 0
        out = capsys.readouterr().out
        assert "model=claude-opus-4-7" in out
        assert "input_tokens=100" in out

    def test_search_kind_commit_filters(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "abc999", "feat: add teleporter maintenance")
        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "search", "--fts", "teleporter", "--kind", "commit"],
        ):
            assert main_session() == 0
        assert "teleporter" in capsys.readouterr().out

    def test_orchestration_run_recent_search_and_export(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops import session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        assert callable(recorder), "record_orchestration_run must exist"
        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="cli-batch",
            driver="ll-auto",
            issue_id="ENH-2492",
            status="failed",
            failure_reason="fluxcapacitor",
            duration_s=3.0,
        )

        with patch(
            "sys.argv",
            ["ll-session", "--db", str(db), "recent", "--kind", "orchestration_run"],
        ):
            assert main_session() == 0
        recent_out = capsys.readouterr().out
        assert "ENH-2492" in recent_out
        assert "cli-batch" in recent_out

        with patch(
            "sys.argv",
            [
                "ll-session",
                "--db",
                str(db),
                "search",
                "--fts",
                "fluxcapacitor",
                "--kind",
                "orchestration_run",
            ],
        ):
            assert main_session() == 0
        assert "fluxcapacitor" in capsys.readouterr().out

        with patch(
            "sys.argv",
            [
                "ll-session",
                "--db",
                str(db),
                "export",
                "--tables",
                "orchestration_run",
            ],
        ):
            assert main_session() == 0
        exported = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
        row = next(item for item in exported if item["type"] == "orchestration_run")
        assert row["issue_id"] == "ENH-2492"
