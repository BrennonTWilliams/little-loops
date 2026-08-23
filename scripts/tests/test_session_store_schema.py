"""Tests for little_loops.session_store — schema module."""

from __future__ import annotations

import itertools
import json
import re
import sqlite3
from pathlib import Path

import pytest

from little_loops.session_store import (
    _KIND_TABLE,
    SCHEMA_VERSION,
    VALID_KINDS,
    SQLiteTransport,
    backfill_raw_events,
    connect,
    ensure_db,
    recent,
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
            "learning_test_events",
            "hook_events",
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
        assert SCHEMA_VERSION == 44


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
        assert SCHEMA_VERSION == 44
        assert int(row[0]) == 44

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
        assert SCHEMA_VERSION == 44
        assert int(row[0]) == 44

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
        assert int(version[0]) == 44
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
        assert SCHEMA_VERSION == 44
        assert int(row[0]) == 44

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


class TestRawEventsTable:
    """v19 migration: raw_events is the JSONL source of truth (ENH-2581)."""

    def test_table_and_columns_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_events)")}
        finally:
            conn.close()
        assert {
            "id",
            "ts",
            "session_id",
            "host",
            "source_path",
            "line_no",
            "event_type",
            "raw_line",
            "parsed_json",
            "compacted",
            "summary_node_id",
        } <= cols

    def test_meta_seeds_present(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            keys = {
                r[0]
                for r in conn.execute(
                    "SELECT key FROM meta WHERE key IN"
                    " ('last_raw_event_ts', 'last_rebuild_version')"
                )
            }
        finally:
            conn.close()
        assert keys == {"last_raw_event_ts", "last_rebuild_version"}

    def test_backfill_raw_events_ingests_one_row_per_line(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        db = tmp_path / "history.db"
        count = backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        assert count == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT * FROM raw_events").fetchone()
        finally:
            conn.close()
        assert row["event_type"] == "user"
        assert row["session_id"] == "s1"
        assert row["source_path"] == str(jsonl)
        assert row["line_no"] == 1
        assert row["compacted"] == 0
        assert row["host"]  # populated from resolve_host().name

    def test_dedup_on_source_path_and_line_no(self, tmp_path: Path) -> None:
        """Re-ingesting the same file produces no duplicate raw_events rows."""
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        finally:
            conn.close()
        assert count == 1

    def test_updates_last_raw_event_ts(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[], since_ts=0.0)
        conn = connect(db)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_raw_event_ts'").fetchone()
        finally:
            conn.close()
        assert row is not None and row["value"] is not None


class TestSchemaV20UsageEvents:
    """v20 migration adds the usage_events table with the Option C columns (ENH-2461)."""

    def test_usage_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(usage_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "model",
            "state",
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cost_usd",
            # v21 (FEAT-2478) OTel gen_ai.* addenda
            "invocation_id",
            "provider_vendor",
            # v29 (ENH-2723) run_id join key
            "run_id",
        }


class TestValidKindsCentralization:
    """VALID_KINDS is the single source for recent()/search --kind (ENH-2581)."""

    def test_every_valid_kind_has_a_kind_table_entry(self) -> None:
        assert set(VALID_KINDS) == set(_KIND_TABLE.keys())

    def test_recent_snapshot_kind_does_not_raise(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert recent(db, kind="snapshot") == []


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
        assert SCHEMA_VERSION == 44
        assert int(row[0]) == 44

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
        assert SCHEMA_VERSION == 44
        assert int(row[0]) == 44

    def test_issue_snapshots_table_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='issue_snapshots'"
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
        assert int(version[0]) == 44
        assert "issue_snapshots" in names


def _bootstrap_schema_at(db: Path, version: int) -> None:
    """Bootstrap a database at an exact historical schema *version*.

    Applies migrations 0..version-1 verbatim from ``_MIGRATIONS`` and stamps
    the meta row, mirroring the TestSchemaV14 pattern so upgrade tests always
    exercise the real historical DDL.
    """
    from little_loops.session_store import _MIGRATIONS, _split_sql_statements

    conn = sqlite3.connect(str(db))
    try:
        for script in _MIGRATIONS[:version]:
            for stmt in _split_sql_statements(script):
                conn.execute(stmt)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
    finally:
        conn.close()


class TestSchemaV15SkillCompletionColumns:
    """v15 migration: exit_code/success/duration_ms columns on skill_events (ENH-2460)."""

    def test_skill_events_has_completion_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_events)")}
        finally:
            conn.close()
        assert {"exit_code", "success", "duration_ms"} <= cols

    def test_v14_db_upgrades_preserving_dispatch_only_rows(self, tmp_path: Path) -> None:
        """Pre-migration skill_events rows survive with NULL completion columns."""
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 14)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO skill_events(ts, session_id, skill_name, args) "
                "VALUES('2026-06-01T00:00:00Z', 's-old', 'refine-issue', 'ENH-1')"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            row = conn.execute(
                "SELECT * FROM skill_events WHERE skill_name='refine-issue'"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert row is not None
        assert row["exit_code"] is None
        assert row["success"] is None
        assert row["duration_ms"] is None

    def test_dispatch_only_record_skill_event_leaves_completion_null(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_skill_event

        db = tmp_path / "history.db"
        record_skill_event(db, "s-disp", "capture-issue", "")
        rows = recent(db, kind="skill")
        assert rows[0]["exit_code"] is None
        assert rows[0]["success"] is None
        assert rows[0]["duration_ms"] is None


class TestSchemaV16IssueSessionId:
    """v16 migration: authoritative issue_events.session_id column (ENH-2462)."""

    def test_issue_events_has_session_id_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_events)")}
        finally:
            conn.close()
        assert "session_id" in cols

    def test_session_id_index_exists_and_is_used(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='issue_events'"
                )
            }
            plan = " ".join(
                str(r[3])
                for r in conn.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM issue_events WHERE session_id = ?",
                    ("s-x",),
                )
            )
        finally:
            conn.close()
        assert "idx_issue_events_session_id" in indexes
        assert "idx_issue_events_session_id" in plan

    def test_legacy_view_preserved(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        finally:
            conn.close()
        assert "legacy_issue_sessions_ts_overlap" in views
        assert "issue_sessions" in views

    def test_transport_writes_session_id_from_payload(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-07-01T12:00:00Z",
                "issue_id": "ENH-2462",
                "session_id": "sess-exact",
            }
        )
        transport.close()
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT session_id FROM issue_events WHERE issue_id='ENH-2462'"
            ).fetchone()
        finally:
            conn.close()
        assert row["session_id"] == "sess-exact"

    def test_transport_accepts_camelcase_session_id(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        transport = SQLiteTransport(db)
        transport.send(
            {
                "event": "issue.started",
                "ts": "2026-07-01T12:00:00Z",
                "issue_id": "ENH-2463",
                "sessionId": "sess-camel",
            }
        )
        transport.close()
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT session_id FROM issue_events WHERE issue_id='ENH-2463'"
            ).fetchone()
        finally:
            conn.close()
        assert row["session_id"] == "sess-camel"

    def test_transport_without_session_id_writes_null(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        transport = SQLiteTransport(db)
        transport.send(
            {"event": "issue.completed", "ts": "2026-07-01T12:00:00Z", "issue_id": "ENH-2464"}
        )
        transport.close()
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT session_id FROM issue_events WHERE issue_id='ENH-2464'"
            ).fetchone()
        finally:
            conn.close()
        assert row["session_id"] is None

    def test_issue_sessions_view_returns_exact_match(self, tmp_path: Path) -> None:
        """An authoritative session_id row yields an exact issue_sessions join."""
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, session_id) "
                "VALUES('2026-07-01T12:00:00Z', 'ENH-2462', 'done', 'sess-exact')"
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES('sess-exact', '/p/e.jsonl')"
            )
            # A decoy overlapping message from an unrelated session must NOT be joined.
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) "
                "VALUES('2026-07-01T12:00:01Z', 'sess-decoy', 'unrelated')"
            )
            conn.commit()
        finally:
            conn.close()
        conn = connect(db)
        try:
            rows = conn.execute(
                "SELECT session_id, jsonl_path FROM issue_sessions WHERE issue_id='ENH-2462'"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-exact"
        assert rows[0]["jsonl_path"] == "/p/e.jsonl"

    def test_v14_db_upgrades_preserving_null_session_id(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 14)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition) "
                "VALUES('2026-06-01T00:00:00Z', 'ENH-1', 'done')"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT session_id FROM issue_events WHERE issue_id='ENH-1'"
            ).fetchone()
            views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        finally:
            conn.close()
        assert row["session_id"] is None
        assert {"issue_sessions", "legacy_issue_sessions_ts_overlap"} <= views


