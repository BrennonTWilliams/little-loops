"""Tests for little_loops.session_store - the unified SQLite + FTS5 session store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.session_store import (
    SCHEMA_VERSION,
    SQLiteTransport,
    _derive_transition,
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

    def test_migrates_legacy_session_db(self, tmp_path: Path) -> None:
        """ENH-1635: a pre-existing ``session.db`` (+ sidecars) is renamed
        to ``history.db`` on first ``ensure_db()`` call after upgrade.

        Bootstraps a real (versioned) SQLite legacy file, then drops an
        arbitrary ``-shm`` sidecar next to it. The schema-bootstrap step
        after the rename should not delete the renamed sidecar (unlike a
        renamed ``-wal``, which SQLite will tidy on open if the main file
        is not in WAL mode).
        """
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        legacy = ll_dir / "session.db"
        ensure_db(legacy)
        legacy_bytes = legacy.read_bytes()
        (ll_dir / "session.db-shm").write_bytes(b"shm-data")
        new = ll_dir / "history.db"

        ensure_db(new)

        assert new.exists()
        assert not legacy.exists()
        # New db must carry the legacy content (rename, not recreate).
        assert new.read_bytes() == legacy_bytes
        assert (ll_dir / "history.db-shm").read_bytes() == b"shm-data"
        assert not (ll_dir / "session.db-shm").exists()

    def test_migration_skipped_when_new_db_exists(self, tmp_path: Path) -> None:
        """If both legacy and new exist, leave legacy alone (don't clobber)."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        # Create the new db first so ``new.exists()`` is true when the
        # shim sees both. (Creating ``legacy`` first would trigger the
        # very migration we want to verify is skipped here.)
        new = ll_dir / "history.db"
        ensure_db(new)
        legacy = ll_dir / "session.db"
        ensure_db(legacy)
        legacy_size = legacy.stat().st_size

        ensure_db(new)

        assert legacy.exists()
        assert legacy.stat().st_size == legacy_size


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
        assert counts == {"issues": 0, "loops": 0, "tools": 0, "messages": 0, "sessions": 0}

    def test_backfill_jsonl_populates_sessions(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "sess-abc",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT jsonl_path FROM sessions WHERE session_id = 'sess-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["jsonl_path"] == str(jsonl)

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

    def _user_record(self, session_id: str, ts: str, content: object) -> str:
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
        backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl])
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
        backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl])
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


class TestDeriveTransition:
    """_derive_transition() maps issue event types to canonical status strings."""

    def test_known_mappings(self) -> None:
        cases = [
            ("issue.completed", "done"),
            ("issue.closed", "done"),
            ("issue.deferred", "deferred"),
            ("issue.skipped", "cancelled"),
            ("issue.created", "open"),
            ("issue.started", "in_progress"),
        ]
        for event_type, expected in cases:
            assert _derive_transition(event_type) == expected, event_type

    def test_unknown_event_falls_back_to_suffix(self) -> None:
        assert _derive_transition("issue.failure_captured") == "failure_captured"
        assert _derive_transition("issue.reopened") == "reopened"


class TestSQLiteTransportIssueEvents:
    """SQLiteTransport records issue.* events into issue_events (ENH-1690)."""

    def test_records_issue_completed_event(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-24T12:00:00Z",
                "issue_id": "ENH-99",
                "issue_type": "ENH",
                "priority": "P2",
            }
        )
        transport.close()
        rows = recent(db, kind="issue")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "ENH-99"
        assert rows[0]["transition"] == "done"

    def test_issue_event_transition_mapping(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        events = [
            ("issue.completed", "done"),
            ("issue.deferred", "deferred"),
            ("issue.skipped", "cancelled"),
            ("issue.created", "open"),
            ("issue.started", "in_progress"),
        ]
        for event_type, _ in events:
            transport.send({"event": event_type, "ts": "2026-05-24T12:00:00Z", "issue_id": "X-1"})
        transport.close()
        rows = recent(db, kind="issue", limit=10)
        transitions = {r["transition"] for r in rows}
        for _, expected in events:
            assert expected in transitions

    def test_loop_event_does_not_create_issue_row(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "x", "state": "s"})
        transport.close()
        assert recent(db, kind="issue") == []

    def test_issue_event_is_fts_searchable(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-24T12:00:00Z",
                "issue_id": "ENH-1690",
                "issue_type": "ENH",
            }
        )
        transport.close()
        # FTS5 tokenizes "ENH-1690" as ["ENH", "1690"]; search the numeric token
        results = search(db, query="1690")
        assert any(r["kind"] == "issue" for r in results)

    def test_unrecognized_event_not_recorded_as_issue(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "action_output", "issue_id": "X-1"})
        transport.close()
        assert recent(db, kind="issue") == []


