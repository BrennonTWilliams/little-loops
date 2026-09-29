"""ENH-3543 conservative Codex coverage through stored usage rows."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from little_loops.history_reader import aggregate_usage, cost_attribution, waste_attribution
from little_loops.history_reader.usage import select_usage_coverage, select_usage_observations
from little_loops.session_store import (
    backfill_raw_events,
    connect,
    ensure_db,
    rebuild,
    record_loop_run_summary,
    record_usage_event,
)
from little_loops.session_store.sessions import SessionHandle

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def _handle(path: Path, cwd: Path) -> SessionHandle:
    native = json.loads(path.read_text().splitlines()[0])["payload"]
    return SessionHandle("codex", native["id"], path, cwd, 1.0)


def _stored_rollout(db: Path, fixture: str, cwd: Path) -> str:
    path = FIXTURES / fixture
    thread_id = json.loads(path.read_text().splitlines()[0])["payload"]["id"]
    ensure_db(db)
    backfill_raw_events(db, handles=[_handle(path, cwd)])
    rebuild(db)
    return thread_id


def _live(db: Path, thread_id: str, *, run_id: str = "run-live") -> None:
    record_usage_event(
        db,
        run_id=run_id,
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
        session_id=thread_id,
        identity_basis="host_observed",
        invocation_id="local-invocation",
    )


def test_current_rollout_only_has_canonical_request_rows(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-exec-resume-v0.158.0.jsonl", tmp_path)
    with connect(db) as conn:
        selection = select_usage_coverage(conn, host="codex", session_id=thread_id)

    assert selection.coverage == "non_overlapping"
    assert len(selection.audit_rows) == len(selection.selected_rows) == 2
    assert all(
        row["request_identity_basis"] == "native_response" for row in selection.selected_rows
    )


def test_live_and_stored_rollout_overlap_stays_audit_only_across_filters(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-exec-resume-v0.158.0.jsonl", tmp_path)
    _live(db, thread_id)
    with connect(db) as conn:
        full = select_usage_coverage(conn, host="codex", session_id=thread_id)
        recent = select_usage_coverage(
            conn, host="codex", session_id=thread_id, since="2026-09-29T08:00:00Z"
        )
        attributed = select_usage_coverage(
            conn, host="codex", session_id=thread_id, require_run_id=True
        )

    assert full.coverage == "overlap_unresolved"
    assert full.reason == "live_replay_join_unproven"
    assert len(full.audit_rows) == 3
    assert full.selected_rows == ()
    assert full.groups[0].channel_subtotals["live"]["events"] == 1
    assert full.groups[0].channel_subtotals["rollout"]["events"] == 2
    assert len(recent.audit_rows) == len(attributed.audit_rows) == 1
    assert recent.selected_rows == attributed.selected_rows == ()
    assert recent.coverage == attributed.coverage == "overlap_unresolved"
    assert all(row["_coverage_reason"] == "live_replay_join_unproven" for row in recent.audit_rows)

    grouped = aggregate_usage(group_by="session", db=db)
    assert len(grouped) == 1
    assert grouped[0]["coverage"] == "overlap_unresolved"
    assert grouped[0]["input_tokens"] is None
    assert grouped[0]["cost_usd"] is None
    assert grouped[0]["channel_subtotals"]["rollout"]["events"] == 2
    recent_grouped = aggregate_usage(group_by="session", since="2026-09-29T08:00:00Z", db=db)
    assert recent_grouped[0]["coverage"] == "overlap_unresolved"
    assert recent_grouped[0]["input_tokens"] is None
    cost = cost_attribution(group_by="session_id", db=db)
    assert cost[0]["cost_usd"] is None
    assert "gen_ai.usage.input_tokens" not in cost[0]
    state_cost = cost_attribution(group_by="state", db=db)
    assert next(row for row in state_cost if row["state"] == "check")["cost_usd"] is None


def test_old_rollout_and_live_only_scope_are_unknown(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-exec-resume.jsonl", tmp_path)
    with connect(db) as conn:
        old = select_usage_coverage(conn, host="codex", session_id=thread_id)
    assert old.coverage == "unknown"
    assert old.reason == "rollout_request_identity_unverified"
    assert len(old.audit_rows) == 3 and old.selected_rows == ()

    db_live = tmp_path / "live.db"
    ensure_db(db_live)
    _live(db_live, "thread-live")
    with connect(db_live) as conn:
        live = select_usage_coverage(conn, host="codex", session_id="thread-live")
    assert live.coverage == "unknown"
    assert live.reason == "codex_live_scope_unknown"
    assert len(live.audit_rows) == 1 and live.selected_rows == ()


def test_mixed_current_and_old_rollout_keeps_partial_request_coverage_unknown(
    tmp_path: Path,
) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-mixed-v0.158.0-synthetic.jsonl", tmp_path)
    with connect(db) as conn:
        selection = select_usage_coverage(conn, host="codex", session_id=thread_id)

    assert selection.coverage == "unknown"
    assert selection.reason == "rollout_request_identity_unverified"
    assert len(selection.audit_rows) == 2
    assert {row["request_identity_basis"] for row in selection.audit_rows} == {
        "native_response",
        "unverified",
    }
    assert selection.selected_rows == ()


def test_native_request_without_closed_turn_does_not_become_canonical(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-exec-resume-v0.158.0.jsonl", tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE usage_events SET turn_id = NULL WHERE id = "
            "(SELECT MIN(id) FROM usage_events WHERE channel = 'rollout')"
        )
    with connect(db) as conn:
        selection = select_usage_coverage(conn, host="codex", session_id=thread_id)

    assert selection.coverage == "unknown"
    assert selection.reason == "rollout_request_identity_unverified"
    assert len(selection.audit_rows) == 2 and selection.selected_rows == ()


def test_pair_filter_admits_verified_live_but_not_other_or_unverified_hosts(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    _live(db, "shared-thread")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, host, host_basis, channel, "
            "identity_basis, input_tokens) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "2026-09-29T09:00:00Z",
                "shared-thread",
                "m",
                "claude-code",
                "handle",
                "transcript",
                None,
                1,
            ),
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, model, host, channel, "
            "identity_basis, input_tokens) VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-29T09:00:00Z", "shared-thread", "m", "codex", "live", None, 1),
        )
    with connect(db) as conn:
        rows = list(select_usage_observations(conn, host="codex", session_id="shared-thread"))
    assert len(rows) == 1
    assert rows[0]["identity_basis"] == "host_observed"


def test_waste_rates_unavailable_when_run_row_has_rollout_counterpart(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    thread_id = _stored_rollout(db, "rollout-exec-resume-v0.158.0.jsonl", tmp_path)
    _live(db, thread_id)
    record_loop_run_summary(
        db,
        run_id="run-live",
        loop_name="coverage-loop",
        terminated_by="error",
        final_state="check",
    )

    rows = waste_attribution(db=db)
    assert len(rows) == 1
    assert rows[0]["coverage"] == "overlap_unresolved"
    assert rows[0]["tokens_total"] is None
    assert rows[0]["tokens_wasted"] is None
    assert rows[0]["waste_pct"] is None