class TestLoopEventTypes:
    """BUG-2204: _LOOP_EVENT_TYPES contains expected event type strings."""

    def test_max_steps_summary_in_loop_event_types(self) -> None:
        """'max_steps_summary' is a member of _LOOP_EVENT_TYPES."""
        from little_loops.session_store import _LOOP_EVENT_TYPES

        assert "max_steps_summary" in _LOOP_EVENT_TYPES

    def test_max_iterations_reached_summary_in_loop_event_types(self) -> None:
        """'max_iterations_reached_summary' is a member of _LOOP_EVENT_TYPES."""
        from little_loops.session_store import _LOOP_EVENT_TYPES

        assert "max_iterations_reached_summary" in _LOOP_EVENT_TYPES

    def test_stable_event_types_remain(self) -> None:
        """Core event types remain in _LOOP_EVENT_TYPES after BUG-2204 changes."""
        from little_loops.session_store import _LOOP_EVENT_TYPES

        for name in ("loop_start", "loop_complete", "state_enter", "route"):
            assert name in _LOOP_EVENT_TYPES


class TestSchemaV27:
    """v27 migration adds the session_lifecycle_events table (ENH-2495)."""

    def test_session_lifecycle_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(session_lifecycle_events)")}
        finally:
            conn.close()
        assert cols == {"id", "ts", "session_id", "event", "detail", "head_sha", "branch"}

    def test_v26_db_upgrades_gains_session_lifecycle_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 26)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "session_lifecycle_events" in names


class TestSchemaV28:
    """v28 migration adds the subagent_runs table (ENH-2505)."""

    def test_subagent_runs_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(subagent_runs)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "parent_session_id",
            "agent_id",
            "agent_type",
            "agent_transcript_path",
            "started_at",
            "ended_at",
            "status",
            "head_sha",
            "branch",
        }

    def test_v27_db_upgrades_gains_subagent_runs(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 27)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "subagent_runs" in names

    def test_subagent_run_id_is_kinded(self) -> None:
        assert "subagent_run" in VALID_KINDS
        assert _KIND_TABLE["subagent_run"] == "subagent_runs"


