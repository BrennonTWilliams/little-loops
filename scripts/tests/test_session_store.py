"""Tests for little_loops.session_store - the unified SQLite + FTS5 session store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.session_store import (
    SCHEMA_VERSION,
    SQLiteTransport,
    backfill,
    connect,
    ensure_db,
    recent,
    search,
)
from little_loops.transport import Transport


class TestEnsureDb:
    """Schema bootstrap and migration framework."""

    def test_creates_database_file(self, tmp_path: Path) -> None:
        db = tmp_path / "nested" / "session.db"
        ensure_db(db)
        assert db.exists()

    def test_applies_schema_version(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        conn.close()
        assert int(row[0]) == SCHEMA_VERSION

    def test_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        ensure_db(db)  # second call must not raise or duplicate schema
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM meta WHERE key='schema_version'").fetchone()[0]
        conn.close()
        assert count == 1

    def test_all_tables_created(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        for table in (
            "tool_events",
            "file_events",
            "issue_events",
            "loop_events",
            "user_corrections",
        ):
            assert table in names

    def test_tool_events_reserves_feat1160_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_events)")}
        conn.close()
        assert {"bytes_in", "bytes_out", "cache_hit"} <= cols


class TestSQLiteTransport:
    """The SQLiteTransport EventBus sink."""

    def test_satisfies_transport_protocol(self, tmp_path: Path) -> None:
        transport = SQLiteTransport(tmp_path / "session.db")
        assert isinstance(transport, Transport)
        transport.close()

    def test_records_loop_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "docs-sync", "state": "verify"})
        transport.close()
        rows = recent(db, kind="loop")
        assert len(rows) == 1
        assert rows[0]["loop_name"] == "docs-sync"
        assert rows[0]["transition"] == "state_enter"

    def test_ignores_unrecognized_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "action_output", "loop_name": "x"})
        transport.close()
        assert recent(db, kind="loop") == []

    def test_loop_complete_records_outcome_as_state(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "loop_complete", "loop_name": "x", "outcome": "success"})
        transport.close()
        assert recent(db, kind="loop")[0]["state"] == "success"

    def test_send_after_close_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.close()
        transport.send({"event": "state_enter", "loop_name": "x"})  # must not raise

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        transport = SQLiteTransport(tmp_path / "session.db")
        transport.close()
        transport.close()  # must not raise


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


class TestBackfill:
    """Seeding the database from existing on-disk sources."""

    def test_backfill_issues(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "bugs"
        issues.mkdir(parents=True)
        (issues / "P1-BUG-1-x.md").write_text(
            "---\nid: BUG-1\nstatus: done\ntype: BUG\n---\n# x\n", encoding="utf-8"
        )
        db = tmp_path / "session.db"
        counts = backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / ".loops")
        assert counts["issues"] == 1
        rows = recent(db, kind="issue")
        assert rows[0]["issue_id"] == "BUG-1"

    def test_backfill_loops(self, tmp_path: Path) -> None:
        running = tmp_path / ".loops" / ".running"
        running.mkdir(parents=True)
        (running / "docs-sync.json").write_text(
            json.dumps({"loop_name": "docs-sync", "current_state": "verify"}), encoding="utf-8"
        )
        db = tmp_path / "session.db"
        counts = backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / ".loops")
        assert counts["loops"] == 1

    def test_backfill_tool_events_from_jsonl(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
                        ]
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db, issues_dir=tmp_path / "none", loops_dir=tmp_path / "none", jsonl_files=[jsonl]
        )
        assert counts["tools"] == 1
        assert recent(db, kind="tool")[0]["tool_name"] == "Bash"

    def test_backfill_missing_sources_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        counts = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no")
        assert counts == {"issues": 0, "loops": 0, "tools": 0, "messages": 0}

    def test_backfilled_issue_is_searchable(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues"
        issues.mkdir()
        (issues / "P1-BUG-2-y.md").write_text(
            "---\nid: BUG-2\nstatus: done\ntype: BUG\n---\n", encoding="utf-8"
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=issues, loops_dir=tmp_path / "no")
        results = search(db, query="done")
        assert any(r["kind"] == "issue" for r in results)


class TestConnect:
    """The connect() helper."""

    def test_connect_returns_row_factory(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "session.db")
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


class TestSchemaV2:
    """v2 migration: widened issue_events + message_events table (ENH-1621)."""

    def test_issue_events_has_v2_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_events)")}
        conn.close()
        assert {
            "issue_type",
            "priority",
            "completed_date",
            "captured_at",
            "completed_at",
        } <= cols

    def test_message_events_table_created(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "message_events" in names

    def test_v1_db_upgrades_to_v2_idempotently(self, tmp_path: Path) -> None:
        """A pre-existing v1 database is migrated forward on next ensure_db()."""
        db = tmp_path / "session.db"
        # Bootstrap as if v1 only (no ALTER + no message_events).
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE tool_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, tool_name TEXT, args_hash TEXT,
                result_size INTEGER, bytes_in INTEGER, bytes_out INTEGER, cache_hit INTEGER
            );
            CREATE TABLE file_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, path TEXT, op TEXT, issue_id TEXT, git_sha TEXT
            );
            CREATE TABLE issue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                issue_id TEXT, transition TEXT, discovered_by TEXT
            );
            CREATE TABLE loop_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                loop_name TEXT, state TEXT, transition TEXT, retries INTEGER
            );
            CREATE TABLE user_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, content TEXT, source TEXT
            );
            CREATE VIRTUAL TABLE search_index USING fts5(
                content, kind UNINDEXED, ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO meta(key, value) VALUES('schema_version', '1');
            """
        )
        conn.commit()
        conn.close()

        ensure_db(db)  # should upgrade to v2

        conn = sqlite3.connect(str(db))
        version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_events)")}
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert int(version) == SCHEMA_VERSION
        assert "issue_type" in cols and "completed_at" in cols
        assert "message_events" in tables


