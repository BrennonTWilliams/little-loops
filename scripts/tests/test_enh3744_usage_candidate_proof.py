"""ENH-3744: native usage-candidate proof, derive-gap retention and prune veto.

Real Claude/Codex fixtures run through production ingest, derive and prune. Pure-proof
tests build ``UsageReplayRecord`` values directly so the helper is exercised with no
storage at all.
"""

from __future__ import annotations

import ast
import builtins
import copy
import json
import shutil
import sqlite3
import zlib
from pathlib import Path
from typing import Any

import pytest

from little_loops import pii
from little_loops.session_store import (
    backfill_raw_events,
    backfill_usage_incremental,
    connect,
    lifecycle,
    prune,
    rebuild,
)
from little_loops.session_store import usage_proof as proof_mod
from little_loops.session_store import usage_proof_scope as scope_mod
from little_loops.session_store.usage_proof import (
    PROOF_IDENTITY_PATHS,
    UsageCandidateProof,
    UsageReplayFailure,
    codex_components,
    inspect_usage_candidates,
    retention_reasons,
)
from little_loops.session_store.usage_proof_scope import (
    ProofLimits,
    inspect_retained_source,
)
from little_loops.session_store.writers import UsageReplayRecord

_FIXTURES = Path(__file__).parent / "fixtures"
_CLAUDE = _FIXTURES / "claude" / "transcript-v2.1.284.jsonl"
_CODEX = _FIXTURES / "codex" / "rollout-exec-resume-v0.158.0.jsonl"
_CODEX_INTERACTIVE = _FIXTURES / "codex" / "rollout-interactive.jsonl"
_OLD = "2020-01-01T00:00:00Z"
_CFG = {
    "analytics": {
        "retention": {
            "raw_event_max_age_days": 1,
            "min_project_age_days": 0,
            "min_db_size_mb": 0,
        }
    }
}


def _sql(db: Path, statement: str, params: tuple = ()) -> list[tuple]:
    conn = connect(db)
    try:
        rows = [tuple(row) for row in conn.execute(statement, params).fetchall()]
        conn.commit()
        return rows
    finally:
        conn.close()


def _ingest(tmp_path: Path, fixture: Path, host: str, name: str) -> tuple[Path, Path]:
    source = tmp_path / name
    shutil.copy(fixture, source)
    db = tmp_path / "history.db"
    backfill_raw_events(db, jsonl_files=[source], host=host)
    backfill_usage_incremental(db)
    return db, source


def _make_old(db: Path, where: str = "1 = 1") -> None:
    _sql(db, f"UPDATE raw_events SET compacted = 1, ts = ? WHERE {where}", (_OLD,))


def _proofs(db: Path, source: Path, **kwargs: Any) -> tuple[UsageCandidateProof, ...]:
    conn = connect(db)
    try:
        return inspect_retained_source(conn, str(source), **kwargs)
    finally:
        conn.close()


def _outcomes(proofs: tuple[UsageCandidateProof, ...]) -> set[tuple[str, str]]:
    return {(p.correspondence, p.reason) for p in proofs}


@pytest.fixture
def claude(tmp_path: Path) -> tuple[Path, Path]:
    return _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")


@pytest.fixture
def codex(tmp_path: Path) -> tuple[Path, Path]:
    return _ingest(tmp_path, _CODEX, "codex", "rollout.jsonl")


class TestRealFixtureParity:
    def test_claude_snapshots_coalesce_without_false_gaps(self, claude: Any) -> None:
        db, source = claude
        proofs = _proofs(db, source)
        assert proofs
        assert {p.correspondence for p in proofs} == {"represented"}
        assert all(p.matched_observation_ids for p in proofs)

    def test_codex_copies_and_notifications_do_not_invent_gaps(self, codex: Any) -> None:
        db, source = codex
        proofs = _proofs(db, source)
        assert {p.correspondence for p in proofs} == {"represented"}
        assert ("represented", "coalesced_copy") in _outcomes(proofs)

    def test_unkeyed_codex_audit_rows_correspond_through_their_raw_link(
        self, tmp_path: Path
    ) -> None:
        db, source = _ingest(tmp_path, _CODEX_INTERACTIVE, "codex", "rollout.jsonl")
        proofs = _proofs(db, source)
        assert _outcomes(proofs) == {("represented", "linked_audit")}

    def test_proof_surface_holds_no_native_references(self, claude: Any) -> None:
        db, source = claude
        for proof in _proofs(db, source):
            assert set(proof.status()) == {"correspondence", "reason"}
            assert str(source) not in repr(proof)
            assert "session" not in repr(proof).lower()


