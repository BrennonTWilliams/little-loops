"""Tests for ENH-2497: discriminate subagent Task spawns in history.db.

Covers the v24 migration (nullable ``agent_type`` column on ``tool_events``),
live-write population from ``post_tool_use``, backfill population from
session JSONL, the ``agent_usage()`` / ``recent_tool_events()`` reader
helpers, and live FTS indexing of spawn rows.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.hooks.post_tool_use import handle
from little_loops.hooks.types import LLHookEvent
from little_loops.session_store import _MIGRATIONS, SCHEMA_VERSION, _split_sql_statements, ensure_db


def _event(payload: dict, *, cwd: str) -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="post_tool_use", payload=payload, cwd=cwd)


def _bootstrap_schema_at(db: Path, version: int) -> None:
    """Bootstrap a database at an exact historical schema *version*.

    Applies migrations 0..version-1 verbatim from ``_MIGRATIONS``, mirroring
    the helper in ``test_session_store.py``.
    """
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


def _write_config(project_dir: Path) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"analytics": {"enabled": True}}), encoding="utf-8"
    )


class TestSchemaV24AgentType:
    def test_tool_events_has_agent_type_column(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_events)")}
        finally:
            conn.close()
        assert "agent_type" in cols

    def test_v23_db_upgrades_preserving_task_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 23)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash) "
                "VALUES('2026-06-01T00:00:00Z', 's-old', 'Task', 'abc')"
            )
            conn.commit()
        finally:
            conn.close()

        ensure_db(db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            version = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            row = conn.execute("SELECT * FROM tool_events WHERE session_id='s-old'").fetchone()
        finally:
            conn.close()
        assert int(version[0]) == SCHEMA_VERSION
        assert row is not None
        assert row["agent_type"] is None


class TestTaskSpawnAgentType:
    def test_live_write_populates_agent_type(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "codebase-locator", "prompt": "find files"},
            "tool_response": {},
            "session_id": "sess-task",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT tool_name, agent_type FROM tool_events WHERE session_id='sess-task'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "Task"
        assert row[1] == "codebase-locator"

    def test_ll_prefix_normalized(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "ll:codebase-locator"},
            "tool_response": {},
            "session_id": "sess-prefixed",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (agent_type,) = conn.execute(
                "SELECT agent_type FROM tool_events WHERE session_id='sess-prefixed'"
            ).fetchone()
        finally:
            conn.close()
        assert agent_type == "codebase-locator"


class TestNonTaskNullAgent:
    def test_non_task_tool_leaves_agent_type_null(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/foo", "content": "bar"},
            "tool_response": {},
            "session_id": "sess-write",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (agent_type,) = conn.execute(
                "SELECT agent_type FROM tool_events WHERE session_id='sess-write'"
            ).fetchone()
        finally:
            conn.close()
        assert agent_type is None


class TestGracefulMissingField:
    def test_task_call_without_subagent_type_writes_null(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Task",
            "tool_input": {},
            "tool_response": {},
            "session_id": "sess-missing",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (agent_type,) = conn.execute(
                "SELECT agent_type FROM tool_events WHERE session_id='sess-missing'"
            ).fetchone()
        finally:
            conn.close()
        assert agent_type is None


class TestAgentUsageAggregation:
    def test_aggregation_counts_per_agent_excludes_non_task(self, tmp_path: Path) -> None:
        from little_loops.history_reader import agent_usage

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            rows = [
                ("2026-07-01T00:00:00Z", "s1", "Task", "codebase-locator"),
                ("2026-07-01T00:01:00Z", "s1", "Task", "codebase-locator"),
                ("2026-07-01T00:02:00Z", "s1", "Task", "codebase-locator"),
                ("2026-07-01T00:03:00Z", "s1", "Task", "Explore"),
                ("2026-07-01T00:04:00Z", "s1", "Task", "Explore"),
                ("2026-07-01T00:05:00Z", "s1", "Write", None),
            ]
            conn.executemany(
                "INSERT INTO tool_events(ts, session_id, tool_name, agent_type) VALUES(?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

        result = agent_usage(db=db)
        assert result == [
            {"agent_type": "codebase-locator", "invocations": 3},
            {"agent_type": "Explore", "invocations": 2},
        ]


class TestBackfillAgentType:
    def test_backfill_populates_agent_type(self, tmp_path: Path) -> None:
        from little_loops.session_store import backfill

        jsonl_path = tmp_path / "session.jsonl"
        record = {
            "type": "assistant",
            "sessionId": "sess-backfill",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Task",
                        "input": {"subagent_type": "loop-specialist", "prompt": "diagnose"},
                    }
                ]
            },
        }
        jsonl_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

        db = tmp_path / "history.db"
        backfill(
            db,
            issues_dir=tmp_path / "none",
            loops_dir=tmp_path / "none",
            jsonl_files=[jsonl_path],
            also_rebuild=True,
        )

        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT tool_name, agent_type FROM tool_events WHERE session_id='sess-backfill'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "Task"
        assert row[1] == "loop-specialist"


class TestFTSIndexing:
    def test_live_write_indexed_in_search(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Task",
            "tool_input": {"subagent_type": "loop-specialist"},
            "tool_response": {},
            "session_id": "sess-fts",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT content, kind FROM search_index WHERE content LIKE '%loop-specialist%'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[1] == "tool"


class TestReadersEmptyOnMissingDb:
    def test_agent_usage_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import agent_usage

        assert agent_usage(db=tmp_path / "nonexistent.db") == []

    def test_recent_tool_events_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_tool_events

        assert recent_tool_events(db=tmp_path / "nonexistent.db") == []