class TestSchemaV29:
    """v29 migration adds the run_id column + index on usage_events (ENH-2723)."""

    def test_usage_events_run_id_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(usage_events)")}
        finally:
            conn.close()
        assert "run_id" in cols

    def test_usage_events_run_id_index_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert "idx_usage_events_run_id" in names

    def test_v28_db_upgrades_gains_run_id_column(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 28)
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(usage_events)")}
        finally:
            conn.close()
        assert "run_id" in cols


class TestSchemaV30HookEvents:
    """v30 migration adds the hook_events table (ENH-2506)."""

    def test_hook_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(hook_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "event_name",
            "matcher",
            "script",
            "exit_code",
            "duration_ms",
            "stderr_preview",
            "head_sha",
            "branch",
        }

    def test_hook_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {"idx_hook_event_name", "idx_hook_session", "idx_hook_exit"} <= names

    def test_v29_db_upgrades_gains_hook_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 29)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "hook_events" in names

    def test_hook_event_is_kinded(self) -> None:
        assert "hook_event" in VALID_KINDS
        assert _KIND_TABLE["hook_event"] == "hook_events"

    def test_hook_events_excluded_from_rebuild_tables(self) -> None:
        from little_loops.session_store import _REBUILD_TABLES

        assert "hook_events" not in _REBUILD_TABLES


class TestSchemaV31HarnessEvents:
    """v31 migration adds the harness_events table (ENH-2739)."""

    def test_harness_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(harness_events)")}
        finally:
            conn.close()
        # v31 base columns; v39 ENH-141 adds target_content_hash/target_path/dirty.
        # Subset assertion so later migrations can extend the table without breaking
        # the original contract — mirrors the v38 base-stamp test at :1909.
        assert {
            "id",
            "ts",
            "runner",
            "target",
            "exit_code",
            "semantic_verdict",
            "semantic_passed",
            "timed_out",
            "duration_ms",
            "head_sha",
            "branch",
            "parent_id",
            "semantic_prompt",
            "semantic_confidence",
            "semantic_reason",
            "semantic_evidence",
            "semantic_model",
        } <= cols

    def test_harness_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {
            "idx_harness_runner",
            "idx_harness_target",
            "idx_harness_exit",
            "idx_harness_parent",
        } <= names

    def test_v30_db_upgrades_gains_harness_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 30)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "harness_events" in names

    def test_harness_is_kinded(self) -> None:
        assert "harness" in VALID_KINDS
        assert _KIND_TABLE["harness"] == "harness_events"

    def test_harness_events_excluded_from_rebuild_tables(self) -> None:
        from little_loops.session_store import _REBUILD_TABLES

        assert "harness_events" not in _REBUILD_TABLES


class TestSchemaV32PromptOptEvents:
    """v32 migration adds the prompt_opt_events table (ENH-2498)."""

    def test_prompt_opt_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(prompt_opt_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "mode",
            "offered",
            "bypass_reason",
            "raw_len",
            "optimized_len",
            "optimized_text",
            "accepted",
        }

    def test_prompt_opt_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {"idx_prompt_opt_events_session", "idx_prompt_opt_events_mode"} <= names

    def test_v31_db_upgrades_gains_prompt_opt_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 31)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "prompt_opt_events" in names

    def test_prompt_opt_is_kinded(self) -> None:
        assert "prompt_opt" in VALID_KINDS
        assert _KIND_TABLE["prompt_opt"] == "prompt_opt_events"

    def test_prompt_opt_events_excluded_from_rebuild_tables(self) -> None:
        from little_loops.session_store import _REBUILD_SEARCH_KINDS, _REBUILD_TABLES

        assert "prompt_opt_events" not in _REBUILD_TABLES
        assert "prompt_opt" not in _REBUILD_SEARCH_KINDS

    def test_prompt_opt_events_not_kindless(self) -> None:
        from little_loops.session_store import _KINDLESS_TABLES

        assert "prompt_opt_events" not in _KINDLESS_TABLES


class TestSchemaV33VerdictEvents:
    """v33 migration adds the verdict_events table (ENH-2504)."""

    def test_verdict_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(verdict_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "verdict_kind",
            "target_kind",
            "target_id",
            "verdict",
            "severity_counts",
            "findings_count",
            "confidence",
            "abstention_reason",
            "head_sha",
            "branch",
        }

    def test_verdict_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {"idx_verdict_kind", "idx_verdict_target", "idx_verdict_session"} <= names

    def test_v32_db_upgrades_gains_verdict_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 32)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "verdict_events" in names

    def test_verdict_is_kinded(self) -> None:
        assert "verdict" in VALID_KINDS
        assert _KIND_TABLE["verdict"] == "verdict_events"

    def test_verdict_events_excluded_from_rebuild_tables(self) -> None:
        from little_loops.session_store import _REBUILD_SEARCH_KINDS, _REBUILD_TABLES

        assert "verdict_events" not in _REBUILD_TABLES
        assert "verdict" not in _REBUILD_SEARCH_KINDS

    def test_verdict_events_not_kindless(self) -> None:
        from little_loops.session_store import _KINDLESS_TABLES

        assert "verdict_events" not in _KINDLESS_TABLES


