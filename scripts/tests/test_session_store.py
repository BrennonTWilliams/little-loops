"""Tests for little_loops.session_store - the unified SQLite + FTS5 session store."""

from __future__ import annotations

import itertools
import json
import logging
import re
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.session_store import (
    _KIND_TABLE,
    SCHEMA_VERSION,
    VALID_KINDS,
    SQLiteTransport,
    _derive_transition,
    _estimate_tokens,
    _pack_payload,
    _summarize_block,
    _unpack_payload,
    backfill,
    backfill_incremental,
    backfill_raw_events,
    cli_event_context,
    compact,
    compact_session,
    connect,
    ensure_db,
    is_correction,
    prune,
    rebuild,
    recent,
    recompress_raw_events,
    record_correction,
    search,
)
from little_loops.transport import Transport

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


class TestDbPathResolution:
    """ENH-2623: unified env → config → default DB-path precedence.

    ``resolve_history_db()`` and ``ensure_db()`` must agree for the same inputs
    (the historical divergence footgun), and the new ``history.db_path`` config
    key slots in as the middle precedence rung below ``LL_HISTORY_DB``.
    """

    def _resolvers(self):
        from little_loops.session_store import DEFAULT_DB_PATH, resolve_history_db

        return DEFAULT_DB_PATH, resolve_history_db

    def test_resolve_and_ensure_agree_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_history_db(p) == ensure_db(p) for {default, override} × {env set, unset}."""
        DEFAULT_DB_PATH, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        env_db = tmp_path / "env.db"
        override = tmp_path / "override.db"
        for path in (None, DEFAULT_DB_PATH, override):
            for env in (str(env_db), None):
                if env is None:
                    monkeypatch.delenv("LL_HISTORY_DB", raising=False)
                else:
                    monkeypatch.setenv("LL_HISTORY_DB", env)
                assert resolve_history_db(path) == ensure_db(path), (
                    f"divergence for path={path!r} env={env!r}"
                )

    def test_explicit_override_wins_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deliberate (non-default-shaped) path is honored verbatim over LL_HISTORY_DB."""
        _, resolve_history_db = self._resolvers()
        override = tmp_path / "override.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "env.db"))
        assert resolve_history_db(override) == override

    def test_env_wins_over_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """LL_HISTORY_DB beats history.db_path for a default-shaped path."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": str(tmp_path / "cfg.db")}}), encoding="utf-8"
        )
        env_db = tmp_path / "env.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(env_db))
        assert resolve_history_db(None) == env_db

    def test_config_used_when_env_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With env unset, history.db_path is the resolved path for a default-shaped input."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        cfg_db = tmp_path / "cfg.db"
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": str(cfg_db)}}), encoding="utf-8"
        )
        assert resolve_history_db(None) == cfg_db

    def test_config_relative_path_resolves_against_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative history.db_path resolves against the project root (cwd)."""
        _, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"history": {"db_path": "data/hist.db"}}), encoding="utf-8"
        )
        assert resolve_history_db(None) == tmp_path / "data" / "hist.db"

    def test_default_when_neither_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No env, no config → DEFAULT_DB_PATH."""
        DEFAULT_DB_PATH, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        assert resolve_history_db(None) == DEFAULT_DB_PATH

    def test_malformed_config_falls_back_to_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A malformed ll-config.json must not raise; resolution falls through to default."""
        DEFAULT_DB_PATH, resolve_history_db = self._resolvers()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "ll-config.json").write_text("{ not valid json", encoding="utf-8")
        assert resolve_history_db(None) == DEFAULT_DB_PATH


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

    def test_search_hyphenated_id_matches(self, tmp_path: Path) -> None:
        """Hyphenated issue IDs must match literally, not raise ValueError
        via FTS operator parsing (BUG-2651)."""
        db = tmp_path / "session.db"
        record_correction(db, "sess-h1", "Fixed BUG-490 in the parser", "user")
        results = search(db, query="BUG-490")
        assert results
        assert "BUG-490" in results[0]["content"]


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
            db,
            issues_dir=tmp_path / "none",
            loops_dir=tmp_path / "none",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["tools"] == 1
        assert recent(db, kind="tool")[0]["tool_name"] == "Bash"

    def test_backfill_missing_sources_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "session.db"
        counts = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no")
        assert counts == {
            "issues": 0,
            "loops": 0,
            "snapshots": 0,
            "commits": 0,
            "raw_events": 0,
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
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
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
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
            also_rebuild=True,
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
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
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
        assert SCHEMA_VERSION == 23


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
        assert counts["raw_events"] >= 1

    def test_filters_files_with_future_since_ts(self, tmp_path: Path) -> None:
        """Files with mtime before a far-future since_ts are excluded."""
        jsonl = self._make_tool_jsonl(tmp_path, "s2")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=9_999_999_999.0)
        assert counts["raw_events"] == 0

    def test_writes_last_raw_event_ts_after_run(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[], since_ts=0.0)
        conn = connect(db)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_raw_event_ts'").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["value"] is not None

    def test_reads_last_raw_event_ts_from_meta_when_since_none(self, tmp_path: Path) -> None:
        """When since_ts=None, meta value controls the mtime filter."""
        jsonl = self._make_tool_jsonl(tmp_path, "s3")
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("9999-12-31T23:59:59Z",),
            )
            conn.commit()
        finally:
            conn.close()
        counts = backfill_incremental(db, jsonl_files=[jsonl])
        assert counts["raw_events"] == 0

    def test_missing_file_is_skipped_silently(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        counts = backfill_incremental(
            db, jsonl_files=[tmp_path / "nonexistent.jsonl"], since_ts=0.0
        )
        assert counts["raw_events"] == 0

    def test_also_rebuild_materializes_messages_and_sessions(self, tmp_path: Path) -> None:
        jsonl = self._make_msg_jsonl(tmp_path, "s4")
        db = tmp_path / "history.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0, also_rebuild=True)
        assert counts["messages"] >= 1
        assert counts["sessions"] >= 1

    def test_without_also_rebuild_cache_tables_stay_empty(self, tmp_path: Path) -> None:
        """backfill_incremental() is ingest-only by default (ENH-2581)."""
        jsonl = self._make_tool_jsonl(tmp_path, "sess-1")
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0)
        conn = connect(db)
        try:
            sessions_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            tools_count = conn.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
            raw_count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        finally:
            conn.close()
        assert sessions_count == 0
        assert tools_count == 0
        assert raw_count == 1

    def test_also_rebuild_materializes_sessions(self, tmp_path: Path) -> None:
        jsonl = self._make_tool_jsonl(tmp_path, "sess-1")
        db = tmp_path / "history.db"
        backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0, also_rebuild=True)
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        finally:
            conn.close()
        assert count == 1


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


