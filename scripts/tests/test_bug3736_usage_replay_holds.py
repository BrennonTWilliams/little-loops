"""BUG-3736: prune/rebuild/catch-up must not erase replay-derived usage.

Production ingestion, derive, prune and rebuild run against temporary
databases and committed fixtures. The copied originals are removed before any
replay, so a passing test also proves no path reopens them.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

import little_loops.session_store as store
from little_loops.cli.session import main_session
from little_loops.session_store import (
    SCHEMA_VERSION,
    backfill_raw_events,
    backfill_usage_incremental,
    compact,
    connect,
    ensure_db,
    lifecycle,
    prune,
    rebuild,
)
from little_loops.session_store.usage_refresh import refresh_raw_events
from little_loops.session_store.writers import USAGE_NOT_HELD_SQL

_FIXTURES = Path(__file__).parent / "fixtures"
_CLAUDE = _FIXTURES / "claude" / "transcript-v2.1.284.jsonl"
_CHANGING = _FIXTURES / "claude" / "transcript-changing-usage-observed.jsonl"
_CODEX = _FIXTURES / "codex" / "rollout-exec-resume-v0.158.0.jsonl"

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


def _usage(db: Path) -> list[tuple]:
    """Every column of every non-live observation except the surrogate id."""
    conn = connect(db)
    try:
        columns = [
            row[1] for row in conn.execute("PRAGMA table_info(usage_events)") if row[1] != "id"
        ]
        return [
            tuple(row)
            for row in conn.execute(
                f"SELECT {', '.join(columns)} FROM usage_events WHERE channel IS NOT 'live' "
                "ORDER BY channel, session_id, source_path, source_line_no, ts, request_id"
            )
        ]
    finally:
        conn.close()


def _make_old(db: Path, where: str = "1 = 1", *, ts: bool = True) -> None:
    """Mark rows compacted, and (by default) past any retention cutoff."""
    if ts:
        _sql(db, f"UPDATE raw_events SET compacted = 1, ts = ? WHERE {where}", (_OLD,))
    else:
        _sql(db, f"UPDATE raw_events SET compacted = 1 WHERE {where}")


def _ingest(tmp_path: Path, fixture: Path, host: str, name: str) -> tuple[Path, Path]:
    source = tmp_path / name
    shutil.copy(fixture, source)
    db = tmp_path / "history.db"
    backfill_raw_events(db, jsonl_files=[source], host=host)
    backfill_usage_incremental(db)
    return db, source


def _holds(db: Path) -> list[tuple]:
    return _sql(db, "SELECT source_path, host, channel, reason FROM usage_replay_holds")


def _downgrade_and_remigrate(db: Path) -> None:
    """Re-run the v59 migration (and its legacy seeds) against current store state."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP TABLE usage_replay_holds")
        # A v58 store predates every later migration too (v60, BUG-3755).
        conn.execute("ALTER TABLE loop_events DROP COLUMN to_state")
        conn.execute("UPDATE meta SET value = '58' WHERE key = 'schema_version'")
        conn.commit()
    finally:
        conn.close()
    ensure_db(db)


@pytest.fixture
def claude(tmp_path: Path) -> tuple[Path, Path]:
    return _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")


@pytest.fixture
def pruned_claude(claude: tuple[Path, Path]) -> tuple[Path, list[tuple]]:
    """Claude store whose only source was pruned whole; returns the db and usage snapshot."""
    db, source = claude
    before = _usage(db)
    assert len(before) == 2
    source.unlink()
    _make_old(db)
    result = prune(db, config=_CFG)
    assert result["deleted"] == {"raw_events": 4}
    assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
    assert _usage(db) == before
    return db, before