class TestMissingCandidatesRetainRaw:
    def test_checkpoint_covered_source_with_one_observation_removed(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "DELETE FROM usage_events WHERE id = (SELECT MIN(id) FROM usage_events)")
        assert {p.correspondence for p in _proofs(db, source)} >= {"missing"}
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert result["retained"] == {"raw_events": 4}
        assert "usage_derive_gap" in result["retention_reasons"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]

    def test_unlinked_source_branch_also_vetoes(self, claude: Any) -> None:
        db, _ = claude
        _sql(db, "DELETE FROM usage_events")
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert result["retained"] == {"raw_events": 4}
        assert result["retention_reasons"] == ["usage_derive_gap"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]

    def test_codex_missing_observation_in_both_branches(self, codex: Any) -> None:
        db, _ = codex
        _sql(db, "DELETE FROM usage_events WHERE id = (SELECT MIN(id) FROM usage_events)")
        _make_old(db)
        assert "usage_derive_gap" in prune(db, config=_CFG, dry_run=True)["retention_reasons"]
        _sql(db, "DELETE FROM usage_events")
        result = prune(db, config=_CFG)
        assert result["retention_reasons"] == ["usage_derive_gap"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events")[0][0] > 0

    def test_gap_clears_once_the_observation_exists_again(self, claude: Any) -> None:
        db, _ = claude
        before = _sql(db, "SELECT COUNT(*) FROM usage_events")
        _sql(db, "DELETE FROM usage_events")
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        backfill_usage_incremental(db)
        assert _sql(db, "SELECT COUNT(*) FROM usage_events") == before
        _make_old(db)
        assert prune(db, config=_CFG)["deleted"] == {"raw_events": 4}


class TestSameKeyAndValueCapture:
    def test_older_observation_cannot_certify_a_newer_same_key_candidate(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "UPDATE usage_events SET output_tokens = output_tokens + 1000")
        assert ("missing", "newer_snapshot_not_captured") in _outcomes(_proofs(db, source))
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["retained"] == {"raw_events": 4}
        assert "usage_derive_gap" in result["retention_reasons"]

    def test_keyed_observation_for_a_different_session_is_unprovable(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "UPDATE usage_events SET session_id = 'someone-else'")
        assert ("unprovable", "identity_contradiction") in _outcomes(_proofs(db, source))

    def test_pointer_and_session_alone_do_not_prove_an_unkeyed_audit(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")
        _sql(db, "UPDATE raw_events SET usage_contract = NULL")
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        rebuild(db)
        # NULL persisted markers leave audit observations; they are not promoted.
        assert _sql(db, "SELECT DISTINCT provenance, usage_contract FROM usage_events") == [
            ("unknown", None)
        ]
        proofs = _proofs(db, source)
        assert _outcomes(proofs) == {("represented", "linked_audit")}
        _sql(db, "UPDATE usage_events SET output_tokens = output_tokens + 7")
        assert ("unprovable", "value_mismatch") in _outcomes(_proofs(db, source))
        assert _sql(db, "SELECT DISTINCT provenance FROM usage_events") == [("unknown",)]

    def test_two_distinct_unkeyed_candidates_with_one_observation_leave_a_gap(
        self, tmp_path: Path
    ) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")
        _sql(db, "UPDATE raw_events SET usage_contract = NULL")
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        rebuild(db)
        _sql(db, "DELETE FROM usage_events WHERE id = (SELECT MIN(id) FROM usage_events)")
        outcomes = _outcomes(_proofs(db, source))
        assert ("missing", "no_exact_link") in outcomes
        assert ("represented", "linked_audit") in outcomes

    def test_codex_pointer_with_wrong_captured_values_is_unprovable(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CODEX_INTERACTIVE, "codex", "rollout.jsonl")
        _sql(db, "UPDATE usage_events SET output_tokens = output_tokens + 1")
        assert ("unprovable", "value_mismatch") in _outcomes(_proofs(db, source))
        _make_old(db)
        result = prune(db, config=_CFG)
        assert "usage_proof_unprovable" in result["retention_reasons"]
        assert result["deleted"] == {"raw_events": 0}


class TestIdentityContradictions:
    def test_envelope_session_disagreeing_with_the_claude_payload(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "UPDATE raw_events SET session_id = 'other-session'")
        assert _outcomes(_proofs(db, source)) == {("unprovable", "identity_contradiction")}
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["retention_reasons"] == ["usage_proof_unprovable"]
        assert result["deleted"] == {"raw_events": 0}

    def test_codex_header_disagreeing_with_the_envelope(self, codex: Any) -> None:
        db, source = codex
        _sql(
            db,
            "UPDATE raw_events SET session_id = 'other-thread' WHERE event_type != 'session_meta'",
        )
        assert ("unprovable", "identity_contradiction") in _outcomes(_proofs(db, source))

    def test_unregistered_host_identity_is_unprovable(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "UPDATE raw_events SET host = 'mystery'")
        assert ("unprovable", "identity_path_unregistered") in _outcomes(_proofs(db, source))

    def test_disagreement_is_never_an_excluded_channel(self, claude: Any) -> None:
        db, source = claude
        _sql(db, "UPDATE raw_events SET session_id = 'other-session'")
        outcomes = _outcomes(_proofs(db, source, channel="transcript"))
        assert ("excluded_channel", "channel_filtered") not in outcomes
        assert ("unprovable", "identity_contradiction") in outcomes


def _claude_record(
    raw_id: int,
    *,
    message_id: str | None = "msg-1",
    usage: dict[str, Any] | None = None,
    line_no: int | None = None,
    source: str = "/s/a.jsonl",
    contract: str | None = "claude-code/2.1.284",
    version: str = "2.1.284",
) -> UsageReplayRecord:
    usage = usage or {
        "input_tokens": 3,
        "output_tokens": 5,
        "cache_read_input_tokens": 7,
        "cache_creation_input_tokens": 11,
    }
    message: dict[str, Any] = {"model": "claude-x", "usage": usage}
    if message_id is not None:
        message["id"] = message_id
    return UsageReplayRecord(
        payload={
            "type": "assistant",
            "sessionId": "sess-1",
            "version": version,
            "message": message,
        },
        event_type="assistant",
        ts="2026-01-01T00:00:00Z",
        session_id="sess-1",
        host="claude-code",
        host_basis="handle",
        source_label=source,
        line_no=line_no if line_no is not None else raw_id,
        ordinal=None,
        usage_contract=contract,
        raw_event_id=raw_id,
    )


def _claude_obs(obs_id: int, record: UsageReplayRecord, **overrides: Any) -> dict[str, Any]:
    usage = record.payload["message"]["usage"]
    obs = {
        "id": obs_id,
        "host": "claude-code",
        "session_id": "sess-1",
        "channel": "transcript",
        "provenance": "measured",
        "model": "claude-x",
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "observation_key": json.dumps(
            ["claude-code", "sess-1", record.payload["message"].get("id")], separators=(",", ":")
        ),
        "source_raw_event_id": record.raw_event_id,
        "source_path": record.source_label,
        "source_line_no": record.line_no,
        "source_ordinal": None,
        "request_id": None,
        "turn_id": None,
    }
    obs.update(overrides)
    return obs


class TestPureProof:
    def test_applied_snapshot_is_represented_and_older_ones_coalesce(self) -> None:
        old = _claude_record(
            1, usage={**_claude_record(1).payload["message"]["usage"], "output_tokens": 2}
        )
        new = _claude_record(2)
        proofs = inspect_usage_candidates([old, new], [_claude_obs(10, new)])
        assert [p.correspondence for p in proofs] == ["represented", "represented"]
        assert all(p.matched_observation_ids == (10,) for p in proofs)
        assert all(2 in p.context_raw_event_ids for p in proofs)
        assert all(p.supplier_sources == ("/s/a.jsonl",) for p in proofs)

    def test_older_matching_key_does_not_certify_a_newer_candidate(self) -> None:
        old = _claude_record(
            1, usage={**_claude_record(1).payload["message"]["usage"], "output_tokens": 2}
        )
        new = _claude_record(2)
        proofs = inspect_usage_candidates([old, new], [_claude_obs(10, old)])
        assert {p.reason for p in proofs} == {"newer_snapshot_not_captured"}
        assert {p.correspondence for p in proofs} == {"missing"}

    def test_dominated_by_a_newer_snapshot_in_another_source(self) -> None:
        mine = _claude_record(1)
        elsewhere = _claude_record(
            9, source="/s/b.jsonl", usage={**mine.payload["message"]["usage"], "output_tokens": 50}
        )
        obs = _claude_obs(10, elsewhere)
        (proof,) = inspect_usage_candidates([mine], [obs])
        assert (proof.correspondence, proof.reason) == (
            "represented",
            "dominated_by_newer_snapshot",
        )
        assert proof.supplier_sources == ("/s/b.jsonl",)

    def test_cross_source_value_conflict_is_unprovable_and_order_independent(self) -> None:
        a = _claude_record(1, source="/s/a.jsonl")
        b = _claude_record(
            2,
            source="/s/b.jsonl",
            usage={**a.payload["message"]["usage"], "output_tokens": 99},
        )
        obs = _claude_obs(10, b)
        forward = inspect_usage_candidates([a, b], [obs])
        backward = inspect_usage_candidates([b, a], [obs])
        assert {p.reason for p in forward} == {"cross_source_conflict"}
        assert {p.correspondence for p in backward} == {"unprovable"}
        assert all(p.protected_observation_ids == (10,) for p in forward)

    def test_native_order_must_agree_with_snapshot_dominance(self) -> None:
        newer_first = _claude_record(5, line_no=1)
        older_last = _claude_record(
            6, line_no=9, usage={**newer_first.payload["message"]["usage"], "output_tokens": 1}
        )
        # Highest raw ID is not the latest by native position: raw-ID order is not native order.
        proofs = inspect_usage_candidates(
            [newer_first, _claude_record(7, line_no=0), older_last], [_claude_obs(1, older_last)]
        )
        assert {p.reason for p in proofs} == {"native_order_unproven"}

    @pytest.mark.parametrize(
        "usage",
        [
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            {"input_tokens": 3, "output_tokens": 5},
            {
                "input_tokens": -1,
                "output_tokens": 5,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ],
    )
    def test_current_native_terminal_snapshots_fabricate_no_usage(
        self, usage: dict[str, Any]
    ) -> None:
        (proof,) = inspect_usage_candidates([_claude_record(1, usage=usage)], [])
        assert (proof.correspondence, proof.reason) == (
            "intentional_omission",
            "claude_terminal_snapshot",
        )
        assert retention_reasons([proof]) == frozenset()

    def test_malformed_snapshot_without_a_verified_identity_stays_a_candidate(self) -> None:
        record = _claude_record(1, message_id=None, usage={"input_tokens": 3, "output_tokens": 5})
        (proof,) = inspect_usage_candidates([record], [])
        assert (proof.correspondence, proof.reason) == ("missing", "no_exact_link")

    def test_null_marker_snapshot_is_audit_not_promoted(self) -> None:
        record = _claude_record(1, contract=None)
        obs = _claude_obs(
            3, record, observation_key=None, provenance="unknown", usage_contract=None
        )
        (proof,) = inspect_usage_candidates([record], [obs])
        assert (proof.correspondence, proof.reason) == ("represented", "linked_audit")

    def test_non_usage_records_are_benign_and_failures_are_never_dropped(self) -> None:
        user = UsageReplayRecord(
            payload={"type": "user"},
            event_type="user",
            ts="",
            session_id="sess-1",
            host="claude-code",
            host_basis="handle",
            source_label="/s/a.jsonl",
            line_no=1,
            ordinal=None,
            raw_event_id=1,
        )
        failure = UsageReplayFailure("/s/a.jsonl", "invalid_json", raw_event_id=2)
        proofs = inspect_usage_candidates([user, failure], [])
        assert [(p.correspondence, p.reason) for p in proofs] == [
            ("unprovable", "decode_invalid_json")
        ]

    def test_channel_filter_excludes_other_channels_without_evaluating(self) -> None:
        record = _claude_record(1)
        (proof,) = inspect_usage_candidates([record], [], channel="rollout")
        assert proof.correspondence == "excluded_channel"
        assert retention_reasons([proof]) == frozenset()

    def test_cross_host_session_collision_is_not_a_match(self) -> None:
        record = _claude_record(1)
        obs = _claude_obs(4, record, host="opencode")
        (proof,) = inspect_usage_candidates([record], [obs])
        assert proof.correspondence == "unprovable"


_CODEX_USAGE = {
    "input_tokens": 10,
    "cached_input_tokens": 4,
    "cache_write_input_tokens": 0,
    "output_tokens": 2,
    "reasoning_output_tokens": 0,
    "total_tokens": 12,
}


def _codex_records(
    raw_start: int = 1, *, source: str = "/c/r.jsonl", rate_limit: bool = False
) -> list[UsageReplayRecord]:
    def rec(i: int, etype: str, payload: dict[str, Any]) -> UsageReplayRecord:
        return UsageReplayRecord(
            payload=payload,
            event_type=etype,
            ts="2026-01-01T00:00:00Z",
            session_id="thr-1",
            host="codex",
            host_basis="handle",
            source_label=source,
            line_no=i,
            ordinal=i,
            raw_event_id=raw_start + i,
        )

    usage = dict(_CODEX_USAGE)
    last = dict(_CODEX_USAGE)
    info = {"total_token_usage": last, "last_token_usage": last}
    out = [
        rec(0, "session_meta", {"id": "thr-1"}),
        rec(1, "event_msg", {"type": "task_started", "turn_id": "t1"}),
        rec(2, "turn_context", {"turn_id": "t1", "model": "gpt-x"}),
        rec(
            3,
            "token_usage_record",
            {"thread_id": "thr-1", "turn_id": "t1", "response_id": "r1", "usage": usage},
        ),
        rec(4, "event_msg", {"type": "token_count", "info": info}),
    ]
    if rate_limit:
        out.append(rec(5, "event_msg", {"type": "token_count", "info": None}))
    out.append(rec(6, "event_msg", {"type": "task_complete", "turn_id": "t1"}))
    return out


_CODEX_COMPONENTS = codex_components(_CODEX_USAGE)[:4]


def _codex_obs(obs_id: int, rec: UsageReplayRecord, **overrides: Any) -> dict[str, Any]:
    obs = {
        "id": obs_id,
        "host": "codex",
        "session_id": "thr-1",
        "channel": "rollout",
        "provenance": "measured",
        "model": "gpt-x",
        "input_tokens": _CODEX_COMPONENTS[0],
        "output_tokens": _CODEX_COMPONENTS[1],
        "cache_read_input_tokens": _CODEX_COMPONENTS[2],
        "cache_creation_input_tokens": _CODEX_COMPONENTS[3],
        "observation_key": None,
        "source_raw_event_id": rec.raw_event_id,
        "source_path": rec.source_label,
        "source_line_no": rec.line_no,
        "source_ordinal": rec.ordinal,
        "request_id": "r1",
        "turn_id": "t1",
        "request_identity_basis": "native_response",
    }
    obs.update(overrides)
    return obs


class TestPureCodexProof:
    def test_adjacent_notification_coalesces_with_its_response_record(self) -> None:
        records = _codex_records(rate_limit=True)
        obs = _codex_obs(1, records[3])
        proofs = inspect_usage_candidates(records, [obs])
        assert [(p.correspondence, p.reason) for p in proofs] == [
            ("represented", "native_response"),
            ("represented", "coalesced_copy"),
            ("intentional_omission", "codex_rate_limit_notification"),
        ]

    def test_missing_model_and_closure_do_not_invalidate_audit_correspondence(self) -> None:
        records = [r for r in _codex_records() if r.event_type not in {"turn_context"}]
        records = [r for r in records if r.payload.get("type") != "task_complete"]
        obs = _codex_obs(
            1, records[2 if records[2].event_type == "token_usage_record" else 3], model=None
        )
        proofs = inspect_usage_candidates(records, [obs])
        assert proofs[0].correspondence == "represented"

    def test_missing_recognition_context_is_not_assumed(self) -> None:
        records = _codex_records()
        obs = _codex_obs(1, records[3], turn_id="other-turn")
        (first, _) = inspect_usage_candidates(records, [obs])
        assert first.correspondence == "unprovable"

    def test_nonadvancing_total_with_changed_last_usage_is_a_new_candidate(self) -> None:
        records = _codex_records()
        notif = records[4]
        total = notif.payload["info"]["total_token_usage"]
        changed = UsageReplayRecord(
            **{
                **notif.__dict__,
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": total,
                        "last_token_usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                },
                "line_no": 7,
                "ordinal": 7,
                "raw_event_id": 20,
            }
        )
        records.append(changed)
        records.sort(key=lambda r: r.ordinal)
        proofs = inspect_usage_candidates(records, [_codex_obs(1, records[3])])
        assert ("missing", "no_exact_link") in {(p.correspondence, p.reason) for p in proofs}

    def test_unkeyed_notification_cannot_borrow_another_sources_representation(self) -> None:
        records = _codex_records()
        notif = records[4]
        alone = UsageReplayRecord(
            **{
                **notif.__dict__,
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 3, "output_tokens": 1},
                        "last_token_usage": {"input_tokens": 3, "output_tokens": 1},
                    },
                },
                "source_label": "/c/other.jsonl",
                "raw_event_id": 90,
            }
        )
        other_obs = _codex_obs(
            5, alone, request_id=None, input_tokens=3, output_tokens=1, cache_read_input_tokens=0
        )
        other_obs["source_raw_event_id"] = 77  # linked to a different raw row
        (proof,) = [
            p
            for p in inspect_usage_candidates([alone], [other_obs])
            if p.source_label == "/c/other.jsonl"
        ]
        assert proof.correspondence == "missing"

    def test_conflicting_response_copies_stay_separate_candidates(self) -> None:
        a = _codex_records(1, source="/c/a.jsonl")
        b = _codex_records(100, source="/c/b.jsonl")
        b[3] = UsageReplayRecord(
            **{
                **b[3].__dict__,
                "payload": {
                    **b[3].payload,
                    "usage": {**_CODEX_USAGE, "output_tokens": 3},
                },
            }
        )
        proofs = inspect_usage_candidates([*a, *b], [_codex_obs(1, a[3])])
        by_source = {(p.source_label, p.raw_event_id): p.correspondence for p in proofs}
        assert by_source[("/c/a.jsonl", 4)] == "represented"
        assert by_source[("/c/b.jsonl", 103)] == "missing"

    def test_duplicate_or_reset_positions_make_order_unproven(self) -> None:
        records = _codex_records()
        records[4] = UsageReplayRecord(**{**records[4].__dict__, "ordinal": 3, "line_no": 3})
        proofs = inspect_usage_candidates(records, [_codex_obs(1, records[3])])
        assert {p.reason for p in proofs} == {"native_order_unproven"}