class TestBackfillSkillEvents:
    """BUG-2283: _backfill_skill_events() seeds skill_events from JSONL user records."""

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

    def test_backfill_populates_skill_events_from_command_name_tag(self, tmp_path: Path) -> None:
        text = "<command-name>/ll:tradeoff-review-issues</command-name>\n<command-args>BUG-100</command-args>"
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("sess-pre", "2026-06-01T10:00:00Z", text),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["skill_events"] == 1
        rows = recent(db, kind="skill")
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "tradeoff-review-issues"
        assert rows[0]["args"] == "BUG-100"
        assert rows[0]["session_id"] == "sess-pre"

    def test_backfill_skill_events_no_args_when_tag_absent(self, tmp_path: Path) -> None:
        text = "<command-name>/ll:check-code</command-name>"
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("sess2", "2026-06-02T10:00:00Z", text),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["skill_events"] == 1
        rows = recent(db, kind="skill")
        assert rows[0]["skill_name"] == "check-code"
        assert rows[0]["args"] == ""

    def test_backfill_skill_events_skips_non_skill_records(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("sess3", "2026-06-03T10:00:00Z", "just a normal message")
            + self._user_record("sess3", "2026-06-03T10:00:01Z", ""),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["skill_events"] == 0

    def test_backfill_skill_events_block_list_content(self, tmp_path: Path) -> None:
        text = "<command-name>/ll:scan-codebase</command-name>"
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("sess4", "2026-06-04T10:00:00Z", [{"type": "text", "text": text}]),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["skill_events"] == 1
        rows = recent(db, kind="skill")
        assert rows[0]["skill_name"] == "scan-codebase"

    def test_backfill_skill_events_are_searchable(self, tmp_path: Path) -> None:
        text = "<command-name>/ll:ready-issue</command-name>"
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            self._user_record("sess5", "2026-06-05T10:00:00Z", text),
            encoding="utf-8",
        )
        db = tmp_path / "session.db"
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        results = search(db, query="ready")
        assert any(r["kind"] == "skill" for r in results)


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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
        assert int(version[0]) == 23
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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
            counts = backfill(db, jsonl_files=[jsonl], config=config, also_rebuild=True)
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
        counts = backfill(
            db, jsonl_files=[jsonl], also_rebuild=True
        )  # no config → compaction.enabled=False
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


