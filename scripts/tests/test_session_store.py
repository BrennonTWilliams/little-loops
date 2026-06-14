"""Tests for little_loops.session_store - the unified SQLite + FTS5 session store."""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.session_store import (
    SCHEMA_VERSION,
    SQLiteTransport,
    _derive_transition,
    _estimate_tokens,
    _summarize_block,
    backfill,
    backfill_incremental,
    cli_event_context,
    compact_session,
    connect,
    ensure_db,
    is_correction,
    prune,
    recent,
    record_correction,
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
            "skill_events",
            "cli_events",
            "issue_snapshots",
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

        Bootstraps a real (versioned) SQLite legacy file, then drops a ``-shm``
        sidecar next to it, and asserts the legacy paths are moved away rather
        than orphaned. The ``-shm`` byte content is *not* asserted: ``ensure_db``
        now opens the database in WAL mode, so SQLite actively manages and
        rebuilds the shared-memory ``-shm`` file on open — preserving arbitrary
        bytes in it was only meaningful under the old rollback-journal mode.
        """
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        # Legacy sidecar is moved away, not orphaned at the old path.
        assert not (ll_dir / "session.db-shm").exists()

    def test_migration_skipped_when_new_db_exists(self, tmp_path: Path) -> None:
        """If both legacy and new exist, leave legacy alone (don't clobber)."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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


class TestConcurrencyHardening:
    """Lock-contention safety for the migration framework (the ``ll-issues``
    'table tool_events already exists' crash)."""

    def test_locked_db_error_is_not_misread_as_version_zero(self) -> None:
        """A transient ``database is locked`` must NOT be treated as a fresh DB.

        Regression for the crash: ``_current_version`` swallowed every
        ``OperationalError`` and returned 0, so a contended open re-ran
        migration 0 and died with "table tool_events already exists". Only a
        genuinely absent ``meta`` table ("no such table") means version 0.
        """
        from little_loops.session_store import _current_version

        class _LockedConn:
            def execute(self, _sql: str):  # noqa: ANN202 - test stub
                raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            _current_version(_LockedConn())  # type: ignore[arg-type]

    def test_missing_meta_table_still_reads_as_version_zero(self, tmp_path: Path) -> None:
        """A genuinely absent ``meta`` table is the one case that means v0."""
        from little_loops.session_store import _current_version

        db = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db))
        try:
            assert _current_version(conn) == 0
        finally:
            conn.close()

    def test_connect_applies_wal_and_busy_timeout(self, tmp_path: Path) -> None:
        """``connect`` configures WAL journal mode and a non-zero busy_timeout."""
        from little_loops.session_store import _BUSY_TIMEOUT_MS

        conn = connect(tmp_path / "history.db")
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == _BUSY_TIMEOUT_MS
        finally:
            conn.close()

    def test_concurrent_ensure_db_on_fresh_path(self, tmp_path: Path) -> None:
        """Many threads calling ``ensure_db`` on a fresh DB at once must produce
        exactly one schema with no 'table already exists' race."""
        import threading

        db = tmp_path / "history.db"
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            try:
                barrier.wait()
                ensure_db(db)
            except BaseException as exc:  # noqa: BLE001 - surface any race
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent ensure_db raced: {errors!r}"
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[
                0
            ]
            count = conn.execute("SELECT COUNT(*) FROM meta WHERE key='schema_version'").fetchone()[
                0
            ]
        finally:
            conn.close()
        assert int(version) == SCHEMA_VERSION
        assert count == 1


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
        issues.mkdir(parents=True, exist_ok=True)
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
        running.mkdir(parents=True, exist_ok=True)
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
        assert counts == {
            "issues": 0,
            "loops": 0,
            "tools": 0,
            "messages": 0,
            "assistant_messages": 0,
            "sessions": 0,
            "corrections": 0,
            "summaries": 0,
            "snapshots": 0,
        }

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
        issues.mkdir(exist_ok=True)
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

    def test_backfill_populates_corrections_from_correction_message(self, tmp_path: Path) -> None:
        """Backfill with a correction-pattern message populates user_corrections."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s-corr", "2026-06-03T10:00:00Z", "no, don't do that"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl]
        )
        assert counts["corrections"] == 1
        rows = recent(db, kind="correction")
        assert len(rows) == 1
        assert rows[0]["content"] == "no, don't do that"
        assert rows[0]["session_id"] == "s-corr"

    def test_backfill_corrections_gate_disabled(self, tmp_path: Path) -> None:
        """analytics.capture.corrections=false suppresses correction mining during backfill."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s-gate", "2026-06-03T10:00:00Z", "no, don't do that"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            config={"analytics": {"capture": {"corrections": False}}},
        )
        assert counts["corrections"] == 0
        assert len(recent(db, kind="correction")) == 0

    def test_backfill_corrections_idempotent(self, tmp_path: Path) -> None:
        """Running backfill twice on same JSONL produces exactly 1 correction row."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("s-idem", "2026-06-03T10:00:00Z", "no, don't do that"),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl])
        backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", jsonl_files=[jsonl])
        rows = recent(db, kind="correction")
        assert len(rows) == 1, "re-running backfill must not duplicate correction rows"


class TestBackfillIssuesV2Columns:
    """_backfill_issues() populates the v2 issue_events columns (ENH-1621)."""

    def test_v2_columns_populated_from_frontmatter(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "enhancements"
        issues.mkdir(parents=True, exist_ok=True)
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
        issues.mkdir(parents=True, exist_ok=True)
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

    def test_issue_event_captured_at_round_trip(self, tmp_path: Path) -> None:
        """captured_at in send() dict is stored and retrieved from issue_events."""
        db = tmp_path / "session.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-20T10:00:00Z",
                "issue_id": "ENH-1839",
                "captured_at": "2026-05-20T10:00:00Z",
            }
        )
        transport.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT captured_at FROM issue_events WHERE issue_id = ?", ("ENH-1839",)
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["captured_at"] == "2026-05-20T10:00:00Z"


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


class TestSchemaV5:
    """v5 migration: issue_sessions VIEW joins issue_events to message_events (ENH-1711)."""

    def test_issue_sessions_view_exists_after_ensure_db(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        conn.close()
        assert "issue_sessions" in names

    def test_issue_sessions_view_returns_match(self, tmp_path: Path) -> None:
        """A backfilled issue with a session that sent messages during its active period appears."""
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", "ENH-99", "open", "2026-01-10T00:00:00Z", None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", "sess-abc", "hello"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-abc", "/path/to/sess-abc.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT issue_id, session_id, jsonl_path FROM issue_sessions WHERE issue_id = ?",
                ("ENH-99",),
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-abc"
        assert rows[0]["jsonl_path"] == "/path/to/sess-abc.jsonl"

    def test_issue_sessions_excludes_null_captured_at(self, tmp_path: Path) -> None:
        """Live-emitted rows (captured_at=NULL) are excluded from the view."""
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?,?,?,?)",
                ("2026-01-10T12:00:00Z", "ENH-100", "open", None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", "sess-xyz", "hello"),
            )
            conn.commit()
        finally:
            conn.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT * FROM issue_sessions WHERE issue_id = ?", ("ENH-100",)
            ).fetchall()
        finally:
            conn.close()
        assert rows == []

    def test_live_emitted_row_with_captured_at_appears_in_view(self, tmp_path: Path) -> None:
        """A live-emitted issue_events row with captured_at set appears in issue_sessions VIEW."""
        db = tmp_path / "session.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?,?,?,?)",
                ("2026-05-20T10:00:00Z", "ENH-1839", "done", "2026-05-20T10:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-05-20T11:00:00Z", "sess-live", "worked on ENH-1839"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-live", "/path/to/sess-live.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT issue_id, session_id FROM issue_sessions WHERE issue_id = ?",
                ("ENH-1839",),
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-live"

    def test_v4_db_upgrades_to_v5(self, tmp_path: Path) -> None:
        """A v4 database gains the issue_sessions view on next ensure_db()."""
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
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, jsonl_path TEXT NOT NULL,
                started_at TEXT, project_path TEXT
            );
            CREATE VIRTUAL TABLE search_index USING fts5(
                content, kind UNINDEXED, ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_events_dedup
                ON issue_events(issue_id, transition);
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO meta(key, value) VALUES('schema_version', '4');
            """
        )
        conn.commit()
        conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        conn.close()
        assert int(version) == SCHEMA_VERSION
        assert "issue_sessions" in views


