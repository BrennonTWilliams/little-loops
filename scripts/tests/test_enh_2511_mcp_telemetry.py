"""Tests for ENH-2511: MCP tool-call telemetry in history.db.

Covers the v25 migration (nullable ``mcp_server``/``mcp_tool``/``mcp_outcome``/
``latency_ms`` columns on ``tool_events``), live-write population from
``post_tool_use``, backfill population from session JSONL, the
``mcp_server_usage()`` / ``mcp_failure_rate()`` / ``recent_tool_events()``
reader helpers.
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


class TestSchemaV25McpColumns:
    def test_tool_events_has_mcp_columns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(tool_events)")}
        finally:
            conn.close()
        assert {"mcp_server", "mcp_tool", "mcp_outcome", "latency_ms"} <= cols

    def test_v24_db_upgrades_preserving_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        _bootstrap_schema_at(db, 24)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash) "
                "VALUES('2026-06-01T00:00:00Z', 's-old', 'mcp__pencil__draw', 'abc')"
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
        assert row["mcp_server"] is None
        assert row["mcp_tool"] is None
        assert row["mcp_outcome"] is None
        assert row["latency_ms"] is None


class TestMcpToolLiveWrite:
    def test_live_write_populates_mcp_columns_on_success(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "mcp__pencil__batch_design",
            "tool_input": {"prompt": "draw a cat"},
            "tool_response": {"content": [{"type": "text", "text": "ok"}]},
            "session_id": "sess-mcp-ok",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT mcp_server, mcp_tool, mcp_outcome FROM tool_events "
                "WHERE session_id='sess-mcp-ok'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "pencil"
        assert row[1] == "batch_design"
        assert row[2] == "success"

    def test_live_write_populates_error_outcome(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "mcp__zai-mcp-server__analyze_image",
            "tool_input": {},
            "tool_response": {"isError": True, "content": [{"type": "text", "text": "boom"}]},
            "session_id": "sess-mcp-err",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT mcp_server, mcp_tool, mcp_outcome FROM tool_events "
                "WHERE session_id='sess-mcp-err'"
            ).fetchone()
        finally:
            conn.close()
        assert row == ("zai-mcp-server", "analyze_image", "error")

    def test_live_write_populates_latency_when_present(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "mcp__pencil__batch_design",
            "tool_input": {},
            "tool_response": {},
            "tool_call": {"started_at": 1000.0, "completed_at": 1250.0},
            "session_id": "sess-mcp-latency",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (latency_ms,) = conn.execute(
                "SELECT latency_ms FROM tool_events WHERE session_id='sess-mcp-latency'"
            ).fetchone()
        finally:
            conn.close()
        assert latency_ms == 250

    def test_live_write_leaves_latency_null_when_absent(self, tmp_path: Path, monkeypatch) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "mcp__pencil__batch_design",
            "tool_input": {},
            "tool_response": {},
            "session_id": "sess-mcp-no-latency",
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (latency_ms,) = conn.execute(
                "SELECT latency_ms FROM tool_events WHERE session_id='sess-mcp-no-latency'"
            ).fetchone()
        finally:
            conn.close()
        assert latency_ms is None


class TestNonMcpNullColumns:
    def test_non_mcp_tool_leaves_mcp_columns_null(self, tmp_path: Path, monkeypatch) -> None:
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
            row = conn.execute(
                "SELECT mcp_server, mcp_tool, mcp_outcome, latency_ms FROM tool_events "
                "WHERE session_id='sess-write'"
            ).fetchone()
        finally:
            conn.close()
        assert row == (None, None, None, None)


class TestGracefulMalformedResponse:
    def test_malformed_tool_response_writes_null_never_raises(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _write_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "mcp__pencil__batch_design",
            "tool_input": {},
            "tool_response": "not-a-dict",
            "session_id": "sess-malformed",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT mcp_server, mcp_tool FROM tool_events WHERE session_id='sess-malformed'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "pencil"
        assert row[1] == "batch_design"


class TestBackfillMcpColumns:
    def test_backfill_populates_mcp_server_and_tool(self, tmp_path: Path) -> None:
        from little_loops.session_store import backfill

        jsonl_path = tmp_path / "session.jsonl"
        record = {
            "type": "assistant",
            "sessionId": "sess-backfill-mcp",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "mcp__pencil__batch_design",
                        "input": {"prompt": "draw"},
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
                "SELECT mcp_server, mcp_tool, mcp_outcome, latency_ms FROM tool_events "
                "WHERE session_id='sess-backfill-mcp'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "pencil"
        assert row[1] == "batch_design"
        assert row[2] is None
        assert row[3] is None

    def test_backfill_leaves_non_mcp_tool_null(self, tmp_path: Path) -> None:
        from little_loops.session_store import backfill

        jsonl_path = tmp_path / "session.jsonl"
        record = {
            "type": "assistant",
            "sessionId": "sess-backfill-non-mcp",
            "timestamp": "2026-07-01T00:00:00Z",
            "message": {"content": [{"type": "tool_use", "name": "Write", "input": {}}]},
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
                "SELECT mcp_server, mcp_tool FROM tool_events WHERE session_id='sess-backfill-non-mcp'"
            ).fetchone()
        finally:
            conn.close()
        assert row == (None, None)


class TestMcpUsageAggregation:
    def test_mcp_server_usage_success_rate(self, tmp_path: Path) -> None:
        from little_loops.history_reader import mcp_server_usage

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            rows = [
                (
                    "2026-07-01T00:00:00Z",
                    "s1",
                    "mcp__pencil__draw",
                    "pencil",
                    "draw",
                    "success",
                    100,
                ),
                (
                    "2026-07-01T00:01:00Z",
                    "s1",
                    "mcp__pencil__draw",
                    "pencil",
                    "draw",
                    "success",
                    200,
                ),
                (
                    "2026-07-01T00:02:00Z",
                    "s1",
                    "mcp__pencil__draw",
                    "pencil",
                    "draw",
                    "error",
                    None,
                ),
                ("2026-07-01T00:03:00Z", "s1", "Write", None, None, None, None),
            ]
            conn.executemany(
                "INSERT INTO tool_events(ts, session_id, tool_name, mcp_server, mcp_tool, "
                "mcp_outcome, latency_ms) VALUES(?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

        result = mcp_server_usage(db=db)
        assert len(result) == 1
        assert result[0]["mcp_server"] == "pencil"
        assert result[0]["invocations"] == 3
        assert result[0]["successes"] == 2

    def test_mcp_failure_rate(self, tmp_path: Path) -> None:
        from little_loops.history_reader import mcp_failure_rate

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            rows = [
                ("2026-07-01T00:00:00Z", "s1", "mcp__pencil__draw", "pencil", "draw", "success"),
                ("2026-07-01T00:01:00Z", "s1", "mcp__pencil__draw", "pencil", "draw", "error"),
            ]
            conn.executemany(
                "INSERT INTO tool_events(ts, session_id, tool_name, mcp_server, mcp_tool, "
                "mcp_outcome) VALUES(?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

        result = mcp_failure_rate(db=db)
        assert len(result) == 1
        assert result[0]["mcp_server"] == "pencil"
        assert result[0]["error_count"] == 1
        assert result[0]["failure_rate"] == 0.5


class TestRecentToolEventsMcpFilters:
    def test_filters_by_mcp_server(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_tool_events

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = sqlite3.connect(str(db))
        try:
            conn.executemany(
                "INSERT INTO tool_events(ts, session_id, tool_name, mcp_server, mcp_tool) "
                "VALUES(?, ?, ?, ?, ?)",
                [
                    ("2026-07-01T00:00:00Z", "s1", "mcp__pencil__draw", "pencil", "draw"),
                    ("2026-07-01T00:01:00Z", "s1", "mcp__other__x", "other", "x"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        result = recent_tool_events(mcp_server="pencil", db=db)
        assert len(result) == 1
        assert result[0]["mcp_server"] == "pencil"


class TestReadersEmptyOnMissingDbMcp:
    def test_mcp_server_usage_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import mcp_server_usage

        assert mcp_server_usage(db=tmp_path / "nonexistent.db") == []

    def test_mcp_failure_rate_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import mcp_failure_rate

        assert mcp_failure_rate(db=tmp_path / "nonexistent.db") == []
