"""Logical ``channel=`` acquisition scope on the usage coverage selectors (ENH-3748)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from little_loops.history_reader.usage import select_usage_coverage, select_usage_observations
from little_loops.session_store import connect, ensure_db

_INSERT = (
    "INSERT INTO usage_events(ts, session_id, model, host, host_basis, channel, "
    "identity_basis, provenance, input_tokens, output_tokens, "
    "cache_read_input_tokens, cache_creation_input_tokens) "
    "VALUES(?, ?, 'm', ?, ?, ?, ?, 'measured', 10, 2, 4, 0)"
)


def _db(tmp_path: Path, *, live: bool = True, rollout: bool = False) -> Path:
    """Verified claude transcript (explicit NULL channel) plus optional counterparts."""
    db = tmp_path / "history.db"
    ensure_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            _INSERT,
            ("2026-10-05T09:00:00Z", "session-a", "claude-code", "handle", None, None),
        )
        if live:
            # Sessionless live row: an unresolved possible counterpart.
            conn.execute(_INSERT, ("2026-10-05T09:00:01Z", None, None, None, "live", None))
            conn.execute(
                _INSERT,
                ("2026-10-05T09:00:02Z", "thread-z", "codex", None, "live", "host_observed"),
            )
        if rollout:
            conn.execute(
                _INSERT,
                ("2026-10-05T09:00:03Z", "thread-y", "codex", "handle", "rollout", None),
            )
    return db


def test_transcript_scope_excludes_live_counterparts_from_coverage(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with connect(db) as conn:
        unscoped = select_usage_coverage(conn)
        scoped = select_usage_coverage(conn, channel="transcript")
    assert unscoped.coverage == "overlap_unresolved"
    assert unscoped.selected_rows == ()
    assert scoped.coverage == "non_overlapping"
    assert [row["session_id"] for row in scoped.audit_rows] == ["session-a"]
    assert scoped.selected_rows == scoped.audit_rows
    assert len(scoped.groups) == 1
    assert set(scoped.groups[0].channel_subtotals) == {"transcript"}


def test_legacy_null_channel_with_session_resolves_to_transcript(tmp_path: Path) -> None:
    db = _db(tmp_path, live=False)
    with connect(db) as conn:
        transcript = select_usage_coverage(conn, channel="transcript")
        live = select_usage_coverage(conn, channel="live")
    assert len(transcript.audit_rows) == 1
    assert live.audit_rows == ()


def test_null_channel_without_session_resolves_to_live(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(_INSERT, ("2026-10-05T09:00:01Z", None, None, None, None, None))
    with connect(db) as conn:
        assert len(select_usage_coverage(conn, channel="live").audit_rows) == 1
        assert select_usage_coverage(conn, channel="transcript").audit_rows == ()


def test_all_three_channels_are_accepted_and_partition_rows(tmp_path: Path) -> None:
    db = _db(tmp_path, rollout=True)
    with connect(db) as conn:
        counts = {
            channel: len(list(select_usage_observations(conn, channel=channel)))
            for channel in ("live", "transcript", "rollout")
        }
        total = len(list(select_usage_observations(conn)))
    assert counts == {"live": 2, "transcript": 1, "rollout": 1}
    assert sum(counts.values()) == total


def test_out_of_channel_rows_absent_from_every_output(tmp_path: Path) -> None:
    db = _db(tmp_path, rollout=True)
    with connect(db) as conn:
        scoped = select_usage_coverage(conn, channel="rollout")
    assert {row["id"] for row in scoped.audit_rows} == {
        row["id"] for group in scoped.groups for row in group.audit_rows
    }
    for row in (*scoped.audit_rows, *scoped.selected_rows):
        assert row["session_id"] == "thread-y"
    for group in scoped.groups:
        assert set(group.channel_subtotals) == {"rollout"}


def test_unrelated_live_counterpart_cannot_change_transcript_scope(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with_live = _db(tmp_path / "a")
    without_live = _db(tmp_path / "b", live=False)
    with connect(with_live) as c1, connect(without_live) as c2:
        a = select_usage_coverage(c1, channel="transcript")
        b = select_usage_coverage(c2, channel="transcript")
    assert (a.coverage, a.reason) == (b.coverage, b.reason) == ("non_overlapping", None)
    assert [r["input_tokens"] for r in a.audit_rows] == [r["input_tokens"] for r in b.audit_rows]


def test_default_scope_still_blocks_unresolved_counterparts(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with connect(db) as conn:
        default = select_usage_coverage(conn)
        explicit_none = select_usage_coverage(conn, channel=None)
    assert default == explicit_none
    assert default.coverage == "overlap_unresolved"
    assert len(default.audit_rows) == 3


def test_unrecognized_stored_channel_is_not_dropped_by_default(tmp_path: Path) -> None:
    db = _db(tmp_path, live=False)
    with sqlite3.connect(db) as conn:
        conn.execute(_INSERT, ("2026-10-05T09:00:05Z", "s-x", "claude-code", None, "weird", None))
    with connect(db) as conn:
        assert len(select_usage_coverage(conn).audit_rows) == 2
        assert len(select_usage_coverage(conn, channel="transcript").audit_rows) == 1


def test_since_and_run_filters_cannot_certify_scoped_coverage(tmp_path: Path) -> None:
    db = _db(tmp_path, live=False, rollout=True)
    with sqlite3.connect(db) as conn:
        # Same verified identity on two channels: unresolved even if one row is windowed out.
        conn.execute(
            _INSERT,
            ("2026-10-05T08:00:00Z", "session-a", "claude-code", "handle", "live", "host_observed"),
        )
    with connect(db) as conn:
        unscoped = select_usage_coverage(conn, since="2026-10-05T08:30:00Z")
        scoped = select_usage_coverage(conn, channel="transcript", since="2026-10-05T08:30:00Z")
        no_run = select_usage_coverage(conn, channel="transcript", require_run_id=True)
    assert unscoped.coverage == "overlap_unresolved" and unscoped.selected_rows == ()
    # The live counterpart is outside the declared channel, so it is not an overlap input.
    assert scoped.coverage == "non_overlapping" and len(scoped.selected_rows) == 1
    assert no_run.audit_rows == () and no_run.coverage == "unknown"


def test_host_session_narrowing_applies_after_channel_scope(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with connect(db) as conn:
        scoped = select_usage_coverage(
            conn, host="claude-code", session_id="session-a", channel="transcript"
        )
        other = select_usage_coverage(
            conn, host="claude-code", session_id="session-a", channel="live"
        )
    assert scoped.coverage == "non_overlapping" and len(scoped.selected_rows) == 1
    assert other.audit_rows == ()


@pytest.mark.parametrize("bad", ["", "Transcript", "stored", "all"])
def test_invalid_channel_raises_on_populated_store(tmp_path: Path, bad: str) -> None:
    db = _db(tmp_path)
    with connect(db) as conn:
        with pytest.raises(ValueError, match="channel"):
            select_usage_coverage(conn, channel=bad)
        with pytest.raises(ValueError, match="channel"):
            list(select_usage_observations(conn, channel=bad))


def test_invalid_channel_raises_on_empty_store(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    ensure_db(db)
    with connect(db) as conn:
        with pytest.raises(ValueError, match="channel"):
            select_usage_coverage(conn, channel="bogus")
        with pytest.raises(ValueError, match="channel"):
            list(select_usage_observations(conn, channel="bogus"))


def test_invalid_channel_raises_on_legacy_store_before_early_return(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE usage_events(id INTEGER PRIMARY KEY, ts TEXT, session_id TEXT, "
        "model TEXT, input_tokens INTEGER, output_tokens INTEGER, "
        "cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER, cost_usd REAL)"
    )
    # The legacy-column early return would otherwise swallow an invalid channel.
    with pytest.raises(ValueError, match="channel"):
        select_usage_coverage(conn, host="claude-code", session_id="s", channel="bogus")
    with pytest.raises(ValueError, match="channel"):
        list(select_usage_observations(conn, host="claude-code", session_id="s", channel="bogus"))
    with pytest.raises(ValueError, match="channel"):
        select_usage_coverage(conn, host="claude-code", channel="bogus")
    conn.close()