class TestSchemaV34ContextPressureEvents:
    """v34 migration adds the context_pressure_events table (ENH-2507)."""

    def test_context_pressure_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(context_pressure_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "used_pct",
            "used_tokens_est",
            "threshold_crossed",
            "crossed_level",
            "head_sha",
            "branch",
        }

    def test_context_pressure_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {"idx_pressure_session", "idx_pressure_ts", "idx_pressure_crossed"} <= names

    def test_v33_db_upgrade_gains_context_pressure_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 33)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "context_pressure_events" in names

    def test_kind_registration(self) -> None:
        assert "context_pressure" in VALID_KINDS
        assert _KIND_TABLE["context_pressure"] == "context_pressure_events"

    def test_excluded_from_rebuild(self) -> None:
        from little_loops.session_store import _REBUILD_SEARCH_KINDS, _REBUILD_TABLES

        assert "context_pressure_events" not in _REBUILD_TABLES
        assert "context_pressure" not in _REBUILD_SEARCH_KINDS

    def test_not_kindless(self) -> None:
        from little_loops.session_store import _KINDLESS_TABLES

        assert "context_pressure_events" not in _KINDLESS_TABLES


class TestSchemaV35ReviewEvents:
    """v35 migration adds the review_events table (ENH-2512)."""

    def test_review_events_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(review_events)")}
        finally:
            conn.close()
        assert cols == {
            "id",
            "ts",
            "session_id",
            "reviewer_skill",
            "target_kind",
            "target_id",
            "severity_counts",
            "findings_count",
            "findings_json_summary",
            "verdict",
            "head_sha",
            "branch",
        }

    def test_review_events_indexes_exist(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        finally:
            conn.close()
        assert {"idx_review_skill", "idx_review_target", "idx_review_session"} <= names

    def test_v34_db_upgrade_gains_review_events(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 34)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "review_events" in names

    def test_kind_registration(self) -> None:
        assert "review" in VALID_KINDS
        assert _KIND_TABLE["review"] == "review_events"


class TestSchemaV38BaseShaColumns:
    """v38 migration: base_sha/base_dirty columns on orchestration_runs (ENH-2866)."""

    def test_orchestration_runs_has_base_stamp_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(orchestration_runs)")}
        finally:
            conn.close()
        assert {"base_sha", "base_dirty"} <= cols

    def test_loop_runs_gains_no_base_stamp_columns(self, tmp_path: Path) -> None:
        """Decision 3: autodev is covered transitively; loop_runs is untouched."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(loop_runs)")}
        finally:
            conn.close()
        assert "base_sha" not in cols
        assert "base_dirty" not in cols

    def test_v37_db_upgrades_preserving_unstamped_rows(self, tmp_path: Path) -> None:
        """Pre-migration orchestration rows survive with NULL stamp columns."""
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 37)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO orchestration_runs(run_id, driver, issue_id, status, ended_at) "
                "VALUES('old-run', 'll-auto', 'ENH-1', 'completed', '2026-06-01T00:00:00Z')"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            row = conn.execute("SELECT * FROM orchestration_runs WHERE run_id='old-run'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert row is not None
        assert row["status"] == "completed"
        assert row["base_sha"] is None
        assert row["base_dirty"] is None

    def test_excluded_from_rebuild(self) -> None:
        from little_loops.session_store import _REBUILD_SEARCH_KINDS, _REBUILD_TABLES

        assert "review_events" not in _REBUILD_TABLES
        assert "review" not in _REBUILD_SEARCH_KINDS

    def test_not_kindless(self) -> None:
        from little_loops.session_store import _KINDLESS_TABLES

        assert "review_events" not in _KINDLESS_TABLES


class TestSchemaV39HarnessContentPin:
    """v39 migration: content-pin columns on harness_events (ENH-141)."""

    def test_harness_events_has_content_pin_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(harness_events)")}
        finally:
            conn.close()
        assert {"target_content_hash", "target_path", "dirty"} <= cols

    def test_v38_db_upgrades_preserving_unpinned_rows(self, tmp_path: Path) -> None:
        """Pre-v39 harness rows survive with NULL content-pin columns."""
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 38)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO harness_events(ts, runner, target, exit_code) "
                "VALUES('2026-06-01T00:00:00Z', 'cmd', 'echo hi', 0)"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            row = conn.execute("SELECT * FROM harness_events WHERE target='echo hi'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert row is not None
        assert row["target_content_hash"] is None
        assert row["target_path"] is None
        assert row["dirty"] is None


def _stamp_version(conn: sqlite3.Connection, version: int) -> None:
    """Write ``meta.schema_version`` directly, bypassing migration application.

    Makes a structurally-drifted database constructible in a test: the
    recorded version says one thing while the actual schema says another,
    exactly the BUG-3236 scenario `_bootstrap_schema_at` cannot produce (it
    always stamps a version that matches what it just applied).
    """
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(version),),
    )
    conn.commit()


class TestSchemaV42IssueSessionsRepair:
    """v42 migration: rebuild issue_sessions with issue_num (BUG-3236)."""

    def test_issue_sessions_view_has_issue_num_on_fresh_db(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_sessions)")}
        finally:
            conn.close()
        assert "issue_num" in cols

    def test_issue_sessions_view_repaired_on_drifted_db(self, tmp_path: Path) -> None:
        """Regression gate: a database recorded at the pre-fix current version

        with a pre-v36-shaped issue_sessions view (no issue_num) is repaired
        by ensure_db() once SCHEMA_VERSION moves past it. Reproduces BUG-3236's
        drift (a database whose recorded version is >= 36 but whose view body
        never projected issue_num) rather than genuine pre-v36 staleness, since
        the columns the view depends on (issue_events.issue_num) only exist
        from v36 onward.
        """
        db = tmp_path / "history.db"
        # Bootstrap through v40 (not just v36) so every column later
        # migrations assume unconditionally -- e.g. v43's blanket
        # `CREATE INDEX ... loop_runs(failure_terminal)` re-assertion --
        # genuinely exists; only the view itself is reverted below to
        # simulate the drift, matching BUG-3236's actual failure mode
        # (a manually-patched view, not a partially-applied migration chain).
        _bootstrap_schema_at(db, 40)
        conn = sqlite3.connect(str(db))
        try:
            # Overwrite the correct v36 view with the pre-v36-shaped body
            # (no issue_num projection) to simulate the drift in place.
            conn.executescript(
                """
                DROP VIEW IF EXISTS issue_sessions;
                CREATE VIEW issue_sessions AS
                SELECT ie.issue_id,
                       ie.session_id,
                       s.jsonl_path,
                       MIN(ie.ts) AS first_message_ts,
                       MAX(ie.ts) AS last_message_ts
                FROM issue_events ie
                LEFT JOIN sessions s ON s.session_id = ie.session_id
                WHERE ie.session_id IS NOT NULL
                GROUP BY ie.issue_id, ie.session_id
                UNION ALL
                SELECT l.issue_id, l.session_id, l.jsonl_path, l.first_message_ts,
                       l.last_message_ts
                FROM legacy_issue_sessions_ts_overlap l
                WHERE l.issue_id NOT IN (
                    SELECT issue_id FROM issue_events
                    WHERE session_id IS NOT NULL AND issue_id IS NOT NULL
                );
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_sessions)")}
            assert "issue_num" not in cols
            _stamp_version(conn, 41)
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_sessions)")}
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert "issue_num" in cols


