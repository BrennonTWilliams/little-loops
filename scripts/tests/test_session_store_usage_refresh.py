"""Upgrade tests for raw source refresh after normalized payloads lost usage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.session_store import (
    _pack_payload,
    _unpack_payload,
    backfill_raw_events,
    connect,
    ensure_db,
    rebuild,
)
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


_USAGE_QUERY = (
    "SELECT id, session_id, channel, provenance, input_tokens, output_tokens, "
    "cache_read_input_tokens, cache_creation_input_tokens, host_basis, observation_key, "
    "usage_contract, cost_usd, source_raw_event_id FROM usage_events ORDER BY id"
)


def _usage(db: Path) -> list[tuple]:
    conn = connect(db)
    try:
        return [tuple(row) for row in conn.execute(_USAGE_QUERY)]
    finally:
        conn.close()


def _insert_observation(db: Path, handle: SessionHandle, *, values: tuple, **extra: object) -> int:
    """Insert one linked transcript observation for the single raw row; return its id."""
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
        return int(conn.execute("SELECT MAX(id) FROM usage_events").fetchone()[0])
    finally:
        conn.close()


def _pending(db: Path) -> list[tuple]:
    conn = connect(db)
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT kind, reason, raw_cache_pending, usage_pending, "
                "original_acquisition_json IS NOT NULL FROM usage_source_pending ORDER BY kind"
            )
        ]
    finally:
        conn.close()


def _forget_tracking(db: Path) -> None:
    """Emulate a legacy raw-only source: raw rows exist but no acquisition head or pending."""
    conn = connect(db)
    try:
        for table in ("usage_source_pending", "usage_source_state"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


_NO_PRICING = "little_loops.pricing.estimate_cost_usd"


def test_refresh_keeps_raw_ids_and_recovers_the_payload_in_place(tmp_path: Path) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        before = conn.execute("SELECT id, ts, source_path, line_no FROM raw_events").fetchone()
    finally:
        conn.close()
    refreshed = refresh_raw_events(db, handles=[handle])
    assert refreshed.sources[0].status == "refreshed" and refreshed.sources[0].rows == 1
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT id, ts, source_path, line_no, raw_line, usage_contract FROM raw_events"
        ).fetchone()
    finally:
        conn.close()
    assert tuple(row[:4]) == tuple(before)  # the verified line keeps its raw id
    assert json.loads(_unpack_payload(row[4]))["message"]["usage"]["cache_read_input_tokens"] == 7
    assert row[5] == "claude-code/2.1.284"  # NULL -> marker recovery, never changed afterwards


def test_raw_only_ingestion_stages_acquisition_and_a_retained_only_derive_completes(
    tmp_path: Path,
) -> None:
    from little_loops.session_store import backfill_usage_incremental, read_source_derive_completion

    db, handle, source = _source(tmp_path)
    conn = connect(db)
    try:
        head = conn.execute(
            "SELECT acquisition_version, acquired_offset, acquired_line_no, status "
            "FROM usage_source_state WHERE source_path = ?",
            (str(handle.path),),
        ).fetchone()
        assert tuple(head) == ("enh3745-v1", source.stat().st_size, 1, "pending")
        # Acquisition alone never publishes completion: a usage-pending handoff remains.
        assert read_source_derive_completion(conn, str(handle.path)).basis == "none"
    finally:
        conn.close()
    assert _pending(db) == [("derive_gap", "derive_pending", 0, 1, 0)]
    source.unlink()  # the original is gone: derive must work from retained rows alone
    backfill_usage_incremental(db)
    conn = connect(db)
    try:
        done = read_source_derive_completion(conn, str(handle.path))
    finally:
        conn.close()
    assert (done.status, done.basis, done.outstanding) == ("complete", "semantic", "none")
    assert _pending(db) == []


def test_raw_only_ingestion_of_a_changed_or_historical_source_gains_no_invented_lineage(
    tmp_path: Path,
) -> None:
    db, handle, source = _source(tmp_path)
    _forget_tracking(db)  # historical raw rows with no acquisition head
    second = json.loads(source.read_text().splitlines()[0])
    second["message"]["id"] = "m2"
    with source.open("a", encoding="utf-8") as out:
        out.write(json.dumps(second) + "\n")
    assert backfill_raw_events(db, handles=[handle]) == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM usage_source_state").fetchone()[0] == 0
    finally:
        conn.close()


def test_refresh_commits_acquisition_and_both_obligations_for_an_untracked_source(
    tmp_path: Path,
) -> None:
    db, handle, source = _source(tmp_path)
    _forget_tracking(db)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM usage_source_state").fetchone()[0] == 0
    finally:
        conn.close()
    refreshed = refresh_raw_events(db, handles=[handle])
    assert refreshed.needs_rebuild
    conn = connect(db)
    try:
        head = conn.execute(
            "SELECT acquisition_version, acquired_offset, acquired_line_no, status "
            "FROM usage_source_state WHERE source_path = ?",
            (str(handle.path),),
        ).fetchone()
    finally:
        conn.close()
    assert head is not None
    assert tuple(head) == ("enh3745-v1", source.stat().st_size, 1, "pending")
    # Both components under one durable obligation carrying the acquisition authority.
    assert _pending(db) == [("refresh", "parser_refresh", 1, 1, 1)]


def test_unchanged_retry_after_a_crash_between_phases_still_reports_the_work(
    tmp_path: Path,
) -> None:
    db, handle, _ = _source(tmp_path)
    _forget_tracking(db)
    _remove_stored_usage(db)
    assert refresh_raw_events(db, handles=[handle]).needs_rebuild
    # "Crash" before derive: reopen the store and repeat with unchanged parser output.
    before = _usage(db)
    retry = refresh_raw_events(db, handles=[handle])
    assert retry.sources[0].status == "unchanged"
    assert retry.needs_rebuild  # committed pending, not this call's replacement count
    assert _usage(db) == before
    assert _pending(db) == [("refresh", "parser_refresh", 1, 1, 1)]


def test_matching_audit_observation_is_recovered_in_place_and_never_repriced(
    tmp_path: Path,
) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    obs_id = _insert_observation(db, handle, values=(3, 5, 7, 11))
    assert refresh_raw_events(db, handles=[handle]).needs_rebuild
    assert _usage(db)[0][3] == "unknown"  # phase 1 alone never promotes
    rebuild(db)
    (row,) = _usage(db)
    assert row[0] == obs_id  # same row, same ID
    assert row[3:8] == ("measured", 3, 5, 7, 11)
    assert row[9] is not None and row[10] == "claude-code/2.1.284"  # key + contract recovered
    assert _pending(db) == []  # both components resolved
    assert not refresh_raw_events(db, handles=[handle]).needs_rebuild
    with patch(_NO_PRICING, side_effect=AssertionError("priced")):
        rebuild(db)
        rebuild(db)
    assert _usage(db) == [row]


def test_contradictory_captured_values_stay_protected_and_incomplete(tmp_path: Path) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    obs_id = _insert_observation(db, handle, values=(1, 5, 7, 11))  # input 1 vs original 3
    refreshed = refresh_raw_events(db, handles=[handle])
    assert refreshed.needs_rebuild
    before = _usage(db)
    rebuild(db)
    (row,) = _usage(db)
    assert row == before[0] and row[0] == obs_id  # no numeric correction, no promotion
    assert row[3] == "unknown" and row[4] == 1
    # Usage stays pending and protected; the refresh flag survives the rebuild.
    assert refresh_raw_events(db, handles=[handle]).needs_rebuild
    assert any(entry[3] == 1 for entry in _pending(db))


def test_absent_observation_is_derived_normally_after_refresh(tmp_path: Path) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        raw_before = conn.execute("SELECT id FROM raw_events").fetchone()[0]
        conn.execute("INSERT INTO meta(key, value) VALUES('usage_derive_version', 'old')")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('usage_derive_raw_id', ?)", (str(raw_before),)
        )
        conn.commit()
    finally:
        conn.close()
    assert refresh_raw_events(db, handles=[handle]).needs_rebuild
    rebuild(db)
    (row,) = _usage(db)
    assert row[3:8] == ("measured", 3, 5, 7, 11) and row[8] == "handle"
    assert not refresh_raw_events(db, handles=[handle]).needs_rebuild
    conn = connect(db)
    try:
        assert conn.execute("SELECT id FROM raw_events").fetchone()[0] == raw_before
    finally:
        conn.close()


def test_refresh_leaves_unrelated_live_usage_and_the_global_checkpoint_alone(
    tmp_path: Path,
) -> None:
    db, handle, _ = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, input_tokens) "
            "VALUES('2026-09-29T01:01:00Z', 'live-only', 'live', 99)"
        )
        conn.execute("INSERT INTO meta(key, value) VALUES('usage_derive_version', 'enh3651-v1')")
        conn.execute("INSERT INTO meta(key, value) VALUES('usage_derive_raw_id', '1')")
        conn.commit()
    finally:
        conn.close()
    refresh_raw_events(db, handles=[handle])
    conn = connect(db)
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM usage_events WHERE channel='live'").fetchone()[0]
            == 1
        )
        assert dict(
            conn.execute("SELECT key, value FROM meta WHERE key LIKE 'usage_derive_%'")
        ) == {
            "usage_derive_version": "enh3651-v1",
            "usage_derive_raw_id": "1",
        }
    finally:
        conn.close()


def test_pre_commit_failure_rolls_back_updates_acquisition_and_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from little_loops.session_store import usage_refresh

    db, handle, _ = _source(tmp_path)
    _forget_tracking(db)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        original = conn.execute("SELECT id, raw_line, usage_contract FROM raw_events").fetchone()
    finally:
        conn.close()

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("before commit")

    monkeypatch.setattr(usage_refresh, "_record_replacement_acquisition", fail)
    with pytest.raises(RuntimeError, match="before commit"):
        refresh_raw_events(db, handles=[handle])
    conn = connect(db)
    try:
        assert conn.execute("SELECT id, raw_line, usage_contract FROM raw_events").fetchone() == (
            original
        )
        assert conn.execute("SELECT COUNT(*) FROM usage_source_state").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM usage_source_pending").fetchone()[0] == 0
    finally:
        conn.close()


def test_appended_native_line_is_inserted_and_extends_the_acquired_boundary(
    tmp_path: Path,
) -> None:
    db, handle, source = _source(tmp_path)
    _remove_stored_usage(db)
    conn = connect(db)
    try:
        raw_before = conn.execute("SELECT id FROM raw_events").fetchone()[0]
    finally:
        conn.close()
    second = json.loads(source.read_text().splitlines()[0])
    second["message"]["id"] = "m2"
    second["timestamp"] = "2026-09-29T01:02:00Z"
    with source.open("a", encoding="utf-8") as handle_out:
        handle_out.write(json.dumps(second) + "\n")
    refreshed = refresh_raw_events(db, handles=[handle])
    assert refreshed.sources[0].status == "refreshed" and refreshed.sources[0].rows == 2
    conn = connect(db)
    try:
        ids = [row[0] for row in conn.execute("SELECT id FROM raw_events ORDER BY line_no")]
        head = conn.execute(
            "SELECT acquired_offset, acquired_line_no FROM usage_source_state"
        ).fetchone()
    finally:
        conn.close()
    assert ids[0] == raw_before and len(ids) == 2  # existing line kept, new line appended
    assert tuple(head) == (source.stat().st_size, 2)
    rebuild(db)
    assert len(_usage(db)) == 2 and not refresh_raw_events(db, handles=[handle]).needs_rebuild


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


def test_refresh_refuses_parser_output_that_drops_nonusage_fields(tmp_path: Path) -> None:
    db, handle, source = _source(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["message"]["model"]
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "skipped"
    assert result.sources[0].reason in {"existing_payload_not_preserved", "usage_contract_changed"}
    assert not result.needs_rebuild


def test_refresh_refuses_parser_output_that_drops_existing_fields(tmp_path: Path) -> None:
    db, handle, source = _source(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    del payload["message"]["usage"]
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = refresh_raw_events(db, handles=[handle])
    # Dropping usage also drops the persisted qualification; the marker is never removed
    # (ENH-3751), and that refusal runs before payload preservation.
    assert result.sources[0].reason == "usage_contract_changed"
    assert not result.needs_rebuild
    conn = connect(db)
    try:
        stored = json.loads(
            _unpack_payload(conn.execute("SELECT raw_line FROM raw_events").fetchone()[0])
        )
        assert stored["message"]["usage"]["input_tokens"] == 3
    finally:
        conn.close()