class TestBackfillDedup:
    """_backfill_issues() is idempotent via INSERT OR IGNORE + unique index (ENH-1690)."""

    def test_double_backfill_produces_single_row(self, tmp_path: Path) -> None:
        issues = tmp_path / ".issues" / "bugs"
        issues.mkdir(parents=True, exist_ok=True)
        (issues / "P1-BUG-10-x.md").write_text(
            "---\nid: BUG-10\nstatus: done\ntype: BUG\n---\n# x\n", encoding="utf-8"
        )
        db = tmp_path / "session.db"
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        backfill(db, issues_dir=tmp_path / ".issues", loops_dir=tmp_path / "no")
        rows = recent(db, kind="issue")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "BUG-10"


class TestSchemaV6:
    """v6 migration: last_backfill_ts meta key for incremental JSONL backfill (ENH-1830)."""

    def test_last_backfill_ts_key_in_meta_after_ensure_db(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_backfill_ts'").fetchone()
        finally:
            conn.close()
        assert row is not None, "last_backfill_ts key must exist in meta after v6 migration"

    def test_schema_version_is_seven(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        finally:
            conn.close()
        assert int(row[0]) == SCHEMA_VERSION
        assert SCHEMA_VERSION == 14


class TestBackfillIncremental:
    """backfill_incremental() filters JSONL by mtime and tracks last_backfill_ts (ENH-1830)."""

    def _make_tool_jsonl(self, directory: Path, session_id: str) -> Path:
        jsonl = directory / f"{session_id}.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {
                        "content": [
                            {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}
                        ]
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return jsonl

    def _make_msg_jsonl(self, directory: Path, session_id: str) -> Path:
        jsonl = directory / f"{session_id}.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": session_id,
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello from " + session_id},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return jsonl

    def test_processes_all_files_when_since_ts_zero(self, tmp_path: Path) -> None:
        jsonl = self._make_tool_jsonl(tmp_path, "s1")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        assert counts["tools"] >= 1

    def test_filters_files_with_future_since_ts(self, tmp_path: Path) -> None:
        """Files with mtime before a far-future since_ts are excluded."""
        jsonl = self._make_tool_jsonl(tmp_path, "s2")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=9_999_999_999.0)
        assert counts["tools"] == 0
        assert counts["messages"] == 0

    def test_writes_last_backfill_ts_after_run(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[], since_ts=0.0)
        conn = connect(db)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_backfill_ts'").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["value"] is not None

    def test_reads_last_backfill_ts_from_meta_when_since_none(self, tmp_path: Path) -> None:
        """When since_ts=None, meta value controls the mtime filter."""
        jsonl = self._make_tool_jsonl(tmp_path, "s3")
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('last_backfill_ts', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("9999-12-31T23:59:59Z",),
            )
            conn.commit()
        finally:
            conn.close()
        counts = backfill_incremental(db, jsonl_files=[jsonl])
        assert counts["tools"] == 0

    def test_missing_file_is_skipped_silently(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        counts = backfill_incremental(
            db, jsonl_files=[tmp_path / "nonexistent.jsonl"], since_ts=0.0
        )
        assert counts["tools"] == 0

    def test_messages_and_sessions_backfilled(self, tmp_path: Path) -> None:
        jsonl = self._make_msg_jsonl(tmp_path, "s4")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        assert counts["messages"] >= 1
        assert counts["sessions"] >= 1

    def test_sessions_inserted_from_jsonl(self, tmp_path: Path) -> None:
        jsonl = self._make_tool_jsonl(tmp_path, "sess-1")
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        finally:
            conn.close()
        assert count == 1


class TestBackfillIncrementalAssistantMessages:
    """Per-table watermark for assistant_messages (BUG-1882)."""

    def _make_assistant_text_jsonl(self, directory: Path, session_id: str) -> Path:
        jsonl = directory / f"{session_id}.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": [{"type": "text", "text": "hello from assistant"}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return jsonl

    def test_populates_assistant_messages_on_first_run(self, tmp_path: Path) -> None:
        """When last_backfill_ts_assistant_messages is absent, all files are processed."""
        jsonl = self._make_assistant_text_jsonl(tmp_path, "asst-1")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        assert counts["assistant_messages"] >= 1
        conn = connect(db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM assistant_messages").fetchone()[0]
        finally:
            conn.close()
        assert n >= 1

    def test_per_table_watermark_written_after_run(self, tmp_path: Path) -> None:
        """backfill_incremental writes last_backfill_ts_assistant_messages to meta."""
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[], since_ts=0.0)
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'last_backfill_ts_assistant_messages'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None and row["value"] is not None

    def test_historical_files_included_even_when_global_ts_excludes_them(
        self, tmp_path: Path
    ) -> None:
        """Files older than global last_backfill_ts are still processed for assistant_messages
        when last_backfill_ts_assistant_messages is absent (schema migration gap scenario)."""
        jsonl = self._make_assistant_text_jsonl(tmp_path, "asst-hist")
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            # Set global watermark to far future → global filter excludes the file
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('last_backfill_ts', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("9999-12-31T23:59:59Z",),
            )
            # No last_backfill_ts_assistant_messages → per-table ts defaults to 0
            conn.commit()
        finally:
            conn.close()

        counts = backfill_incremental(db, jsonl_files=[jsonl])
        # Global filter skips the file for other tables but assistant_messages uses its own ts
        assert counts["assistant_messages"] >= 1
        assert counts["tools"] == 0  # global ts still excludes tools

    def test_assistant_messages_respects_own_watermark_on_subsequent_runs(
        self, tmp_path: Path
    ) -> None:
        """Once last_backfill_ts_assistant_messages is set, future runs skip old files."""
        jsonl = self._make_assistant_text_jsonl(tmp_path, "asst-2")
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('last_backfill_ts_assistant_messages', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("9999-12-31T23:59:59Z",),
            )
            conn.commit()
        finally:
            conn.close()

        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        assert counts["assistant_messages"] == 0  # own watermark excludes the file


class TestIsCorrectionHeuristic:
    """ENH-1831: correction-detection heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "no, don't do that",
            "stop doing that",
            "revert that last change",
            "don't add comments",
            "No! That's wrong",
            "that's wrong, try again",
            "use snake_case instead",
            "actually that function is in utils.py",
            "you missed the import",
            "should be wrapped in a try/except",
            "remember that we always use dataclasses",
            "never use bare except clauses",
            "from now on always add type hints",
            "!remember always use snake_case",
            "!Remember use absolute imports",
            "wrong approach, use a generator",
        ],
    )
    def test_true_positives(self, text: str) -> None:
        assert is_correction(text), f"expected correction signal: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "no problem",
            "sounds good",
            "noted, thanks",
            "implement the login feature",
            "fix the authentication bug",
            "noted",
            "that should be fine",
            "use it as-is",
            "this is actually a great idea",
            "never mind, good work",
            "I'm always happy with this approach",
        ],
    )
    def test_true_negatives(self, text: str) -> None:
        assert not is_correction(text), f"expected non-correction: {text!r}"

    def test_extra_patterns_fire(self) -> None:
        assert is_correction("not quite what I wanted", extra_patterns=["not quite"])

    def test_extra_patterns_do_not_replace_builtins(self) -> None:
        assert is_correction("no, that's wrong", extra_patterns=["not quite"])

    def test_extra_patterns_empty(self) -> None:
        assert is_correction("no, don't do that", extra_patterns=[]) == is_correction(
            "no, don't do that"
        )
        assert not is_correction("sounds good", extra_patterns=[])


class TestRecordCorrection:
    """ENH-1831: record_correction() DB write round-trip."""

    def test_record_correction_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        record_correction(db, "sess-r1", "no, don't do that", "user_prompt_submit")
        rows = recent(db, kind="correction")
        assert len(rows) == 1
        assert rows[0]["content"] == "no, don't do that"
        assert rows[0]["source"] == "user_prompt_submit"

    def test_record_correction_truncates_to_512(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        long_text = "stop " + "x" * 600
        record_correction(db, None, long_text, "user_prompt_submit")
        rows = recent(db, kind="correction")
        assert len(rows[0]["content"]) <= 512

    def test_record_correction_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import search

        db = tmp_path / "session.db"
        record_correction(db, "sess-r2", "revert that last commit", "user_prompt_submit")
        results = search(db, query="revert")
        assert any(r["kind"] == "correction" for r in results)

    def test_record_correction_gate_disabled(self, tmp_path: Path) -> None:
        """capture.corrections: false suppresses write regardless of call site."""
        from little_loops.session_store import recent

        db = tmp_path / "session.db"
        record_correction(
            db,
            "sess-g1",
            "no, stop",
            "user_prompt_submit",
            config={"analytics": {"capture": {"corrections": False}}},
        )
        rows = recent(db, kind="correction")
        assert len(rows) == 0, "record_correction must be a no-op when capture.corrections is false"

    def test_write_file_event_gate_disabled(self, tmp_path: Path) -> None:
        """capture.file_events: false suppresses write regardless of call site."""
        from little_loops.session_store import recent, write_file_event

        db = tmp_path / "session.db"
        write_file_event(
            db,
            "sess-g2",
            "scripts/foo.py",
            "Read",
            config={"analytics": {"capture": {"file_events": False}}},
        )
        rows = recent(db, kind="file")
        assert len(rows) == 0, "write_file_event must be a no-op when capture.file_events is false"


class TestRecordSkillEvent:
    """ENH-1833: record_skill_event() DB write round-trip."""

    def test_record_skill_event_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s1", "refine-issue", "ENH-1833")
        rows = recent(db, kind="skill")
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "refine-issue"
        assert rows[0]["args"] == "ENH-1833"
        assert rows[0]["session_id"] == "sess-s1"

    def test_record_skill_event_truncates_args_to_200(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        long_args = "x" * 300
        record_skill_event(db, None, "capture-issue", long_args)
        rows = recent(db, kind="skill")
        assert len(rows[0]["args"]) <= 200

    def test_record_skill_event_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_skill_event, search

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s2", "ready-issue", "")
        # FTS5 tokenises hyphens, so query on individual word "ready"
        results = search(db, query="ready")
        assert any(r["kind"] == "skill" for r in results)

    def test_record_skill_event_config_stub_accepted(self, tmp_path: Path) -> None:
        """config= param is accepted (forward-compat stub for ENH-1835); no gate applied."""
        from little_loops.session_store import recent, record_skill_event

        db = tmp_path / "session.db"
        record_skill_event(db, "sess-s3", "check-code", "", config={"analytics": {}})
        rows = recent(db, kind="skill")
        assert len(rows) == 1, "config stub must not suppress the write"


class TestCliEventContext:
    """ENH-1848: cli_event_context() DB write round-trip and mechanics."""

    def test_cli_event_roundtrip(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with cli_event_context(db, binary="ll-refine-issue", args=["ENH-1848"]):
            pass
        rows = recent(db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-refine-issue"
        assert json.loads(rows[0]["args"]) == ["ENH-1848"]
        assert rows[0]["exit_code"] == 0
        assert rows[0]["duration_ms"] is not None

    def test_cli_event_exception_exit(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with pytest.raises(ValueError):
            with cli_event_context(db, binary="ll-check-code", args=[]):
                raise ValueError("simulated failure")
        rows = recent(db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["exit_code"] == 1

    def test_cli_event_duration_accuracy(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        with cli_event_context(db, binary="ll-session", args=["recent"]):
            pass
        rows = recent(db, kind="cli")
        assert rows[0]["duration_ms"] is not None
        assert isinstance(rows[0]["duration_ms"], int)
        assert rows[0]["duration_ms"] >= 0

    def test_schema_v8_cli_events_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert "cli_events" in names
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_cli_event_context_respects_LL_HISTORY_DB(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LL_HISTORY_DB env var must redirect DB writes when the default path is used."""
        from little_loops.session_store import DEFAULT_DB_PATH

        isolated_db = tmp_path / "isolated.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(isolated_db))
        with cli_event_context(DEFAULT_DB_PATH, binary="ll-test-env-var", args=["--check"]):
            pass
        rows = recent(isolated_db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-test-env-var"

    def test_cli_event_context_explicit_path_not_redirected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit path passed to cli_event_context must not be overridden by LL_HISTORY_DB."""

        explicit_db = tmp_path / "explicit.db"
        env_db = tmp_path / "env.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(env_db))
        # Pass a path that is NOT DEFAULT_DB_PATH — must write to explicit_db
        with cli_event_context(explicit_db, binary="ll-explicit", args=[]):
            pass
        rows = recent(explicit_db, kind="cli")
        assert len(rows) == 1
        assert rows[0]["binary"] == "ll-explicit"
        # env_db must be empty (not written to)
        assert not env_db.exists()


class TestMineCorrectionsFromMessages:
    """Unit tests for mine_corrections_from_messages() (ENH-1904)."""

    def test_mines_corrections_from_existing_message_events(self, tmp_path: Path) -> None:
        """mine_corrections_from_messages picks up pre-existing message_events rows."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-mine", "no, don't do that"),
            )
            conn.commit()
            count = mine_corrections_from_messages(conn)
            conn.commit()
            assert count == 1
        finally:
            conn.close()
        rows = recent(db, kind="correction")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "s-mine"

    def test_mine_corrections_idempotent(self, tmp_path: Path) -> None:
        """Calling mine_corrections_from_messages twice produces exactly 1 row."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-idem2", "no, don't do that"),
            )
            conn.commit()
            mine_corrections_from_messages(conn)
            conn.commit()
            mine_corrections_from_messages(conn)
            conn.commit()
        finally:
            conn.close()
        assert len(recent(db, kind="correction")) == 1

    def test_mine_corrections_gate_disabled(self, tmp_path: Path) -> None:
        """mine_corrections_from_messages respects analytics.capture.corrections gate."""
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import mine_corrections_from_messages

        db = tmp_path / "session.db"
        conn = ss_connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-03T10:00:00Z", "s-gated", "no, don't do that"),
            )
            conn.commit()
            count = mine_corrections_from_messages(
                conn, config={"analytics": {"capture": {"corrections": False}}}
            )
            conn.commit()
            assert count == 0
        finally:
            conn.close()
        assert len(recent(db, kind="correction")) == 0


class TestSchemaV9:
    """Verify that the v9 migration creates idx_corrections_dedup (ENH-1904)."""

    def test_schema_version_is_nine(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_idx_corrections_dedup_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_corrections_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "idx_corrections_dedup index must exist after ensure_db()"

    def test_v8_to_v9_migration(self, tmp_path: Path) -> None:
        """Manually bootstrap a v8 schema, then verify ensure_db() applies the v9 migration."""
        db = tmp_path / "history.db"
        from little_loops.session_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for sql in _MIGRATIONS[:8]:  # indices 0-7 = v1 through v8
                conn.executescript(sql)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '8')")
            conn.commit()
        finally:
            conn.close()
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            index_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_corrections_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION  # ensure_db applies all pending migrations
        assert index_row is not None


class TestSchemaV10:
    """Verify that the v10 migration creates summary_nodes and summary_spans (FEAT-1712)."""

    def test_schema_version_is_ten(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_summary_nodes_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "summary_nodes" in names
        assert "summary_spans" in names

    def test_summary_nodes_leaf_dedup_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_leaf_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "idx_summary_nodes_leaf_dedup index must exist after ensure_db()"

    def test_summary_nodes_condensed_dedup_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_condensed_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, (
            "idx_summary_nodes_condensed_dedup index must exist after ensure_db()"
        )

    def test_summary_nodes_parent_id_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_parent_id'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "idx_summary_nodes_parent_id index must exist after ensure_db()"

    def test_v9_to_v10_migration(self, tmp_path: Path) -> None:
        """Manually bootstrap a v9 schema, then verify ensure_db() applies v10+v11 migrations."""
        db = tmp_path / "history.db"
        from little_loops.session_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for sql in _MIGRATIONS[:9]:  # indices 0–8 = v1 through v9
                conn.executescript(sql)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '9')")
            conn.commit()
        finally:
            conn.close()
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert int(version[0]) == 14
        assert "summary_nodes" in names
        assert "summary_spans" in names
        assert "assistant_messages" in names


class TestSchemaV12:
    """Verify that the v12 migration adds level column and cross-session dedup index (ENH-1953)."""

    def test_schema_version_is_twelve(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_summary_nodes_has_level_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info('summary_nodes')")}
        finally:
            conn.close()
        assert "level" in cols

    def test_cross_dedup_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_cross_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "idx_summary_nodes_cross_dedup index must exist after ensure_db()"

    def test_v11_to_v12_migration(self, tmp_path: Path) -> None:
        """Bootstrap v11 schema, insert a row, migrate to v12, verify level=0 preserved."""
        db = tmp_path / "history.db"
        from little_loops.session_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for sql in _MIGRATIONS[:11]:  # v1–v11
                conn.executescript(sql)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '11')")
            # Insert a row to verify data preservation through ALTER TABLE ADD COLUMN
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
                " VALUES('condensed', 'pre-migration test', 100, 's-test', NULL, NULL, '2026-01-01T00:00:00Z')"
            )
            conn.commit()
        finally:
            conn.close()
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            cols = {r[1] for r in conn.execute("PRAGMA table_info('summary_nodes')")}
            index_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_summary_nodes_cross_dedup'"
            ).fetchone()
            # Verify data preserved with level=0 (DEFAULT)
            row = conn.execute("SELECT level FROM summary_nodes WHERE kind='condensed'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert "level" in cols
        assert index_row is not None
        assert row is not None and row[0] == 0


class TestCompactSession:
    """Tests for compact_session() and the summary DAG (FEAT-1712)."""

    def _make_db_with_messages(self, tmp_path: Path, session_id: str, messages: list[str]) -> Path:
        """Bootstrap a DB with the given session_id and user messages."""
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            # Seed sessions table so the session exists
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            for i, content in enumerate(messages):
                ts = f"2026-01-01T00:{i:02d}:00Z"
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (ts, session_id, content),
                )
            conn.commit()
        finally:
            conn.close()
        return db

    def test_compact_session_creates_leaf_nodes(self, tmp_path: Path) -> None:
        """compact_session() creates at least one leaf node for a session with messages."""
        session_id = "test-session-leaf"
        # One message that fits in a single block
        db = self._make_db_with_messages(tmp_path, session_id, ["Hello world, this is a test."])
        compact_session(session_id, db)
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT id, kind, session_id FROM summary_nodes WHERE session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) >= 1
        assert any(r["kind"] == "leaf" for r in rows)

    def test_compact_session_idempotent(self, tmp_path: Path) -> None:
        """Running compact_session() twice does not create duplicate summary_nodes."""
        session_id = "test-session-idem"
        db = self._make_db_with_messages(
            tmp_path, session_id, ["First message.", "Second message."]
        )
        compact_session(session_id, db)
        compact_session(session_id, db)  # second call must not create duplicates
        conn = connect(db)
        try:
            leaf_rows = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchall()
            condensed_rows = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='condensed' AND session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        # Idempotency: second run adds zero new rows
        assert len(leaf_rows) >= 1  # leaves from first run still present
        assert len(condensed_rows) <= 1  # at most one condensed per session

    def test_compact_session_creates_spans(self, tmp_path: Path) -> None:
        """compact_session() populates summary_spans linking leaf nodes to message_events."""
        session_id = "test-session-spans"
        db = self._make_db_with_messages(tmp_path, session_id, ["Span test message."])
        compact_session(session_id, db)
        conn = connect(db)
        try:
            spans = conn.execute(
                "SELECT ss.summary_id, ss.message_event_id"
                " FROM summary_spans ss"
                " JOIN summary_nodes sn ON sn.id = ss.summary_id"
                " WHERE sn.session_id=?",
                (session_id,),
            ).fetchall()
            # Single-message fixture → single leaf → no condensed node → parent_id is NULL
            leaf_parent = conn.execute(
                "SELECT parent_id FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        assert len(spans) >= 1
        assert leaf_parent is not None
        assert leaf_parent["parent_id"] is None

    def test_compact_session_condensed_node_when_multiple_leaves(self, tmp_path: Path) -> None:
        """A condensed node is created when a session has >= 2 leaf nodes."""
        session_id = "test-session-condensed"
        # Many short messages so greedy grouping with tiny budget creates multiple leaves
        messages = [f"Message number {i}. " * 5 for i in range(30)]
        db = self._make_db_with_messages(tmp_path, session_id, messages)
        # Use a very small budget (10 tokens ~ 40 chars) to force multiple leaf blocks
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        # Mock subprocess so _call_llm_for_summary never invokes the real claude binary
        # (which would trigger SessionStart hooks writing to the production db).
        short_summary = "Condensed summary."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            compact_session(session_id, db, config=config)
        conn = connect(db)
        try:
            leaf_count = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchone()[0]
            condensed_count = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind='condensed' AND session_id=?",
                (session_id,),
            ).fetchone()[0]
            # Verify parent_id linkage: leaves should point to the condensed node
            condensed_id = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='condensed' AND session_id=?",
                (session_id,),
            ).fetchone()["id"]
            leaf_parent_ids = conn.execute(
                "SELECT parent_id FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        assert leaf_count >= 2
        assert condensed_count == 1
        assert all(row["parent_id"] == condensed_id for row in leaf_parent_ids), (
            f"Expected all leaf nodes to have parent_id={condensed_id}, "
            f"got {[row['parent_id'] for row in leaf_parent_ids]}"
        )

    def test_compact_session_empty_session_is_noop(self, tmp_path: Path) -> None:
        """compact_session() returns 0 and inserts nothing for a session with no messages."""
        session_id = "test-session-empty"
        db = self._make_db_with_messages(tmp_path, session_id, [])
        result = compact_session(session_id, db)
        assert result == 0
        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE session_id=?", (session_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 0

    def test_backfill_with_compaction_enabled(self, tmp_path: Path) -> None:
        """backfill() runs compaction when config enables it."""
        jsonl = tmp_path / "session.jsonl"
        session_id = "test-backfill-compact"
        import json

        records = [
            {
                "type": "user",
                "sessionId": session_id,
                "timestamp": f"2026-01-01T00:{i:02d}:00Z",
                "message": {"content": f"Backfill compaction message {i}."},
            }
            for i in range(5)
        ]
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        db = tmp_path / "history.db"
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 4096}}}
        # Mock subprocess to avoid real LLM calls in test; return a short summary
        # that passes the size check so level 1 is accepted.
        short_summary = "Compacted summary."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            counts = backfill(db, jsonl_files=[jsonl], config=config)
        assert counts["summaries"] >= 1
        conn = connect(db)
        try:
            leaf_count = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchone()[0]
            # Single-block fixture (5 messages fit in 4096 tokens) → parent_id is NULL
            parent_rows = conn.execute(
                "SELECT parent_id FROM summary_nodes WHERE kind='leaf' AND session_id=?",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        assert leaf_count >= 1
        assert all(row["parent_id"] is None for row in parent_rows)

    def test_backfill_compaction_disabled_by_default(self, tmp_path: Path) -> None:
        """backfill() does not compact when config is absent (default disabled)."""
        jsonl = tmp_path / "session.jsonl"
        import json

        record = {
            "type": "user",
            "sessionId": "s-no-compact",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": "No compaction by default."},
        }
        jsonl.write_text(json.dumps(record) + "\n", encoding="utf-8")
        db = tmp_path / "history.db"
        counts = backfill(db, jsonl_files=[jsonl])  # no config → compaction.enabled=False
        assert counts["summaries"] == 0
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM summary_nodes").fetchone()[0]
        finally:
            conn.close()
        assert count == 0

    # -- cross-session condensation tests (ENH-1954) -------------------------------

    def _make_multi_session_db(self, tmp_path: Path, sessions: list[tuple[str, list[str]]]) -> Path:
        """Bootstrap a DB with multiple sessions, each with messages."""
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            for session_id, messages in sessions:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                    (session_id, str(tmp_path / f"{session_id}.jsonl")),
                )
                for i, content in enumerate(messages):
                    ts = f"2026-01-01T00:{i:02d}:00Z"
                    conn.execute(
                        "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                        (ts, session_id, content),
                    )
            conn.commit()
        finally:
            conn.close()
        return db

    def test_cross_session_condensation_produces_root(self, tmp_path: Path) -> None:
        """Cross-session pass creates exactly one root node with session_id=NULL, level=max."""
        from little_loops.session_store import _compact_sessions

        sessions = [
            (f"cross-root-sess-{i}", [f"Message {j} in session {i}. " * 5 for j in range(30)])
            for i in range(2)
        ]
        db = self._make_multi_session_db(tmp_path, sessions)
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        short_summary = "Compacted."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            conn = connect(db)
            try:
                _compact_sessions(conn, config)
                conn.commit()
            finally:
                conn.close()

        conn = connect(db)
        try:
            # Verify per-session condensed nodes exist
            per_session = conn.execute(
                "SELECT id, level FROM summary_nodes"
                " WHERE kind='condensed' AND session_id IS NOT NULL"
            ).fetchall()
            # Verify cross-session nodes exist
            cross_session = conn.execute(
                "SELECT id, level, parent_id FROM summary_nodes"
                " WHERE kind='condensed' AND session_id IS NULL ORDER BY level"
            ).fetchall()
        finally:
            conn.close()

        assert len(per_session) >= 2, "Expected ≥2 per-session condensed nodes"
        assert len(cross_session) >= 1, "Expected ≥1 cross-session condensed node"
        # Root is the highest-level cross-session node
        max_level = max(r["level"] for r in cross_session)
        roots = [r for r in cross_session if r["level"] == max_level]
        assert len(roots) == 1, f"Expected exactly 1 root, got {len(roots)}"
        # Root should have no parent
        assert roots[0]["parent_id"] is None

    def test_cross_session_condensation_idempotent(self, tmp_path: Path) -> None:
        """Running cross-session pass twice does not create duplicate higher-order nodes."""
        from little_loops.session_store import _compact_sessions

        sessions = [
            (f"cross-idem-sess-{i}", [f"Msg {j} sess {i}. " * 5 for j in range(30)])
            for i in range(2)
        ]
        db = self._make_multi_session_db(tmp_path, sessions)
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        short_summary = "Compacted."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            # First run
            conn = connect(db)
            try:
                _compact_sessions(conn, config)
                conn.commit()
            finally:
                conn.close()
            # Second run
            conn = connect(db)
            try:
                _compact_sessions(conn, config)
                conn.commit()
            finally:
                conn.close()

        conn = connect(db)
        try:
            cross_session = conn.execute(
                "SELECT level, COUNT(*) as cnt FROM summary_nodes"
                " WHERE kind='condensed' AND session_id IS NULL"
                " GROUP BY level ORDER BY level"
            ).fetchall()
        finally:
            conn.close()

        # Idempotency: each level should have at most one condensed node
        # (since with 2 sessions, each level groups into a single node)
        for row in cross_session:
            assert row["cnt"] <= 1, (
                f"Duplicate cross-session nodes at level {row['level']}: found {row['cnt']}"
            )

    def test_cross_session_condensation_parent_id_links_existing(self, tmp_path: Path) -> None:
        """Re-running _compact_sessions sets parent_id on existing per-session condensed nodes."""
        from little_loops.session_store import _compact_sessions

        sessions = [
            (f"cross-link-sess-{i}", [f"Link msg {j} in s{i}. " * 5 for j in range(30)])
            for i in range(2)
        ]
        db = self._make_multi_session_db(tmp_path, sessions)
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        short_summary = "Linked summary."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            conn = connect(db)
            try:
                _compact_sessions(conn, config)
                conn.commit()
            finally:
                conn.close()

        # After first run, verify parent_id is set on per-session condensed nodes
        conn = connect(db)
        try:
            per_session = conn.execute(
                "SELECT id, parent_id FROM summary_nodes"
                " WHERE kind='condensed' AND session_id IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()

        assert len(per_session) >= 2
        for row in per_session:
            assert row["parent_id"] is not None, (
                f"Per-session condensed node {row['id']} has NULL parent_id after"
                f" cross-session pass"
            )

    def test_cross_session_disabled_preserves_old_behavior(self, tmp_path: Path) -> None:
        """cross_session_enabled: false skips the cross-session pass entirely."""
        from little_loops.session_store import _compact_sessions

        sessions = [
            (f"cross-off-sess-{i}", [f"Msg {j} in session {i}. " * 5 for j in range(30)])
            for i in range(2)
        ]
        db = self._make_multi_session_db(tmp_path, sessions)
        config = {
            "history": {
                "compaction": {
                    "enabled": True,
                    "budget_tokens": 10,
                    "cross_session_enabled": False,
                }
            }
        }
        short_summary = "Off."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            conn = connect(db)
            try:
                _compact_sessions(conn, config)
                conn.commit()
            finally:
                conn.close()

        conn = connect(db)
        try:
            cross_session = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind='condensed' AND session_id IS NULL"
            ).fetchone()[0]
            per_session = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes"
                " WHERE kind='condensed' AND session_id IS NOT NULL"
            ).fetchone()[0]
        finally:
            conn.close()

        assert cross_session == 0, (
            f"cross_session_enabled=false should produce no cross-session nodes,"
            f" got {cross_session}"
        )
        assert per_session >= 2, "Per-session compaction should still run"


# -- helpers for _summarize_block tests -----------------------------------------


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    """Create a subprocess.CompletedProcess mock result."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _llm_response(result_text: str) -> str:
    """Build a JSON envelope matching the Claude CLI --output-format json shape."""
    return json.dumps({"type": "result", "subtype": "success", "result": result_text})


class TestEstimateTokens:
    """Unit tests for _estimate_tokens()."""

    def test_empty_string_returns_zero(self) -> None:
        assert _estimate_tokens("") == 0

    def test_ascii_text_returns_len_div_4(self) -> None:
        assert _estimate_tokens("abcd") == 1
        assert _estimate_tokens("abcdefgh") == 2
        # "this is a test of 40 chars total." = 35 chars → 35 // 4 = 8
        assert _estimate_tokens("this is a test of 40 chars total.") == 8

    def test_short_string_rounds_down(self) -> None:
        assert _estimate_tokens("abc") == 0

    def test_unicode_multibyte(self) -> None:
        # ≟ chars/token is a coarse approximation; unicode chars count as 1 len
        text = "こんにちは世界"  # 7 chars (multi-byte UTF-8)
        assert _estimate_tokens(text) == 1  # 7 // 4 = 1

    def test_very_long_string(self) -> None:
        text = "x" * 10_000
        assert _estimate_tokens(text) == 2500  # 10000 // 4


class TestSummarizeBlock:
    """Tests for the three-level LCM Algorithm 3 escalation in _summarize_block()."""

    # Input must exceed the 25-token short-circuit guard in _summarize_block()
    SHORT_INPUT = [
        "Hello world, this is a test message with enough content to exceed "
        "the short-circuit guard threshold in the summarization function."
    ]
    SHORT_INPUT_EST = _estimate_tokens("\n---\n".join(SHORT_INPUT))

    def test_level_1_accepts_smaller_summary(self) -> None:
        """Level 1: LLM returns a summary smaller than input — accepted immediately."""
        short_summary = "Short summary."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(short_summary)
            )
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        assert result == short_summary
        # Only one subprocess call (level 1 succeeded)
        assert mock_run.call_count == 1

    def test_level_1_escalates_when_summary_not_smaller(self) -> None:
        """Level 1 summary >= input size → escalates to level 2."""
        verbose = "x" * (self.SHORT_INPUT_EST * 4 + 10)  # longer than input
        short_summary = "Short bullet list."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            # Level 1 returns verbose (long), level 2 returns short
            mock_run.side_effect = [
                _make_completed(returncode=0, stdout=_llm_response(verbose)),
                _make_completed(returncode=0, stdout=_llm_response(short_summary)),
            ]
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        assert result == short_summary
        assert mock_run.call_count == 2  # level 1 + level 2

    def test_level_2_accepts_smaller_summary(self) -> None:
        """Level 2 produces a smaller summary after level 1 fails to reduce."""
        verbose = "x" * (self.SHORT_INPUT_EST * 4 + 10)
        medium = "Medium summary but still verbose." * 20  # verbose level 2
        # Both levels fail, fall through to truncation
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _make_completed(returncode=0, stdout=_llm_response(verbose)),
                _make_completed(returncode=0, stdout=_llm_response(medium)),
            ]
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        assert mock_run.call_count == 2
        # Result was truncated (level 3) because both LLM calls returned long text
        combined = "\n---\n".join(self.SHORT_INPUT)
        assert result == combined[: min(256 * 4, 2048)]

    def test_level_3_truncation_when_llm_fails(self) -> None:
        """LLM call raises FileNotFoundError → all levels escalate → truncation."""
        with patch(
            "little_loops.session_store.subprocess.run",
            side_effect=FileNotFoundError("claude"),
        ):
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        combined = "\n---\n".join(self.SHORT_INPUT)
        assert result == combined[: min(256 * 4, 2048)]

    def test_level_3_truncation_when_timeout(self) -> None:
        """LLM call times out → escalates through levels → truncation."""
        with patch(
            "little_loops.session_store.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=60),
        ):
            result = _summarize_block(self.SHORT_INPUT, budget=1024)
        combined = "\n---\n".join(self.SHORT_INPUT)
        assert result == combined[: min(1024 * 4, 2048)]

    def test_level_3_truncation_when_nonzero_returncode(self) -> None:
        """LLM returns non-zero exit code → escalates → truncation."""
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(returncode=1, stderr="API error")
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        assert mock_run.call_count == 2  # both levels tried, both failed
        combined = "\n---\n".join(self.SHORT_INPUT)
        assert result == combined[: min(256 * 4, 2048)]

    def test_truncation_uses_min_cap(self) -> None:
        """Truncation respects the min(budget * 4, 2048) cap."""
        long_input = ["Long message. " * 100]
        # Force LLM failure so truncation is used
        with patch(
            "little_loops.session_store.subprocess.run",
            side_effect=FileNotFoundError("claude"),
        ):
            result = _summarize_block(long_input, budget=4096)
        # budget=4096 → budget * 4 = 16384, but cap at 2048
        assert len(result) <= 2048

    def test_json_envelope_parsing(self) -> None:
        """The result field is extracted from the JSON envelope, not stored raw."""
        summary_text = "Extracted summary prose."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response(summary_text)
            )
            result = _summarize_block(self.SHORT_INPUT, budget=256)
        # Result is the extracted prose, not the JSON envelope
        assert result == summary_text
        assert "{" not in result

    def test_model_and_timeout_wired_to_subprocess(self) -> None:
        """model and timeout params flow through to subprocess.run."""
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(returncode=0, stdout=_llm_response("ok"))
            _summarize_block(self.SHORT_INPUT, budget=256, model="haiku", timeout=30)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 30
        # model flows to build_blocking_json, not directly to subprocess.run;
        # we verify it was passed to resolve_host().build_blocking_json
        # The subprocess call uses inv.binary/inv.args from the HostInvocation

    def test_escalation_logs_warning(self, caplog) -> None:
        """Escalation produces WARNING log messages."""
        verbose = "x" * (self.SHORT_INPUT_EST * 4 + 10)
        short_summary = "Short."
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _make_completed(returncode=0, stdout=_llm_response(verbose)),
                _make_completed(returncode=0, stdout=_llm_response(short_summary)),
            ]
            with caplog.at_level(logging.WARNING, logger="little_loops.session_store"):
                _summarize_block(self.SHORT_INPUT, budget=256)
        assert any("escalating to level 2" in m for m in caplog.messages)

    def test_multiple_messages_joined(self) -> None:
        """Multiple messages are joined with --- separator."""
        # Messages must exceed the 25-token short-circuit guard
        messages = [
            "Message one with enough text to pass the guard threshold.",
            "Message two also has plenty of content for testing.",
            "Message three is similarly substantive in length.",
        ]
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(returncode=0, stdout=_llm_response("short"))
            _summarize_block(messages, budget=256)
        # The prompt text appears in the subprocess args regardless of host
        # convention: Claude Code uses -p <prompt>, Codex appends directly, etc.
        cmd_args = mock_run.call_args[0][0]
        prompt_args = [a for a in cmd_args if isinstance(a, str) and "Message one" in a]
        assert len(prompt_args) == 1, f"Expected one arg containing the prompt, got {prompt_args}"
        prompt = prompt_args[0]
        assert "Message one" in prompt
        assert "\n---\n" in prompt
        assert "Message three" in prompt