class TestRawEventsPayloadCompression:
    """raw_events payload columns are stored zlib-compressed, losslessly.

    Guards the pack/unpack round-trip, the writer emitting BLOBs, the coexistence
    of legacy TEXT rows with new BLOB rows through rebuild(), and the batched
    recompress maintenance command.
    """

    @staticmethod
    def _user_line(content: str, ts: str = "2026-05-22T00:00:00Z", line_no: int = 1) -> str:
        return json.dumps(
            {
                "type": "user",
                "sessionId": "s1",
                "timestamp": ts,
                "message": {"content": content},
            }
        )

    def test_pack_unpack_round_trip(self) -> None:
        for text in ["", "hello", "unïcodé 🎉", json.dumps({"a": [1, 2, 3], "b": "x" * 2000})]:
            packed = _pack_payload(text)
            assert isinstance(packed, bytes)
            assert _unpack_payload(packed) == text

    def test_unpack_passes_through_legacy_text(self) -> None:
        """A str value (legacy uncompressed row) is returned unchanged."""
        assert _unpack_payload('{"type":"user"}') == '{"type":"user"}'

    def test_backfill_stores_compressed_blobs(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(self._user_line("hello") + "\n", encoding="utf-8")
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT typeof(raw_line), typeof(parsed_json) FROM raw_events"
            ).fetchone()
        finally:
            conn.close()
        assert tuple(row) == ("blob", "blob")

    def test_rebuild_reads_mixed_legacy_and_compressed_rows(self, tmp_path: Path) -> None:
        """A legacy TEXT row and a compressed BLOB row both materialize correctly."""
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(self._user_line("compressed") + "\n", encoding="utf-8")
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)  # writes a BLOB row
        conn = connect(db)
        legacy = self._user_line("legacy", ts="2026-05-22T00:00:01Z")
        conn.execute(
            "INSERT INTO raw_events"
            "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
            " VALUES('2026-05-22T00:00:01Z', 's1', 'claude-code', ?, 2, 'user', ?, '{}')",
            (str(jsonl), legacy),  # raw_line stored as plain TEXT
        )
        conn.commit()
        conn.close()
        counts = rebuild(db)
        assert counts["messages"] == 2

    def test_recompress_converts_legacy_rows_and_preserves_rebuild(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        for i in range(3):
            conn.execute(
                "INSERT INTO raw_events"
                "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
                " VALUES(?, 's1', 'claude-code', 's.jsonl', ?, 'user', ?, ?)",
                (
                    f"2026-05-22T00:00:0{i}Z",
                    i + 1,
                    self._user_line(f"m{i}", ts=f"2026-05-22T00:00:0{i}Z"),
                    "{}",
                ),
            )
        conn.commit()
        conn.close()
        before = rebuild(db)["messages"]

        result = recompress_raw_events(db, batch_size=2)
        assert result["recompressed"] == 3

        conn = connect(db)
        try:
            types = {r[0] for r in conn.execute("SELECT DISTINCT typeof(raw_line) FROM raw_events")}
        finally:
            conn.close()
        assert types == {"blob"}
        assert rebuild(db)["messages"] == before  # output identical after compression

    def test_recompress_is_idempotent(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(self._user_line("hello") + "\n", encoding="utf-8")
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)  # already compressed
        result = recompress_raw_events(db)
        assert result["recompressed"] == 0  # nothing legacy left to convert


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


class TestRebuild:
    """rebuild() wipes+re-derives the JSONL-derived cache tables from raw_events (ENH-2581)."""

    def _seed_raw_events(self, tmp_path: Path, db: Path) -> None:
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello from rebuild test"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)

    def test_rebuild_materializes_from_raw_events_without_original_files(
        self, tmp_path: Path
    ) -> None:
        """rebuild() replays raw_events rows even after the source JSONL is gone."""
        db = tmp_path / "history.db"
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "hello from rebuild test"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        jsonl.unlink()  # source file gone — rebuild must not need it

        counts = rebuild(db)
        assert counts["messages"] == 1
        assert counts["sessions"] == 1
        conn = connect(db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM message_events").fetchone()[0]
        finally:
            conn.close()
        assert n == 1

    def test_rebuild_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed_raw_events(tmp_path, db)
        rebuild(db)
        rebuild(db)
        conn = connect(db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM message_events").fetchone()[0]
        finally:
            conn.close()
        assert n == 1

    def test_rebuild_updates_last_rebuild_version(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed_raw_events(tmp_path, db)
        rebuild(db)
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'last_rebuild_version'"
            ).fetchone()
        finally:
            conn.close()
        assert int(row["value"]) == SCHEMA_VERSION

    def test_rebuild_does_not_touch_out_of_scope_tables(self, tmp_path: Path) -> None:
        """issue_events/loop_events/commit_events are outside raw_events's scope."""
        db = tmp_path / "history.db"
        self._seed_raw_events(tmp_path, db)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition) VALUES(?,?,?)",
                ("2026-01-01T00:00:00Z", "ENH-2581", "open"),
            )
            conn.commit()
        finally:
            conn.close()

        rebuild(db)

        conn2 = connect(db)
        try:
            n = conn2.execute("SELECT COUNT(*) FROM issue_events").fetchone()[0]
        finally:
            conn2.close()
        assert n == 1


class TestBackfillUsageEvents:
    """_backfill_usage_events parses real LLM token usage from raw_events (ENH-2461)."""

    def _assistant_usage_record(self, session_id: str, ts: str, model: str, usage: dict) -> str:
        return json.dumps(
            {
                "type": "assistant",
                "sessionId": session_id,
                "timestamp": ts,
                "message": {"model": model, "usage": usage},
            }
        )

    def _seed(self, tmp_path: Path, db: Path, records: list[str]) -> None:
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text("\n".join(records) + "\n", encoding="utf-8")
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)

    def test_roundtrip_known_model_computes_cost(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed(
            tmp_path,
            db,
            [
                self._assistant_usage_record(
                    "s1",
                    "2026-07-13T03:00:00Z",
                    "claude-opus-4-7",
                    {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cache_read_input_tokens": 50,
                        "cache_creation_input_tokens": 10,
                    },
                )
            ],
        )
        counts = rebuild(db)
        assert counts["usage_events"] == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT * FROM usage_events").fetchone()
        finally:
            conn.close()
        assert row["session_id"] == "s1"
        assert row["model"] == "claude-opus-4-7"
        assert row["state"] is None  # never populated by the parser path
        assert row["input_tokens"] == 100
        assert row["output_tokens"] == 20
        assert row["cache_read_input_tokens"] == 50
        assert row["cache_creation_input_tokens"] == 10
        # 100*15 + 20*75 + 50*1.5 + 10*18.75, all /1e6
        assert row["cost_usd"] == pytest.approx(0.0032625)

    def test_unknown_model_cost_is_null(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed(
            tmp_path,
            db,
            [
                self._assistant_usage_record(
                    "s1",
                    "2026-07-13T03:00:00Z",
                    "some-unpriced-model",
                    {"input_tokens": 5, "output_tokens": 5},
                )
            ],
        )
        rebuild(db)
        conn = connect(db)
        try:
            row = conn.execute("SELECT cost_usd FROM usage_events").fetchone()
        finally:
            conn.close()
        assert row["cost_usd"] is None  # no warning, just NULL

    def test_non_assistant_and_usageless_records_skipped(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed(
            tmp_path,
            db,
            [
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s1",
                        "timestamp": "t",
                        "message": {"content": "hi"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "s1",
                        "timestamp": "t",
                        "message": {"model": "claude-opus-4-7"},
                    }  # no usage block
                ),
                self._assistant_usage_record(
                    "s1",
                    "2026-07-13T03:00:00Z",
                    "claude-opus-4-7",
                    {"input_tokens": 1, "output_tokens": 1},
                ),
            ],
        )
        counts = rebuild(db)
        assert counts["usage_events"] == 1  # only the real usage record

    def test_usage_row_is_fts_indexed_and_recent_queryable(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed(
            tmp_path,
            db,
            [
                self._assistant_usage_record(
                    "s1",
                    "2026-07-13T03:00:00Z",
                    "claude-sonnet-4-6",
                    {"input_tokens": 10, "output_tokens": 2},
                )
            ],
        )
        rebuild(db)
        # recent() by kind
        rows = recent(db, kind="usage")
        assert len(rows) == 1
        # FTS by model name (quoted phrase — hyphens are token separators in FTS5)
        hits = search(db, query='"claude-sonnet-4-6"', limit=10)
        assert any(h["kind"] == "usage" for h in hits)

    def test_rebuild_is_idempotent_for_usage(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        self._seed(
            tmp_path,
            db,
            [
                self._assistant_usage_record(
                    "s1",
                    "2026-07-13T03:00:00Z",
                    "claude-opus-4-7",
                    {"input_tokens": 1, "output_tokens": 1},
                )
            ],
        )
        rebuild(db)
        rebuild(db)
        conn = connect(db)
        try:
            n = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        finally:
            conn.close()
        assert n == 1


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
        }


class TestCompact:
    """compact() sweeps old raw_events into retention summaries (ENH-2581)."""

    _RETENTION_CFG = {"analytics": {"retention": {"raw_event_max_age_days": 90}}}

    def _insert_old_raw_event(self, conn: sqlite3.Connection, session_id: str = "s1") -> None:
        conn.execute(
            "INSERT INTO raw_events"
            "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
            " VALUES('2020-01-01T00:00:00Z', ?, 'claude-code', 's.jsonl', 1, 'user', '{}', '{}')",
            (session_id,),
        )
        conn.commit()

    def test_compact_marks_rows_and_creates_retention_summary(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        conn = connect(db)
        self._insert_old_raw_event(conn)
        conn.close()

        result = compact(db, config=self._RETENTION_CFG)
        assert result["compacted_rows"] == 1
        assert result["summary_nodes"] == 1

        conn2 = connect(db)
        try:
            row = conn2.execute("SELECT compacted, summary_node_id FROM raw_events").fetchone()
            summary = conn2.execute(
                "SELECT kind, session_id FROM summary_nodes WHERE id = ?",
                (row["summary_node_id"],),
            ).fetchone()
        finally:
            conn2.close()
        assert row["compacted"] == 1
        assert row["summary_node_id"] is not None
        assert summary["kind"] == "retention"
        assert summary["session_id"] == "s1"

    def test_compact_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        conn = connect(db)
        self._insert_old_raw_event(conn)
        conn.close()

        compact(db, config=self._RETENTION_CFG)
        result2 = compact(db, config=self._RETENTION_CFG)
        assert result2["compacted_rows"] == 0  # already compacted, nothing left to sweep

        conn2 = connect(db)
        try:
            n = conn2.execute(
                "SELECT COUNT(*) FROM summary_nodes WHERE kind = 'retention'"
            ).fetchone()[0]
        finally:
            conn2.close()
        assert n == 1

    def test_and_prune_deletes_compacted_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        conn = connect(db)
        self._insert_old_raw_event(conn)
        conn.close()

        config = {
            "analytics": {
                "retention": {
                    "raw_event_max_age_days": 90,
                    "min_project_age_days": 0,
                    "min_db_size_mb": 0,
                }
            }
        }
        result = compact(db, config=config, and_prune=True)
        assert result["pruned_rows"] == 1

        conn2 = connect(db)
        try:
            n = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        finally:
            conn2.close()
        assert n == 0

    def test_null_max_age_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        conn = connect(db)
        self._insert_old_raw_event(conn)
        conn.close()

        result = compact(db, config={"analytics": {"retention": {"raw_event_max_age_days": None}}})
        assert result["compacted_rows"] == 0
        assert result["summary_nodes"] == 0


class TestFts5LeakFixed:
    """rebuild() re-derives search_index from the current raw_events state (ENH-2581).

    Regression coverage for the FTS5 leak: prune() used to delete cache-table
    rows without ever touching search_index, leaving stale FTS rows pointing
    at deleted events. Now prune() only deletes raw_events, and rebuild()
    always wipes+re-populates search_index — so after prune+rebuild, the FTS
    row count matches the surviving cache-table row count.
    """

    def test_fts_row_count_drops_to_match_after_prune_and_rebuild(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        jsonl = tmp_path / "s.jsonl"
        records = [
            {
                "type": "user",
                "sessionId": "s1",
                "timestamp": f"2020-01-01T00:0{i}:00Z",
                "message": {"content": f"message number {i}"},
            }
            for i in range(2)
        ]
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        rebuild(db)

        conn = connect(db)
        try:
            before = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind = 'message'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert before == 2

        # Mark one raw_events row compacted and prune it away.
        conn = connect(db)
        try:
            conn.execute("UPDATE raw_events SET compacted = 1 WHERE line_no = 1")
            conn.commit()
        finally:
            conn.close()
        prune(
            db,
            config={
                "analytics": {
                    "retention": {
                        "raw_event_max_age_days": 0,
                        "min_project_age_days": 0,
                        "min_db_size_mb": 0,
                    }
                }
            },
        )

        rebuild(db)

        conn = connect(db)
        try:
            after = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind = 'message'"
            ).fetchone()[0]
            message_count = conn.execute("SELECT COUNT(*) FROM message_events").fetchone()[0]
        finally:
            conn.close()
        assert after == 1
        assert after == message_count


class TestValidKindsCentralization:
    """VALID_KINDS is the single source for recent()/search --kind (ENH-2581)."""

    def test_every_valid_kind_has_a_kind_table_entry(self) -> None:
        assert set(VALID_KINDS) == set(_KIND_TABLE.keys())

    def test_recent_snapshot_kind_does_not_raise(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert recent(db, kind="snapshot") == []


class TestPrune:
    """Retention lifecycle for raw_events (ENH-1906, refactored onto raw_events by ENH-2581).

    prune() only deletes raw_events rows already marked compacted=1 (see
    TestCompact for compact()'s role in setting that flag) — an uncompacted row
    is never deleted even past the cutoff, matching the compact -> prune
    lifecycle order.
    """

    # Config that disables both dual gates so pruning always runs in tests.
    _GATES_OPEN = {"analytics": {"retention": {"min_project_age_days": 0, "min_db_size_mb": 0}}}

    def _insert_raw_event(
        self,
        conn: sqlite3.Connection,
        ts: str = "2020-01-01T00:00:00Z",
        *,
        compacted: int = 1,
        source_path: str = "s.jsonl",
        line_no: int = 1,
    ) -> None:
        """Insert a minimal raw_events row, compacted by default (prune-eligible)."""
        conn.execute(
            "INSERT INTO raw_events"
            "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json,"
            " compacted)"
            " VALUES(?, 's1', 'claude-code', ?, ?, 'user', '{}', '{}', ?)",
            (ts, source_path, line_no, compacted),
        )
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

    def test_prunes_old_compacted_raw_events(self, tmp_path: Path) -> None:
        """Compacted rows older than raw_event_max_age_days are deleted."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, compacted=1)
        conn.close()

        config = {**self._GATES_OPEN, "analytics": {**self._GATES_OPEN["analytics"]}}
        config["analytics"]["retention"]["raw_event_max_age_days"] = 90
        result = prune(db, config=config)

        assert result["pruned"]
        assert result["deleted"]["raw_events"] == 1
        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        conn2.close()
        assert count == 0

    def test_uncompacted_rows_never_pruned(self, tmp_path: Path) -> None:
        """Rows past the cutoff but not yet compacted survive — compact() must run first."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, compacted=0)
        conn.close()

        result = prune(db, config=self._GATES_OPEN)
        assert result["deleted"]["raw_events"] == 0

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        conn2.close()
        assert count == 1

    def test_retains_recent_rows(self, tmp_path: Path) -> None:
        """Rows newer than the cutoff are kept after pruning even if compacted."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, "2020-01-01T00:00:00Z", compacted=1, line_no=1)
        self._insert_raw_event(conn, "2099-12-31T00:00:00Z", compacted=1, line_no=2)
        conn.close()

        result = prune(db, config=self._GATES_OPEN)
        assert result["deleted"]["raw_events"] == 1

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        conn2.close()
        assert count == 1  # only the future row survives

    def test_high_value_tables_never_pruned(self, tmp_path: Path) -> None:
        """issue_events and user_corrections are never touched by prune()."""
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
        self._insert_raw_event(conn, compacted=1)
        conn.close()

        prune(db, config=self._GATES_OPEN)
        result2 = prune(db, config=self._GATES_OPEN)
        assert result2["pruned"]
        assert result2["deleted"].get("raw_events", 0) == 0

    def test_dry_run_does_not_delete_rows(self, tmp_path: Path) -> None:
        """dry_run=True counts rows without deleting them."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, compacted=1)
        conn.close()

        result = prune(db, config=self._GATES_OPEN, dry_run=True)
        assert result["pruned"]
        assert result["deleted"]["raw_events"] == 1
        assert not result["vacuumed"]

        conn2 = connect(db)
        count = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        conn2.close()
        assert count == 1  # row still present

    def test_null_raw_event_max_age_disables_pruning(self, tmp_path: Path) -> None:
        """raw_event_max_age_days=null means no row is pruned."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, compacted=1)
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
        count = conn2.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        conn2.close()
        assert count == 1

    def test_vacuum_runs_after_prune(self, tmp_path: Path) -> None:
        """vacuumed flag is set True when pruning runs and rows are deleted."""
        db = tmp_path / "h.db"
        conn = connect(db)
        self._insert_raw_event(conn, compacted=1)
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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
        assert SCHEMA_VERSION == 23
        assert int(row[0]) == 23

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
        assert int(version[0]) == 23
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
            row = conn.execute("SELECT * FROM issue_snapshots WHERE issue_id='ENH-2151'").fetchone()
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


class TestSkillEventContext:
    """ENH-2460: skill_event_context() insert-then-update round-trip."""

    def test_success_path_populates_completion_columns(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "sess-1", "refine-issue", "ENH-2460"):
            pass
        rows = recent(db, kind="skill")
        assert len(rows) == 1
        assert rows[0]["skill_name"] == "refine-issue"
        assert rows[0]["exit_code"] == 0
        assert rows[0]["success"] == 1
        assert rows[0]["duration_ms"] is not None
        assert rows[0]["duration_ms"] >= 0

    def test_raise_path_records_failure(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with pytest.raises(ValueError):
            with skill_event_context(db, "sess-2", "check-code", ""):
                raise ValueError("boom")
        rows = recent(db, kind="skill")
        assert rows[0]["exit_code"] == 1
        assert rows[0]["success"] == 0

    def test_host_provided_exit_code_wins(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, None, "manage-issue", "") as completion:
            completion.exit_code = 3
        rows = recent(db, kind="skill")
        assert rows[0]["exit_code"] == 3
        assert rows[0]["success"] == 0

    def test_args_truncated_to_200(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, None, "capture-issue", "x" * 300):
            pass
        rows = recent(db, kind="skill")
        assert len(rows[0]["args"]) <= 200

    def test_fts_indexed(self, tmp_path: Path) -> None:
        from little_loops.session_store import skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "sess-3", "ready-issue", ""):
            pass
        results = search(db, query="ready")
        assert any(r["kind"] == "skill" for r in results)

    def test_best_effort_on_unopenable_db(self, tmp_path: Path) -> None:
        """A db path that cannot be opened must not prevent the body from running."""
        from little_loops.session_store import skill_event_context

        ran = False
        # tmp_path is a directory — sqlite cannot open it as a database file.
        with skill_event_context(tmp_path, None, "broken-db-skill", ""):
            ran = True
        assert ran


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


class TestInferIssueId:
    """ENH-2458: _infer_issue_id() message/branch parsing."""

    def test_typed_closes_reference(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("fix: something\n\nCloses ENH-2458") == "ENH-2458"

    def test_fixes_hash_reference_falls_back_to_typed_token(self) -> None:
        from little_loops.session_store import _infer_issue_id

        # "#123" has no type prefix; a typed token elsewhere wins.
        assert _infer_issue_id("Fixes #123 (BUG-99 regression)") == "BUG-99"

    def test_trailer_reference(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("feat: add thing\n\nIssue: FEAT-777") == "FEAT-777"

    def test_bare_typed_token(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("enh(store): ENH-2458 add commit_events") == "ENH-2458"

    def test_branch_convention(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("misc cleanup", branch="feat/ENH-2458-commit-events") == "ENH-2458"

    def test_no_reference_returns_none(self) -> None:
        from little_loops.session_store import _infer_issue_id

        assert _infer_issue_id("chore: tidy imports", branch="main") is None


class TestRecordCommitEvent:
    """ENH-2458: record_commit_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        inserted = record_commit_event(
            db,
            "abc123def456",
            "enh(store): add commit_events (ENH-2458)",
            author="Test Author",
            branch="feat/ENH-2458-commits",
            files=["scripts/little_loops/session_store.py"],
            parent_sha="000111",
        )
        assert inserted
        rows = recent(db, kind="commit")
        assert len(rows) == 1
        assert rows[0]["commit_sha"] == "abc123def456"
        assert rows[0]["issue_id"] == "ENH-2458"
        assert rows[0]["branch"] == "feat/ENH-2458-commits"
        assert json.loads(rows[0]["files_json"]) == ["scripts/little_loops/session_store.py"]

    def test_dedupe_on_sha(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        assert record_commit_event(db, "dupsha", "first")
        assert not record_commit_event(db, "dupsha", "second attempt")
        rows = recent(db, kind="commit")
        assert len(rows) == 1
        assert rows[0]["message"] == "first"

    def test_fts_searchable_by_message_fragment(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "ftssha", "fix flaky teleporter alignment")
        results = search(db, query="teleporter")
        assert any(r["kind"] == "commit" for r in results)

    def test_explicit_issue_id_not_overridden(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "explsha", "mentions BUG-1 in passing", issue_id="ENH-42")
        rows = recent(db, kind="commit")
        assert rows[0]["issue_id"] == "ENH-42"


class TestBackfillCommitEvents:
    """ENH-2458: _backfill_commit_events() seeds commit_events from git log."""

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@t.t", "-c", "user.name=T", *args],
            cwd=str(repo),
            check=True,
            capture_output=True,
            timeout=30,
        )

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        import shutil

        if shutil.which("git") is None:
            pytest.skip("git not available")
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        (repo / "a.txt").write_text("one\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "feat: initial commit")
        (repo / "b.txt").write_text("two\n", encoding="utf-8")
        self._git(repo, "add", "b.txt")
        self._git(repo, "commit", "-q", "-m", "enh(store): wire it up\n\nCloses ENH-2458")
        return repo

    def test_backfill_populates_commit_events(self, repo: Path, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        counts = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", repo_root=repo)
        assert counts["commits"] == 2
        rows = recent(db, kind="commit")
        messages = {r["message"] for r in rows}
        assert any("initial commit" in m for m in messages)
        by_issue = {r["issue_id"] for r in rows}
        assert "ENH-2458" in by_issue

    def test_backfill_records_touched_files(self, repo: Path, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", repo_root=repo)
        rows = recent(db, kind="commit")
        newest = next(r for r in rows if "wire it up" in r["message"])
        assert "b.txt" in json.loads(newest["files_json"])

    def test_backfill_idempotent(self, repo: Path, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        first = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", repo_root=repo)
        second = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no", repo_root=repo)
        assert first["commits"] == 2
        assert second["commits"] == 0
        assert len(recent(db, kind="commit")) == 2

    def test_backfill_skipped_without_repo_root(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        counts = backfill(db, issues_dir=tmp_path / "no", loops_dir=tmp_path / "no")
        assert counts["commits"] == 0

    def test_record_head_commit_hook_helper(self, repo: Path, tmp_path: Path) -> None:
        """The post-commit hook helper records HEAD with branch attribution."""
        from little_loops.hooks.post_commit import record_head_commit

        db = tmp_path / "history.db"
        assert record_head_commit(db, repo)
        rows = recent(db, kind="commit")
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "ENH-2458"
        assert rows[0]["branch"] is not None
        assert "b.txt" in json.loads(rows[0]["files_json"])
        # Second call is a duplicate → no new row
        assert not record_head_commit(db, repo)
        assert len(recent(db, kind="commit")) == 1


class TestRecordTestRunEvent:
    """ENH-2459: record_test_run_event() DB write round-trip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T12:00:00Z",
            ended_at="2026-07-01T12:00:31Z",
            total=10,
            passed=8,
            failed=1,
            errored=1,
            skipped=0,
            duration_s=31.2,
            failing_names=["tests/test_x.py::test_flaky"],
            env_label="local",
            head_sha="deadbeef",
            branch="main",
            command="python -m pytest scripts/tests/",
        )
        rows = recent(db, kind="test_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["total"] == 10
        assert row["passed"] == 8
        assert row["failed"] == 1
        assert row["errored"] == 1
        assert json.loads(row["failing_names_json"]) == ["tests/test_x.py::test_flaky"]
        assert row["env_label"] == "local"
        assert row["head_sha"] == "deadbeef"

    def test_failing_names_fts_searchable(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T12:00:00Z",
            total=1,
            failed=1,
            failing_names=["tests/test_teleporter.py::test_alignment"],
        )
        results = search(db, query="teleporter")
        assert any(r["kind"] == "test_run" for r in results)

    def test_multiple_runs_are_distinct_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(db, ts="2026-07-01T12:00:00Z", total=1, passed=1)
        record_test_run_event(db, ts="2026-07-01T12:05:00Z", total=1, passed=1)
        rows = recent(db, kind="test_run")
        assert len(rows) == 2
        assert rows[0]["ts"] > rows[1]["ts"]

    def test_v14_db_upgrades_gains_test_run_events(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 14)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        assert "test_run_events" in names
        assert "commit_events" in names


class TestOrchestrationRuns:
    """ENH-2492: orchestration_runs schema, UPSERT, and FTS contract."""

    @staticmethod
    def _recorder():
        from little_loops import session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        assert callable(recorder), "record_orchestration_run must be public"
        return recorder

    def test_v21_db_upgrades_gains_orchestration_runs(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 23
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 21)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='orchestration_runs'"
                )
            }
        finally:
            conn.close()
        assert "orchestration_runs" in names
        assert {
            "idx_orchestration_runs_driver",
            "idx_orchestration_runs_issue_id",
            "idx_orchestration_runs_status",
        } <= indexes

    def test_roundtrip(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        record_orchestration_run(
            db,
            run_id="batch-1",
            driver="ll-sprint",
            issue_id="ENH-2492",
            status="failed",
            failure_reason="teleporterfailure",
            duration_s=12.5,
            wave="Wave 2/3",
            pr_url="https://example.test/pr/42",
            started_at="2026-07-17T10:00:00Z",
            ended_at="2026-07-17T10:00:13Z",
            head_sha="abc123",
            branch="feature/ENH-2492",
        )

        rows = recent(db, kind="orchestration_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "batch-1"
        assert row["driver"] == "ll-sprint"
        assert row["issue_id"] == "ENH-2492"
        assert row["status"] == "failed"
        assert row["failure_reason"] == "teleporterfailure"
        assert row["duration_s"] == 12.5
        assert row["wave"] == "Wave 2/3"
        assert row["pr_url"] == "https://example.test/pr/42"

    def test_upsert_replaces_outcome_and_fts_row(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        common = {
            "run_id": "batch-retry",
            "driver": "ll-sprint",
            "issue_id": "BUG-17",
            "wave": "Wave 1/1",
        }
        record_orchestration_run(
            db,
            **common,
            status="failed",
            failure_reason="teleporterfailure",
            duration_s=4.0,
        )
        record_orchestration_run(
            db,
            **common,
            status="completed",
            failure_reason=None,
            duration_s=2.0,
        )

        rows = recent(db, kind="orchestration_run")
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["failure_reason"] is None
        assert rows[0]["duration_s"] == 2.0
        stale = search(db, query="teleporterfailure")
        assert not any(row["kind"] == "orchestration_run" for row in stale)
        completed = [
            row for row in search(db, query="completed") if row["kind"] == "orchestration_run"
        ]
        assert len(completed) == 1

        conn = connect(db)
        try:
            indexed = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='orchestration_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert indexed == 1

    def test_identical_write_is_idempotent(self, tmp_path: Path) -> None:
        record_orchestration_run = self._recorder()
        db = tmp_path / "history.db"
        kwargs = {
            "run_id": "batch-same",
            "driver": "ll-auto",
            "issue_id": "ENH-1",
            "status": "completed",
            "duration_s": 1.0,
        }
        record_orchestration_run(db, **kwargs)
        record_orchestration_run(db, **kwargs)

        conn = connect(db)
        try:
            table_rows = conn.execute("SELECT COUNT(*) FROM orchestration_runs").fetchone()[0]
            fts_rows = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='orchestration_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert table_rows == 1
        assert fts_rows == 1


class TestLoopRuns:
    """loop_runs summary rows (ENH-2463)."""

    @staticmethod
    def _recorder():
        from little_loops import session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        assert callable(recorder), "record_loop_run_summary must be public"
        return recorder

    @staticmethod
    def _diagnostics_updater():
        from little_loops import session_store

        updater = getattr(session_store, "update_loop_run_diagnostics", None)
        assert callable(updater), "update_loop_run_diagnostics must be public"
        return updater

    def test_v22_db_upgrades_gains_loop_runs(self, tmp_path: Path) -> None:
        assert SCHEMA_VERSION == 23
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 22)
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            names = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            indexes = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='loop_runs'"
                )
            }
        finally:
            conn.close()
        assert "loop_runs" in names
        assert {
            "idx_loop_runs_loop_name",
            "idx_loop_runs_terminated_by",
            "idx_loop_runs_evaluator_score",
        } <= indexes

    def test_roundtrip(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-implement",
            loop_name="rn-implement",
            started_at="2026-07-17T10:15:30Z",
            ended_at="2026-07-17T10:20:00Z",
            final_state="done",
            iterations=3,
            terminated_by="terminal",
            head_sha="abc123",
            branch="feature/ENH-2463",
        )

        rows = recent(db, kind="loop_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["run_id"] == "20260717T101530-rn-implement"
        assert row["loop_name"] == "rn-implement"
        assert row["final_state"] == "done"
        assert row["iterations"] == 3
        assert row["terminated_by"] == "terminal"
        assert row["evaluator_score"] is None
        assert row["diagnostics_path"] is None

    def test_error_termination(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-refine",
            loop_name="rn-refine",
            terminated_by="error",
            error="boom",
        )
        rows = recent(db, kind="loop_run")
        assert rows[0]["terminated_by"] == "error"
        assert rows[0]["error"] == "boom"

    def test_duplicate_run_id_is_idempotent(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        kwargs = {
            "run_id": "20260717T101530-rn-implement",
            "loop_name": "rn-implement",
            "terminated_by": "terminal",
        }
        record_loop_run_summary(db, **kwargs)
        record_loop_run_summary(db, **kwargs)

        conn = connect(db)
        try:
            table_rows = conn.execute("SELECT COUNT(*) FROM loop_runs").fetchone()[0]
            fts_rows = conn.execute(
                "SELECT COUNT(*) FROM search_index WHERE kind='loop_run'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert table_rows == 1
        assert fts_rows == 1

    def test_missing_identity_fields_returns_false(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        db = tmp_path / "history.db"
        assert record_loop_run_summary(db, run_id="", loop_name="rn-implement") is False
        assert record_loop_run_summary(db, run_id="run-1", loop_name="") is False

    def test_update_loop_run_diagnostics_links_artifact(self, tmp_path: Path) -> None:
        record_loop_run_summary = self._recorder()
        update_loop_run_diagnostics = self._diagnostics_updater()
        db = tmp_path / "history.db"
        record_loop_run_summary(
            db,
            run_id="20260717T101530-rn-implement",
            loop_name="rn-implement",
            terminated_by="terminal",
        )
        result = update_loop_run_diagnostics(
            db, "20260717T101530-rn-implement", ".loops/diagnostics/rn-implement-20260717.md"
        )
        assert result is True

        rows = recent(db, kind="loop_run")
        assert rows[0]["diagnostics_path"] == ".loops/diagnostics/rn-implement-20260717.md"
        # other fields untouched by the diagnostics-only update
        assert rows[0]["terminated_by"] == "terminal"

    def test_update_loop_run_diagnostics_missing_run_id_returns_false(
        self, tmp_path: Path
    ) -> None:
        update_loop_run_diagnostics = self._diagnostics_updater()
        db = tmp_path / "history.db"
        ensure_db(db)
        assert update_loop_run_diagnostics(db, "no-such-run", "path.md") is False


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
