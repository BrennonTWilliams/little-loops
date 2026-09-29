"""ll-session refresh command for verified stored originals (ENH-3534)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.session import main_session
from little_loops.session_store import (
    SessionHandle,
    _pack_payload,
    _unpack_payload,
    backfill_raw_events,
    connect,
    ensure_db,
)


def _prepared(tmp_path: Path) -> tuple[Path, SessionHandle]:
    source = tmp_path / "session.jsonl"
    record = {
        "type": "assistant",
        "version": "2.1.284",
        "sessionId": "s1",
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {
            "id": "m1",
            "model": "claude-sonnet-4-6",
            "role": "assistant",
            "content": [],
            "usage": {
                "input_tokens": 3,
                "output_tokens": 5,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 11,
            },
        },
    }
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")
    handle = SessionHandle("claude-code", "s1", source, tmp_path, source.stat().st_mtime)
    db = tmp_path / "history.db"
    ensure_db(db)
    assert backfill_raw_events(db, handles=[handle]) == 1
    conn = connect(db)
    try:
        del record["message"]["usage"]
        packed = _pack_payload(json.dumps(record))
        conn.execute(
            "UPDATE raw_events SET raw_line = ?, parsed_json = ?, usage_contract = NULL",
            (packed, packed),
        )
        conn.commit()
    finally:
        conn.close()
    return db, handle


def _run(db: Path, args: list[str]) -> int:
    with patch("sys.argv", ["ll-session", "--db", str(db), "refresh", *args]):
        return main_session()


def test_refresh_requires_explicit_host_and_scope(tmp_path: Path, monkeypatch, capsys) -> None:
    db, _ = _prepared(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--all"]) == 1
    assert "requires --host" in capsys.readouterr().err
    assert _run(db, ["--host", "claude-code"]) == 1
    assert "exactly one" in capsys.readouterr().err
    assert _run(db, ["--host", "claude-code", "--all", "--session-id", "s1"]) == 1


def test_refresh_from_original_and_rebuild_on_request(tmp_path: Path, monkeypatch, capsys) -> None:
    db, handle = _prepared(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--session-id", "s1", "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["sources"][0]["status"] == "refreshed"
    assert first["needs_rebuild"] is True
    conn = connect(db)
    try:
        raw = json.loads(
            _unpack_payload(conn.execute("SELECT raw_line FROM raw_events").fetchone()[0])
        )
        assert raw["message"]["usage"]["cache_read_input_tokens"] == 7
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    finally:
        conn.close()

    assert _run(db, ["--host", "claude-code", "--all", "--rebuild", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["sources"][0]["status"] == "unchanged"
    assert second["needs_rebuild"] is False
    assert second["rebuild_counts"]["usage_events"] == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT input_tokens FROM usage_events").fetchone()[0] == 3
    finally:
        conn.close()
    assert handle.path.exists()


def test_missing_original_reports_skip_without_data_loss(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db, handle = _prepared(tmp_path)
    handle.path.unlink()
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--session-id", "s1", "--json"]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["sources"][0]["reason"] == "original_missing"
    assert "original_missing" in captured.err
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 1
    finally:
        conn.close()


def test_legacy_host_rows_are_not_blanket_certified(tmp_path: Path, monkeypatch, capsys) -> None:
    db, _ = _prepared(tmp_path)
    conn = connect(db)
    try:
        conn.execute("UPDATE raw_events SET host_basis = NULL")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--all"]) == 1
    assert "No verified stored sources" in capsys.readouterr().err
    conn = connect(db)
    try:
        assert conn.execute("SELECT host_basis FROM raw_events").fetchone()[0] is None
    finally:
        conn.close()