class TestPrune:
    """Retention/compaction policy for history.db raw event tables (ENH-1906)."""

    # Config that disables both dual gates so pruning always runs in tests.
    _GATES_OPEN = {"analytics": {"retention": {"min_project_age_days": 0, "min_db_size_mb": 0}}}

    def _insert_old_row(
        self, conn: sqlite3.Connection, table: str, ts: str = "2020-01-01T00:00:00Z"
    ) -> None:
        """Insert a minimal row with an old timestamp into a prunable table."""
        if table == "tool_events":
            conn.execute("INSERT INTO tool_events(ts) VALUES(?)", (ts,))
        elif table == "cli_events":
            conn.execute(
                "INSERT INTO cli_events(ts, binary, args) VALUES(?, 'll-session', '[]')", (ts,)
            )
        elif table == "file_events":
            conn.execute("INSERT INTO file_events(ts) VALUES(?)", (ts,))
        elif table == "message_events":
            conn.execute("INSERT INTO message_events(ts) VALUES(?)", (ts,))
        conn.commit()

    def _insert_session(self, conn: sqlite3.Connection, started_at: str) -> None:
        """Insert a session row with the given started_at timestamp."""
        conn.execute(
            "INSERT INTO sessions(session_id, jsonl_path, started_at) VALUES(?,?,?)",
            ("test-session", "test.jsonl", started_at),
        )
        conn.commit()

    def test_both_gates_unmet_by_default_fresh_db(self, tmp_path: Path) -> None:
        """Fresh small DB with no sessions fails both gates."""
        db = tmp_path / "h.db"
        result = prune(db)
        assert not result["pruned"]
        assert len(result["gate_unmet"]) == 2

    def test_blocks_when_project_too_young(self, tmp_path: Path) -> None:
        """Gate fails when project age < threshold even if DB is large enough."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_session(conn, "2026-05-01T00:00:00Z")  # ~35 days old
        conn.close()
        config = {"analytics": {"retention": {"min_project_age_days": 365, "min_db_size_mb": 0}}}
        result = prune(db, config=config)
        assert not result["pruned"]
        assert any("project age" in g for g in result["gate_unmet"])
        assert result["project_age_days"] < 365

    def test_blocks_when_db_too_small(self, tmp_path: Path) -> None:
        """Gate fails when DB size < threshold even if project is old enough."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_session(conn, "2020-01-01T00:00:00Z")  # very old
        conn.close()
        config = {"analytics": {"retention": {"min_project_age_days": 0, "min_db_size_mb": 9999}}}
        result = prune(db, config=config)
        assert not result["pruned"]
        assert any("db size" in g for g in result["gate_unmet"])

    def test_gate_unmet_messages_include_thresholds(self, tmp_path: Path) -> None:
        """gate_unmet entries quote the threshold values for operator visibility."""
        db = tmp_path / "h.db"
        config = {"analytics": {"retention": {"min_project_age_days": 365, "min_db_size_mb": 800}}}
        result = prune(db, config=config)
        assert any("365d" in g for g in result["gate_unmet"])
        assert any("800MB" in g for g in result["gate_unmet"])

    def test_prunes_old_rows_from_high_volume_tables(self, tmp_path: Path) -> None:
        """Rows older than raw_event_max_age_days are deleted from all prunable tables."""
        db = tmp_path / "h.db"
        conn = connect(db)
        for table in ("tool_events", "cli_events", "file_events", "message_events"):
            self._insert_old_row(conn, table)
        conn.close()

        config = {**self._GATES_OPEN, "analytics": {**self._GATES_OPEN["analytics"]}}
        config["analytics"]["retention"]["raw_event_max_age_days"] = 90
        result = prune(db, config=config)

        assert result["pruned"]
        conn2 = connect(db)
        for table in ("tool_events", "cli_events", "file_events", "message_events"):
            count = conn2.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} should be empty after prune"
            assert result["deleted"][table] == 1
        conn2.close()

    def test_retains_recent_rows(self, tmp_path: Path) -> None:
        """Rows newer than the cutoff are kept after pruning."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_old_row(conn, "tool_events", "2020-01-01T00:00:00Z")
        conn.execute("INSERT INTO tool_events(ts) VALUES(?)", ("2099-12-31T00:00:00Z",))
        conn.commit()
        conn.close()

        result = prune(db, config=self._GATES_OPEN)
        assert result["deleted"]["tool_events"] == 1

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
        conn2.close()
        assert count == 1  # only the future row survives

    def test_high_value_tables_never_pruned(self, tmp_path: Path) -> None:
        """issue_events and user_corrections are never deleted by prune()."""
        db = tmp_path / "h.db"
        conn = connect(db)
        conn.execute(
            "INSERT INTO issue_events(ts, issue_id, transition) VALUES(?,?,?)",
            ("2020-01-01T00:00:00Z", "ENH-1906", "open"),
        )
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?,?,?,?)",
            ("2020-01-01T00:00:00Z", "s1", "don't do that", "message"),
        )
        conn.commit()
        conn.close()

        prune(db, config=self._GATES_OPEN)

        conn2 = connect(db)
        ie_count = conn2.execute("SELECT COUNT(*) FROM issue_events").fetchone()[0]
        uc_count = conn2.execute("SELECT COUNT(*) FROM user_corrections").fetchone()[0]
        conn2.close()
        assert ie_count == 1
        assert uc_count == 1

    def test_idempotent(self, tmp_path: Path) -> None:
        """Second prune call with no new rows reports 0 deleted."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_old_row(conn, "tool_events")
        conn.close()

        prune(db, config=self._GATES_OPEN)
        result2 = prune(db, config=self._GATES_OPEN)
        assert result2["pruned"]
        assert result2["deleted"].get("tool_events", 0) == 0

    def test_dry_run_does_not_delete_rows(self, tmp_path: Path) -> None:
        """dry_run=True counts rows without deleting them."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_old_row(conn, "message_events")
        conn.close()

        result = prune(db, config=self._GATES_OPEN, dry_run=True)
        assert result["pruned"]
        assert result["deleted"]["message_events"] == 1
        assert not result["vacuumed"]

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM message_events").fetchone()[0]
        conn2.close()
        assert count == 1  # row still present

    def test_null_raw_event_max_age_disables_pruning(self, tmp_path: Path) -> None:
        """raw_event_max_age_days=null means no table is pruned."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_old_row(conn, "tool_events")
        conn.close()

        config = {
            "analytics": {
                "retention": {
                    "min_project_age_days": 0,
                    "min_db_size_mb": 0,
                    "raw_event_max_age_days": None,
                }
            }
        }
        result = prune(db, config=config)
        assert result["pruned"]
        assert result["deleted"] == {}

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
        conn2.close()
        assert count == 1

    def test_vacuum_runs_after_prune(self, tmp_path: Path) -> None:
        """vacuumed flag is set True when pruning runs and rows are deleted."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_old_row(conn, "cli_events")
        conn.close()

        result = prune(db, config=self._GATES_OPEN)
        assert result["vacuumed"]

    def test_returns_project_age_and_db_size(self, tmp_path: Path) -> None:
        """Result always includes measured project_age_days and db_size_mb."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_session(conn, "2022-01-01T00:00:00Z")
        conn.close()

        result = prune(db)
        assert result["project_age_days"] > 0
        assert result["db_size_mb"] > 0


