"""Codex cache-rate cutover reads the verified current rollout from storage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.ctx_stats import _compute_cache_rate_from_usage, main_ctx_stats
from little_loops.session_store import SessionHandle, connect, record_usage_event
from little_loops.session_store.lifecycle import refresh_usage_source

_FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def _stored_rollout(tmp_path: Path, fixture: str) -> tuple[Path, SessionHandle]:
    source = tmp_path / "rollout.jsonl"
    shutil.copyfile(_FIXTURES / fixture, source)
    session_id = json.loads(source.read_text().splitlines()[0])["payload"]["id"]
    handle = SessionHandle("codex", session_id, source, tmp_path, source.stat().st_mtime)
    db = tmp_path / "history.db"
    assert refresh_usage_source(db, source, host="codex")["status"] == "complete"
    return db, handle


def test_current_codex_rollout_uses_selected_stored_requests_and_host_pair(tmp_path: Path) -> None:
    db, handle = _stored_rollout(tmp_path, "rollout-exec-resume-v0.158.0.jsonl")
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'transcript', 'claude-code', 'handle', 999, 999, 999)",
            (handle.session_id,),
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'rollout', 'codex', NULL, 888, 888, 888)",
            (handle.session_id,),
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]

    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["source"] == "stored_usage"
    assert result["host"] == "codex" and result["session_id"] == handle.session_id
    assert result["coverage"] == "non_overlapping"
    assert result["provenance"] == "measured"
    assert (result["cache_read"], result["cache_write"], result["uncached"]) == (26880, 0, 7485)
    assert result["hit_rate_pct"] == 78
    assert result["counts"]["hit_rate_pct"] == {"known": 2, "missing": 0}
    assert result["freshness"] == "fresh"
    assert result["as_of_offset"] == handle.path.stat().st_size
    with connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == before


def test_live_rollout_overlap_is_audit_only_for_ctx_stats(tmp_path: Path) -> None:
    db, handle = _stored_rollout(tmp_path, "rollout-exec-resume-v0.158.0.jsonl")
    record_usage_event(
        db,
        run_id="run-live",
        ts="2026-09-29T09:00:00Z",
        state="check",
        model="gpt-5.6-sol",
        input_tokens=4585,
        output_tokens=5,
        cache_read_tokens=11264,
        cache_creation_tokens=0,
        provenance="measured",
        host="codex",
        scope_kind="unknown",
        session_id=handle.session_id,
        identity_basis="host_observed",
        invocation_id="local-invocation",
    )
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["coverage"] == "overlap_unresolved"
    assert result["coverage_reason"] == "live_replay_join_unproven"
    assert result["hit_rate_pct"] is None
    assert result["cache_read"] is None
    assert result["channel_subtotals"]["live"]["events"] == 1
    assert result["channel_subtotals"]["rollout"]["events"] == 2


def test_old_codex_rollout_is_unknown_but_auditable(tmp_path: Path) -> None:
    db, handle = _stored_rollout(tmp_path, "stop-rollout-v0.152.1.jsonl")
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["coverage"] == "unknown"
    assert result["coverage_reason"] == "rollout_request_identity_unverified"
    assert result["hit_rate_pct"] is None
    assert result["channel_subtotals"]["rollout"]["events"] == 1


def test_codex_cli_uses_latest_selected_stored_session_and_clean_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db, handle = _stored_rollout(tmp_path, "rollout-exec-resume-v0.158.0.jsonl")
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size, "
            "bytes_in, bytes_out, cache_hit) VALUES('t', ?, 'Read', 'h', 1, 2, 3, 0)",
            (handle.session_id,),
        )
        conn.commit()
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]) as detect:
        assert main_ctx_stats(["--db", str(db), "--host", "codex", "--json"]) == 0
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["cache_rate_source"] == "stored_usage"
    assert payload["cache_rate_host"] == "codex"
    assert payload["cache_hit_rate_pct"] == 78
    assert payload["cache_rate_freshness"] == "fresh"
    assert output.err == ""
    detect.assert_called_once_with(tmp_path, "codex", include_agents=False, limit=1)


def test_codex_missing_store_keeps_json_parseable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "rollout.jsonl"
    source.write_text((_FIXTURES / "stop-rollout-v0.152.1.jsonl").read_text())
    session_id = json.loads(source.read_text().splitlines()[0])["payload"]["id"]
    handle = SessionHandle("codex", session_id, source, tmp_path, source.stat().st_mtime)
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        main_ctx_stats(["--db", str(tmp_path / "missing.db"), "--json"])
    output = capsys.readouterr()
    assert isinstance(json.loads(output.out), dict)
    assert "Stored Codex usage unavailable" in output.err
    assert "no history store is available" in output.err
