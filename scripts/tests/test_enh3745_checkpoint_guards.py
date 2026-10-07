"""ENH-3745 phase 1: validated checkpoints, bootstrap, retention floor and freshness reads."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from little_loops.session_store import (
    backfill_usage_incremental,
    connect,
    ensure_db,
    lifecycle,
    rebuild,
    refresh_usage_source,
    usage_source_freshness,
)
from little_loops.session_store.backend import connect_readonly

_CLAUDE = Path(__file__).parent / "fixtures" / "claude"


def _sql(db: Path, statement: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def _usage(db: Path) -> list[tuple]:
    return _sql(
        db,
        "SELECT id, session_id, model, input_tokens, output_tokens, channel, observation_key "
        "FROM usage_events ORDER BY id",
    )


def _checkpoint(db: Path) -> dict[str, str]:
    return dict(_sql(db, "SELECT key, value FROM meta WHERE key LIKE 'usage_derive_%'"))


@pytest.fixture
def store(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "session.jsonl"
    source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
    db = tmp_path / "history.db"
    refresh_usage_source(db, source)
    assert len(_usage(db)) == 2
    return db, source


class TestCheckpointReading:
    def test_valid_checkpoint_carries_its_floor(self, store: tuple[Path, Path]) -> None:
        db, _ = store
        conn = connect(db)
        try:
            state = lifecycle._read_usage_checkpoint(conn)
        finally:
            conn.close()
        assert state.valid and state.floor == int(_checkpoint(db)["usage_derive_raw_id"])

    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ("DELETE FROM meta WHERE key LIKE 'usage_derive_%'", "absent"),
            ("DELETE FROM meta WHERE key = 'usage_derive_raw_id'", "partial"),
            ("DELETE FROM meta WHERE key = 'usage_derive_version'", "partial"),
            ("UPDATE meta SET value = 'old' WHERE key = 'usage_derive_version'", "version_changed"),
            ("UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'", "invalid"),
            ("UPDATE meta SET value = '-4' WHERE key = 'usage_derive_raw_id'", "invalid"),
            ("UPDATE meta SET value = '' WHERE key = 'usage_derive_raw_id'", "invalid"),
            ("UPDATE meta SET value = '1.5' WHERE key = 'usage_derive_raw_id'", "invalid"),
            (
                "UPDATE meta SET value = '99999999999999999999' WHERE key = 'usage_derive_raw_id'",
                "invalid",
            ),
            ("UPDATE meta SET value = '999999' WHERE key = 'usage_derive_raw_id'", "contradictory"),
            ("DELETE FROM sqlite_sequence WHERE name = 'raw_events'", "sequence_unprovable"),
            (
                "UPDATE sqlite_sequence SET seq = 'x' WHERE name = 'raw_events'",
                "sequence_unprovable",
            ),
        ],
    )
    def test_malformed_or_contradictory_proof_is_classified(
        self, store: tuple[Path, Path], mutation: str, expected: str
    ) -> None:
        db, _ = store
        _sql(db, mutation)
        conn = connect(db)
        try:
            state = lifecycle._read_usage_checkpoint(conn)
        finally:
            conn.close()
        assert state.status == expected and not state.valid
        assert state.floor is None

    def test_version_is_checked_before_the_raw_id_is_converted(
        self, store: tuple[Path, Path]
    ) -> None:
        db, _ = store
        _sql(db, "UPDATE meta SET value = 'old' WHERE key = 'usage_derive_version'")
        _sql(db, "UPDATE meta SET value = 'not-a-number' WHERE key = 'usage_derive_raw_id'")
        conn = connect(db)
        try:
            assert lifecycle._read_usage_checkpoint(conn).status == "version_changed"
        finally:
            conn.close()

    def test_proved_zero_is_valid_in_an_empty_store_without_a_sequence_row(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _sql(
            db,
            "INSERT INTO meta(key, value) VALUES('usage_derive_version', ?)",
            (lifecycle._USAGE_DERIVE_VERSION,),
        )
        _sql(db, "INSERT INTO meta(key, value) VALUES('usage_derive_raw_id', '0')")
        conn = connect(db)
        try:
            state = lifecycle._read_usage_checkpoint(conn)
        finally:
            conn.close()
        assert state.valid and state.floor == 0

    def test_sequence_never_raises_a_floor(self, store: tuple[Path, Path]) -> None:
        db, _ = store
        _sql(db, "UPDATE sqlite_sequence SET seq = seq + 50 WHERE name = 'raw_events'")
        before = _checkpoint(db)
        conn = connect(db)
        try:
            assert lifecycle._read_usage_checkpoint(conn).floor == int(
                before["usage_derive_raw_id"]
            )
        finally:
            conn.close()


class TestDeriveGuard:
    @pytest.mark.parametrize(
        "mutation",
        [
            "DELETE FROM meta WHERE key LIKE 'usage_derive_%'",
            "DELETE FROM meta WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = 'old' WHERE key = 'usage_derive_version'",
            "UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = '-1' WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = '999999' WHERE key = 'usage_derive_raw_id'",
            "DELETE FROM sqlite_sequence WHERE name = 'raw_events'",
        ],
    )
    def test_established_store_with_unusable_proof_skips_untouched(
        self, store: tuple[Path, Path], mutation: str
    ) -> None:
        db, _ = store
        _sql(db, mutation)
        usage_before, meta_before = _usage(db), _checkpoint(db)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            disposition = lifecycle._derive_usage_incremental_disposition(conn)
            conn.commit()
        finally:
            conn.close()
        assert disposition.status == "skipped"
        assert disposition.reason and disposition.reason.startswith("checkpoint_")
        assert disposition.count == 0
        assert _usage(db) == usage_before
        assert _checkpoint(db) == meta_before
        assert backfill_usage_incremental(db) == 0

    def test_smaller_surviving_max_is_not_a_reset(self, store: tuple[Path, Path]) -> None:
        db, _ = store
        before_usage, before_meta = _usage(db), _checkpoint(db)
        _sql(db, "DELETE FROM raw_events WHERE id > 1")  # retention removed the newest rows
        assert backfill_usage_incremental(db) == 0
        assert _usage(db) == before_usage
        assert _checkpoint(db) == before_meta  # floor preserved, not lowered

    def test_floor_survives_refresh_after_retention(self, store: tuple[Path, Path]) -> None:
        db, source = store
        floor = int(_checkpoint(db)["usage_derive_raw_id"])
        _sql(db, "DELETE FROM raw_events")
        with source.open("a") as handle:
            handle.write("\n")
        backfill_usage_incremental(db)
        assert int(_checkpoint(db)["usage_derive_raw_id"]) >= floor

    def test_pristine_store_bootstraps_without_deleting_live_usage(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, "
            "channel) VALUES('2026-01-01T00:00:00Z', 'live', 'm', 1, 2, 'live')",
        )
        source = tmp_path / "session.jsonl"
        source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
        from little_loops.session_store import backfill_raw_events

        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        assert _checkpoint(db) == {}
        assert backfill_usage_incremental(db) == 2
        rows = _usage(db)
        assert sum(1 for r in rows if r[5] == "live") == 1
        assert len(rows) == 3
        assert int(_checkpoint(db)["usage_derive_raw_id"]) > 0

    def test_legacy_unlinked_usage_blocks_bootstrap(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, "
            "channel) VALUES('2026-01-01T00:00:00Z', 's', 'm', 1, 2, 'transcript')",
        )
        source = tmp_path / "session.jsonl"
        source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
        from little_loops.session_store import backfill_raw_events

        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        before = _usage(db)
        assert backfill_usage_incremental(db) == 0
        assert _usage(db) == before
        assert _checkpoint(db) == {}

    def test_replay_holds_block_bootstrap(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES('/x.jsonl', '*', '*', 'dangling_raw_link', '2026-01-01T00:00:00Z')",
        )
        source = tmp_path / "session.jsonl"
        source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
        from little_loops.session_store import backfill_raw_events

        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        assert backfill_usage_incremental(db) == 0
        assert _usage(db) == []

    def test_held_append_is_reported_as_skipped_work(self, store: tuple[Path, Path]) -> None:
        db, source = store
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, host, channel, reason, created_at) "
            "VALUES(?, '*', '*', 'dangling_raw_link', '2026-01-01T00:00:00Z')",
            (str(source),),
        )
        floor = int(_checkpoint(db)["usage_derive_raw_id"])
        _sql(
            db,
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json) "
            "VALUES('2026-01-01T00:00:00Z', 's', 'claude-code', 'handle', ?, 99, 'assistant', "
            "'{}', '{}')",
            (str(source),),
        )
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            disposition = lifecycle._derive_usage_incremental_disposition(conn)
            conn.commit()
        finally:
            conn.close()
        assert disposition.status == "derived"
        assert [(src, lo > floor, hi > floor) for src, lo, hi in disposition.held_skipped] == [
            (str(source), True, True)
        ]
        # The scan advanced past the held row; durable pending (phase 3) keeps it reachable.
        assert int(_checkpoint(db)["usage_derive_raw_id"]) > floor


class TestRebuildStamping:
    def test_rebuild_carries_a_valid_floor_forward(self, store: tuple[Path, Path]) -> None:
        db, _ = store
        _sql(db, "UPDATE meta SET value = '1' WHERE key = 'usage_derive_raw_id'")
        rebuild(db)
        assert int(_checkpoint(db)["usage_derive_raw_id"]) >= 1

    @pytest.mark.parametrize(
        "mutation",
        [
            "UPDATE meta SET value = 'old' WHERE key = 'usage_derive_version'",
            "UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'",
            "DELETE FROM meta WHERE key = 'usage_derive_raw_id'",
        ],
    )
    def test_rebuild_leaves_invalid_proof_untouched(
        self, store: tuple[Path, Path], mutation: str
    ) -> None:
        db, _ = store
        _sql(db, mutation)
        before = _checkpoint(db)
        rebuild(db)
        assert _checkpoint(db) == before

    def test_rebuild_does_not_lower_a_floor_after_retention(self, store: tuple[Path, Path]) -> None:
        db, _ = store
        floor = int(_checkpoint(db)["usage_derive_raw_id"])
        _sql(db, "DELETE FROM raw_events WHERE id > 1")
        rebuild(db)
        assert int(_checkpoint(db)["usage_derive_raw_id"]) == floor

    def test_rebuild_bootstraps_a_pristine_store(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        source = tmp_path / "session.jsonl"
        source.write_bytes((_CLAUDE / "transcript-v2.1.284.jsonl").read_bytes())
        from little_loops.session_store import backfill_raw_events

        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        rebuild(db)
        assert int(_checkpoint(db)["usage_derive_raw_id"]) > 0


class TestFreshnessReads:
    def test_malformed_cursor_numbers_are_unknown_not_an_exception(
        self, store: tuple[Path, Path]
    ) -> None:
        db, source = store
        assert usage_source_freshness(db, source)["status"] == "fresh"
        _sql(db, "UPDATE usage_source_cursors SET committed_offset = 'x'")
        result = usage_source_freshness(db, source)
        assert result["status"] == "unknown" and result["reason"] == "cursor_invalid"

    def test_invalid_checkpoint_is_unknown_not_fresh(self, store: tuple[Path, Path]) -> None:
        db, source = store
        _sql(db, "UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'")
        result = usage_source_freshness(db, source)
        assert (result["status"], result["reason"]) == ("unknown", "checkpoint_invalid")

    def test_retention_does_not_make_a_source_derive_pending(
        self, store: tuple[Path, Path]
    ) -> None:
        db, source = store
        _sql(db, "DELETE FROM raw_events WHERE id > 1")
        assert usage_source_freshness(db, source)["status"] == "fresh"

    def test_supplied_snapshot_is_used_and_left_open(self, store: tuple[Path, Path]) -> None:
        db, source = store
        conn = connect_readonly(db)
        try:
            conn.execute("BEGIN")
            assert usage_source_freshness(db, source, conn=conn)["status"] == "fresh"
            assert conn.in_transaction  # not committed/rolled back by the reader
            conn.rollback()
        finally:
            conn.close()

    def test_autocommit_or_writable_connections_are_rejected_unchanged(
        self, store: tuple[Path, Path]
    ) -> None:
        db, source = store
        idle = connect_readonly(db)
        writable = sqlite3.connect(str(db))
        try:
            for conn in (idle, writable):
                result = usage_source_freshness(db, source, conn=conn)
                assert (result["status"], result["reason"]) == (
                    "unknown",
                    "read_snapshot_unavailable",
                )
            assert not idle.in_transaction
            writable.execute("BEGIN")
            result = usage_source_freshness(db, source, conn=writable)
            assert result["reason"] == "read_snapshot_unavailable"  # active but writable
            assert writable.in_transaction
        finally:
            idle.close()
            writable.rollback()
            writable.close()

    def test_pinned_snapshot_keeps_older_figures_across_a_concurrent_commit(
        self, store: tuple[Path, Path]
    ) -> None:
        db, source = store
        conn = connect_readonly(db)
        try:
            conn.execute("BEGIN")
            conn.execute("SELECT COUNT(*) FROM meta").fetchone()  # pin the snapshot
            _sql(db, "UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'")
            pinned: dict[str, Any] = usage_source_freshness(db, source, conn=conn)  # type: ignore[assignment]
            assert pinned["status"] == "fresh"
            conn.rollback()
        finally:
            conn.close()
        assert usage_source_freshness(db, source)["reason"] == "checkpoint_invalid"

    def test_path_swap_is_unknown(self, store: tuple[Path, Path], tmp_path: Path) -> None:
        db, source = store
        data = source.read_bytes()
        source.unlink()
        source.write_bytes(data)  # new inode, same bytes
        result = usage_source_freshness(db, source)
        assert result["status"] == "unknown" and result["reason"] == "source_changed"


class TestPreMigrationReaders:
    def test_freshness_on_a_member_without_the_new_tables_falls_back_without_writes(
        self, store: tuple[Path, Path]
    ) -> None:
        db, source = store
        raw = sqlite3.connect(str(db))
        for table in (
            "usage_source_state",
            "usage_source_pending",
            "usage_observation_witnesses",
            "usage_observation_dependencies",
            "usage_completion_dependencies",
        ):
            raw.execute(f"DROP TABLE {table}")
        raw.commit()
        raw.close()
        before = db.read_bytes()
        result = usage_source_freshness(db, source)  # legacy fallback; no ensure_db/migration
        assert result["status"] == "fresh"
        assert db.read_bytes() == before
