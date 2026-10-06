"""Sanitize raw_events payloads on every ingest path; canonical refresh comparisons (ENH-3751)."""

from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path
from typing import Any

import pytest

from little_loops.cli import backfill_worker
from little_loops.pii import HistorySanitizationError
from little_loops.session_store import (
    _pack_payload,
    _unpack_payload,
    backfill,
    backfill_raw_events,
    connect,
    ensure_db,
    lifecycle,
    refresh_usage_source,
)
from little_loops.session_store.sessions import SessionHandle
from little_loops.session_store.usage_refresh import (
    _decode_stored_payload,
    _payload_equal,
    _preserves_fields,
    refresh_raw_events,
)

SECRET = "AKIA" + "I" * 16  # fragments keep gitleaks quiet
_CODEX_INTERACTIVE = Path(__file__).parent / "fixtures" / "codex" / "rollout-interactive.jsonl"


def _record(text: str = "ok", **extra: Any) -> dict[str, Any]:
    return {
        "type": "assistant",
        "version": "2.1.284",
        "sessionId": "s1",
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {
            "id": "m1",
            "model": "claude-sonnet-4-6",
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "usage": {
                "input_tokens": 3,
                "output_tokens": 5,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 11,
            },
        },
        **extra,
    }


def _write(path: Path, *records: dict[str, Any]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _handle(path: Path, tmp_path: Path, host: str = "claude-code") -> SessionHandle:
    return SessionHandle(host, "s1", path, tmp_path, path.stat().st_mtime)


def _columns(db: Path) -> list[tuple[Any, Any, Any]]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT raw_line, parsed_json, usage_contract FROM raw_events ORDER BY line_no"
        ).fetchall()
    finally:
        conn.close()


def _decoded(value: bytes | str) -> dict[str, Any]:
    return json.loads(_unpack_payload(value))


def _watermark(db: Path) -> Any:
    conn = connect(db)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='last_raw_event_ts'").fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _store_plaintext(db: Path, payloads: list[dict[str, Any]], *, as_text: bool = True) -> None:
    """Rewrite stored payloads as legacy plaintext (TEXT) rows."""
    conn = connect(db)
    try:
        ids = [r[0] for r in conn.execute("SELECT id FROM raw_events ORDER BY line_no")]
        for row_id, payload in zip(ids, payloads, strict=True):
            text = json.dumps(payload)
            value: Any = text if as_text else _pack_payload(text)
            conn.execute(
                "UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = ?",
                (value, value, row_id),
            )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- insert seams


def test_local_ingest_sanitizes_both_columns_identically(tmp_path: Path) -> None:
    source = tmp_path / "s.jsonl"
    _write(source, _record(f"key {SECRET}"))
    db = tmp_path / "h.db"
    ensure_db(db)
    assert backfill_raw_events(db, handles=[_handle(source, tmp_path)]) == 1

    ((raw, parsed, contract),) = _columns(db)
    assert raw == parsed
    assert SECRET not in _unpack_payload(raw)
    stored = _decoded(raw)
    assert stored["message"]["content"][0]["text"] == "key [AWS_ACCESS_KEY]"
    assert stored["message"]["usage"]["cache_read_input_tokens"] == 7
    assert contract is not None  # qualification derives from the original event


def test_ingest_does_not_mutate_the_original_event_objects(tmp_path: Path) -> None:
    source = tmp_path / "s.jsonl"
    _write(source, _record(f"key {SECRET}"))
    seen: list[dict[str, Any]] = []
    real = lifecycle.iter_events

    def spy(handle: SessionHandle):  # type: ignore[no-untyped-def]
        for event in real(handle):
            seen.append(event.payload)
            yield event

    db = tmp_path / "h.db"
    ensure_db(db)
    lifecycle.iter_events = spy  # type: ignore[assignment]
    try:
        backfill_raw_events(db, handles=[_handle(source, tmp_path)])
    finally:
        lifecycle.iter_events = real  # type: ignore[assignment]
    assert SECRET in json.dumps(seen[0])


def test_claude_usage_source_insert_is_sanitized(tmp_path: Path) -> None:
    source = tmp_path / "live.jsonl"
    _write(source, _record(f"key {SECRET}"))
    db = tmp_path / "h.db"
    ensure_db(db)
    refresh_usage_source(db, source, host="claude-code")
    ((raw, parsed, contract),) = _columns(db)
    assert raw == parsed and SECRET not in _unpack_payload(raw)
    assert contract is not None


