"""ENH-2505: subagent spawn-tree linkage in ``.ll/history.db``.

Covers the ``subagent_runs`` table writers (``record_subagent_run_start`` /
``record_subagent_run_stop``), the ``SubagentStart``/``SubagentStop`` hook
handlers, the ``history_reader`` tree/retries/budget helpers, and backfill
from nested subagent transcripts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.history_reader import subagent_budget, subagent_retries, subagent_tree
from little_loops.hooks.subagent_start import handle as subagent_start_handle
from little_loops.hooks.subagent_stop import handle as subagent_stop_handle
from little_loops.hooks.types import LLHookEvent
from little_loops.session_store import (
    _backfill_subagent_runs,
    connect,
    ensure_db,
    host_layout_for,
    reconcile_stale_subagent_runs,
    record_subagent_run_start,
    record_subagent_run_stop,
    writers,
)
from little_loops.session_store.writers import STALE_SUBAGENT_MIN_AGE_SECONDS


def _ts(offset_seconds: float) -> str:
    """A ``_now()``-formatted timestamp *offset_seconds* from the real current time."""
    return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_tool_event(db: Path, session_id: str, ts: str) -> None:
    conn = connect(db)
    try:
        conn.execute("INSERT INTO tool_events(ts, session_id) VALUES (?, ?)", (ts, session_id))
        conn.commit()
    finally:
        conn.close()


def _row_status(db: Path, agent_id: str) -> str | None:
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT status FROM subagent_runs WHERE agent_id = ?", (agent_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["status"] if row else None


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


class TestKimiSubagentPayloadTolerance:
    """FEAT-2915: kimi-code sends ``agent_name`` (the type label) and no
    ``agent_id``; SubagentStop carries the full result text as ``response``
    instead of ``agent_transcript_path``.

    Verified shapes (thoughts/research/kimi-cli-surface.md, kimi 0.30.0):
    SubagentStart ``{agent_name, prompt}``; SubagentStop ``{agent_name,
    response}``. Because kimi has no per-instance ``agent_id``, the writers
    no-op — the ``agent_type`` fallback is what these tests pin down.
    """

    def test_kimi_start_agent_name_fallback_no_crash(self, tmp_path: Path, monkeypatch) -> None:
        """kimi-shaped SubagentStart (agent_name, no agent_id) is a clean no-op."""
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="kimi-code",
            intent="subagent_start",
            session_id="parent-1",
            payload={"agent_name": "coder", "prompt": "fix the bug"},
        )
        result = subagent_start_handle(event)
        assert result.exit_code == 0
        # No agent_id → no row (the writers no-op on a missing agent_id).
        db = tmp_path / ".ll" / "history.db"
        if db.exists():
            conn = connect(db)
            try:
                count = conn.execute("SELECT COUNT(*) FROM subagent_runs").fetchone()[0]
            finally:
                conn.close()
            assert count == 0

    def test_kimi_stop_response_fallback_no_crash(self, tmp_path: Path, monkeypatch) -> None:
        """kimi-shaped SubagentStop (agent_name + response, no agent_id) is a clean no-op."""
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="kimi-code",
            intent="subagent_stop",
            session_id="parent-1",
            payload={"agent_name": "coder", "response": "fixed the bug"},
        )
        result = subagent_stop_handle(event)
        assert result.exit_code == 0

    def test_agent_name_used_as_type_when_agent_id_present(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The agent_name → agent_type fallback applies when a row can be written."""
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="kimi-code",
            intent="subagent_start",
            session_id="parent-1",
            payload={"agent_id": "agent-xyz", "agent_name": "coder"},
        )
        result = subagent_start_handle(event)
        assert result.exit_code == 0
        conn = connect(tmp_path / ".ll" / "history.db")
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-xyz'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row["agent_type"] == "coder"

    def test_response_surfaces_via_transcript_field_when_agent_id_present(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """kimi's ``response`` text lands in agent_transcript_path on the stop row."""
        monkeypatch.chdir(tmp_path)
        subagent_start_handle(
            LLHookEvent(
                host="kimi-code",
                intent="subagent_start",
                session_id="parent-1",
                payload={"agent_id": "agent-xyz", "agent_name": "coder"},
            )
        )
        result = subagent_stop_handle(
            LLHookEvent(
                host="kimi-code",
                intent="subagent_stop",
                session_id="parent-1",
                payload={"agent_id": "agent-xyz", "agent_name": "coder", "response": "done"},
            )
        )
        assert result.exit_code == 0
        conn = connect(tmp_path / ".ll" / "history.db")
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-xyz'"
            ).fetchone()
        finally:
            conn.close()
        assert row["status"] == "completed"
        assert row["agent_type"] == "coder"
        assert row["agent_transcript_path"] == "done"

    def test_claude_fields_still_preferred(self, tmp_path: Path, monkeypatch) -> None:
        """Regression guard: claude's agent_type/agent_transcript_path win when present."""
        monkeypatch.chdir(tmp_path)
        subagent_start_handle(
            LLHookEvent(
                host="claude-code",
                intent="subagent_start",
                session_id="parent-1",
                payload={"agent_id": "agent-abc", "agent_type": "Explore"},
            )
        )
        subagent_stop_handle(
            LLHookEvent(
                host="claude-code",
                intent="subagent_stop",
                session_id="parent-1",
                payload={
                    "agent_id": "agent-abc",
                    "agent_type": "Explore",
                    "agent_name": "should-not-win",
                    "agent_transcript_path": "/tmp/t.jsonl",
                    "response": "should-not-win",
                },
            )
        )
        conn = connect(tmp_path / ".ll" / "history.db")
        try:
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert row["agent_type"] == "Explore"
        assert row["agent_transcript_path"] == "/tmp/t.jsonl"