class TestSchemaV3:
    """v3 migration: unique dedup index on issue_events (ENH-1690)."""

    def test_dedup_index_exists_after_ensure_db(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='issue_events'"
            )
        }
        conn.close()
        assert "idx_issue_events_dedup" in indexes

    def test_v2_db_upgrades_to_v3(self, tmp_path: Path) -> None:
        """A v2 database gains the dedup index on next ensure_db()."""
        db = tmp_path / "session.db"
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
                issue_id TEXT, transition TEXT, discovered_by TEXT,
                issue_type TEXT, priority TEXT, completed_date TEXT,
                captured_at TEXT, completed_at TEXT
            );
            CREATE TABLE loop_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                loop_name TEXT, state TEXT, transition TEXT, retries INTEGER
            );
            CREATE TABLE user_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, content TEXT, source TEXT
            );
            CREATE TABLE message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, content TEXT
            );
            CREATE VIRTUAL TABLE search_index USING fts5(
                content, kind UNINDEXED, ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO meta(key, value) VALUES('schema_version', '2');
            """
        )
        conn.commit()
        conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='issue_events'"
            )
        }
        conn.close()
        assert int(version) == SCHEMA_VERSION
        assert "idx_issue_events_dedup" in indexes


class TestSchemaV4:
    """v4 migration: sessions table maps session_id to JSONL path (ENH-1710)."""

    def test_sessions_table_exists_after_ensure_db(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "sessions" in names

    def test_v3_db_upgrades_to_v4(self, tmp_path: Path) -> None:
        """A v3 database gains the sessions table on next ensure_db()."""
        db = tmp_path / "session.db"
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
                issue_id TEXT, transition TEXT, discovered_by TEXT,
                issue_type TEXT, priority TEXT, completed_date TEXT,
                captured_at TEXT, completed_at TEXT
            );
            CREATE TABLE loop_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                loop_name TEXT, state TEXT, transition TEXT, retries INTEGER
            );
            CREATE TABLE user_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, content TEXT, source TEXT
            );
            CREATE TABLE message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                session_id TEXT, content TEXT
            );
            CREATE VIRTUAL TABLE search_index USING fts5(
                content, kind UNINDEXED, ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup
                ON issue_events(issue_id, transition);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO meta(key, value) VALUES('schema_version', '3');
            """
        )
        conn.commit()
        conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert int(version) == SCHEMA_VERSION
        assert "sessions" in tables

    def test_sessions_insert_or_ignore_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("abc123", "/path/to/abc123.jsonl"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("abc123", "/path/to/abc123.jsonl"),
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        finally:
            conn.close()
        assert count == 1


class TestBackfillDedup:
    """_backfill_issues() is idempotent via INSERT OR IGNORE + unique index (ENH-1690)."""

    def test_double_backfill_produces_single_row(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "bugs"
        issues.mkdir(parents=True)
        (issues / "P1-BUG-10-x.md").write_text(
            "---\nid: BUG-10\nstatus: done\ntype: BUG\n---\n# x\n", encoding="utf-8"
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        rows = recent(db, kind="issue")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "BUG-10"