class TestWholeSourceReplayGuard:
    def test_rebuild_after_prune_preserves_usage(self, pruned_claude: Any) -> None:
        db, before = pruned_claude
        rebuild(db)
        rebuild(db)
        assert _usage(db) == before

    def test_max_below_checkpoint_catch_up_preserves_usage(self, pruned_claude: Any) -> None:
        db, before = pruned_claude
        # Pruning removed the highest raw IDs, so the checkpoint now exceeds MAX(id).
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") != [("0",)]
        backfill_usage_incremental(db)
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_normalizer_mismatch_catch_up_preserves_usage(
        self, pruned_claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, before = pruned_claude
        monkeypatch.setattr(lifecycle, "_USAGE_DERIVE_VERSION", "future-normalizer")
        backfill_usage_incremental(db)
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_first_enable_missing_metadata_preserves_usage(self, pruned_claude: Any) -> None:
        db, before = pruned_claude
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_reingested_pruned_positions_cannot_duplicate_or_reprice(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")
        before = _usage(db)
        _make_old(db)
        prune(db, config=_CFG)
        # The original is still on disk: re-ingesting yields new, larger raw IDs.
        assert backfill_raw_events(db, jsonl_files=[source], host="claude-code") == 4
        source.unlink()
        backfill_usage_incremental(db)
        rebuild(db)
        assert _usage(db) == before

    def test_codex_whole_source_prune_survives_rebuild_and_append(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CODEX, "codex", "rollout.jsonl")
        before = _usage(db)
        assert {row[0] for row in before} == {"rollout"} or before
        source.unlink()
        _make_old(db)
        assert prune(db, config=_CFG)["retained"] == {"raw_events": 0}
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        rebuild(db)
        assert _usage(db) == before
        # An ordinary append to the same rollout: new raw row, id above the checkpoint.
        conn = connect(db)
        try:
            path = str(source)
            conn.execute(
                "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
                "event_type, raw_line, parsed_json) "
                "VALUES('2099-01-01T00:00:00Z', 's', 'codex', 'handle', ?, 999, 'event_msg', "
                "'{}', '{}')",
                (path,),
            )
            conn.commit()
        finally:
            conn.close()
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_unheld_source_still_replays_while_held_source_is_preserved(
        self, tmp_path: Path
    ) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "held.jsonl")
        held_before = _usage(db)
        _make_old(db)
        prune(db, config=_CFG)
        other = tmp_path / "other.jsonl"
        shutil.copy(_CHANGING, other)
        backfill_raw_events(db, jsonl_files=[other], host="claude-code")
        backfill_usage_incremental(db)
        both = _usage(db)
        assert len(both) == len(held_before) + 1
        source.unlink()
        other.unlink()
        rebuild(db)
        assert _usage(db) == both

    def test_live_rows_and_unknown_audit_rows_survive(self, pruned_claude: Any) -> None:
        db, before = pruned_claude
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, input_tokens, output_tokens, "
            "channel) VALUES('2026-01-01T00:00:00Z', NULL, 'm', 1, 2, 'live')",
        )
        rebuild(db)
        backfill_usage_incremental(db)
        assert _usage(db) == before
        assert _sql(db, "SELECT COUNT(*) FROM usage_events WHERE channel = 'live'") == [(1,)]

    def test_new_raw_appends_keep_autoincrement_order(self, pruned_claude: Any) -> None:
        db, _ = pruned_claude
        highest = _sql(db, "SELECT seq FROM sqlite_sequence WHERE name = 'raw_events'")[0][0]
        _sql(
            db,
            "INSERT INTO raw_events(ts, session_id, host, source_path, line_no, event_type, "
            "raw_line, parsed_json) VALUES('2099-01-01T00:00:00Z', 's', 'claude-code', 'n', 1, "
            "'user', '{}', '{}')",
        )
        assert _sql(db, "SELECT id FROM raw_events")[0][0] > highest

    def test_refresh_of_held_source_is_rejected_before_invalidating(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "session.jsonl")
        _sql(
            db,
            "INSERT INTO usage_source_cursors(source_path, host, session_id, device, inode, "
            "committed_offset, committed_line_no, tail_sha256, source_mtime_ns, "
            "derived_raw_event_id, status, updated_at) "
            "VALUES(?, 'claude-code', 's', 1, 1, 1, 1, 'x', 1, 1, 'complete', 'now')",
            (str(source.resolve()),),
        )
        _make_old(db)
        prune(db, config=_CFG)
        # Leave one surviving row so the source is non-empty yet held.
        _sql(
            db,
            "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
            "event_type, raw_line, parsed_json) VALUES(?, 's', 'claude-code', 'handle', ?, 1, "
            "'user', '{}', '{}')",
            (_OLD, str(source)),
        )
        usage = _usage(db)
        meta = _sql(db, "SELECT key, value FROM meta WHERE key LIKE 'usage_derive_%' ORDER BY key")
        cursors = _sql(db, "SELECT source_path FROM usage_source_cursors")
        from little_loops.session_store.sessions import handles_from_paths

        result = refresh_raw_events(db, handles=handles_from_paths([source], "claude-code"))
        assert [(o.status, o.reason) for o in result.sources] == [("skipped", "usage_replay_held")]
        assert _usage(db) == usage
        assert (
            _sql(db, "SELECT key, value FROM meta WHERE key LIKE 'usage_derive_%' ORDER BY key")
            == meta
        )
        assert _sql(db, "SELECT source_path FROM usage_source_cursors") == cursors