# Modeled on a real qwen 0.21.6 sidecar (~/.qwen/projects/<encoded>/subagents/
# <session-id>/agent-*.meta.json): camelCase keys, file stem carries an extra
# "agent-" prefix the sidecar's agentId does not.
_QWEN_SESSION_ID = "cd4599f4-e1af-4d50-9b24-da04c4737edb"
_QWEN_STEM = "agent-Explore-call_2ef9d7cca532405b9e723bb0"
_QWEN_AGENT_ID = "Explore-call_2ef9d7cca532405b9e723bb0"


def _qwen_sidecar(**overrides: object) -> dict:
    sidecar = {
        "agentId": _QWEN_AGENT_ID,
        "agentType": "Explore",
        "description": "Map figure-to-rig toolchain",
        "parentSessionId": _QWEN_SESSION_ID,
        "toolUseId": "call_2ef9d7cca532405b9e723bb0",
        "parentAgentId": None,
        "createdAt": "2026-08-13T23:01:41.299Z",
        "lastUpdatedAt": "2026-08-13T23:05:44.318Z",
        "status": "completed",
        "depth": 0,
    }
    sidecar.update(overrides)
    return sidecar


def _build_qwen_tree(
    root: Path,
    *,
    session_id: str = _QWEN_SESSION_ID,
    stem: str = _QWEN_STEM,
    sidecar: dict | None = None,
    sidecar_text: str | None = None,
) -> Path:
    """Create ``<root>/subagents/<session-id>/<stem>.jsonl`` (+ optional sidecar)."""
    session_dir = root / "subagents" / session_id
    session_dir.mkdir(parents=True)
    transcript = session_dir / f"{stem}.jsonl"
    transcript.write_text(json.dumps({"type": "model"}) + "\n", encoding="utf-8")
    if sidecar_text is not None:
        (session_dir / f"{stem}.meta.json").write_text(sidecar_text, encoding="utf-8")
    elif sidecar is not None:
        (session_dir / f"{stem}.meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return transcript


class TestQwenSubagentBackfill:
    """ENH-3165: qwen inverts the nesting (``subagents/<session-id>/agent-*.jsonl``)
    and every transcript carries a ``.meta.json`` sidecar that is strictly better
    than the Claude mtime heuristic — real status and timestamps included."""

    def test_backfill_populates_row_from_sidecar(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        transcript = _build_qwen_tree(root, sidecar=_qwen_sidecar())
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
        finally:
            conn.close()
        assert count == 1
        conn = connect(db)
        try:
            row = conn.execute("SELECT * FROM subagent_runs").fetchone()
        finally:
            conn.close()
        # agent_id comes from the sidecar verbatim — NOT the filename stem.
        assert row["agent_id"] == _QWEN_AGENT_ID
        assert row["agent_type"] == "Explore"
        assert row["parent_session_id"] == _QWEN_SESSION_ID
        assert row["started_at"] == "2026-08-13T23:01:41.299Z"
        assert row["ended_at"] == "2026-08-13T23:05:44.318Z"
        assert row["status"] == "completed"
        assert row["agent_transcript_path"] == str(transcript)

    def test_failed_sidecar_status_lands_as_failed(self, tmp_path: Path) -> None:
        """A persisted transcript does NOT imply completion on qwen."""
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        _build_qwen_tree(root, sidecar=_qwen_sidecar(status="failed"))
        conn = connect(db)
        try:
            _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
            row = conn.execute("SELECT * FROM subagent_runs").fetchone()
        finally:
            conn.close()
        assert row["status"] == "failed"

    def test_missing_sidecar_falls_back_to_mtime(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        _build_qwen_tree(root)  # no sidecar
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
            row = conn.execute("SELECT * FROM subagent_runs").fetchone()
        finally:
            conn.close()
        assert count == 1
        assert row["agent_id"] == _QWEN_STEM  # filename stem, Claude-style
        assert row["status"] == "completed"
        assert row["started_at"] == row["ended_at"]
        assert row["started_at"] is not None

    def test_unparseable_sidecar_falls_back_to_mtime(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        _build_qwen_tree(root, sidecar_text="{not json")
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
            row = conn.execute("SELECT * FROM subagent_runs").fetchone()
        finally:
            conn.close()
        assert count == 1
        assert row["agent_id"] == _QWEN_STEM
        assert row["status"] == "completed"

    def test_live_capture_then_backfill_inserts_no_duplicates(self, tmp_path: Path) -> None:
        """Backfill must derive the same agent_id the FEAT-3158 live hooks record."""
        db = tmp_path / "history.db"
        record_subagent_run_start(
            db,
            parent_session_id=_QWEN_SESSION_ID,
            agent_id=_QWEN_AGENT_ID,
            agent_type="Explore",
        )
        root = tmp_path / "project"
        _build_qwen_tree(root, sidecar=_qwen_sidecar())
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM subagent_runs").fetchone()[0]
        finally:
            conn.close()
        assert count == 0
        assert total == 1

    def test_sidecar_parent_session_id_preferred_over_dir_name(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        _build_qwen_tree(
            root,
            session_id="dir-name-session",
            sidecar=_qwen_sidecar(parentSessionId="sidecar-session"),
        )
        conn = connect(db)
        try:
            _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
            row = conn.execute("SELECT * FROM subagent_runs").fetchone()
        finally:
            conn.close()
        assert row["parent_session_id"] == "sidecar-session"

    def test_parent_agent_id_in_sidecar_is_tolerated(self, tmp_path: Path) -> None:
        """Nested spawn trees carry parentAgentId; no subagent_runs column exists
        for it yet, but it must not break ingestion."""
        db = tmp_path / "history.db"
        ensure_db(db)
        root = tmp_path / "project"
        _build_qwen_tree(
            root,
            sidecar=_qwen_sidecar(parentAgentId="Explore-call_outer", depth=1),
        )
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(conn, root, layout=host_layout_for("qwen"))
            conn.commit()
        finally:
            conn.close()
        assert count == 1

    def test_claude_layout_explicit_matches_default(self, tmp_path: Path) -> None:
        """Regression: the explicit claude-code layout is the None-layout behavior."""
        db = tmp_path / "history.db"
        ensure_db(db)
        sessions_root = tmp_path / "sessions"
        subagents_dir = sessions_root / "parent-1" / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-abc.jsonl").write_text("{}\n", encoding="utf-8")
        conn = connect(db)
        try:
            count = _backfill_subagent_runs(
                conn, sessions_root, layout=host_layout_for("claude-code")
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM subagent_runs WHERE agent_id = 'agent-abc'"
            ).fetchone()
        finally:
            conn.close()
        assert count == 1
        assert row["parent_session_id"] == "parent-1"
        assert row["status"] == "completed"


class TestReconcileStaleSubagentRuns:
    """ENH-3210: reconciling orphaned ``running`` rows to ``orphaned``."""

    def test_primary_branch_reconciles_old_row_with_no_post_spawn_activity(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="dead-parent",
            agent_id="agent-orphan",
            agent_type="Explore",
            started_at=old_started,
        )
        count = reconcile_stale_subagent_runs(db, current_session_id=None)
        assert count == 1
        assert _row_status(db, "agent-orphan") == "orphaned"

    def test_secondary_branch_within_quiet_period_is_not_reconciled(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="active-parent",
            agent_id="agent-active",
            agent_type="Explore",
            started_at=old_started,
        )
        # Parent shows later activity, but within the last hour — still quiet
        # for less than the shared window, so this must NOT be reconciled.
        _insert_tool_event(db, "active-parent", _ts(-1800))
        count = reconcile_stale_subagent_runs(db, current_session_id=None, include_secondary=True)
        assert count == 0
        assert _row_status(db, "agent-active") == "running"

    def test_current_session_is_never_reconciled(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="me",
            agent_id="agent-mine",
            agent_type="Explore",
            started_at=old_started,
        )
        count = reconcile_stale_subagent_runs(db, current_session_id="me")
        assert count == 0
        assert _row_status(db, "agent-mine") == "running"

    def test_fresh_sibling_worker_row_is_not_reconciled(self, tmp_path: Path) -> None:
        """The ll-parallel/ll-sprint concurrency hazard: a subagent spawned
        seconds ago in a sibling session has the primary branch's exact
        signature (blocked parent, no post-spawn activity, not the current
        session) — the age guard is what keeps it from being misclassified.
        """
        db = tmp_path / "history.db"
        fresh_started = _ts(0)
        record_subagent_run_start(
            db,
            parent_session_id="sibling-worker",
            agent_id="agent-fresh",
            agent_type="Explore",
            started_at=fresh_started,
        )
        count = reconcile_stale_subagent_runs(db, current_session_id="current-worker")
        assert count == 0
        assert _row_status(db, "agent-fresh") == "running"

    def test_none_current_session_id_only_drops_the_exclusion(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="some-session",
            agent_id="agent-null-session",
            agent_type="Explore",
            started_at=old_started,
        )
        count = reconcile_stale_subagent_runs(db, current_session_id=None)
        assert count == 1
        assert _row_status(db, "agent-null-session") == "orphaned"

    def test_second_sweep_is_idempotent_noop(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="dead-parent",
            agent_id="agent-orphan",
            agent_type="Explore",
            started_at=old_started,
        )
        first = reconcile_stale_subagent_runs(db, current_session_id=None)
        second = reconcile_stale_subagent_runs(db, current_session_id=None)
        assert first == 1
        assert second == 0
        assert _row_status(db, "agent-orphan") == "orphaned"

    def test_completed_row_is_never_touched(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="dead-parent",
            agent_id="agent-done",
            agent_type="Explore",
            started_at=old_started,
        )
        record_subagent_run_stop(db, parent_session_id="dead-parent", agent_id="agent-done")
        count = reconcile_stale_subagent_runs(db, current_session_id=None)
        assert count == 0
        assert _row_status(db, "agent-done") == "completed"

    def test_zero_running_rows_short_circuits_before_tool_events_query(
        self, tmp_path: Path
    ) -> None:
        # sqlite3.Connection is a C type — its methods can't be patched
        # directly, so trace calls through a thin wrapper around the real
        # connection instead.
        db = tmp_path / "history.db"
        ensure_db(db)
        _insert_tool_event(db, "some-session", _ts(0))

        executed_sql: list[str] = []
        real_connect = writers._pkg.connect

        class _TracingConnection:
            def __init__(self, conn: sqlite3.Connection) -> None:
                self._conn = conn

            def execute(self, sql: str, *args: object, **kwargs: object):
                executed_sql.append(sql)
                return self._conn.execute(sql, *args, **kwargs)

            def commit(self) -> None:
                self._conn.commit()

            def close(self) -> None:
                self._conn.close()

        def fake_connect(path: Path | str) -> _TracingConnection:
            return _TracingConnection(real_connect(path))

        with patch.object(writers._pkg, "connect", fake_connect):
            count = reconcile_stale_subagent_runs(db, current_session_id=None)

        assert count == 0
        assert not any("tool_events" in sql for sql in executed_sql)

    def test_dry_run_selects_without_mutating(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        old_started = _ts(-(STALE_SUBAGENT_MIN_AGE_SECONDS + 3600))
        record_subagent_run_start(
            db,
            parent_session_id="dead-parent",
            agent_id="agent-orphan",
            agent_type="Explore",
            started_at=old_started,
        )
        count = reconcile_stale_subagent_runs(db, current_session_id=None, dry_run=True)
        assert count == 1
        assert _row_status(db, "agent-orphan") == "running"

        # A negative case with dry_run=False exercises the real UPDATE path
        # against a row that must not match.
        real_count = reconcile_stale_subagent_runs(
            db, current_session_id="dead-parent", dry_run=False
        )
        assert real_count == 0
        assert _row_status(db, "agent-orphan") == "running"
