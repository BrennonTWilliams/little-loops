"""Claude cache-rate cutover: stored selection, correction, and freshness."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.ctx_stats import (
    _compute_cache_rate_from_jsonl,
    _compute_cache_rate_from_usage,
    main_ctx_stats,
)
from little_loops.session_store import SessionHandle, connect, ensure_db
from little_loops.session_store.lifecycle import refresh_usage_source

_CAPTURE = Path(__file__).parent / "fixtures" / "claude" / "transcript-v2.1.284.jsonl"
_CHANGING = (
    Path(__file__).parent / "fixtures" / "claude" / "transcript-changing-usage-observed.jsonl"
)


def _captured_session(tmp_path: Path) -> tuple[Path, SessionHandle]:
    source = tmp_path / "session.jsonl"
    shutil.copyfile(_CAPTURE, source)
    session_id = json.loads(source.read_text(encoding="utf-8").splitlines()[0])["sessionId"]
    handle = SessionHandle("claude-code", session_id, source, tmp_path, source.stat().st_mtime)
    db = tmp_path / "history.db"
    ensure_db(db)
    return db, handle


def test_captured_duplicate_uuids_correct_to_two_native_requests(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        direct = _compute_cache_rate_from_jsonl(tmp_path, "claude-code")
    assert direct is not None
    assert direct["cache_read"] == 76858
    assert direct["cache_write"] == 22446
    assert direct["uncached"] == 36
    assert direct["counts"]["hit_rate_pct"] == {"known": 4, "missing": 0}

    assert refresh_usage_source(db, handle.path)["usage_events"] == 2
    stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stored is not None
    assert (stored["cache_read"], stored["cache_write"], stored["uncached"]) == (
        38429,
        11223,
        18,
    )
    assert stored["hit_rate_pct"] == direct["hit_rate_pct"] == 77
    assert stored["counts"]["hit_rate_pct"] == {"known": 2, "missing": 0}
    assert stored["provenance"] == "measured"
    assert stored["coverage"] == "non_overlapping"
    assert stored["freshness"] == "fresh"
    assert stored["as_of_offset"] == handle.path.stat().st_size


def test_pair_filter_excludes_same_id_other_host_and_legacy_attribution(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'rollout', 'codex', 'handle', 999, 999, 999)",
            (handle.session_id,),
        )
        conn.execute(
            "INSERT INTO usage_events(ts, session_id, channel, host, host_basis, "
            "input_tokens, cache_read_input_tokens, cache_creation_input_tokens) "
            "VALUES('t', ?, 'transcript', 'claude-code', NULL, 888, 888, 888)",
            (handle.session_id,),
        )
        conn.commit()
    finally:
        conn.close()
    stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stored is not None
    assert stored["cache_read"] == 38429
    assert stored["counts"]["cache_read"] == {"known": 2, "missing": 0}


def test_repeated_message_id_uses_final_observed_usage(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    shutil.copyfile(_CHANGING, handle.path)
    session_id = json.loads(handle.path.read_text(encoding="utf-8").splitlines()[0])["sessionId"]
    handle = SessionHandle("claude-code", session_id, handle.path, tmp_path, 1.0)
    assert refresh_usage_source(db, handle.path)["usage_events"] == 1
    conn = connect(db)
    try:
        assert conn.execute("SELECT output_tokens FROM usage_events").fetchone()[0] == 481
    finally:
        conn.close()
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["cache_read"] == 19809
    assert result["counts"]["hit_rate_pct"] == {"known": 1, "missing": 0}


def test_missing_native_id_is_unverified_and_partial_or_zero_is_unavailable(tmp_path: Path) -> None:
    sample = json.loads(_CAPTURE.read_text(encoding="utf-8").splitlines()[0])
    for case in ("missing_id", "partial", "zero"):
        case_dir = tmp_path / case
        case_dir.mkdir()
        db, handle = _captured_session(case_dir)
        record = json.loads(json.dumps(sample))
        if case == "missing_id":
            del record["message"]["id"]
        elif case == "partial":
            del record["message"]["usage"]["output_tokens"]
        else:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            ):
                record["message"]["usage"][key] = 0
        handle.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        refresh_usage_source(db, handle.path)
        result, diagnostic = _compute_cache_rate_from_usage(handle, db)
        if case == "missing_id":
            assert diagnostic is None and result is not None
            assert result["provenance"] == "unknown"
            assert result["qualification_reason"] == "unverified_usage"
            assert result["hit_rate_pct"] is None
        else:
            assert result is None
            assert diagnostic == "ingested_without_usage"


def test_four_stored_absence_diagnostics(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    assert _compute_cache_rate_from_usage(handle, tmp_path / "missing.db")[1] == "no_store"
    unreadable = tmp_path / "broken.db"
    unreadable.write_text("not a sqlite database", encoding="utf-8")
    assert _compute_cache_rate_from_usage(handle, unreadable)[1] == "unreadable_store"
    assert _compute_cache_rate_from_usage(handle, db)[1] == "session_not_ingested"

    no_usage = {
        "type": "assistant",
        "sessionId": handle.session_id,
        "timestamp": "2026-09-29T01:00:00Z",
        "message": {"id": "msg-no-usage", "role": "assistant", "content": []},
    }
    handle.path.write_text(json.dumps(no_usage) + "\n", encoding="utf-8")
    refresh_usage_source(db, handle.path)
    assert _compute_cache_rate_from_usage(handle, db)[1] == "ingested_without_usage"


def test_stale_append_and_unknown_tail_never_report_fresh(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    with handle.path.open("a", encoding="utf-8") as source:
        source.write(json.dumps({"type": "user", "sessionId": handle.session_id}) + "\n")
    stale, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and stale is not None
    assert stale["freshness"] == "stale"
    assert stale["lag_reason"] == "new_append"
    assert stale["as_of_offset"] < handle.path.stat().st_size

    with handle.path.open("a", encoding="utf-8") as source:
        source.write('{"type":')
    unknown, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and unknown is not None
    assert unknown["freshness"] == "unknown"
    assert unknown["lag_reason"] == "partial_tail"


def test_missing_cursor_after_refresh_is_unknown(tmp_path: Path) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute("DELETE FROM usage_source_cursors")
        conn.commit()
    finally:
        conn.close()
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    assert result["freshness"] == "unknown"
    assert result["lag_reason"] == "source_untracked"


def test_current_session_json_reads_store_with_as_of(tmp_path: Path, monkeypatch, capsys) -> None:
    db, handle = _captured_session(tmp_path)
    refresh_usage_source(db, handle.path)
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size, "
            "bytes_in, bytes_out, cache_hit) VALUES('t', ?, 'Read', 'h', 1, 2, 3, 0)",
            (handle.session_id,),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        assert main_ctx_stats(["--db", str(db), "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["cache_rate_source"] == "stored_usage"
    assert payload["cache_hit_rate_pct"] == 77
    assert payload["cache_rate_freshness"] == "fresh"
    assert payload["cache_rate_as_of_offset"] == handle.path.stat().st_size
    assert "Stored Claude usage unavailable" not in captured.err


def test_json_stderr_distinguishes_four_store_absences(tmp_path: Path, monkeypatch, capsys) -> None:
    db, handle = _captured_session(tmp_path)
    broken = tmp_path / "broken.db"
    broken.write_text("not sqlite", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
        cases = (
            (tmp_path / "missing.db", "no history store is available"),
            (broken, "history store is unreadable"),
            (db, "selected session has not been ingested"),
        )
        for path, expected in cases:
            main_ctx_stats(["--db", str(path), "--json"])
            captured = capsys.readouterr()
            json.loads(captured.out)
            assert expected in captured.err

        record = {
            "type": "assistant",
            "sessionId": handle.session_id,
            "timestamp": "2026-09-29T01:00:00Z",
            "message": {"id": "msg-no-usage", "role": "assistant", "content": []},
        }
        handle.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        refresh_usage_source(db, handle.path)
        main_ctx_stats(["--db", str(db), "--json"])
        captured = capsys.readouterr()
        json.loads(captured.out)
        assert "ingested without qualified usage observations" in captured.err


class TestEnH3746RetainedIngestionAdmission:
    """ENH-3746: ``_compute_cache_rate_from_usage`` admits a stored session
    when a verified source-attributed ``usage_events`` row exists, even
    after the original ``raw_events`` rows have been pruned (BUG-3736
    retention). The legacy raw-only check still admits a fresh
    ``refresh_usage_source`` ingest that lacks qualified observations.

    Six scenarios covered:
      1. Raw pruned, replay admit → rate stays visible
      2. Raw preserved, replay absent (legacy path) → admitted
      3. Raw preserved, replay absent, no qualified observation → ingested_without_usage
      4. Neither raw nor replay → session_not_ingested
      5. Other-host usage row does not admit (identity probe must match)
      6. Unverified usage row does not admit (``_verified_usage_identity`` is False)
    """

    def test_retained_replay_admits_after_raw_prune(self, tmp_path: Path) -> None:
        """After raw_events rows are deleted, a verified usage_events row
        still admits the session."""
        db, handle = _captured_session(tmp_path)
        refresh_usage_source(db, handle.path)
        before_raw = _compute_cache_rate_from_usage(handle, db)[0]
        assert before_raw is not None  # sanity: live raw path admits
        with connect(db) as conn:
            # Prune all raw_events rows whose path matches the handle.
            conn.execute(
                "DELETE FROM raw_events WHERE source_path IN (?, ?) AND host = ? AND session_id = ?",
                (
                    str(handle.path),
                    str(handle.path.expanduser().resolve()),
                    handle.host,
                    handle.session_id,
                ),
            )
            conn.commit()
        stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
        # The replay path picks up — the verified usage_events row proves
        # historical ingestion even with no raw.
        assert diagnostic is None and stored is not None
        assert stored["hit_rate_pct"] == before_raw["hit_rate_pct"] == 77

    def test_raw_only_admits_fresh_ingest_with_no_observations(self, tmp_path: Path) -> None:
        """A fresh refresh_usage_source ingest on a no_usage record admits
        the session via the legacy raw path (no usage_events row yet)."""
        db, handle = _captured_session(tmp_path)
        no_usage = {
            "type": "assistant",
            "sessionId": handle.session_id,
            "timestamp": "2026-09-29T01:00:00Z",
            "message": {"id": "msg-no-usage", "role": "assistant", "content": []},
        }
        handle.path.write_text(json.dumps(no_usage) + "\n", encoding="utf-8")
        refresh_usage_source(db, handle.path)
        stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
        # Legacy raw check admits the handle-path raw row, but no
        # qualified observation → ``ingested_without_usage``.
        assert diagnostic == "ingested_without_usage"
        assert stored is None

    def test_raw_preserved_replay_admits(self, tmp_path: Path) -> None:
        """A normal refresh + compute rate cycle admits via the legacy
        raw-only path (this is the existing happy path, regression-only)."""
        db, handle = _captured_session(tmp_path)
        refresh_usage_source(db, handle.path)
        stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic is None and stored is not None
        assert stored["hit_rate_pct"] == 77

    def test_session_with_neither_raw_nor_replay_is_not_ingested(self, tmp_path: Path) -> None:
        """Empty store + no usage_events row → session_not_ingested."""
        db, handle = _captured_session(tmp_path)
        # Neither refresh_usage_source nor any other writer has run.
        _, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic == "session_not_ingested"

    def test_other_host_usage_does_not_admit(self, tmp_path: Path) -> None:
        """A usage_events row with the right session_id but a different host
        does not satisfy _verified_usage_identity, so admission fails."""
        db, handle = _captured_session(tmp_path)
        with connect(db) as conn:
            conn.execute(
                "INSERT INTO usage_events(ts, host, host_basis, session_id, model, "
                "input_tokens, output_tokens, cache_read_input_tokens, "
                "cache_creation_input_tokens, cost_usd, channel, identity_basis, "
                "provenance) "
                "VALUES(?, ?, 'handle', ?, 'claude-haiku-4-5-20251001', "
                "10, 5, 1, 0, 0.001, 'transcript', 'host_observed', 'measured')",
                (
                    "2026-09-29T07:00:00Z",
                    "codex",  # different host from the handle's "claude-code"
                    handle.session_id,
                ),
            )
            conn.commit()
        _, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic == "session_not_ingested"

    def test_unverified_usage_does_not_admit(self, tmp_path: Path) -> None:
        """A usage_events row with host_basis != 'handle' fails the
        _verified_usage_identity check (live/rollout channels) and does
        not admit even though host+session_id match."""
        db, handle = _captured_session(tmp_path)
        with connect(db) as conn:
            conn.execute(
                "INSERT INTO usage_events(ts, host, host_basis, session_id, model, "
                "input_tokens, output_tokens, cache_read_input_tokens, "
                "cache_creation_input_tokens, cost_usd, channel, identity_basis, "
                "provenance) "
                "VALUES(?, ?, ?, ?, 'claude-haiku-4-5-20251001', "
                "10, 5, 1, 0, 0.001, ?, NULL, 'measured')",
                (
                    "2026-09-29T07:00:00Z",
                    handle.host,
                    "ingest",  # not 'handle' → unverified
                    handle.session_id,
                    "live",
                ),
            )
            conn.commit()
        _, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic == "session_not_ingested"


class TestEnH3746FreshnessSnapshotIsolation:
    """ENH-3746 AC #5 (partial coverage): the rate-path code uses a
    single SQLite connection across the admission + selection +
    freshness reads so the three reads cannot see a connection-open race.

    The implementation shares a single ``sqlite3.Connection`` between the
    admission predicate (``_has_verified_retained_ingestion`` /
    ``_has_ingested_raw``), ``select_usage_coverage`` and
    ``usage_source_freshness(..., conn=conn)``.

    These tests pin the connection-sharing contract by verifying the
    freshness field reflects the latest committed cursor state — they do
    NOT simulate a concurrent writer committing *between* the
    selection and freshness reads. The deeper race contract (a
    concurrent ``refresh_usage_source`` that bumps the cursor between
    our two reads) is left as a follow-up: SQLite's WAL mode gives
    each statement a fresh snapshot, and a true BEGIN IMMEDIATE on the
    readonly connection is blocked by ``PRAGMA query_only=ON``. A
    proper race test needs an isolation harness (separate process or
    a held-clock injection) that's out of scope for this PR.

    Note: these tests do not guard against a regression to two
    connections, since both single-threaded test paths read the latest
    committed cursor regardless of connection count. The connection-
    sharing pattern is a *latency / connection-open* optimization, not
    a snapshot-isolation mechanism in WAL mode without explicit
    transactions.
    """

    def test_bumped_cursor_visible_after_race(self, tmp_path: Path) -> None:
        """When a separate connection commits a cursor bump before the
        call, the function's freshness field reflects the bumped offset
        and timestamp. Pins the contract that the read path picks up
        the latest committed values.
        """
        db, handle = _captured_session(tmp_path)
        refresh_usage_source(db, handle.path)
        initial_offset = handle.path.stat().st_size
        with connect(db) as conn:
            row = conn.execute(
                "SELECT committed_offset FROM usage_source_cursors "
                "WHERE source_path = ?",
                (str(handle.path.expanduser().resolve()),),
            ).fetchone()
            assert row is not None and row[0] == initial_offset

        # Simulate a concurrent refresh_usage_source commit before the
        # function call: bump committed_offset and updated_at.
        writable = connect(db)
        try:
            writable.execute(
                "UPDATE usage_source_cursors SET committed_offset = ?, "
                "updated_at = '2099-01-01T00:00:00' "
                "WHERE source_path = ?",
                (
                    initial_offset + 1000,
                    str(handle.path.expanduser().resolve()),
                ),
            )
            writable.commit()
        finally:
            writable.close()

        stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic is None and stored is not None
        assert stored["as_of_offset"] == initial_offset + 1000
        assert stored["as_of"] == "2099-01-01T00:00:00"

    def test_pre_and_post_bump_cursor_consistency(self, tmp_path: Path) -> None:
        """Two sequential calls see pre-bump and post-bump cursor values
        consistently with the figure. ``hit_rate_pct`` is unchanged by
        the cursor bump (the figure is independent of the cursor), but
        the freshness field reflects the committed state of the cursor.
        """
        db, handle = _captured_session(tmp_path)
        refresh_usage_source(db, handle.path)
        initial_offset = handle.path.stat().st_size

        # Snapshot before the call.
        with connect(db) as conn:
            row = conn.execute(
                "SELECT committed_offset, updated_at FROM usage_source_cursors "
                "WHERE source_path = ?",
                (str(handle.path.expanduser().resolve()),),
            ).fetchone()
            assert row is not None
            pre_bump_updated_at = row[1]
            assert row[0] == initial_offset

        # Pre-bump call: reads the pre-bump cursor.
        stored, diagnostic = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic is None and stored is not None
        assert stored["as_of_offset"] == initial_offset
        assert stored["as_of"] == pre_bump_updated_at

        # Bump the cursor and verify a subsequent call sees it.
        writable = connect(db)
        try:
            writable.execute(
                "UPDATE usage_source_cursors SET committed_offset = ?, "
                "updated_at = '2099-01-01T00:00:00' "
                "WHERE source_path = ?",
                (
                    initial_offset + 1000,
                    str(handle.path.expanduser().resolve()),
                ),
            )
            writable.commit()
        finally:
            writable.close()

        stored2, diagnostic2 = _compute_cache_rate_from_usage(handle, db)
        assert diagnostic2 is None and stored2 is not None
        assert stored2["as_of_offset"] == initial_offset + 1000
        assert stored2["as_of"] == "2099-01-01T00:00:00"
        assert stored2["hit_rate_pct"] == stored["hit_rate_pct"] == 77