class TestSchemaV13:
    """Verify that the v13 migration creates correction_retirements table (ENH-2046)."""

    def test_schema_version_is_thirteen(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_correction_retirements_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name='correction_retirements'"
            ).fetchone()
        finally:
            conn.close()
        assert result is not None, "correction_retirements table must exist after ensure_db()"

    def test_retirement_fingerprint_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_retirements_fingerprint'"
            ).fetchone()
        finally:
            conn.close()
        assert result is not None, "idx_retirements_fingerprint index must exist after ensure_db()"


class TestSchemaV14:
    """Verify that the v14 migration creates issue_snapshots table (ENH-2151)."""

    def test_schema_version_is_fourteen(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert SCHEMA_VERSION == 14
        assert int(row[0]) == 14

    def test_issue_snapshots_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name='issue_snapshots'"
            ).fetchone()
        finally:
            conn.close()
        assert result is not None, "issue_snapshots table must exist after ensure_db()"

    def test_issue_snapshots_dedup_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='idx_issue_snapshots_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert result is not None, "idx_issue_snapshots_dedup index must exist after ensure_db()"

    def test_v13_to_v14_migration(self, tmp_path: Path) -> None:
        """Bootstrapping a v13 DB then calling ensure_db() applies the v14 migration."""
        db = tmp_path / "history.db"
        from little_loops.session_store import _MIGRATIONS

        conn = sqlite3.connect(str(db))
        try:
            for stmt in _MIGRATIONS[:13]:
                for s in stmt.split(";"):
                    s = s.strip()
                    if s:
                        conn.execute(s)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '13')")
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert int(version[0]) == 14
        assert "issue_snapshots" in names