class TestRetainedDecodeTotality:
    def _poison(self, db: Path, source: Path, raw: Any, event_type: str = "assistant") -> None:
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
                "event_type, raw_line, parsed_json) VALUES(?, 's', 'claude-code', 'handle', ?, "
                "900, ?, ?, '{}')",
                (_OLD, str(source), event_type, raw),
            )
            conn.execute(
                "UPDATE meta SET value = (SELECT MAX(id) FROM raw_events) "
                "WHERE key = 'usage_derive_raw_id'"
            )
            conn.commit()
        finally:
            conn.close()

    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            ("{not json", "decode_invalid_json"),
            ("[1, 2]", "decode_non_object_payload"),
            (zlib.compress(b"{not json"), "decode_invalid_json"),
            (zlib.compress(b"[]"), "decode_non_object_payload"),
            (b"\x00not-zlib", "decode_invalid_compression"),
            (zlib.compress(b"\xff\xfe{}"), "decode_invalid_encoding"),
            ("[" * 200_000, "decode_recursion"),
        ],
    )
    def test_corruption_is_bounded_unprovable_evidence(
        self, claude: Any, raw: Any, reason: str
    ) -> None:
        db, source = claude
        self._poison(db, source, raw)
        assert ("unprovable", reason) in _outcomes(_proofs(db, source))
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert "usage_proof_unprovable" in result["retention_reasons"]

    def test_deeply_nested_packed_json_is_not_a_crash(self, claude: Any) -> None:
        db, source = claude
        self._poison(db, source, zlib.compress(b"[" * 200_000))
        assert ("unprovable", "decode_recursion") in _outcomes(_proofs(db, source))

    def test_retained_replay_still_skips_what_it_always_skipped(self, claude: Any) -> None:
        db, source = claude
        self._poison(db, source, "{not json")
        before = _sql(db, "SELECT COUNT(*) FROM usage_events")
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        backfill_usage_incremental(db)
        assert _sql(db, "SELECT COUNT(*) FROM usage_events") == before


