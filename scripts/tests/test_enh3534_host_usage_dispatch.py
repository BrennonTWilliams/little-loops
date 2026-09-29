"""The shared host usage seam does not certify unproved producer contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from little_loops.session_store import backfill_raw_events, connect, ensure_db, rebuild
from little_loops.session_store.claude_usage import CLAUDE_USAGE_CONTRACT
from little_loops.session_store.sessions import SessionHandle
from little_loops.session_store.writers import (
    HostUsageState,
    UsageObservation,
    UsageReplayRecord,
    normalize_host_usage,
)


def _payload() -> dict[str, Any]:
    return {
        "type": "assistant",
        "version": "2.1.284",
        "sessionId": "session-1",
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {
            "id": "request-1",
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": 3,
                "output_tokens": 5,
                "cache_read_input_tokens": 7,
                "cache_creation_input_tokens": 11,
            },
        },
    }


def _replay(host: str, *, marker: str | None = None) -> UsageReplayRecord:
    return UsageReplayRecord(
        payload=_payload(),
        event_type="assistant",
        ts="2026-09-29T01:00:00Z",
        session_id="session-1",
        host=host,
        host_basis="handle",
        source_label="session.jsonl",
        line_no=1,
        ordinal=None,
        usage_contract=marker,
    )


def _normalize(record: UsageReplayRecord) -> list[UsageObservation]:
    state = HostUsageState(record.source_label, record.host, record.session_id)
    return normalize_host_usage(record, state=state)


def test_only_persisted_claude_contract_qualifies() -> None:
    measured = _normalize(_replay("claude-code", marker=CLAUDE_USAGE_CONTRACT))
    assert len(measured) == 1
    assert measured[0].qualified
    assert measured[0].observation_key == '["claude-code","session-1","request-1"]'

    legacy = _normalize(_replay("claude-code"))
    assert len(legacy) == 1
    assert not legacy[0].qualified
    assert legacy[0].observation_key is None


@pytest.mark.parametrize("host", ["opencode", "pi", "qwen", "gemini", "omp"])
def test_claude_shaped_other_host_usage_stays_unknown(host: str) -> None:
    # Even an accidentally copied Claude marker cannot certify another host.
    observations = _normalize(_replay(host, marker=CLAUDE_USAGE_CONTRACT))
    assert len(observations) == 1
    assert not observations[0].qualified
    assert observations[0].observation_key is None


def test_native_hosts_and_missing_usage_have_no_assistant_observation() -> None:
    assert _normalize(_replay("codex")) == []
    assert _normalize(_replay("kimi-code")) == []
    record = _replay("opencode")
    del record.payload["message"]["usage"]
    assert _normalize(record) == []


def test_legacy_missing_event_type_still_uses_assistant_payload() -> None:
    record = replace(_replay("claude-code"), event_type="")
    assert len(_normalize(record)) == 1


def test_state_scope_cannot_cross_host_or_session() -> None:
    record = _replay("qwen")
    with pytest.raises(ValueError, match="does not match"):
        normalize_host_usage(
            record, state=HostUsageState("session.jsonl", "claude-code", "session-1")
        )
    with pytest.raises(ValueError, match="does not match"):
        normalize_host_usage(record, state=HostUsageState("session.jsonl", "qwen", "session-2"))


def test_opencode_shape_rebuild_preserves_unknown_provenance(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    source = tmp_path / "session.jsonl"
    source.write_text(json.dumps(_payload()) + "\n", encoding="utf-8")
    handle = SessionHandle("opencode", "session-1", source, tmp_path, source.stat().st_mtime)
    ensure_db(db)
    assert backfill_raw_events(db, handles=[handle]) == 1
    for _ in range(2):
        rebuild(db)
        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT host, host_basis, provenance, usage_contract, input_tokens, "
                "cache_read_input_tokens FROM usage_events"
            ).fetchone()
            count = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        finally:
            conn.close()
        assert count == 1
        assert tuple(row) == ("opencode", "handle", "unknown", None, 3, 7)