def test_codex_first_cursor_rows_are_sanitized_and_certify(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    source.write_text(_CODEX_INTERACTIVE.read_text())
    db = tmp_path / "h.db"
    ensure_db(db)
    refresh_usage_source(db, source, host="codex")
    rows = _columns(db)
    assert rows
    assert all("brennon@brenentech.com" not in _unpack_payload(r[0]) for r in rows)
    assert any("[EMAIL]" in _unpack_payload(r[0]) for r in rows)


def test_codex_certifies_legacy_plaintext_rows_without_rewriting_them(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    source.write_text(_CODEX_INTERACTIVE.read_text())
    db = tmp_path / "h.db"
    ensure_db(db)
    handle = SessionHandle("codex", "x", source, tmp_path, source.stat().st_mtime)
    originals = [e.payload for e in lifecycle.iter_events(handle)]
    refresh_usage_source(db, source, host="codex")
    _store_plaintext(db, originals, as_text=True)
    conn = connect(db)
    conn.execute("DELETE FROM usage_source_cursors")
    conn.commit()
    conn.close()
    before = _columns(db)

    refresh_usage_source(db, source, host="codex")  # first-cursor certification again
    assert _columns(db) == before  # unchanged is no-write; legacy plaintext is not scrubbed
    assert any("brennon@brenentech.com" in r[0] for r in before)


def test_codex_certification_refuses_unsanitized_new_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "rollout.jsonl"
    source.write_text(_CODEX_INTERACTIVE.read_text())
    db = tmp_path / "h.db"
    ensure_db(db)

    class _Identity:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

    monkeypatch.setattr(
        lifecycle, "sanitize_history_payload", lambda payload, **_kw: _Identity(payload)
    )
    with pytest.raises(RuntimeError, match="differs"):
        refresh_usage_source(db, source, host="codex")
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM usage_source_cursors").fetchone()[0] == 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- failures


def test_non_finite_payload_aborts_ingest_after_prior_insert(tmp_path: Path) -> None:
    source = tmp_path / "s.jsonl"
    source.write_text(
        json.dumps(_record("one")) + "\n" + json.dumps(_record("two")).replace("3", "NaN", 1) + "\n"
    )
    assert "NaN" in source.read_text()
    db = tmp_path / "h.db"
    ensure_db(db)
    baseline = _watermark(db)
    with pytest.raises(HistorySanitizationError) as err:
        backfill_raw_events(db, handles=[_handle(source, tmp_path)])
    assert err.value.reason == "invalid_payload"
    assert _columns(db) == []  # rolled back, no watermark
    assert _watermark(db) == baseline


def test_full_backfill_failure_rolls_back_earlier_writes(tmp_path: Path) -> None:
    issues = tmp_path / ".issues" / "bugs"
    issues.mkdir(parents=True)
    (issues / "P3-BUG-001-x.md").write_text("---\nid: BUG-001\nstatus: open\n---\n# BUG-001: x\n")
    source = tmp_path / "s.jsonl"
    source.write_text(json.dumps(_record("one")).replace("3", "NaN", 1) + "\n")
    db = tmp_path / "h.db"
    ensure_db(db)
    baseline = _watermark(db)
    with pytest.raises(HistorySanitizationError):
        backfill(
            db,
            issues_dir=tmp_path / ".issues",
            loops_dir=tmp_path / "none",
            handles=[_handle(source, tmp_path)],
            also_rebuild=True,
        )
    assert _watermark(db) == baseline
    assert _columns(db) == []
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM issue_events").fetchone()[0] == 0
    finally:
        conn.close()


def test_worker_reports_reason_only_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "s.jsonl"
    source.write_text(json.dumps(_record(f"k {SECRET}")).replace("3", "NaN", 1) + "\n")
    db = tmp_path / "h.db"
    ensure_db(db)
    code = backfill_worker.main([str(db), str(source), "--host", "claude-code"])
    err = capsys.readouterr().err
    assert code == 1
    assert "invalid_payload" in err and SECRET not in err and "Traceback" not in err


# --------------------------------------------------------------------------- refresh


def _ingest(tmp_path: Path, *records: dict[str, Any]) -> tuple[Path, SessionHandle, Path]:
    source = tmp_path / "s.jsonl"
    _write(source, *records)
    db = tmp_path / "h.db"
    ensure_db(db)
    handle = _handle(source, tmp_path)
    assert backfill_raw_events(db, handles=[handle]) == len(records)
    return db, handle, source


def test_refresh_of_redacted_rows_is_a_no_write_no_op(tmp_path: Path) -> None:
    db, handle, _ = _ingest(tmp_path, _record(f"k {SECRET}"))
    before = _columns(db)
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "unchanged"
    assert _columns(db) == before


def test_refresh_treats_legacy_plaintext_as_compatible_without_scrubbing(tmp_path: Path) -> None:
    record = _record(f"k {SECRET}")
    db, handle, _ = _ingest(tmp_path, record)
    _store_plaintext(db, [record], as_text=True)
    before = _columns(db)
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "unchanged" and not result.needs_rebuild
    assert _columns(db) == before


@pytest.mark.parametrize("as_text", [True, False])
def test_refresh_replacement_writes_sanitized_rows(tmp_path: Path, as_text: bool) -> None:
    record = _record(f"k {SECRET}")
    db, handle, source = _ingest(tmp_path, record)
    _store_plaintext(db, [record], as_text=as_text)
    _write(source, {**record, "newField": "added"})  # parser upgrade adds a field
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "refreshed" and result.needs_rebuild
    ((raw, parsed, _),) = _columns(db)
    assert raw == parsed
    stored = _decoded(raw)
    assert stored["newField"] == "added" and SECRET not in json.dumps(stored)


@pytest.mark.parametrize(
    ("old", "new"),
    [(True, 1), (1, True), (False, 0), (3, 3.0)],
)
def test_refresh_refuses_scalar_type_coercion_in_either_column(
    tmp_path: Path, old: Any, new: Any
) -> None:
    record = {**_record(), "flag": old}
    db, handle, source = _ingest(tmp_path, record)
    _write(source, {**record, "flag": new})
    for column in ("raw_line", "parsed_json"):
        result = refresh_raw_events(db, handles=[handle])
        # source differs from both columns in type: refuse
        assert result.sources[0].reason == "existing_payload_not_preserved", column
    assert not result.needs_rebuild


def test_refresh_refuses_when_only_parsed_json_would_lose_a_field(tmp_path: Path) -> None:
    record = _record()
    db, handle, source = _ingest(tmp_path, record)
    extra = _pack_payload(json.dumps({**record, "onlyInParsed": "keep"}))
    conn = connect(db)
    conn.execute("UPDATE raw_events SET parsed_json = ?", (extra,))
    conn.commit()
    conn.close()
    _write(source, {**record, "other": 1})
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].reason == "existing_payload_not_preserved"


def test_refresh_refuses_per_line_metadata_changes_before_decoding(tmp_path: Path) -> None:
    db, handle, source = _ingest(tmp_path, _record())
    conn = connect(db)
    conn.execute("UPDATE raw_events SET parsed_json = X'00', event_type = 'unknown'")
    conn.commit()
    conn.close()
    result = refresh_raw_events(db, handles=[handle])
    # metadata mismatch is reported ahead of the corrupt payload
    assert result.sources[0].reason == "source_metadata_changed"


def test_refresh_refuses_new_session_id_even_with_intact_lines(tmp_path: Path) -> None:
    record = _record()
    db, handle, source = _ingest(tmp_path, record)
    _write(source, record, {**_record("two"), "sessionId": "other"})
    assert refresh_raw_events(db, handles=[handle]).sources[0].reason == (
        "session_attribution_changed"
    )


def test_refresh_promotes_null_contract_and_refuses_marker_changes(tmp_path: Path) -> None:
    db, handle, _ = _ingest(tmp_path, _record())
    conn = connect(db)
    conn.execute("UPDATE raw_events SET usage_contract = NULL")
    conn.commit()
    conn.close()
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "refreshed" and result.needs_rebuild
    assert _columns(db)[0][2] is not None
    assert refresh_raw_events(db, handles=[handle]).sources[0].status == "unchanged"

    conn = connect(db)
    conn.execute("UPDATE raw_events SET usage_contract = 'bogus-marker'")
    conn.commit()
    conn.close()
    assert refresh_raw_events(db, handles=[handle]).sources[0].reason == "usage_contract_changed"


@pytest.mark.parametrize("column", ["raw_line", "parsed_json"])
@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (zlib.compress(b"\xff\xfe"), "invalid_payload"),
        (b"not zlib", "invalid_payload"),
        (zlib.compress(b"[1]"), "invalid_payload"),
        (zlib.compress(b'{"a":1,"a":2}'), "invalid_payload"),
        (zlib.compress(b"{" * 3000), "resource_limit"),
    ],
)
def test_refresh_decode_failures_are_safe_per_source_refusals(
    tmp_path: Path, column: str, bad: bytes, reason: str
) -> None:
    db, handle, _ = _ingest(tmp_path, _record())
    other = tmp_path / "other.jsonl"
    _write(other, _record("fine"))
    conn = connect(db)
    before = conn.execute("SELECT id, raw_line, parsed_json FROM raw_events").fetchall()
    conn.execute(f"UPDATE raw_events SET {column} = ?", (bad,))
    conn.commit()
    conn.close()
    result = refresh_raw_events(db, handles=[handle])
    assert result.sources[0].status == "skipped"
    # decoder failures are content-free; a deeply nested payload may fail the JSON parser
    # with a resource limit rather than invalid_payload
    assert result.sources[0].reason in {reason, "resource_limit", "invalid_payload"}
    assert not result.needs_rebuild
    conn = connect(db)
    try:
        after = conn.execute("SELECT id, raw_line, parsed_json FROM raw_events").fetchall()
    finally:
        conn.close()
    assert [r[0] for r in after] == [r[0] for r in before]


