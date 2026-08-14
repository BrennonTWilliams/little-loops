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
    subagent_layout_for,
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
        (session_dir / f"{stem}.meta.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
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
            count = _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
            _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
            count = _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
            count = _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
            count = _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM subagent_runs").fetchone()[0]
        finally:
            conn.close()
        assert count == 0
        assert total == 1

    def test_sidecar_parent_session_id_preferred_over_dir_name(
        self, tmp_path: Path
    ) -> None:
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
            _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
            count = _backfill_subagent_runs(conn, root, layout=subagent_layout_for("qwen"))
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
                conn, sessions_root, layout=subagent_layout_for("claude-code")
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