class TestRecordIssueSnapshot:
    """ENH-2151: record_issue_snapshot() DB write round-trip."""

    def _make_issue_file(self, directory: Path, issue_id: str, title: str, status: str) -> Path:
        path = directory / f"P2-{issue_id}-test.md"
        path.write_text(
            f"---\nid: {issue_id}\ntype: ENH\npriority: P2\nstatus: {status}\n"
            f"title: {title}\n---\n\n# {title}\n\nBody text for {issue_id}.",
            encoding="utf-8",
        )
        return path

    def test_record_issue_snapshot_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")

        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT * FROM issue_snapshots WHERE issue_id='ENH-2151'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["issue_id"] == "ENH-2151"
        assert row["transition"] == "done"
        assert row["title"] == "Store snapshots"
        assert "Body text for ENH-2151" in (row["body"] or "")

    def test_record_issue_snapshot_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot, search

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")
        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))

        results = search(db, query="snapshots")
        assert any(r["kind"] == "snapshot" for r in results)

    def test_record_issue_snapshot_idempotent(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        issue_file = self._make_issue_file(tmp_path, "ENH-2151", "Store snapshots", "done")

        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))
        record_issue_snapshot(db, "ENH-2151", "done", str(issue_file))  # duplicate

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM issue_snapshots WHERE issue_id='ENH-2151' AND transition='done'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "INSERT OR IGNORE must deduplicate on (issue_id, transition)"

    def test_record_issue_snapshot_missing_file_is_noop(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_issue_snapshot

        db = tmp_path / "history.db"
        record_issue_snapshot(db, "ENH-9999", "done", str(tmp_path / "nonexistent.md"))

        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0]
        finally:
            conn.close()
        assert count == 0, "Missing file should produce no rows"


