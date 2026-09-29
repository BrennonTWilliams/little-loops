"""Fixture-backed Claude Code result eligibility (ENH-3546)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from little_loops.session_store import backfill_raw_events, ensure_db, rebuild
from little_loops.session_store.claude_usage import (
    CLAUDE_USAGE_CONTRACT,
    claude_transcript_contract,
)
from little_loops.subprocess_utils import _qualify_claude_result_usage, usage_from_event

_FIXTURE = Path(__file__).parent / "fixtures" / "claude" / "live-v2.1.284.jsonl"
_TRANSCRIPT = Path(__file__).parent / "fixtures" / "claude" / "transcript-v2.1.284.jsonl"
_CHANGING = (
    Path(__file__).parent / "fixtures" / "claude" / "transcript-changing-usage-observed.jsonl"
)
_STOP_FIXTURES = Path(__file__).parent / "fixtures" / "claude"


def _captured_result() -> dict:
    return next(
        event
        for line in _FIXTURE.read_text().splitlines()
        if (event := json.loads(line)).get("type") == "result"
    )


def test_captured_result_is_measured_only_at_verified_runner_boundary() -> None:
    usage = usage_from_event(_captured_result(), default_model="claude-haiku-4-5")
    assert usage is not None
    assert usage.provenance == "unknown"
    assert (
        usage.input_tokens,
        usage.cache_creation_tokens,
        usage.cache_read_tokens,
        usage.output_tokens,
    ) == (18, 11223, 38429, 165)
    assert (
        _qualify_claude_result_usage(
            usage, runner_host="claude-code", producer_version="2.1.284"
        ).provenance
        == "measured"
    )
    for host, version in (
        ("opencode", "2.1.284"),
        ("claude-code", None),
        ("claude-code", "2.1.283"),
    ):
        assert (
            _qualify_claude_result_usage(
                usage, runner_host=host, producer_version=version
            ).provenance
            == "unknown"
        )


@pytest.mark.parametrize("value", [None, True, "1", 1.5, -1])
@pytest.mark.parametrize(
    "field",
    [
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ],
)
def test_malformed_component_cannot_be_measured(field: str, value: object) -> None:
    event = _captured_result()
    event["usage"][field] = value
    usage = usage_from_event(event, default_model="claude-haiku-4-5")
    assert usage is not None
    assert (
        _qualify_claude_result_usage(
            usage, runner_host="claude-code", producer_version="2.1.284"
        ).provenance
        == "unknown"
    )


@pytest.mark.parametrize("block", [None, {}, [], "invalid"])
def test_invalid_usage_container_is_absent(block: object) -> None:
    event = _captured_result()
    event["usage"] = block
    assert usage_from_event(event, default_model="x") is None


def test_all_zero_block_remains_unverified() -> None:
    event = _captured_result()
    event["usage"] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    usage = usage_from_event(event, default_model="x")
    assert usage is not None
    assert (
        _qualify_claude_result_usage(
            usage, runner_host="claude-code", producer_version="2.1.284"
        ).provenance
        == "unknown"
    )


def test_transcript_identity_and_final_usage_are_producer_observations() -> None:
    records = [json.loads(line) for line in _TRANSCRIPT.read_text().splitlines()]
    assert {record["version"] for record in records} == {"2.1.284"}
    by_request: dict[str, list[dict]] = {}
    for record in records:
        by_request.setdefault(record["message"]["id"], []).append(record)
    assert len(by_request) == 2
    assert all(len(group) == 2 for group in by_request.values())
    assert all(len({record["uuid"] for record in group}) == 2 for group in by_request.values())
    final = [group[-1]["message"]["usage"] for group in by_request.values()]
    result = _captured_result()["usage"]
    for component in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        assert result[component] == sum(usage[component] for usage in final)

    changing = [json.loads(line) for line in _CHANGING.read_text().splitlines()]
    assert {record["version"] for record in changing} == {"2.1.284"}
    assert len({record["message"]["id"] for record in changing}) == 1
    assert len({record["uuid"] for record in changing}) == len(changing)
    assert [record["message"]["usage"]["output_tokens"] for record in changing] == [
        4,
        4,
        4,
        4,
        481,
    ]


def test_verified_transcript_records_receive_versioned_contract_marker() -> None:
    for path in (_TRANSCRIPT, _CHANGING):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            assert (
                claude_transcript_contract(record, host="claude-code", host_basis="handle")
                == CLAUDE_USAGE_CONTRACT
            )
            assert claude_transcript_contract(record, host="qwen", host_basis="handle") is None
            assert claude_transcript_contract(record, host="claude-code", host_basis=None) is None


@pytest.mark.parametrize(
    "change",
    [
        ("version", None),
        ("sessionId", None),
        ("message.id", None),
        ("message.usage.input_tokens", None),
        ("message.usage.output_tokens", True),
        ("message.usage.cache_read_input_tokens", -1),
        ("message.usage.cache_creation_input_tokens", "1"),
    ],
)
def test_transcript_contract_requires_complete_identity_and_counts(
    change: tuple[str, object],
) -> None:
    record = json.loads(_TRANSCRIPT.read_text().splitlines()[0])
    path, value = change
    target = record
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    assert claude_transcript_contract(record, host="claude-code", host_basis="handle") is None


def test_qualification_is_persisted_at_ingest_and_legacy_rows_stay_unknown(
    tmp_path: Path,
) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    assert backfill_raw_events(db, jsonl_files=[_TRANSCRIPT], host="claude-code") == 4
    legacy = json.loads(_TRANSCRIPT.read_text().splitlines()[0])
    observed_session_id = legacy["sessionId"]
    legacy["sessionId"] = "legacy-session"
    legacy["message"]["id"] = "legacy-request"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT DISTINCT usage_contract FROM raw_events").fetchall() == [
            (CLAUDE_USAGE_CONTRACT,)
        ]
        conn.execute(
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy["timestamp"],
                legacy["sessionId"],
                "claude-code",
                "handle",
                "legacy-source.jsonl",
                1,
                "assistant",
                json.dumps(legacy),
                json.dumps(legacy),
            ),
        )
    for _ in range(2):
        rebuild(db)
        with sqlite3.connect(db) as conn:
            legacy_rows = conn.execute(
                "SELECT provenance, usage_contract FROM usage_events "
                "WHERE session_id='legacy-session'"
            ).fetchall()
            new_rows = conn.execute(
                "SELECT provenance, usage_contract FROM usage_events WHERE session_id=?",
                (observed_session_id,),
            ).fetchall()
        assert legacy_rows == [("unknown", None)]
        assert new_rows and all(row == ("measured", CLAUDE_USAGE_CONTRACT) for row in new_rows)


def test_captured_stop_observation_contains_final_transcript_usage() -> None:
    payload = json.loads((_STOP_FIXTURES / "stop-hook-v2.1.284.json").read_text())
    observed = json.loads((_STOP_FIXTURES / "stop-observation-v2.1.284.json").read_text())
    records = [
        json.loads(line)
        for line in (_STOP_FIXTURES / "stop-transcript-v2.1.284.jsonl").read_text().splitlines()
    ]
    assert payload["hook_event_name"] == observed["hook_event_name"] == "Stop"
    assert payload["session_id"] == observed["session_id"]
    assert observed["source_exists"] is True
    assert observed["complete_usage_records_at_stop"] == len(records) == 2
    assert records[-1]["message"]["id"] == observed["last_usage"]["message_id"]
    assert records[-1]["message"]["usage"] == observed["last_usage"]["usage"]
    assert all(record["version"] == "2.1.284" for record in records)