class TestPruneEligibility:
    def test_source_with_one_recent_row_is_held_whole(self, claude: Any) -> None:
        db, _ = claude
        _make_old(db, "line_no <= 3")
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert result["retained"] == {"raw_events": 3}
        assert result["retention_reasons"] == ["usage_replay_context_required"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]
        assert _holds(db) == []

    def test_uncompacted_aged_row_holds_whole_source(self, claude: Any) -> None:
        db, _ = claude
        _sql(db, "UPDATE raw_events SET ts = ?", (_OLD,))
        _sql(db, "UPDATE raw_events SET compacted = 1 WHERE line_no <= 3")
        result = prune(db, config=_CFG)
        assert result["retained"] == {"raw_events": 3}
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]

    def test_partial_claude_source_keeps_latest_snapshot_through_rebuild(
        self, tmp_path: Path
    ) -> None:
        db, source = _ingest(tmp_path, _CHANGING, "claude-code", "session.jsonl")
        before = _usage(db)
        assert before[0][3] == 481 or any(481 in row for row in before)
        source.unlink()
        _make_old(db, "line_no BETWEEN 3 AND 5", ts=False)
        assert prune(db, config=_CFG)["deleted"] == {"raw_events": 0}
        rebuild(db)
        assert _usage(db) == before

    @pytest.mark.parametrize(
        "mutate",
        [
            "DELETE FROM meta WHERE key = 'usage_derive_raw_id'",
            "DELETE FROM meta WHERE key = 'usage_derive_version'",
            "UPDATE meta SET value = 'garbage' WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = '-4' WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = '' WHERE key = 'usage_derive_raw_id'",
            "UPDATE meta SET value = 'old-normalizer' WHERE key = 'usage_derive_version'",
        ],
    )
    def test_unverified_checkpoint_holds_every_source(self, claude: Any, mutate: str) -> None:
        db, _ = claude
        _make_old(db)
        _sql(db, mutate)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 0}
        assert result["retained"] == {"raw_events": 4}
        assert result["retention_reasons"] == ["usage_derive_unverified"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]

    def test_checkpoint_lagging_the_source_reports_pending(self, claude: Any) -> None:
        db, _ = claude
        _make_old(db)
        _sql(db, "UPDATE meta SET value = '1' WHERE key = 'usage_derive_raw_id'")
        result = prune(db, config=_CFG)
        assert result["retained"] == {"raw_events": 4}
        assert result["retention_reasons"] == ["usage_derive_pending"]

    def test_non_usage_source_keeps_row_level_retention(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        for line_no, ts in ((1, _OLD), (2, "2099-01-01T00:00:00Z")):
            _sql(
                db,
                "INSERT INTO raw_events(ts, session_id, host, source_path, line_no, event_type, "
                "raw_line, parsed_json, compacted) VALUES(?, 's', 'claude-code', 'plain.jsonl', "
                "?, 'user', '{}', '{}', 1)",
                (ts, line_no),
            )
        backfill_usage_incremental(db)
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 1}
        assert result["retained"] == {"raw_events": 0}
        assert result["retention_reasons"] == []
        assert _holds(db) == []

    def test_gated_and_noop_calls_carry_default_fields(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        gated = prune(db)
        assert gated["retained"] == {"raw_events": 0}
        assert gated["retention_reasons"] == []
        noop = prune(db, config=_CFG)
        assert noop["retained"] == {"raw_events": 0}
        assert noop["retention_reasons"] == []
        disabled = {
            "analytics": {
                "retention": {
                    "raw_event_max_age_days": None,
                    "min_project_age_days": 0,
                    "min_db_size_mb": 0,
                }
            }
        }
        assert prune(db, config=disabled)["retention_reasons"] == []

    def test_dry_run_matches_apply_and_writes_nothing(self, claude: Any) -> None:
        db, _ = claude
        _make_old(db, "line_no <= 3")
        dry = prune(db, config=_CFG, dry_run=True)
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]
        applied = prune(db, config=_CFG)
        for key in ("deleted", "retained", "retention_reasons"):
            assert dry[key] == applied[key]
        # Whole-source delete parity too.
        _make_old(db)
        dry = prune(db, config=_CFG, dry_run=True)
        assert _holds(db) == []
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]
        applied = prune(db, config=_CFG)
        for key in ("deleted", "retained", "retention_reasons"):
            assert dry[key] == applied[key]
        assert applied["deleted"] == {"raw_events": 4}

    def test_repeated_prune_is_stable(self, pruned_claude: Any) -> None:
        db, before = pruned_claude
        again = prune(db, config=_CFG)
        assert again["deleted"] == {"raw_events": 0}
        assert again["retained"] == {"raw_events": 0}
        assert len(_holds(db)) == 1
        assert _usage(db) == before

    def test_held_rows_are_counted_once_and_sources_are_isolated(self, tmp_path: Path) -> None:
        db, source = _ingest(tmp_path, _CLAUDE, "claude-code", "a.jsonl")
        other = tmp_path / "b.jsonl"
        shutil.copy(_CHANGING, other)
        backfill_raw_events(db, jsonl_files=[other], host="claude-code")
        backfill_usage_incremental(db)
        _make_old(db)
        _sql(
            db,
            "UPDATE raw_events SET ts = '2099-01-01T00:00:00Z' WHERE source_path = ?",
            (str(other),),
        )
        result = prune(db, config=_CFG)
        assert result["deleted"] == {"raw_events": 4}
        assert result["retained"] == {"raw_events": 0}  # recent rows are not aged candidates
        assert [row[0] for row in _holds(db)] == [str(source)]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events WHERE source_path = ?", (str(other),)) != [
            (0,)
        ]


