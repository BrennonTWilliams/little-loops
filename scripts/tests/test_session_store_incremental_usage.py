"""ENH-3651 source-tail ingestion and atomic replay equivalence."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from little_loops.session_store import (
    backfill_raw_events,
    backfill_usage_incremental,
    connect,
    ensure_db,
    lifecycle,
    rebuild,
    refresh_usage_source,
    usage_source_freshness,
)

_CLAUDE = Path(__file__).parent / "fixtures" / "claude"


def _usage_rows(db: Path) -> list[tuple]:
    conn = connect(db)
    try:
        return conn.execute(
            "SELECT session_id, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, channel, "
            "provenance, usage_contract, observation_key, source_line_no "
            "FROM usage_events WHERE channel IS NOT 'live' ORDER BY observation_key, source_line_no"
        ).fetchall()
    finally:
        conn.close()


def test_claude_slices_keep_last_valid_message_snapshot_and_match_rebuild(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    records = (_CLAUDE / "transcript-changing-usage-observed.jsonl").read_text().splitlines()
    source.write_text("\n".join(records[:2]) + "\n")
    db = tmp_path / "history.db"

    first = refresh_usage_source(db, source)
    assert first["raw_events"] == 2
    assert len(_usage_rows(db)) == 1
    assert _usage_rows(db)[0][3] == 4
    assert usage_source_freshness(db, source)["status"] == "fresh"

    with source.open("a") as handle:
        handle.write("\n".join(records[2:]) + "\n")
    assert usage_source_freshness(db, source)["status"] == "stale"
    second = refresh_usage_source(db, source)
    assert second["raw_events"] == 3
    sliced = _usage_rows(db)
    assert len(sliced) == 1
    assert sliced[0][3] == 481
    assert sliced[0][7] == "measured"
    assert sliced[0][10] == 5
    assert refresh_usage_source(db, source)["raw_events"] == 0

    conn = connect(db)
    try:
        cursor = conn.execute(
            "SELECT committed_offset, committed_line_no, status, derived_raw_event_id "
            "FROM usage_source_cursors"
        ).fetchone()
        checkpoint = conn.execute(
            "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'"
        ).fetchone()[0]
        assert tuple(cursor[:3]) == (source.stat().st_size, 5, "complete")
        assert cursor[3] <= int(checkpoint)
    finally:
        conn.close()

    rebuild(db)
    assert _usage_rows(db) == sliced


def test_first_enable_catches_up_raw_rows_and_preserves_live(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
    db = tmp_path / "history.db"
    ensure_db(db)
    assert backfill_raw_events(db, jsonl_files=[source], host="claude-code") == 4
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, model, channel, input_tokens) "
            "VALUES('2026-01-01', 'live-model', 'live', 99)"
        )
        conn.commit()
    finally:
        conn.close()
    assert backfill_usage_incremental(db) == 2
    assert len(_usage_rows(db)) == 2
    assert backfill_usage_incremental(db) == 0
    conn = connect(db)
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM usage_events WHERE channel = 'live'").fetchone()[0]
            == 1
        )
    finally:
        conn.close()
    before = _usage_rows(db)
    rebuild(db)
    assert _usage_rows(db) == before


def test_partial_tail_is_left_for_next_trigger(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    record = (_CLAUDE / "transcript-v2.1.284.jsonl").read_text().splitlines()[0]
    source.write_text(record + "\n" + record[:20])
    db = tmp_path / "history.db"
    first = refresh_usage_source(db, source)
    assert first == {"raw_events": 1, "usage_events": 1, "status": "partial"}
    assert usage_source_freshness(db, source)["status"] == "unknown"
    with source.open("a") as handle:
        handle.write(record[20:] + "\n")
    assert usage_source_freshness(db, source)["status"] == "stale"
    second = refresh_usage_source(db, source)
    assert second["raw_events"] == 1
    assert second["status"] == "complete"
    assert len(_usage_rows(db)) == 1


def test_truncation_refuses_reused_line_numbers(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    record = (_CLAUDE / "transcript-v2.1.284.jsonl").read_text().splitlines()[0]
    source.write_text(record + "\n")
    db = tmp_path / "history.db"
    refresh_usage_source(db, source)
    source.write_text("{}\n")
    assert usage_source_freshness(db, source)["status"] == "unknown"
    with pytest.raises(RuntimeError, match="rotated|truncated|overwritten"):
        refresh_usage_source(db, source)
    conn = connect(db)
    try:
        assert (
            conn.execute("SELECT status FROM usage_source_cursors").fetchone()[0]
            == "source_changed"
        )
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 1
    finally:
        conn.close()


def test_normalizer_version_change_replays_historical_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "session.jsonl"
    source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
    db = tmp_path / "history.db"
    refresh_usage_source(db, source)
    conn = connect(db)
    try:
        conn.execute("DELETE FROM usage_events WHERE channel = 'transcript'")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", "new-normalizer")
    assert backfill_usage_incremental(db) == 2
    assert len(_usage_rows(db)) == 2


def test_codex_turn_crossing_slice_boundary_matches_rebuild(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "codex" / "rollout-exec-resume-v0.158.0.jsonl"
    lines = fixture.read_text().splitlines()
    source = tmp_path / "rollout.jsonl"
    source.write_text("\n".join(lines[:4]) + "\n")
    db = tmp_path / "history.db"
    assert backfill_raw_events(db, jsonl_files=[source], host="codex") == 4
    backfill_usage_incremental(db)
    assert len(_usage_rows(db)) == 1

    with source.open("a") as handle:
        handle.write("\n".join(lines[4:]) + "\n")
    assert backfill_raw_events(db, jsonl_files=[source], host="codex") == len(lines) - 4
    backfill_usage_incremental(db)
    sliced = _usage_rows(db)
    assert len(sliced) == 2
    assert all(row[7] == "measured" for row in sliced)
    rebuild(db)
    assert _usage_rows(db) == sliced


def test_catchup_failure_rolls_back_rows_and_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "session.jsonl"
    source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
    db = tmp_path / "history.db"
    backfill_raw_events(db, jsonl_files=[source], host="claude-code")

    def fail_after_one(conn: sqlite3.Connection, cursor: object) -> int:
        conn.execute("INSERT INTO usage_events(ts, channel) VALUES('t', 'transcript')")
        raise RuntimeError("injected derive failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(lifecycle, "_backfill_usage_events", fail_after_one)
        with pytest.raises(RuntimeError, match="injected"):
            backfill_usage_incremental(db)
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM meta WHERE key = 'usage_derive_raw_id'").fetchone()[
                0
            ]
            == 0
        )
    finally:
        conn.close()
    assert backfill_usage_incremental(db) == 2


def test_missing_message_id_stays_unqualified_and_copied_source_conflicts(
    tmp_path: Path,
) -> None:
    original = json.loads((_CLAUDE / "transcript-v2.1.284.jsonl").read_text().splitlines()[0])
    missing = json.loads(json.dumps(original))
    missing["message"].pop("id")
    missing["uuid"] = "missing-id-copy"
    first = tmp_path / "first.jsonl"
    first.write_text(json.dumps(original) + "\n" + json.dumps(missing) + "\n")
    db = tmp_path / "history.db"
    refresh_usage_source(db, first)
    rows = _usage_rows(db)
    assert len(rows) == 2
    assert {row[7] for row in rows} == {"measured", "unknown"}

    copied = tmp_path / "copy.jsonl"
    copied.write_text(json.dumps(original) + "\n")
    refresh_usage_source(db, copied)
    assert len(_usage_rows(db)) == 2  # same producer observation across paths

    divergent = json.loads(json.dumps(original))
    divergent["message"]["usage"]["output_tokens"] += 1
    copied2 = tmp_path / "copy-changed.jsonl"
    copied2.write_text(json.dumps(divergent) + "\n")
    refresh_usage_source(db, copied2)
    rows = _usage_rows(db)
    assert len(rows) == 2
    assert {row[7] for row in rows} == {"unknown"}
    assert {row[8] for row in rows} == {None}
    rebuild(db)
    assert _usage_rows(db) == rows


def test_invalid_later_snapshot_does_not_replace_last_valid_one(tmp_path: Path) -> None:
    valid = json.loads((_CLAUDE / "transcript-v2.1.284.jsonl").read_text().splitlines()[0])
    invalid = json.loads(json.dumps(valid))
    invalid["uuid"] = "later-invalid"
    invalid["message"]["usage"]["output_tokens"] = -1
    source = tmp_path / "session.jsonl"
    source.write_text(json.dumps(valid) + "\n" + json.dumps(invalid) + "\n")
    db = tmp_path / "history.db"
    refresh_usage_source(db, source)
    before = _usage_rows(db)
    assert len(before) == 1
    assert before[0][3] == valid["message"]["usage"]["output_tokens"]
    rebuild(db)
    assert _usage_rows(db) == before


def test_two_concurrent_catchup_workers_commit_one_observation_set(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
    db = tmp_path / "history.db"
    backfill_raw_events(db, jsonl_files=[source], host="claude-code")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: backfill_usage_incremental(db), range(2)))
    assert sorted(results) == [0, 2]
    assert len(_usage_rows(db)) == 2


def test_failed_append_derive_leaves_committed_cursor_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "session.jsonl"
    records = (_CLAUDE / "transcript-changing-usage-observed.jsonl").read_text().splitlines()
    source.write_text(records[0] + "\n")
    db = tmp_path / "history.db"
    refresh_usage_source(db, source)
    with source.open("a") as handle:
        handle.write(records[1] + "\n")
    with monkeypatch.context() as patcher:
        patcher.setattr(
            lifecycle,
            "_derive_usage_incremental_conn",
            lambda conn: (_ for _ in ()).throw(RuntimeError("derive failed")),
        )
        with pytest.raises(RuntimeError, match="derive failed"):
            refresh_usage_source(db, source)
    assert usage_source_freshness(db, source)["status"] == "stale"
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 1
    finally:
        conn.close()
    refresh_usage_source(db, source)
    assert usage_source_freshness(db, source)["status"] == "fresh"
