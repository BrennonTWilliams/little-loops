"""ENH-3543: exported usage surfaces preserve selector coverage and privacy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from little_loops.session_store import ensure_db
from little_loops.session_store.queries import _SHAREABLE_COLUMNS, build_snapshot_db

_SENSITIVE_PATH = "/private/snapshot-source-sentinel.jsonl"
_SENSITIVE_TURN = "native-turn-sentinel"
_SENSITIVE_REQUEST = "native-request-sentinel"


def _source_db(tmp_path: Path) -> Path:
    db = tmp_path / "history.db"
    ensure_db(db)
    columns = (
        "ts",
        "session_id",
        "model",
        "host",
        "host_basis",
        "channel",
        "identity_basis",
        "scope_kind",
        "request_identity_basis",
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "cost_usd",
        "provenance",
        "source_path",
        "turn_id",
        "request_id",
    )

    def insert(
        conn: sqlite3.Connection,
        *,
        ts: str = "2026-09-29T10:00:00Z",
        session: str,
        model: str,
        host: str,
        channel: str,
        input_tokens: int,
        cost: float | None,
        scope: str | None = None,
    ) -> None:
        values = (
            ts,
            session,
            model,
            host,
            "handle" if channel != "live" else None,
            channel,
            "host_observed" if host == "codex" else None,
            scope,
            "native_response" if channel == "rollout" else None,
            input_tokens,
            2,
            1,
            0,
            cost,
            "measured",
            _SENSITIVE_PATH,
            _SENSITIVE_TURN,
            _SENSITIVE_REQUEST,
        )
        conn.execute(
            f"INSERT INTO usage_events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            values,
        )

    with sqlite3.connect(db) as conn:
        # Two verified channels for one Codex thread cannot be joined to a
        # native request. The earlier row still governs a later --since export.
        insert(
            conn,
            ts="2026-09-28T10:00:00Z",
            session="partial-thread",
            model="partial-model",
            host="codex",
            channel="live",
            input_tokens=10,
            cost=0.10,
            scope="invocation",
        )
        insert(
            conn,
            session="partial-thread",
            model="partial-model",
            host="codex",
            channel="rollout",
            input_tokens=11,
            cost=0.20,
        )
        # A qualified row for the same model remains visible as a known
        # subtotal, while the model-wide canonical total remains unavailable.
        insert(
            conn,
            session="claude-partial",
            model="partial-model",
            host="claude-code",
            channel="transcript",
            input_tokens=5,
            cost=0.05,
        )
        # Qualified independent channels can be selected; missing cost in one
        # channel must keep the entire model's canonical cost NULL.
        insert(
            conn,
            session="claude-known",
            model="known-model",
            host="claude-code",
            channel="transcript",
            input_tokens=7,
            cost=0.07,
        )
        insert(
            conn,
            session="rollout-known",
            model="known-model",
            host="codex",
            channel="rollout",
            input_tokens=8,
            cost=None,
        )
        insert(
            conn,
            session="rollout-complete",
            model="complete-model",
            host="codex",
            channel="rollout",
            input_tokens=12,
            cost=0.12,
        )
        insert(
            conn,
            session="live-unknown",
            model="unknown-model",
            host="codex",
            channel="live",
            input_tokens=9,
            cost=0.09,
            scope="unknown",
        )
    return db


def _snapshot(db: Path, dest: Path, *, since: str | None = None) -> sqlite3.Connection:
    build_snapshot_db(db, dest, tables=["usage_event"], since=since)
    return sqlite3.connect(dest)


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def test_shareable_snapshot_keeps_known_rows_and_audit_without_claiming_overlap(
    tmp_path: Path,
) -> None:
    db = _source_db(tmp_path)
    dest = tmp_path / "shareable.db"
    with _snapshot(db, dest) as conn:
        raw = _rows(conn, "usage_events")
        selected = _rows(conn, "selected_usage_events")
        audit = _rows(conn, "usage_coverage_audit")
        schemas = {
            table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for table in ("usage_events", "selected_usage_events", "usage_coverage_audit")
        }
        assert [
            row[1] for row in conn.execute("PRAGMA table_info(selected_usage_events)")
        ] == _SHAREABLE_COLUMNS["selected_usage_events"]
        assert [
            row[1] for row in conn.execute("PRAGMA table_info(usage_coverage_audit)")
        ] == _SHAREABLE_COLUMNS["usage_coverage_audit"]

    assert len(raw) == 7
    assert {(row["model"], row["channel"]) for row in selected} == {
        ("partial-model", "transcript"),
        ("known-model", "transcript"),
        ("known-model", "rollout"),
        ("complete-model", "rollout"),
    }
    assert all(row["coverage"] == "non_overlapping" for row in selected)

    by_key = {(row["model"], row["channel"]): row for row in audit}
    partial = [row for row in audit if row["model"] == "partial-model"]
    assert {row["channel"] for row in partial} == {"live", "rollout", "transcript"}
    assert all(row["coverage"] == "overlap_unresolved" for row in partial)
    assert all(row["canonical_input_tokens"] is None for row in partial)
    assert all(row["canonical_cost_usd"] is None for row in partial)
    assert by_key["partial-model", "transcript"]["known_input_tokens"] == 5
    assert by_key["partial-model", "live"]["raw_input_tokens"] == 10
    assert by_key["partial-model", "rollout"]["raw_input_tokens"] == 11
    assert by_key["known-model", "transcript"]["canonical_input_tokens"] == 7
    assert by_key["known-model", "rollout"]["canonical_input_tokens"] == 8
    assert by_key["known-model", "transcript"]["known_cost_usd"] == 0.07
    assert by_key["known-model", "transcript"]["canonical_cost_usd"] is None
    assert by_key["known-model", "rollout"]["canonical_cost_usd"] is None
    assert by_key["complete-model", "rollout"]["canonical_cost_usd"] == 0.12
    assert by_key["unknown-model", "live"]["coverage"] == "unknown"
    assert by_key["unknown-model", "live"]["selected_observation_count"] == 0
    assert by_key["unknown-model", "live"]["canonical_cost_usd"] is None

    forbidden = {"source_path", "turn_id", "request_id", "source_raw_event_id"}
    assert all(not forbidden.intersection(columns) for columns in schemas.values())
    snapshot_bytes = dest.read_bytes()
    for sentinel in (_SENSITIVE_PATH, _SENSITIVE_TURN, _SENSITIVE_REQUEST):
        assert sentinel.encode() not in snapshot_bytes


def test_since_window_keeps_full_source_coverage_classification(tmp_path: Path) -> None:
    db = _source_db(tmp_path)
    with _snapshot(db, tmp_path / "window.db", since="2026-09-29T00:00:00Z") as conn:
        audit = _rows(conn, "usage_coverage_audit")
        selected = _rows(conn, "selected_usage_events")
        raw = _rows(conn, "usage_events")

    by_key = {(row["model"], row["channel"]): row for row in audit}
    assert ("partial-model", "live") not in by_key
    rollout = by_key["partial-model", "rollout"]
    assert rollout["raw_observation_count"] == 1
    assert rollout["coverage"] == "overlap_unresolved"
    assert rollout["canonical_input_tokens"] is None
    assert not any(
        row["model"] == "partial-model" and row["channel"] == "rollout" for row in selected
    )
    assert not any(row["model"] == "partial-model" and row["channel"] == "live" for row in raw)


def test_loop_only_snapshot_does_not_create_usage_surfaces(tmp_path: Path) -> None:
    db = _source_db(tmp_path)
    dest = tmp_path / "loop-only.db"
    build_snapshot_db(db, dest, tables=["loop_run"])
    with sqlite3.connect(dest) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert names == {"loop_runs"}