class TestAtomicPrune:
    def test_prune_holds_the_write_lock_while_proving(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, _ = claude
        _make_old(db)
        real = lifecycle._plan_raw_prune
        seen: list[str] = []

        def contend(conn: sqlite3.Connection, cutoff: str) -> Any:
            other = sqlite3.connect(str(db), timeout=0)
            try:
                other.execute("BEGIN IMMEDIATE")
                seen.append("acquired")
            except sqlite3.OperationalError as exc:
                seen.append(str(exc))
            finally:
                other.close()
            return real(conn, cutoff)

        monkeypatch.setattr(lifecycle, "_plan_raw_prune", contend)
        prune(db, config=_CFG)
        assert seen and "locked" in seen[0]

    def test_pre_commit_failure_rolls_back_markers_and_rows(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, _ = claude
        _make_old(db)
        usage = _usage(db)

        def boom() -> str:
            raise RuntimeError("injected")

        monkeypatch.setattr(lifecycle, "_now", boom)
        with pytest.raises(RuntimeError, match="injected"):
            prune(db, config=_CFG)
        monkeypatch.undo()
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(4,)]
        assert _holds(db) == []
        assert _usage(db) == usage
        # The failed attempt released its write lock.
        assert prune(db, config=_CFG)["deleted"] == {"raw_events": 4}

    def test_vacuum_failure_does_not_undo_retention(
        self, claude: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, _ = claude
        _make_old(db)

        def broken(*args: Any, **kwargs: Any) -> Any:
            raise sqlite3.OperationalError("injected vacuum failure")

        monkeypatch.setattr(store, "open_history", broken)
        result = prune(db, config=_CFG)
        assert result["pruned"] and not result["vacuumed"]
        assert _sql(db, "SELECT COUNT(*) FROM raw_events") == [(0,)]
        assert len(_holds(db)) == 1


class TestLegacySeeding:
    def test_migration_creates_holds_table_and_keeps_version_constants(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        assert SCHEMA_VERSION == 60
        assert _sql(db, "SELECT COUNT(*) FROM usage_replay_holds") == [(0,)]
        assert lifecycle._USAGE_DERIVE_VERSION == "enh3651-v1"
        assert lifecycle.REBUILD_DERIVE_VERSION == "enh3678-v1"

    def test_rebuild_predicate_matches_shared_hold_fragment(self) -> None:
        predicate = lifecycle._REBUILD_TABLE_PREDICATES["usage_events"]
        assert predicate == f"channel IS NOT 'live' AND {USAGE_NOT_HELD_SQL}"

    def test_dangling_raw_pointer_seeds_a_source_hold(self, claude: Any) -> None:
        db, source = claude
        before = _usage(db)
        _sql(db, "DELETE FROM raw_events WHERE line_no >= 3")  # pre-fix partial prune
        _downgrade_and_remigrate(db)
        assert (str(source), "*", "*", "dangling_raw_link") in _holds(db)
        source.unlink()
        rebuild(db)
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_unlinked_usage_seeds_a_population_hold_that_blocks_a_second_set(
        self, claude: Any
    ) -> None:
        db, _ = claude
        _sql(db, "UPDATE usage_events SET source_path = NULL, source_raw_event_id = NULL")
        before = _usage(db)
        _downgrade_and_remigrate(db)
        holds = _holds(db)
        assert holds and all(row[0] is None for row in holds)
        # Raw is intact, but the population is held: replay must not add a second set.
        rebuild(db)
        backfill_usage_incremental(db)
        assert _usage(db) == before

    def test_unlinked_usage_before_first_derive_is_left_for_catch_up(self, claude: Any) -> None:
        db, _ = claude
        _sql(db, "UPDATE usage_events SET source_path = NULL, source_raw_event_id = NULL")
        _sql(db, "DELETE FROM meta WHERE key LIKE 'usage_derive_%'")
        _downgrade_and_remigrate(db)
        assert _holds(db) == []

    def test_missing_first_line_seeds_a_source_hold(self, claude: Any) -> None:
        db, source = claude
        before = _usage(db)
        _sql(db, "DELETE FROM raw_events WHERE line_no = 1")
        _downgrade_and_remigrate(db)
        assert (str(source), "*", "*", "missing_first_line") in _holds(db)
        source.unlink()
        rebuild(db)
        assert _usage(db) == before

    def test_healthy_store_seeds_no_holds(self, claude: Any) -> None:
        db, _ = claude
        _downgrade_and_remigrate(db)
        assert _holds(db) == []


class TestRetentionReporting:
    def _run(self, db: Path, *argv: str, capsys: pytest.CaptureFixture[str]) -> str:
        import os

        cwd = os.getcwd()
        os.chdir(db.parent)
        try:
            from unittest.mock import patch

            with patch("sys.argv", ["ll-session", "--db", str(db), *argv]):
                assert main_session() == 0
        finally:
            os.chdir(cwd)
        return capsys.readouterr().out

    def test_prune_json_and_text_report_retained(
        self, claude: Any, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db, _ = claude
        _make_old(db, "line_no <= 3")
        monkeypatch.setattr(
            "little_loops.config.core.resolve_config_path",
            lambda cwd: _write_config(db.parent),
        )
        payload = json.loads(self._run(db, "prune", "--json", capsys=capsys))
        assert payload["retained"] == {"raw_events": 3}
        assert payload["retention_reasons"] == ["usage_replay_context_required"]
        text = self._run(db, "prune", capsys=capsys)
        assert "Retained 3" in text and "usage_replay_context_required" in text

    def test_compact_and_prune_propagates_retention(self, claude: Any) -> None:
        db, _ = claude
        _make_old(db, "line_no <= 3")
        _sql(db, "UPDATE raw_events SET ts = '2099-01-01T00:00:00Z' WHERE line_no = 4")
        result = compact(db, config=_CFG, and_prune=True)
        assert result["pruned_rows"] == 0
        assert result["retained_rows"] == 3
        assert result["retention_reasons"] == ["usage_replay_context_required"]


def _write_config(directory: Path) -> Path:
    path = directory / "ll-config.json"
    path.write_text(json.dumps(_CFG))
    return path