class TestBackfillSnapshots:
    """ENH-2151: _backfill_snapshots() hydrates issue_snapshots from .issues/."""

    def _make_issues_dir(self, root: Path) -> Path:
        issues = root / ".issues" / "enhancements"
        issues.mkdir(parents=True, exist_ok=True)
        (issues / "P2-ENH-2151-store-snapshots.md").write_text(
            "---\nid: ENH-2151\ntype: ENH\npriority: P2\nstatus: done\n"
            "title: Store snapshots\n---\n\n# Store snapshots\n\nBody content here.",
            encoding="utf-8",
        )
        (issues / "P3-ENH-2200-another.md").write_text(
            "---\nid: ENH-2200\ntype: ENH\npriority: P3\nstatus: open\n"
            "title: Another issue\n---\n\n# Another issue\n\nMore content.",
            encoding="utf-8",
        )
        return root / ".issues"

    def test_backfill_snapshots_hydrates_table(self, tmp_path: Path) -> None:
        issues_dir = self._make_issues_dir(tmp_path)
        db = tmp_path / "history.db"
        counts = backfill(db, issues_dir=issues_dir, loops_dir=tmp_path / "no")
        assert counts["snapshots"] == 2

        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0]
        finally:
            conn.close()
        assert count == 2

    def test_backfill_snapshots_idempotent(self, tmp_path: Path) -> None:
        issues_dir = self._make_issues_dir(tmp_path)
        db = tmp_path / "history.db"
        backfill(db, issues_dir=issues_dir, loops_dir=tmp_path / "no")
        backfill(db, issues_dir=issues_dir, loops_dir=tmp_path / "no")

        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM issue_snapshots").fetchone()[0]
        finally:
            conn.close()
        assert count == 2, "Double backfill must not duplicate rows"

    def test_backfill_snapshots_stores_body(self, tmp_path: Path) -> None:
        issues_dir = self._make_issues_dir(tmp_path)
        db = tmp_path / "history.db"
        backfill(db, issues_dir=issues_dir, loops_dir=tmp_path / "no")

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT body FROM issue_snapshots WHERE issue_id='ENH-2151'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert "Body content here" in (row[0] or "")
