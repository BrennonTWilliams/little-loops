"""Upgrade tests for raw source refresh after normalized payloads lost usage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.session_store import (
    _pack_payload,
    _unpack_payload,
    backfill_raw_events,
    connect,
    ensure_db,
    rebuild,
)
from little_loops.session_store.lifecycle import usage_source_freshness
from little_loops.session_store.sessions import SessionHandle
from little_loops.session_store.usage_refresh import refresh_raw_events


def _source(tmp_path: Path) -> tuple[Path, SessionHandle, Path]:
    db = tmp_path / "history.db"
    source = tmp_path / "session.jsonl"
    payload = {
        "type": "assistant",
        "version": "2.1.284",
        "sessionId": "s1",
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {
            "id": "m1",
            "model": "claude-sonnet-4-6",
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {
                "input_tokens": 3,
                "output_tokens": 5,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 11,
            },
        },
    }
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    handle = SessionHandle("claude-code", "s1", source, tmp_path, source.stat().st_mtime)
    ensure_db(db)
    assert backfill_raw_events(db, handles=[handle]) == 1
    return db, handle, source


def _remove_stored_usage(db: Path) -> None:
    conn = connect(db)
    try:
        row = conn.execute("SELECT raw_line FROM raw_events").fetchone()
        payload = json.loads(_unpack_payload(row[0]))
        del payload["message"]["usage"]
        packed = _pack_payload(json.dumps(payload))
        conn.execute(
            "UPDATE raw_events SET raw_line = ?, parsed_json = ?, usage_contract = NULL",
            (packed, packed),
        )
        conn.commit()
    finally:
        conn.close()


def test_refresh_recovers_stripped_usage_and_rebuild_is_stable(tmp_path: Path) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        raw_id = conn.execute("SELECT id FROM raw_events").fetchone()[0]
        stat = handle.path.stat()
        conn.execute(
            "INSERT INTO usage_source_cursors VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(handle.path),
                "claude-code",
                "s1",
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                1,
                "old-digest",
                stat.st_mtime_ns,
                raw_id,
                "complete",
                "2026-09-29T01:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, input_tokens, "
            "source_raw_event_id, source_path) VALUES(?, ?, ?, ?, ?, ?)",
            ("2026-09-29T01:00:00Z", "s1", "transcript", 1, raw_id, str(handle.path)),
        )
        conn.execute("INSERT INTO meta(key, value) VALUES('usage_derive_version', 'old')")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('usage_derive_raw_id', ?)", (str(raw_id),)
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, input_tokens) "
            "VALUES('2026-09-29T01:01:00Z', 'live-only', 'live', 99)"
        )
        conn.commit()
    finally:
        conn.close()

    refreshed = refresh_raw_events(db, handles=[handle])
    assert refreshed.needs_rebuild
    assert refreshed.sources[0].status == "refreshed"
    assert refreshed.sources[0].rows == 1
    conn = connect(db)
    try:
        raw = json.loads(
            _unpack_payload(conn.execute("SELECT raw_line FROM raw_events").fetchone()[0])
        )
        assert raw["message"]["usage"]["cache_read_input_tokens"] == 7
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM usage_source_cursors").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'usage_derive_%'").fetchone()[0]
            == 0
        )
    finally:
        conn.close()
    assert usage_source_freshness(db, handle.path)["status"] == "unknown"

    query = (
        "SELECT session_id, channel, provenance, input_tokens, output_tokens, "
        "cache_read_input_tokens, cache_creation_input_tokens, host_basis "
        "FROM usage_events ORDER BY channel"
    )
    rebuild(db)
    conn = connect(db)
    try:
        first = [tuple(row) for row in conn.execute(query)]
        raw_id = conn.execute("SELECT id FROM raw_events").fetchone()[0]
    finally:
        conn.close()
    assert ("live-only", "live", None, 99, None, None, None, None) in first
    assert ("s1", "transcript", "measured", 3, 5, 7, 11, "handle") in first

    repeat = refresh_raw_events(db, handles=[handle])
    assert not repeat.needs_rebuild
    assert repeat.sources[0].status == "unchanged"
    rebuild(db)
    conn = connect(db)
    try:
        assert [tuple(row) for row in conn.execute(query)] == first
        assert conn.execute("SELECT id FROM raw_events").fetchone()[0] == raw_id
    finally:
        conn.close()


def test_missing_original_retains_unknown_coverage(tmp_path: Path) -> None:
    db, handle, source = _source(tmp_path)
    _remove_stored_usage(db)
    source.unlink()
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].reason == "original_missing"
    assert not result.needs_rebuild
    rebuild(db)
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    finally:
        conn.close()


def test_refresh_rejects_unverified_host_and_compacted_rows(tmp_path: Path) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        conn.execute("UPDATE raw_events SET host_basis = NULL")
        conn.commit()
    finally:
        conn.close()
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].reason == "unverified_host_attribution"
    conn = connect(db)
    try:
        row = conn.execute("SELECT host_basis, raw_line FROM raw_events").fetchone()
        assert row[0] is None
        assert "usage" not in json.loads(_unpack_payload(row[1]))["message"]
        conn.execute("UPDATE raw_events SET host_basis = 'handle', compacted = 1")
        conn.commit()
    finally:
        conn.close()
    assert refresh_raw_events(db, handles=[handle]).sources[0].reason == "compacted_source"


def test_failed_reingestion_rolls_back_existing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        original = conn.execute("SELECT id, raw_line FROM raw_events").fetchone()
    finally:
        conn.close()

    def fail_after_delete(*_args: object) -> int:
        raise RuntimeError("parser failed")

    monkeypatch.setattr(
        "little_loops.session_store.lifecycle._backfill_raw_events", fail_after_delete
    )
    with pytest.raises(RuntimeError, match="parser failed"):
        refresh_raw_events(db, handles=[handle])
    conn = connect(db)
    try:
        assert conn.execute("SELECT id, raw_line FROM raw_events").fetchone() == original
    finally:
        conn.close()


def test_no_parsed_events_and_duplicate_paths_are_refused(tmp_path: Path) -> None:
    db, handle, source = _source(tmp_path)
    _remove_stored_usage(db)
    with pytest.raises(ValueError, match="duplicate source path"):
        refresh_raw_events(db, handles=[handle, handle])
    source.write_text("not-json\n", encoding="utf-8")
    assert refresh_raw_events(db, handles=[handle]).sources[0].reason == "no_parsed_events"
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 1
    finally:
        conn.close()


def test_refresh_refuses_parser_output_that_drops_existing_fields(tmp_path: Path) -> None:
    db, handle, source = _source(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["message"]["usage"]
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].reason == "existing_payload_not_preserved"
    assert not result.needs_rebuild
    conn = connect(db)
    try:
        stored = json.loads(
            _unpack_payload(conn.execute("SELECT raw_line FROM raw_events").fetchone()[0])
        )
        assert stored["message"]["usage"]["input_tokens"] == 3
    finally:
        conn.close()