class TestBackfillMessages:
    """_backfill_messages() seeds message_events from user JSONL blocks."""

    def _user_record(
        self, session_id: str, ts: str, content: object
    ) -> str:
        return (
            json.dumps(
                {
                    "type": "user",
                    "sessionId": session_id,
                    "timestamp": ts,
                    "message": {"content": content},
                }
            )
            + "\n"
        )

    def test_backfill_messages_plain_string(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s1", "2026-05-22T00:00:00Z", "implement ENH-1621"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        assert counts["messages"] == 1
        rows = recent(db, kind="message")
        assert rows[0]["content"] == "implement ENH-1621"
        assert rows[0]["session_id"] == "s1"

    def test_backfill_messages_block_list_content(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record(
                "s2",
                "2026-05-22T00:00:00Z",
                [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}],
            ),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        rows = recent(db, kind="message")
        assert rows[0]["content"] == "first\nsecond"

    def test_backfill_messages_skips_empty_and_assistant_records(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s3", "2026-05-22T00:00:00Z", "")
            + json.dumps(
                {
                    "type": "assistant",
                    "sessionId": "s3",
                    "timestamp": "2026-05-22T00:00:01Z",
                    "message": {"content": [{"type": "text", "text": "ignored"}]},
                }
            )
            + "\n"
            + self._user_record("s3", "2026-05-22T00:00:02Z", "kept"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        assert counts["messages"] == 1

    def test_message_events_are_searchable(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s4", "2026-05-22T00:00:00Z", "needle in haystack"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        results = search(db, query="needle")
        assert any(r["kind"] == "message" for r in results)

    def test_recent_message_kind_supported(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        assert recent(db, kind="message") == []


class TestBackfillIssuesV2Columns:
    """_backfill_issues() populates the v2 issue_events columns (ENH-1621)."""

    def test_v2_columns_populated_from_frontmatter(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "enhancements"
        issues.mkdir(parents=True)
        (issues / "P2-ENH-99-foo.md").write_text(
            "---\n"
            "id: ENH-99\n"
            "status: done\n"
            "type: ENH\n"
            "priority: P2\n"
            "captured_at: 2026-05-20T10:00:00Z\n"
            "completed_at: 2026-05-22T15:30:00Z\n"
            "---\n# x\n",
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        rows = recent(db, kind="issue")
        assert rows[0]["issue_type"] == "ENH"
        assert rows[0]["priority"] == "P2"
        assert rows[0]["completed_date"] == "2026-05-22"
        assert rows[0]["completed_at"] == "2026-05-22T15:30:00Z"
        assert rows[0]["captured_at"] == "2026-05-20T10:00:00Z"

    def test_v2_columns_derived_from_filename_when_fm_absent(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "bugs"
        issues.mkdir(parents=True)
        (issues / "P3-BUG-7-no-meta.md").write_text(
            "---\nid: BUG-7\nstatus: done\n---\n", encoding="utf-8"
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        rows = recent(db, kind="issue")
        assert rows[0]["issue_type"] == "BUG"
        assert rows[0]["priority"] == "P3"