def _insert_summary_node(
    conn: sqlite3.Connection,
    kind: str,
    session_id: str | None,
    ts_start: str | None,
    ts_end: str | None,
) -> int:
    """Insert a minimal summary_nodes row and return its id (BUG-3241 fixtures)."""
    conn.execute(
        "INSERT INTO summary_nodes(kind, content, session_id, ts_start, ts_end, created_at) "
        "VALUES (?, 'body', ?, ?, ?, '2026-01-01T00:00:00Z')",
        (kind, session_id, ts_start, ts_end),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _insert_raw_event(
    conn: sqlite3.Connection, session_id: str, summary_node_id: int | None
) -> None:
    """Insert a minimal raw_events row pointing at *summary_node_id* (BUG-3241 fixtures)."""
    conn.execute(
        "INSERT INTO raw_events"
        "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json, summary_node_id) "
        "VALUES ('2026-01-01T00:00:00Z', ?, 'h', '/p', 1, 'tool', '{}', '{}', ?)",
        (session_id, summary_node_id),
    )


def test_schema_version_matches_migrations_length() -> None:
    """SCHEMA_VERSION is a hand-maintained int, not derived from len(_MIGRATIONS);
    guard against the two silently desyncing (BUG-3241 wiring finding)."""
    from little_loops.session_store import _MIGRATIONS

    assert SCHEMA_VERSION == len(_MIGRATIONS)


class TestSchemaOverStampedClamp:
    """BUG-3255: recorded schema_version > len(_MIGRATIONS) must not silently
    block future migrations forever. Guarded clamp: only rewrite the stamp
    down when the live structure matches len(_MIGRATIONS); otherwise leave it
    alone (the legitimately-ahead / older-checkout case)."""

    def test_structurally_matching_over_stamp_is_clamped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        from little_loops.session_store import _MIGRATIONS

        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, len(_MIGRATIONS))
        conn = sqlite3.connect(str(db))
        try:
            _stamp_version(conn, len(_MIGRATIONS) + 2)
        finally:
            conn.close()

        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.schema"):
            ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            rebuild = conn.execute(
                "SELECT value FROM meta WHERE key='last_rebuild_version'"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == len(_MIGRATIONS)
        assert rebuild is None or rebuild[0] is None
        assert any("schema_version" in rec.message for rec in caplog.records)

    def test_clamp_unblocks_next_migration_on_subsequent_call(self, tmp_path: Path) -> None:
        """A single ensure_db() call cannot both clamp and apply a migration
        that didn't exist when the clamp ran; the probe migration is only
        picked up on the *next* call."""
        from little_loops import session_store as _ss
        from little_loops.session_store import _MIGRATIONS
        from little_loops.session_store import schema as _schema_mod

        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, len(_MIGRATIONS))
        conn = sqlite3.connect(str(db))
        try:
            _stamp_version(conn, len(_MIGRATIONS) + 2)
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == len(_MIGRATIONS)

        probe_migrations = list(_MIGRATIONS) + ["CREATE TABLE probe (id INTEGER);"]
        monkeypatch_target = _schema_mod
        original = monkeypatch_target._MIGRATIONS
        original_pkg = _ss._MIGRATIONS
        monkeypatch_target._MIGRATIONS = probe_migrations
        _ss._MIGRATIONS = probe_migrations
        try:
            ensure_db(db)
        finally:
            monkeypatch_target._MIGRATIONS = original
            _ss._MIGRATIONS = original_pkg

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            probe = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='probe'"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == len(_MIGRATIONS) + 1
        assert probe is not None

    def test_structurally_mismatched_over_stamp_is_left_unchanged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        from little_loops.session_store import _MIGRATIONS

        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, len(_MIGRATIONS))
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("CREATE TABLE ahead_probe (id INTEGER);")
            _stamp_version(conn, len(_MIGRATIONS) + 2)
        finally:
            conn.close()

        with caplog.at_level(logging.WARNING, logger="little_loops.session_store.schema"):
            ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == len(_MIGRATIONS) + 2
        assert any("schema_version" in rec.message for rec in caplog.records)

    def test_equal_stamp_does_not_reach_manifest_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The `==` fast path must stay lock-free and never pay the ~5ms
        manifest-replay cost."""
        from little_loops.session_store import schema as _schema_mod

        def _boom(_version: int) -> None:
            raise AssertionError("manifest guard reached on == branch")

        monkeypatch.setattr(_schema_mod, "_reference_manifest_at", _boom)

        db = tmp_path / "history.db"
        ensure_db(db)  # brings db to SCHEMA_VERSION == len(_MIGRATIONS)
        ensure_db(db)  # second call must take the == fast path, no guard call

    def test_behind_stamp_still_applies_normally(self, tmp_path: Path) -> None:
        from little_loops.session_store import _MIGRATIONS

        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, len(_MIGRATIONS) - 1)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == len(_MIGRATIONS)


class TestSchemaV43IndexRepair:
    """v43 migration: repair missing dedup indexes on drifted databases (BUG-3241)."""

    def test_assistant_messages_duplicates_repaired_without_raising(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 42)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("DROP INDEX IF EXISTS idx_assistant_messages_dedup")
            conn.execute(
                "INSERT INTO assistant_messages(ts, content, session_id, tool_use_count) "
                "VALUES ('t1', 'c1', 's1', 0)"
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, content, session_id, tool_use_count) "
                "VALUES ('t1', 'c1', 's1', 0)"
            )
            conn.commit()
            _stamp_version(conn, 42)
        finally:
            conn.close()

        ensure_db(db)  # must not raise sqlite3.IntegrityError

        conn = sqlite3.connect(str(db))
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            count = conn.execute("SELECT COUNT(*) FROM assistant_messages").fetchone()[0]
            index_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_assistant_messages_dedup'"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert count == 1
        assert index_row is not None

    def test_clean_database_is_idempotent(self, tmp_path: Path) -> None:
        """A database already carrying the indexes is unaffected: no row deletions."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO assistant_messages(ts, content, session_id, tool_use_count) "
                "VALUES ('t1', 'c1', 's1', 0)"
            )
            surv = _insert_summary_node(conn, "retention", "s1", "a", "b")
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)  # re-run: no pending migrations, but exercise idempotency of a rerun

        conn = sqlite3.connect(str(db))
        try:
            am_count = conn.execute("SELECT COUNT(*) FROM assistant_messages").fetchone()[0]
            sn_count = conn.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind='retention'"
            ).fetchone()[0]
            surviving = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='retention'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert am_count == 1
        assert sn_count == 1
        assert surviving == surv

    def test_all_three_indexes_present_on_drifted_db(self, tmp_path: Path) -> None:
        """A db stamped past the creating migrations but structurally missing the
        indexes has all three present after ensure_db()."""
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 42)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("DROP INDEX IF EXISTS idx_assistant_messages_dedup")
            conn.execute("DROP INDEX IF EXISTS idx_summary_nodes_retention_dedup")
            conn.execute("DROP INDEX IF EXISTS idx_summary_nodes_parent_id")
            conn.commit()
            _stamp_version(conn, 42)
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        finally:
            conn.close()
        assert "idx_assistant_messages_dedup" in have
        assert "idx_summary_nodes_retention_dedup" in have
        assert "idx_summary_nodes_parent_id" in have

    def test_summary_nodes_dedup_preserves_leaf_condensed_and_null_key_rows(
        self, tmp_path: Path
    ) -> None:
        """The retention dedup must not touch leaf/condensed rows, and must not
        delete a retention row whose (session_id, ts_start, ts_end) contains a
        NULL -- SQLite's UNIQUE index accepts those, so the repair must too."""
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 42)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("DROP INDEX IF EXISTS idx_summary_nodes_retention_dedup")
            survivor = _insert_summary_node(conn, "retention", "s1", "a", "b")
            loser = _insert_summary_node(conn, "retention", "s1", "a", "b")
            null_a = _insert_summary_node(conn, "retention", None, "x", "y")
            null_b = _insert_summary_node(conn, "retention", None, "x", "y")
            leaf_a = _insert_summary_node(conn, "leaf", "s1", "a", "b")
            leaf_b = _insert_summary_node(conn, "leaf", "s2", "a", "b")
            _insert_raw_event(conn, "s1", loser)
            conn.commit()
            _stamp_version(conn, 42)
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        try:
            retention_ids = {
                r[0] for r in conn.execute("SELECT id FROM summary_nodes WHERE kind='retention'")
            }
            leaf_ids = {
                r[0] for r in conn.execute("SELECT id FROM summary_nodes WHERE kind='leaf'")
            }
            re_target = conn.execute("SELECT summary_node_id FROM raw_events").fetchone()[0]
            dangling = conn.execute(
                "SELECT COUNT(*) FROM raw_events "
                "WHERE summary_node_id IS NOT NULL "
                "AND summary_node_id NOT IN (SELECT id FROM summary_nodes)"
            ).fetchone()[0]
        finally:
            conn.close()

        assert retention_ids == {survivor, null_a, null_b}
        assert loser not in retention_ids
        assert leaf_ids == {leaf_a, leaf_b}
        assert dangling == 0
        assert re_target == survivor  # repointed from the deleted loser to its survivor


