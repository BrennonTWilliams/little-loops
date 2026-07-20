"""ENH-2505: subagent spawn-tree linkage in ``.ll/history.db``.

Covers the ``subagent_runs`` table writers (``record_subagent_run_start`` /
``record_subagent_run_stop``), the ``SubagentStart``/``SubagentStop`` hook
handlers, the ``history_reader`` tree/retries/budget helpers, and backfill
from nested subagent transcripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.history_reader import subagent_budget, subagent_retries, subagent_tree
from little_loops.hooks.subagent_start import handle as subagent_start_handle
from little_loops.hooks.subagent_stop import handle as subagent_stop_handle
from little_loops.hooks.types import LLHookEvent
from little_loops.session_store import (
    _backfill_subagent_runs,
    connect,
    ensure_db,
    record_subagent_run_start,
    record_subagent_run_stop,
)


class TestSubagentRunLifecycle:
    """record_subagent_run_start / record_subagent_run_stop round-trip."""

    def test_start_writes_running_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert record_subagent_run_start(
            db,
            parent_session_id="parent-1",
            agent_id="agent-abc",
            agent_type="Explore",
            started_at="2026-07-20T00:00:00Z",
        )
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["parent_session_id"] == "parent-1"
        assert row["agent_type"] == "Explore"
        assert row["status"] == "running"
        assert row["ended_at"] is None

    def test_stop_updates_matching_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-abc", agent_type="Explore"
        )
        assert record_subagent_run_stop(
            db,
            parent_session_id="parent-1",
            agent_id="agent-abc",
            agent_transcript_path="/tmp/parent-1/subagents/agent-abc.jsonl",
            ended_at="2026-07-20T00:05:00Z",
        )
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row["status"] == "completed"
        assert row["ended_at"] == "2026-07-20T00:05:00Z"
        assert row["agent_transcript_path"] == "/tmp/parent-1/subagents/agent-abc.jsonl"

    def test_stop_with_no_matching_start_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert not record_subagent_run_stop(
            db, parent_session_id="parent-1", agent_id="agent-missing"
        )

    def test_start_missing_agent_id_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert not record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id=None, agent_type="Explore"
        )

    def test_stop_missing_agent_id_is_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        assert not record_subagent_run_stop(db, parent_session_id="parent-1", agent_id=None)


class TestSubagentRunReplayIdempotency:
    """Replaying a SubagentStart for the same (parent_session_id, agent_id) is a no-op."""

    def test_duplicate_start_does_not_duplicate_row(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        first = record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-abc", agent_type="Explore"
        )
        second = record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-abc", agent_type="Explore"
        )
        assert first is True
        assert second is False
        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1

    def test_same_agent_id_different_parent_does_not_collide(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-abc", agent_type="Explore"
        )
        record_subagent_run_start(
            db, parent_session_id="parent-2", agent_id="agent-abc", agent_type="Explore"
        )
        conn = connect(db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM subagent_runs").fetchone()[0]
        finally:
            conn.close()
        assert count == 2


class TestSubagentTreeAPI:
    """history_reader.subagent_tree / subagent_retries / subagent_budget."""

    def test_subagent_tree_returns_direct_children(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-a", agent_type="Explore"
        )
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-b", agent_type="codebase-locator"
        )
        record_subagent_run_start(
            db, parent_session_id="parent-2", agent_id="agent-c", agent_type="Explore"
        )
        tree = subagent_tree("parent-1", db=db)
        assert {r.agent_id for r in tree} == {"agent-a", "agent-b"}

    def test_subagent_tree_empty_for_missing_db(self, tmp_path: Path) -> None:
        assert subagent_tree("nobody", db=tmp_path / "missing.db") == []

    def test_subagent_retries_flags_repeat_spawns(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-a", agent_type="Explore"
        )
        record_subagent_run_start(
            db, parent_session_id="parent-1", agent_id="agent-b", agent_type="Explore"
        )
        record_subagent_run_start(
            db, parent_session_id="parent-2", agent_id="agent-c", agent_type="Explore"
        )
        rows = subagent_retries("Explore", db=db)
        assert len(rows) == 1
        assert rows[0]["parent_session_id"] == "parent-1"
        assert rows[0]["spawn_count"] == 2

    def test_subagent_budget_sums_duration(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db,
            parent_session_id="parent-1",
            agent_id="agent-a",
            agent_type="Explore",
            started_at="2026-07-20T00:00:00Z",
        )
        record_subagent_run_stop(
            db,
            parent_session_id="parent-1",
            agent_id="agent-a",
            ended_at="2026-07-20T00:01:00Z",
        )
        budget = subagent_budget("parent-1", db=db)
        assert budget is not None
        assert budget["spawn_count"] == 1
        assert budget["total_duration_s"] == pytest.approx(60.0, abs=0.01)

    def test_subagent_budget_none_when_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert subagent_budget("nobody", db=db) is None


class TestSubagentStartStopHookHandlers:
    """SubagentStart/SubagentStop host-agnostic handlers write via session_store."""

    def test_subagent_start_handler_writes_row(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="claude-code",
            intent="subagent_start",
            session_id="parent-1",
            payload={"agent_id": "agent-abc", "agent_type": "Explore"},
        )
        result = subagent_start_handle(event)
        assert result.exit_code == 0
        conn = connect(tmp_path / ".ll" / "history.db")
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["parent_session_id"] == "parent-1"
        assert row["status"] == "running"

    def test_subagent_stop_handler_updates_row(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        start_event = LLHookEvent(
            host="claude-code",
            intent="subagent_start",
            session_id="parent-1",
            payload={"agent_id": "agent-abc", "agent_type": "Explore"},
        )
        subagent_start_handle(start_event)
        stop_event = LLHookEvent(
            host="claude-code",
            intent="subagent_stop",
            session_id="parent-1",
            payload={
                "agent_id": "agent-abc",
                "agent_type": "Explore",
                "agent_transcript_path": "/tmp/parent-1/subagents/agent-abc.jsonl",
            },
        )
        result = subagent_stop_handle(stop_event)
        assert result.exit_code == 0
        conn = connect(tmp_path / ".ll" / "history.db")
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row["status"] == "completed"
        assert row["agent_transcript_path"] == "/tmp/parent-1/subagents/agent-abc.jsonl"

    def test_subagent_start_handler_missing_payload_is_best_effort(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(host="claude-code", intent="subagent_start", payload={})
        result = subagent_start_handle(event)
        assert result.exit_code == 0

    def test_subagent_stop_handler_missing_payload_is_best_effort(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(host="claude-code", intent="subagent_stop", payload={})
        result = subagent_stop_handle(event)
        assert result.exit_code == 0

    def test_subagent_start_handler_never_raises_on_store_failure(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        import little_loops.session_store as session_store

        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(session_store, "record_subagent_run_start", boom)
        event = LLHookEvent(
            host="claude-code",
            intent="subagent_start",
            session_id="parent-1",
            payload={"agent_id": "agent-abc", "agent_type": "Explore"},
        )
        result = subagent_start_handle(event)
        assert result.exit_code == 0


class TestBackfillSubagentRuns:
    """_backfill_subagent_runs() discovers nested subagents/*.jsonl transcripts."""

    def test_backfill_discovers_nested_transcripts(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        sessions_root = tmp_path / "sessions"
        subagents_dir = sessions_root / "parent-1" / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-abc.jsonl").write_text(
            json.dumps({"type": "assistant"}) + "\n", encoding="utf-8"
        )
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, sessions_root)
            conn.commit()
        finally:
            conn.close()
        assert count == 1
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["parent_session_id"] == "parent-1"
        assert row["status"] == "completed"

    def test_backfill_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        sessions_root = tmp_path / "sessions"
        subagents_dir = sessions_root / "parent-1" / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-abc.jsonl").write_text("{}\n", encoding="utf-8")
        conn = connect(db)
        try:
            _backfill_subagent_runs(conn, sessions_root)
            second_count = _backfill_subagent_runs(conn, sessions_root)
            conn.commit()
        finally:
            conn.close()
        assert second_count == 0

    def test_backfill_no_sessions_root_returns_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, tmp_path / "does-not-exist")
        finally:
            conn.close()
        assert count == 0
