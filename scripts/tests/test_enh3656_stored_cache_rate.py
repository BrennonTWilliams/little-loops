"""Claude cache-rate cutover: stored selection, correction, and freshness."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.ctx_stats import (
    _compute_cache_rate_from_jsonl,
    _compute_cache_rate_from_usage,
    main_ctx_stats,
)
from little_loops.session_store import SessionHandle, connect, ensure_db
from little_loops.session_store.lifecycle import refresh_usage_source

_CAPTURE = Path(__file__).parent / "fixtures" / "claude" / "transcript-v2.1.284.jsonl"
_CHANGING = (
    Path(__file__).parent / "fixtures" / "claude" / "transcript-changing-usage-observed.jsonl"
)


def _captured_session(tmp_path: Path) -> tuple[Path, SessionHandle]:
    source = tmp_path / "session.jsonl"
    shutil.copyfile(_CAPTURE, source)
    session_id = json.loads(source.read_text(encoding="utf-8").splitlines()[0])["sessionId"]
    handle = SessionHandle("claude-code", session_id, source, tmp_path, source.stat().st_mtime)
    db = tmp_path / "history.db"
    ensure_db(db)
    return db, handle


def test_captured_duplicate_uuids_correct_to_two_native_requests(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        direct = _compute_cache_rate_from_jsonl(tmp_path, "claude-code")
    assert direct is not None
    assert direct["cache_read"] == 76858
    assert direct["cache_write"] == 22446
    assert direct["uncached"] == 36
    assert direct["counts"]["hit_rate_pct"] == {"known": 4, "missing": 0}

    assert refresh_usage_source(db, handle.path)["usage_events"] == 2
    stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stored is not None
    assert (stored["cache_read"], stored["cache_write"], stored["uncached"]) == (
        38429,
        11223,
        18,
    )
    assert stored["hit_rate_pct"] == direct["hit_rate_pct"] == 77
    assert stored["counts"]["hit_rate_pct"] == {"known": 2, "missing": 0}
    assert stored["provenance"] == "measured"
    assert stored["coverage"] == "non_overlapping"
    assert stored["freshness"] == "fresh"
    assert stored["as_of_offset"] == handle.path.stat().st_size


def test_pair_filter_excludes_same_id_other_host_and_legacy_attribution(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'rollout', 'codex', 'handle', 999, 999, 999)",
            (handle.session_id,),
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'transcript', 'claude-code', NULL, 888, 888, 888)",
            (handle.session_id,),
        )
        conn.commit()
    finally:
        conn.close()
    stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stored is not None
    assert stored["cache_read"] == 38429
    assert stored["counts"]["cache_read"] == {"known": 2, "missing": 0}


def test_repeated_message_id_uses_final_observed_usage(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    shutil.copyfile(_CHANGING, handle.path)
    session_id = json.loads(handle.path.read_text(encoding="utf-8").splitlines()[0])["sessionId"]
    handle = SessionHandle("claude-code", session_id, handle.path, tmp_path, 1.0)
    assert refresh_usage_source(db, handle.path)["usage_events"] == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT output_tokens FROM usage_events").fetchone()[0] == 481
    finally:
        conn.close()
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["cache_read"] == 19809
    assert result["counts"]["hit_rate_pct"] == {"known": 1, "missing": 0}


def test_missing_native_id_is_unverified_and_partial_or_zero_is_unavailable(tmp_path: Path) -> None:
    sample = json.loads(_CAPTURE.read_text(encoding="utf-8").splitlines()[0])
    for case in ("missing_id", "partial", "zero"):
        case_dir = tmp_path / case
        case_dir.mkdir()
        db, handle = _captured_session(case_dir)
        record = json.loads(json.dumps(sample))
        if case == "missing_id":
            del record["message"]["id"]
        elif case == "partial":
            del record["message"]["usage"]["output_tokens"]
        else:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            ):
                record["message"]["usage"][key] = 0
        handle.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        refresh_usage_source(db, handle.path)
        result, diagnostic = _compute_cache_rate_from_usage(handle, db)
        if case == "missing_id":
            assert diagnostic is None and result is not None
            assert result["provenance"] == "unknown"
            assert result["qualification_reason"] == "unverified_usage"
            assert result["hit_rate_pct"] is None
        else:
            assert result is None
            assert diagnostic == "ingested_without_usage"


def test_four_stored_absence_diagnostics(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    assert _compute_cache_rate_from_usage(handle, tmp_path / "missing.db")[1] == "no_store"
    unreadable = tmp_path / "broken.db"
    unreadable.write_text("not a sqlite database", encoding="utf-8")
    assert _compute_cache_rate_from_usage(handle, unreadable)[1] == "unreadable_store"
    assert _compute_cache_rate_from_usage(handle, db)[1] == "session_not_ingested"

    no_usage = {
        "type": "assistant",
        "sessionId": handle.session_id,
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {"id": "msg-no-usage", "role": "assistant", "content": []},
    }
    handle.path.write_text(json.dumps(no_usage) + "\n", encoding="utf-8")
    refresh_usage_source(db, handle.path)
    assert _compute_cache_rate_from_usage(handle, db)[1] == "ingested_without_usage"


def test_stale_append_and_unknown_tail_never_report_fresh(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    with handle.path.open("a", encoding="utf-8") as source:
        source.write(json.dumps({"type": "user", "sessionId": handle.session_id}) + "\n")
    stale, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stale is not None
    assert stale["freshness"] == "stale"
    assert stale["lag_reason"] == "new_append"
    assert stale["as_of_offset"] < handle.path.stat().st_size

    with handle.path.open("a", encoding="utf-8") as source:
        source.write('{"type":')
    unknown, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and unknown is not None
    assert unknown["freshness"] == "unknown"
    assert unknown["lag_reason"] == "partial_tail"


def test_missing_cursor_after_refresh_is_unknown(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute("DELETE FROM usage_source_cursors")
        conn.commit()
    finally:
        conn.close()
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["freshness"] == "unknown"
    assert result["lag_reason"] == "source_untracked"


def test_current_session_json_reads_store_with_as_of(tmp_path: Path, monkeypatch, capsys) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size, "
            "bytes_in, bytes_out, cache_hit) VALUES('t', ?, 'Read', 'h', 1, 2, 3, 0)",
            (handle.session_id,),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        assert main_ctx_stats(["--db", str(db), "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["cache_rate_source"] == "stored_usage"
    assert payload["cache_hit_rate_pct"] == 77
    assert payload["cache_rate_freshness"] == "fresh"
    assert payload["cache_rate_as_of_offset"] == handle.path.stat().st_size
    assert "Stored Claude usage unavailable" not in captured.err


def test_json_stderr_distinguishes_four_store_absences(tmp_path: Path, monkeypatch, capsys) -> None:
    db, handle = _captured_session(tmp_path)
    broken = tmp_path / "broken.db"
    broken.write_text("not sqlite", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        cases = (
            (tmp_path / "missing.db", "no history store is available"),
            (broken, "history store is unreadable"),
            (db, "selected session has not been ingested"),
        )
        for path, expected in cases:
            main_ctx_stats(["--db", str(path), "--json"])
            captured = capsys.readouterr()
            json.loads(captured.out)
            assert expected in captured.err

        record = {
            "type": "assistant",
            "sessionId": handle.session_id,
            "timestamp": "2026-09-29T01:00:00Z",
            "message": {"id": "msg-no-usage", "role": "assistant", "content": []},
        }
        handle.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        refresh_usage_source(db, handle.path)
        main_ctx_stats(["--db", str(db), "--json"])
        captured = capsys.readouterr()
        json.loads(captured.out)
        assert "ingested without qualified usage observations" in captured.err