class TestSchemaV44VerdictGrammar:
    """v44 migration (ENH-230): abstention_reason column + verdict CHECK.

    Pins the grammar so a future regression — adding a fifth
    abstention_reason tag, or widening verdict without updating the CHECK —
    fails the next writer call rather than silently corrupting the
    aggregation in ``verdict_pass_rate()``.
    """

    def test_verdict_events_has_abstention_reason_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(verdict_events)")}
        finally:
            conn.close()
        assert "abstention_reason" in cols

    def test_verdict_check_admits_exactly_four_values(self, tmp_path: Path) -> None:
        """pass/fail/implement/cannot_judge are accepted; anything else is rejected."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            for i, value in enumerate(("pass", "fail", "implement", "cannot_judge")):
                reason = "missing_artifacts" if value == "cannot_judge" else None
                conn.execute(
                    "INSERT INTO verdict_events(ts, verdict_kind, verdict, abstention_reason) "
                    "VALUES(?, 'ready-issue', ?, ?)",
                    (f"2026-08-01T00:0{i}:00Z", value, reason),
                )
            conn.commit()
            accepted = conn.execute("SELECT COUNT(*) FROM verdict_events").fetchone()[0]

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO verdict_events(ts, verdict_kind, verdict) "
                    "VALUES('2026-08-01T01:00:00Z', 'ready-issue', 'unknown')"
                )
        finally:
            conn.close()
        assert accepted == 4

    def test_verdict_check_rejects_refused(self, tmp_path: Path) -> None:
        """`refused` lives on review_events (ENH-2512), not here — no verifier emits it."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO verdict_events(ts, verdict_kind, verdict) "
                    "VALUES('2026-08-01T00:00:00Z', 'ready-issue', 'refused')"
                )
        finally:
            conn.close()

    @pytest.mark.parametrize(
        "tag",
        [
            "missing_artifacts",
            "unparseable_criteria",
            "evaluation_context_unavailable",
            "circular_dependencies",
        ],
    )
    def test_abstention_reason_admits_the_four_closed_tags(self, tmp_path: Path, tag: str) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO verdict_events(ts, verdict_kind, verdict, abstention_reason) "
                "VALUES('2026-08-01T00:00:00Z', 'ready-issue', 'cannot_judge', ?)",
                (tag,),
            )
            conn.commit()
            stored = conn.execute("SELECT abstention_reason FROM verdict_events").fetchone()[0]
        finally:
            conn.close()
        assert stored == tag

    def test_abstention_reason_rejects_unknown_tag(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO verdict_events(ts, verdict_kind, verdict, abstention_reason) "
                    "VALUES('2026-08-01T00:00:00Z', 'ready-issue', 'cannot_judge', 'invalid_tag')"
                )
        finally:
            conn.close()

    def test_abstention_reason_must_be_null_for_non_abstention_verdicts(
        self, tmp_path: Path
    ) -> None:
        """NULL-as-contract: a reason on a pass/fail row is a producer bug, rejected structurally."""
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            for verdict in ("pass", "fail", "implement"):
                with pytest.raises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO verdict_events"
                        "(ts, verdict_kind, verdict, abstention_reason) "
                        "VALUES('2026-08-01T00:00:00Z', 'ready-issue', ?, 'missing_artifacts')",
                        (verdict,),
                    )
        finally:
            conn.close()

    def test_v43_db_upgrades_preserving_existing_rows(self, tmp_path: Path) -> None:
        """Pre-v44 verdict_events rows survive the table rebuild with NULL abstention_reason."""
        assert SCHEMA_VERSION == 44
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 43)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO verdict_events"
                "(ts, verdict_kind, target_kind, target_id, verdict, findings_count, confidence) "
                "VALUES('2026-07-01T00:00:00Z', 'ready-issue', 'issue', 'BUG-1', 'pass', 3, 95)"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            row = conn.execute(
                "SELECT target_id, verdict, abstention_reason, findings_count, confidence "
                "FROM verdict_events"
            ).fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert row is not None
        assert row["target_id"] == "BUG-1"
        assert row["verdict"] == "pass"
        assert row["abstention_reason"] is None  # new column defaults to NULL
        assert row["findings_count"] == 3
        assert row["confidence"] == 95


