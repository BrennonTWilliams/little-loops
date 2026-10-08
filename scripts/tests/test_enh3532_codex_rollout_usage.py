"""ENH-3532 Codex rollout request replay and conservative identity tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history.agent_quality import _usage_totals
from little_loops.session_store import backfill_raw_events, connect, ensure_db, rebuild
from little_loops.session_store.sessions import SessionHandle
from little_loops.session_store.writers import _backfill_usage_events, _iter_usage_replay_records

FIXTURES = Path(__file__).parent / "fixtures" / "codex"
PARENT = "01a0ebf9-897a-7710-8dd9-436ba7483c83"
FORK = "01a0ebfa-3c21-76d1-98d3-f9aa76a00929"


def _handle(path: Path, cwd: Path) -> SessionHandle:
    meta = json.loads(path.read_text().splitlines()[0])["payload"]
    return SessionHandle("codex", meta["id"], path, cwd, 1.0)


def _rows(db: Path) -> list[tuple]:
    conn = connect(db)
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT channel, session_id, host, host_basis, identity_basis, model, "
                "input_tokens, cache_read_input_tokens, cache_creation_input_tokens, output_tokens, "
                "provenance, turn_id, request_id, request_identity_basis, source_ordinal, "
                "source_line_no FROM usage_events ORDER BY session_id, source_ordinal, source_line_no"
            )
        ]
    finally:
        conn.close()


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def _envelope(ordinal: int, kind: str, payload: dict) -> dict:
    return {
        "timestamp": f"2026-09-29T07:00:{ordinal:02d}.000Z",
        "ordinal": ordinal,
        "type": kind,
        "payload": payload,
    }


def test_old_shape_rollout_replays_three_disjoint_requests(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    fixture = FIXTURES / "rollout-exec-resume.jsonl"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(fixture, tmp_path)])
    assert rebuild(db)["usage_events"] == 3
    rows = _rows(db)
    assert len(rows) == 3
    assert {row[0] for row in rows} == {"rollout"}
    assert {row[4] for row in rows} == {"host_observed"}
    assert {row[10] for row in rows} == {"unknown"}  # old request key unproven
    assert all(row[11] and row[12] is None and row[14] is not None for row in rows)
    assert [sum(row[index] for row in rows) for index in (6, 7, 8, 9)] == [12424, 46080, 0, 122]


def test_current_mixed_records_select_each_native_request_once(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    fixtures = [
        FIXTURES / "rollout-exec-resume-v0.158.0.jsonl",
        FIXTURES / "rollout-fork-v0.158.0.jsonl",
    ]
    ensure_db(db)
    assert backfill_raw_events(db, handles=[_handle(path, tmp_path) for path in fixtures]) > 0
    assert rebuild(db)["usage_events"] == 3
    rows = _rows(db)
    assert [row[1] for row in rows] == [PARENT, PARENT, FORK] or [row[1] for row in rows] == [
        FORK,
        PARENT,
        PARENT,
    ]
    assert len({row[12] for row in rows}) == 3
    assert all(row[10] == "measured" and row[13] == "native_response" for row in rows)
    assert all(row[2:5] == ("codex", "handle", "host_observed") for row in rows)
    assert [sum(row[index] for row in rows) for index in (6, 7, 8, 9)] == [14753, 38144, 0, 15]
    conn = connect(db)
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM raw_events WHERE ordinal IS NOT NULL").fetchone()[0]
            > 0
        )
    finally:
        conn.close()


def test_direct_and_stored_replay_agree_and_copy_is_idempotent(tmp_path: Path) -> None:
    fixture = FIXTURES / "rollout-exec-resume-v0.158.0.jsonl"
    direct = tmp_path / "direct.db"
    stored = tmp_path / "stored.db"
    ensure_db(direct)
    ensure_db(stored)
    conn = connect(direct)
    try:
        # ENH-3770: the private direct-file helper has no durable raw identity, so it can
        # neither mutate observations nor price; recognition parity below stays read-only.
        with patch("little_loops.pricing.estimate_cost_usd", side_effect=AssertionError("priced")):
            assert _backfill_usage_events(conn, [fixture]) == 0
        conn.commit()
    finally:
        conn.close()
    assert _rows(direct) == []
    backfill_raw_events(stored, handles=[_handle(fixture, tmp_path)])
    conn = connect(stored)
    try:
        cursor = conn.execute(
            "SELECT raw_line, source_path, host, host_basis, event_type, ts, "
            "session_id, line_no, ordinal FROM raw_events ORDER BY line_no"
        )
        stored_metadata = [
            (
                r.event_type,
                r.ts,
                r.session_id,
                r.host,
                r.host_basis,
                r.line_no,
                r.ordinal,
                r.payload,
            )
            for r in _iter_usage_replay_records(cursor)
        ]
    finally:
        conn.close()
    direct_metadata = [
        (r.event_type, r.ts, r.session_id, r.host, r.host_basis, r.line_no, r.ordinal, r.payload)
        for r in _iter_usage_replay_records([fixture])
    ]
    assert stored_metadata == direct_metadata
    rebuild(stored)
    original = _rows(stored)
    assert len(original) == 2
    copy = tmp_path / "copied-rollout.jsonl"
    copy.write_bytes(fixture.read_bytes())
    backfill_raw_events(stored, handles=[_handle(copy, tmp_path)])
    # Rebuild reconciles with committed rows (ENH-3770): the identical copy shares the
    # survivor's representation, so nothing is inserted -- and nothing is rewritten.
    assert rebuild(stored)["usage_events"] == 0
    assert _rows(stored) == original
    assert rebuild(stored)["usage_events"] == 0
    assert _rows(stored) == original


def test_duplicate_count_notification_and_nonadvancing_total(tmp_path: Path) -> None:
    thread = "thread-count-only"
    first = {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "cache_write_input_tokens": 0,
        "output_tokens": 3,
    }
    second = {**first, "output_tokens": 4}
    records = [
        _envelope(0, "session_meta", {"id": thread, "timestamp": "2026-09-29T07:00:00Z"}),
        _envelope(1, "event_msg", {"type": "task_started", "turn_id": "turn-a"}),
        _envelope(2, "turn_context", {"turn_id": "turn-a", "model": "gpt-5.6-sol"}),
        _envelope(
            3,
            "event_msg",
            {
                "type": "token_count",
                "info": {
                    "total_token_usage": first,
                    "last_token_usage": first,
                },
            },
        ),
        _envelope(
            4,
            "event_msg",
            {
                "type": "token_count",
                "info": {
                    "total_token_usage": first,
                    "last_token_usage": first,
                },
            },
        ),
        _envelope(
            5,
            "event_msg",
            {
                "type": "token_count",
                "info": {
                    "total_token_usage": first,
                    "last_token_usage": second,
                },
            },
        ),
        _envelope(6, "event_msg", {"type": "token_count", "info": None}),
        _envelope(7, "event_msg", {"type": "task_complete", "turn_id": "turn-a"}),
    ]
    path = _write(tmp_path / "counts.jsonl", records)
    db = tmp_path / "history.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(path, tmp_path)])
    assert rebuild(db)["usage_events"] == 2
    rows = _rows(db)
    assert [row[9] for row in rows] == [3, 4]
    assert all(row[10] == "unknown" and row[13] == "unverified" for row in rows)


def test_legacy_ordinal_and_host_attribution_remain_unverified(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    fixture = FIXTURES / "rollout-exec-resume.jsonl"
    backfill_raw_events(db, handles=[_handle(fixture, tmp_path)])
    conn = connect(db)
    try:
        conn.execute("UPDATE raw_events SET ordinal = NULL, host_basis = NULL")
        conn.commit()
    finally:
        conn.close()
    rebuild(db)
    rows = _rows(db)
    assert len(rows) == 3
    assert all(row[2] is None and row[4] is None and row[14] is None for row in rows)
    assert all(row[10] == "unknown" and row[13] == "unverified" for row in rows)


def test_mixed_partial_stream_retains_old_shape_request(tmp_path: Path) -> None:
    mixed = FIXTURES / "rollout-mixed-v0.158.0-synthetic.jsonl"
    db = tmp_path / "mixed.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(mixed, tmp_path)])
    assert rebuild(db)["usage_events"] == 2
    rows = _rows(db)
    assert sorted(row[10] for row in rows) == ["measured", "unknown"]
    assert sorted(row[13] for row in rows) == ["native_response", "unverified"]
    assert sorted(row[9] for row in rows) == [5, 5]


def test_paginated_same_thread_and_reset_ordinals_keep_distinct_requests(tmp_path: Path) -> None:
    pages = [
        FIXTURES / "rollout-page-a-v0.158.0-synthetic.jsonl",
        FIXTURES / "rollout-page-b-v0.158.0-synthetic.jsonl",
    ]
    db = tmp_path / "pages.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(path, tmp_path) for path in pages])
    assert rebuild(db)["usage_events"] == 2
    rows = _rows(db)
    assert {row[1] for row in rows} == {PARENT}
    assert len({row[12] for row in rows}) == 2
    conn = connect(db)
    try:
        streams = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT stream_id FROM usage_events WHERE channel = 'rollout'"
            )
        }
    finally:
        conn.close()
    assert len(streams) == 2


def test_conflicting_response_id_is_retained_but_not_measured(tmp_path: Path) -> None:
    original = [
        json.loads(line)
        for line in (FIXTURES / "rollout-exec-resume-v0.158.0.jsonl").read_text().splitlines()
    ]
    first = _write(tmp_path / "first.jsonl", original)
    copy = json.loads(json.dumps(original))
    usage = next(
        event["payload"]["usage"] for event in copy if event["type"] == "token_usage_record"
    )
    usage["output_tokens"] += 1
    for event in copy:
        if event["type"] == "event_msg" and event["payload"].get("type") == "token_count":
            event["payload"]["info"]["last_token_usage"]["output_tokens"] += 1
            break
    second = _write(tmp_path / "second.jsonl", copy)
    db = tmp_path / "conflict.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(first, tmp_path), _handle(second, tmp_path)])
    assert rebuild(db)["usage_events"] == 3
    rows = _rows(db)
    first_id = next(
        event["payload"]["response_id"]
        for event in original
        if event["type"] == "token_usage_record"
    )
    conflicting = [row for row in rows if row[12] == first_id]
    assert len(conflicting) == 2
    assert {row[10] for row in conflicting} == {"unknown"}


def test_missing_close_or_model_downgrades_native_request(tmp_path: Path) -> None:
    original = [
        json.loads(line)
        for line in (FIXTURES / "rollout-exec-resume-v0.158.0.jsonl").read_text().splitlines()
    ]
    first_turn = next(
        event["payload"]["turn_id"] for event in original if event["type"] == "token_usage_record"
    )
    incomplete = _write(
        tmp_path / "incomplete.jsonl",
        [
            event
            for event in original
            if not (
                event["type"] == "event_msg"
                and event["payload"].get("type") == "task_complete"
                and event["payload"].get("turn_id") == first_turn
            )
            and not (
                event["type"] == "turn_context" and event["payload"].get("turn_id") == first_turn
            )
        ],
    )
    db = tmp_path / "incomplete.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(incomplete, tmp_path)])
    rebuild(db)
    rows = _rows(db)
    assert len(rows) == 2
    assert next(row[10] for row in rows if row[11] == first_turn) == "unknown"


@pytest.mark.parametrize("bad_usage", [{}, None, {"input_tokens": 1, "output_tokens": True}])
def test_malformed_native_usage_stays_unknown_without_zero_filling(
    tmp_path: Path, bad_usage: object
) -> None:
    original = [
        json.loads(line)
        for line in (FIXTURES / "rollout-exec-resume-v0.158.0.jsonl").read_text().splitlines()
    ]
    first = next(event for event in original if event["type"] == "token_usage_record")
    response_id = first["payload"]["response_id"]
    first["payload"]["usage"] = bad_usage
    path = _write(tmp_path / "malformed.jsonl", original)
    db = tmp_path / "malformed.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(path, tmp_path)])
    rebuild(db)
    malformed = next(row for row in _rows(db) if row[12] == response_id)
    assert malformed[10] == "unknown"
    assert malformed[6] is None and malformed[9] is None


def test_rebuild_rolls_back_replacement_when_replay_fails(tmp_path: Path) -> None:
    fixture = FIXTURES / "rollout-exec-resume-v0.158.0.jsonl"
    db = tmp_path / "history.db"
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(fixture, tmp_path)])
    rebuild(db)
    before = _rows(db)
    with patch(
        "little_loops.session_store.lifecycle._backfill_usage_events",
        side_effect=RuntimeError("stop"),
    ):
        with pytest.raises(RuntimeError, match="stop"):
            rebuild(db)
    assert _rows(db) == before


def test_cost_per_issue_remains_transcript_only(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    conn = connect(db)
    try:
        for channel in ("transcript", "live", "rollout"):
            conn.execute(
                "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, "
                "cost_usd, channel) VALUES('2026-09-29T07:00:00Z', 's1', 'm', 10, 1, 2.0, ?)",
                (channel,),
            )
        conn.commit()
        totals = _usage_totals(conn, {"s1": {1}}, {1: ("2026-09", "ll-auto")})
    finally:
        conn.close()
    assert totals == {
        ("2026-09", "ll-auto"): {
            "cost": 2.0,
            "tokens": 11.0,
            "priced_rows": 1.0,
            "total_rows": 1.0,
        }
    }