def test_refresh_multi_source_sanitizer_failure_keeps_other_commits(tmp_path: Path) -> None:
    good_src = tmp_path / "good.jsonl"
    _write(good_src, _record("a"))
    bad_src = tmp_path / "bad.jsonl"
    _write(bad_src, {**_record("b"), "sessionId": "s2"})
    db = tmp_path / "h.db"
    ensure_db(db)
    good = SessionHandle("claude-code", "s1", good_src, tmp_path, good_src.stat().st_mtime)
    bad = SessionHandle("claude-code", "s2", bad_src, tmp_path, bad_src.stat().st_mtime)
    assert backfill_raw_events(db, handles=[good, bad]) == 2
    # parser upgrade on the good source adds a field; the bad source now carries NaN
    _write(good_src, {**_record("a"), "added": 1})
    bad_src.write_text(
        json.dumps({**_record("b"), "sessionId": "s2", "extra": float("nan")}) + "\n"
    )
    bad = SessionHandle("claude-code", "s2", bad_src, tmp_path, bad_src.stat().st_mtime)
    result = refresh_raw_events(db, handles=[bad, good])
    statuses = {s.path.name: (s.status, s.reason) for s in result.sources}
    assert statuses["bad.jsonl"] == ("skipped", "invalid_payload")
    assert statuses["good.jsonl"][0] == "refreshed"
    assert result.needs_rebuild