class TestPackageReexportSurface:
    """ENH-2890: session_store.py -> session_store/ package split.

    The public import path ``little_loops.session_store`` must stay fully
    transparent to every external importer. Every name in ``__all__``, the
    additional private names required for test/CLI access, and ``sqlite3``
    itself (patched by conftest's ``_guard_real_history_db`` autouse fixture)
    must resolve as an attribute of the package object.
    """

    def test_all_and_required_private_names_resolve(self) -> None:
        import little_loops.session_store as session_store

        required_private = [
            "_MIGRATIONS",
            "_KIND_TABLE",
            "_KINDLESS_TABLES",
            "_split_sql_statements",
            "SCHEMA_VERSION",
            "_call_llm_for_summary",
            "_estimate_tokens",
            "compact_session_with_reasoning",
            "_summarize_block",
            "_derive_transition",
            "_pack_payload",
            "_unpack_payload",
        ]
        names = list(session_store.__all__) + required_private + ["sqlite3"]
        missing = [name for name in names if not hasattr(session_store, name)]
        assert not missing, f"missing session_store package attributes: {missing}"


class TestSchemaManifest:
    """ENH-3242 piece 1: structural drift detection via a checked-in manifest.

    Regenerate the checked-in manifest with:

        python -c "
        import json, sqlite3, tempfile
        from pathlib import Path
        from little_loops.session_store.schema import ensure_db, _schema_manifest
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'history.db'
            ensure_db(db)
            conn = sqlite3.connect(str(db))
            manifest = _schema_manifest(conn)
            conn.close()
        Path('little_loops/session_store/schema_manifest.json').write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + chr(10), encoding='utf-8'
        )
        "

    run from ``scripts/`` after any migration that intentionally changes structure.
    """

    def test_schema_manifest_matches_checked_in_file(self, tmp_path: Path) -> None:
        from little_loops.session_store import _load_schema_manifest, _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            live = _schema_manifest(conn)
        finally:
            conn.close()

        checked_in = _load_schema_manifest()
        assert live == checked_in, (
            "schema_manifest.json is stale against the current migrations. "
            "Regenerate it (see this test's docstring) and commit the result."
        )

    def test_manifest_schema_version_matches_live_schema_version(self, tmp_path: Path) -> None:
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            manifest = _schema_manifest(conn)
        finally:
            conn.close()

        assert manifest["schema_version"] == SCHEMA_VERSION

    def test_excludes_sqlite_internal_and_fts5_shadow_tables(self, tmp_path: Path) -> None:
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            manifest = _schema_manifest(conn)
        finally:
            conn.close()

        names = set(manifest["objects"])
        assert not any(name.startswith("sqlite_") for name in names)
        for shadow in (
            "search_index_config",
            "search_index_content",
            "search_index_data",
            "search_index_docsize",
            "search_index_idx",
        ):
            assert shadow not in names
        assert "search_index" in names

    def test_comment_only_ddl_edit_does_not_change_manifest(self, tmp_path: Path) -> None:
        """SQLite never rewrites a stored CREATE statement, so a text diff would
        flag a harmless comment forever (BUG-3236's trap). A PRAGMA-derived
        manifest must be unaffected by it."""
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            before = _schema_manifest(conn)
            conn.execute("DROP TABLE user_corrections")
            conn.execute(
                """
                -- a harmless comment that changes no structure
                CREATE TABLE user_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT,
                    content TEXT,
                    source TEXT
                )
                """
            )
            after = _schema_manifest(conn)
        finally:
            conn.close()

        assert before["objects"]["user_corrections"] == after["objects"]["user_corrections"]

    def test_view_columns_record_name_and_order_only(self, tmp_path: Path) -> None:
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            manifest = _schema_manifest(conn)
        finally:
            conn.close()

        view = manifest["objects"]["issue_sessions"]
        assert view["type"] == "view"
        assert view["columns"] == [
            "issue_id",
            "issue_num",
            "session_id",
            "jsonl_path",
            "first_message_ts",
            "last_message_ts",
        ]

    def test_index_records_unique_partial_origin_and_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            manifest = _schema_manifest(conn)
        finally:
            conn.close()

        retention_idx = manifest["indexes"]["idx_summary_nodes_retention_dedup"]
        assert retention_idx["unique"] is True
        assert retention_idx["partial"] is True

        dedup_idx = manifest["indexes"]["idx_assistant_messages_dedup"]
        assert dedup_idx["unique"] is True
        assert dedup_idx["partial"] is False

    def test_degraded_index_losing_unique_changes_manifest(self, tmp_path: Path) -> None:
        """The BUG-3241 shape: an index present by name but no longer UNIQUE, which
        a name-only manifest would miss entirely."""
        from little_loops.session_store import _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            before = _schema_manifest(conn)
            conn.execute("DROP INDEX idx_assistant_messages_dedup")
            conn.execute(
                "CREATE INDEX idx_assistant_messages_dedup "
                "ON assistant_messages(session_id, ts, content)"
            )
            after = _schema_manifest(conn)
        finally:
            conn.close()

        assert before["indexes"]["idx_assistant_messages_dedup"]["unique"] is True
        assert after["indexes"]["idx_assistant_messages_dedup"]["unique"] is False


class TestReferenceManifestAt:
    """ENH-3242 piece 2 support: replay-based reference manifests at any version."""

    def test_reference_at_current_version_matches_fresh_database(self, tmp_path: Path) -> None:
        from little_loops.session_store import _reference_manifest_at, _schema_manifest

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            fresh = _schema_manifest(conn)
        finally:
            conn.close()

        assert _reference_manifest_at(SCHEMA_VERSION) == fresh

    def test_reference_at_historical_version_matches_bootstrapped_database(
        self, tmp_path: Path
    ) -> None:
        from little_loops.session_store import _reference_manifest_at, _schema_manifest

        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 41)
        conn = sqlite3.connect(str(db))
        try:
            bootstrapped = _schema_manifest(conn)
        finally:
            conn.close()

        assert _reference_manifest_at(41) == bootstrapped
