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


def _usage_obs(db: Path, handle: SessionHandle, values: tuple) -> None:
    conn = connect(db)
    try:
        raw_id = conn.execute("SELECT id FROM raw_events").fetchone()[0]
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, host, host_basis, channel, "
            "provenance, input_tokens, output_tokens, cache_read_input_tokens, "
            "cache_creation_input_tokens, source_raw_event_id, source_path, source_line_no) "
            "VALUES('2026-09-29T01:00:00Z', 's1', 'claude-sonnet-4-6', 'claude-code', 'handle', "
            "'transcript', 'unknown', ?, ?, ?, ?, ?, ?, 1)",
            (*values, raw_id, str(handle.path)),
        )
        conn.commit()
    finally:
        conn.close()


def test_unchanged_retry_keeps_reporting_committed_work_in_json_and_text(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db, _ = _prepared(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--session-id", "s1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["needs_rebuild"] is True
    # A crash or skipped rebuild leaves durable pending work: an unchanged retry replaced no
    # raw row, yet still reports it -- through the API and through both CLI renderings.
    assert _run(db, ["--host", "claude-code", "--session-id", "s1", "--json"]) == 0
    retry = json.loads(capsys.readouterr().out)
    assert retry["sources"][0]["status"] == "unchanged" and retry["needs_rebuild"] is True
    assert _run(db, ["--host", "claude-code", "--session-id", "s1"]) == 0
    assert "Run ll-session rebuild" in capsys.readouterr().out


def test_rebuild_counts_never_suppress_unresolved_usage(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db, handle = _prepared(tmp_path)
    _usage_obs(db, handle, (1, 5, 7, 11))  # contradicts the original (input 3): stays protected
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--all", "--rebuild", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["rebuild_counts"] is not None
    assert result["needs_rebuild"] is True  # counts did not prove resolution
    assert _run(db, ["--host", "claude-code", "--all", "--rebuild"]) == 0
    text = capsys.readouterr().out
    assert "Rebuilt usage and cache tables" not in text
    assert "remains pending after rebuild" in text


def test_full_resolution_permits_the_success_message(tmp_path: Path, monkeypatch, capsys) -> None:
    db, _ = _prepared(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--all", "--rebuild"]) == 0
    assert "Rebuilt usage and cache tables" in capsys.readouterr().out
    assert _run(db, ["--host", "claude-code", "--all", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["needs_rebuild"] is False


def test_skipped_requested_source_with_prior_pending_still_reports_the_work(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db, handle = _prepared(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _run(db, ["--host", "claude-code", "--session-id", "s1"]) == 0
    capsys.readouterr()
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json) "
            "VALUES('2026-09-29T01:05:00Z', 'other', 'claude-code', 'handle', ?, 2, 'user', "
            "'{}', '{}')",
            (str(handle.path),),
        )
        conn.commit()
    finally:
        conn.close()
    assert _run(db, ["--host", "claude-code", "--all", "--json"]) == 1  # ambiguous: skipped
    result = json.loads(capsys.readouterr().out)
    assert result["sources"][0]["reason"] == "ambiguous_session_attribution"
    assert result["needs_rebuild"] is True  # no new handle replayed, the work is not omitted