# --------------------------------------------------------------------------- helpers


def test_payload_equality_is_type_sensitive_and_order_insensitive() -> None:
    assert _payload_equal({"a": 1, "b": [1, 2]}, {"b": [1, 2], "a": 1})
    assert not _payload_equal({"a": True}, {"a": 1})
    assert not _payload_equal({"a": 1}, {"a": 1.0})
    assert not _payload_equal({"a": [1, 2]}, {"a": [1, 2, 3]})
    assert not _preserves_fields({"a": False}, {"a": 0})
    assert _preserves_fields({"a": [1]}, {"a": [1], "b": 2})


def test_decoder_errors_carry_no_input_and_no_context() -> None:
    canary = "CANARY-" + "x" * 8
    with pytest.raises(HistorySanitizationError) as err:
        _decode_stored_payload(zlib.compress(b'"' + canary.encode() + b"\xff"), storage_type="blob")
    exc = err.value
    assert exc.reason == "invalid_payload" and canary not in repr(exc) + str(exc.args)
    assert exc.__cause__ is None and exc.__suppress_context__ is True
    with pytest.raises(HistorySanitizationError):
        _decode_stored_payload(b"{}", storage_type="integer")


def test_ll_session_reports_sanitizer_refusal_by_reason_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from little_loops.cli import session as cli_session

    def boom() -> int:
        raise HistorySanitizationError("invalid_payload")

    monkeypatch.setattr(cli_session, "_main_session", boom)
    assert cli_session.main_session() == 1
    err = capsys.readouterr().err
    assert "invalid_payload" in err and "Traceback" not in err