class TestProofLimits:
    @pytest.mark.parametrize(
        "limits",
        [
            ProofLimits(max_items=2),
            ProofLimits(max_encoded_bytes=64),
            ProofLimits(max_decoded_bytes=64),
        ],
    )
    def test_each_threshold_vetoes_without_partial_success(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch, limits: ProofLimits
    ) -> None:
        db, source = claude
        monkeypatch.setattr(scope_mod, "PROOF_LIMITS", limits)
        with pytest.raises(scope_mod.UsageProofLimit):
            _proofs(db, source)
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert result["retained"] == {"raw_events": 4}
        assert result["retention_reasons"] == ["usage_proof_limit"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]
        assert prune(db, config=_CFG, dry_run=True)["retention_reasons"] == ["usage_proof_limit"]

    def test_single_oversized_plain_and_compressed_expansion(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        big = json.dumps({"type": "user", "pad": "x" * 200_000})
        conn = connect(db)
        try:
            for line_no, raw in ((901, big), (902, zlib.compress(big.encode()))):
                conn.execute(
                    "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, "
                    "line_no, event_type, raw_line, parsed_json) VALUES(?, 's', 'claude-code', "
                    "'handle', ?, ?, 'user', ?, '{}')",
                    (_OLD, str(source), line_no, raw),
                )
            conn.commit()
        finally:
            conn.close()
        # Encoded bytes stay small for the compressed row; its expansion must still be bounded.
        monkeypatch.setattr(scope_mod, "PROOF_LIMITS", ProofLimits(max_decoded_bytes=100_000))
        with pytest.raises(scope_mod.UsageProofLimit):
            _proofs(db, source)

    def test_unrelated_observation_population_does_not_trip_the_budget(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, source = claude
        conn = connect(db)
        try:
            for i in range(50):
                conn.execute(
                    "INSERT INTO usage_events(ts, session_id, channel, provenance, host) "
                    "VALUES('2026-01-01T00:00:00Z', ?, 'transcript', 'unknown', 'claude-code')",
                    (f"unrelated-{i}",),
                )
            conn.commit()
        finally:
            conn.close()
        monkeypatch.setattr(scope_mod, "PROOF_LIMITS", ProofLimits(max_items=20))
        assert {p.correspondence for p in _proofs(db, source)} == {"represented"}


class TestPureness:
    def test_module_imports_no_storage_or_file_apis(self) -> None:
        tree = ast.parse(Path(proof_mod.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in tree.body:  # module level; TYPE_CHECKING-only imports are not runtime
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not imported & {"sqlite3", "pathlib", "os", "subprocess", "zlib"}
        assert not any("pricing" in m or "writers" in m.rsplit(".", 1)[-1] for m in imported)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "open" not in names

    def test_proof_runs_with_all_io_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def deny(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("pure proof touched I/O")

        monkeypatch.setattr(sqlite3, "connect", deny)
        monkeypatch.setattr(builtins, "open", deny)
        monkeypatch.setattr(Path, "read_text", deny)
        monkeypatch.setattr(Path, "open", deny)
        record = _claude_record(1)
        (proof,) = inspect_usage_candidates([record], [_claude_obs(10, record)])
        assert proof.correspondence == "represented"

    def test_inputs_are_not_mutated(self) -> None:
        record = _claude_record(1)
        obs = _claude_obs(10, record)
        snapshot = (copy.deepcopy(record.payload), copy.deepcopy(obs))
        inspect_usage_candidates([record], [obs])
        assert (record.payload, obs) == snapshot


class TestSanitizerParity:
    _CONTEXTS = {
        "claude": ("claude-code", "assistant"),
        "session_meta": ("codex", "session_meta"),
        "turn_context": ("codex", "turn_context"),
        "event_msg": ("codex", "event_msg"),
        "token_usage_record": ("codex", "token_usage_record"),
    }

    def test_every_path_the_proof_reads_is_registry_protected(self) -> None:
        assert set(PROOF_IDENTITY_PATHS) == set(self._CONTEXTS)
        for shape, paths in PROOF_IDENTITY_PATHS.items():
            host, event_type = self._CONTEXTS[shape]
            rules = pii._protocol_rules(host, event_type)
            assert rules is not None, shape
            for path in paths:
                assert path in rules, (shape, path)
                assert rules[path].shape is None  # protected identity, not an opaque exemption

    def test_registered_context_is_required_to_prove_anything(self) -> None:
        assert pii.is_replay_safe_history_context(host="claude-code", event_type="assistant")
        assert not pii.is_replay_safe_history_context(host="mystery", event_type="assistant")


class TestPerSourcePrune:
    def _two_sources(self, tmp_path: Path, first: str, second: str) -> Path:
        db = tmp_path / "history.db"
        for name in (first, second):
            shutil.copy(_CLAUDE, tmp_path / name)
        # Duplicate sessions across sources carry the same message IDs; ingest in this order.
        for name in (first, second):
            backfill_raw_events(db, jsonl_files=[tmp_path / name], host="claude-code")
        backfill_usage_incremental(db)
        return db

    @pytest.mark.parametrize("order", [("a.jsonl", "b.jsonl"), ("b.jsonl", "a.jsonl")])
    def test_cross_source_dedup_survivor_keeps_required_context_in_any_order(
        self, tmp_path: Path, order: tuple[str, str]
    ) -> None:
        db = self._two_sources(tmp_path, *order)
        usage_before = _sql(db, "SELECT COUNT(*) FROM usage_events")
        _make_old(db)
        applied = prune(db, config=_CFG)
        assert applied["retention_reasons"] == []
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert _sql(db, "SELECT COUNT(*) FROM usage_events") == usage_before
        # Every observation is protected by a hold on its actual supplier source.
        assert _sql(
            db,
            "SELECT COUNT(*) FROM usage_events u WHERE NOT EXISTS (SELECT 1 FROM "
            "usage_replay_holds h WHERE h.source_path = u.source_path)",
        ) == [(0,)]

    def test_supplier_without_protection_or_context_blocks_deletion(self, tmp_path: Path) -> None:
        db = self._two_sources(tmp_path, "a.jsonl", "b.jsonl")
        supplier = _sql(db, "SELECT DISTINCT source_path FROM usage_events")
        assert len(supplier) == 1
        # Age only the other source; its observations are supplied by an unprotected source
        # that still has raw, so deleting is fine; remove the supplier's raw and it is not.
        other = next(
            p for p in (tmp_path / "a.jsonl", tmp_path / "b.jsonl") if str(p) != supplier[0][0]
        )
        _sql(db, "DELETE FROM raw_events WHERE source_path = ?", (supplier[0][0],))
        _make_old(db, f"source_path = '{other}'")
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert "usage_replay_context_required" in result["retention_reasons"]

    def test_dry_run_matches_actual_and_writes_nothing(self, tmp_path: Path) -> None:
        db = self._two_sources(tmp_path, "a.jsonl", "b.jsonl")
        _make_old(db)
        dump = _sql(db, "SELECT COUNT(*) FROM raw_events")
        before_holds = _sql(db, "SELECT * FROM usage_replay_holds")
        dry = prune(db, config=_CFG, dry_run=True)
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == dump
        assert _sql(db, "SELECT * FROM usage_replay_holds") == before_holds
        applied = prune(db, config=_CFG)
        for key in ("deleted", "retained", "retention_reasons"):
            assert dry[key] == applied[key]

    def test_dry_run_overlay_sees_earlier_planned_effects(self, tmp_path: Path) -> None:
        db = self._two_sources(tmp_path, "a.jsonl", "b.jsonl")
        _make_old(db)
        # Break the later source's dependency only; the earlier source's virtual deletion
        # must be visible, so dry-run and actual still agree on the retained set.
        _sql(db, "UPDATE usage_events SET output_tokens = output_tokens + 1")
        dry = prune(db, config=_CFG, dry_run=True)
        applied = prune(db, config=_CFG)
        for key in ("deleted", "retained", "retention_reasons"):
            assert dry[key] == applied[key]

    def test_second_source_failure_keeps_first_commit_and_stops(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = tmp_path / "history.db"
        for name in ("a.jsonl", "b.jsonl"):
            shutil.copy(_CLAUDE, tmp_path / name)
        backfill_raw_events(db, jsonl_files=[tmp_path / "a.jsonl"], host="claude-code")
        backfill_raw_events(db, jsonl_files=[tmp_path / "b.jsonl"], host="claude-code")
        backfill_usage_incremental(db)
        _make_old(db)
        calls = {"n": 0}
        real_now = lifecycle._now

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected second source failure")
            return real_now()

        monkeypatch.setattr(lifecycle, "_now", flaky)
        with pytest.raises(RuntimeError, match="injected") as caught:
            prune(db, config=_CFG)
        notes = " ".join(getattr(caught.value, "__notes__", []))
        assert "earlier sources may already be committed" in notes
        assert str(tmp_path) not in notes
        monkeypatch.undo()
        remaining = _sql(db, "SELECT DISTINCT source_path FROM raw_events")
        assert len(remaining) == 1  # first source committed, the failing one untouched
        assert (
            _sql(db, "SELECT COUNT(*) FROM raw_events WHERE source_path = ?", remaining[0])[0][0]
            == 4
        )
        retry = prune(db, config=_CFG)
        assert retry["retention_reasons"] == []
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert prune(db, config=_CFG)["deleted"] == {"raw_events": 0}

    def test_conflicting_cross_source_copy_is_retained_in_both_orders(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        a = tmp_path / "a.jsonl"
        b = tmp_path / "b.jsonl"
        shutil.copy(_CLAUDE, a)
        lines = [json.loads(line) for line in _CLAUDE.read_text().splitlines()]
        for line in lines:
            usage = line.get("message", {}).get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
                usage["output_tokens"] += 1
        b.write_text("".join(json.dumps(line) + "\n" for line in lines))
        backfill_raw_events(db, jsonl_files=[a], host="claude-code")
        backfill_raw_events(db, jsonl_files=[b], host="claude-code")
        backfill_usage_incremental(db)
        _make_old(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert "usage_proof_unprovable" in result["retention_reasons"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events")[0][0] == 8
