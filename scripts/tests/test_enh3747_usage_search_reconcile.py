"""ENH-3747: usage search evidence survives rebuild and source catch-up.

Search evidence is regenerated from committed ``usage_events`` rows, never from the
original transcript, so the tests delete the copied source and patch pricing to raise.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.history_reader import search as reader_search
from little_loops.session_store import (
    backfill_raw_events,
    backfill_usage_incremental,
    connect,
    ensure_db,
    lifecycle,
    prune,
    rebuild,
)
from little_loops.session_store import search as store_search
from little_loops.session_store.writers import (
    UsageSearchScope,
    _reconcile_usage_search,
    _usage_search_entry,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_CLAUDE = _FIXTURES / "claude" / "transcript-v2.1.284.jsonl"
_OLD = "2020-01-01T00:00:00Z"
_CFG = {
    "analytics": {
        "retention": {"raw_event_max_age_days": 1, "min_project_age_days": 0, "min_db_size_mb": 0}
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


def _fts(db: Path) -> list[tuple]:
    return sorted(
        _sql(db, "SELECT content, kind, ref, anchor, ts FROM search_index WHERE kind = 'usage'"),
        key=repr,
    )


def _usage_snapshot(db: Path) -> list[tuple]:
    return _sql(db, "SELECT * FROM usage_events ORDER BY id")


def _ingest(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "session.jsonl"
    shutil.copy(_CLAUDE, source)
    db = tmp_path / "history.db"
    backfill_raw_events(db, jsonl_files=[source], host="claude-code")
    backfill_usage_incremental(db)
    return db, source


def _prune_whole(db: Path, source: Path) -> None:
    source.unlink()
    _sql(db, "UPDATE raw_events SET compacted = 1, ts = ?", (_OLD,))
    assert prune(db, config=_CFG)["deleted"] == {"raw_events": 4}


@pytest.fixture
def ingested(tmp_path: Path) -> tuple[Path, Path]:
    return _ingest(tmp_path)


class TestRebuildRestoresSurvivors:
    def test_pruned_held_usage_regains_search_without_source_or_pricing(
        self, ingested: tuple[Path, Path]
    ) -> None:
        db, source = ingested
        baseline = _fts(db)
        assert len(baseline) == 2
        _prune_whole(db, source)
        before = _usage_snapshot(db)
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        assert _fts(db) == []

        with patch("little_loops.pricing.estimate_cost_usd", side_effect=AssertionError("priced")):
            rebuild(db)

        assert _fts(db) == baseline
        assert _usage_snapshot(db) == before
        rebuild(db)
        assert _fts(db) == baseline  # idempotent: no twins

    def test_both_readers_return_canonical_historical_anchor(
        self, ingested: tuple[Path, Path]
    ) -> None:
        db, source = ingested
        _prune_whole(db, source)
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        rebuild(db)
        model = _sql(db, "SELECT model FROM usage_events LIMIT 1")[0][0]
        phrase = f'"{model}"'
        hits = reader_search(phrase, kind="usage", db=db)
        assert hits and all(h.kind == "usage" and h.ref == model for h in hits)
        records = [h for h in store_search(db, query=phrase) if h["kind"] == "usage"]
        assert len(records) == 2
        assert {r["anchor"] for r in records} == {str(source)}

    def test_rebuild_failure_rolls_back_search_with_observations(
        self, ingested: tuple[Path, Path]
    ) -> None:
        db, _ = ingested
        before = (_fts(db), _usage_snapshot(db))
        with patch.object(lifecycle, "_compact_sessions", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                rebuild(db)
        assert (_fts(db), _usage_snapshot(db)) == before

    def test_live_and_rollout_observations_stay_unindexed(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        _sql(
            db,
            "INSERT INTO usage_events(ts, model, channel, source_path) VALUES"
            "('t', 'm', 'live', '/s'), ('t', 'm', 'rollout', '/s')",
        )
        rebuild(db)
        assert _fts(db) == []


class TestReconciler:
    @staticmethod
    def _db(tmp_path: Path) -> Path:
        db = tmp_path / "history.db"
        ensure_db(db)
        return db

    @staticmethod
    def _reconcile(db: Path, scope: UsageSearchScope) -> int:
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            written = _reconcile_usage_search(conn, scope)
            conn.commit()
            return written
        finally:
            conn.close()

    def test_eligibility_follows_logical_channel_and_source_attribution(
        self, tmp_path: Path
    ) -> None:
        db = self._db(tmp_path)
        rows = [
            # (channel, session_id, source_path)
            ("transcript", "s", "/a"),
            (None, "s", "/a"),  # NULL channel, truthy session -> transcript
            ("", "s", "/a"),  # empty channel, truthy session -> transcript
            (None, None, "/a"),  # NULL channel, no session -> live
            (None, "", "/a"),  # empty session -> live
            ("live", "s", "/a"),
            ("rollout", "s", "/a"),
            ("custom", "s", "/a"),  # unsupported explicit channel
            ("transcript", "s", None),  # missing source attribution
            ("transcript", "s", ""),  # empty source attribution
        ]
        _sql(db, "DELETE FROM usage_events")
        for channel, sid, src in rows:
            _sql(
                db,
                "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
                "VALUES('t', ?, 'm', ?, ?)",
                (sid, channel, src),
            )
        before = _usage_snapshot(db)
        assert self._reconcile(db, UsageSearchScope(full=True)) == 3
        assert len(_fts(db)) == 3
        assert _usage_snapshot(db) == before

    def test_equal_tuples_keep_one_entry_each_and_replay_is_idempotent(
        self, tmp_path: Path
    ) -> None:
        db = self._db(tmp_path)
        for _ in range(3):
            _sql(
                db,
                "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
                "VALUES('t', 's', 'm', 'transcript', '/a')",
            )
        for _ in range(2):
            scope = UsageSearchScope()
            scope.mark("/a")
            assert self._reconcile(db, scope) == 3
        assert len(_fts(db)) == 3

    def test_scoped_reconcile_preserves_other_anchors_and_kinds(self, tmp_path: Path) -> None:
        db = self._db(tmp_path)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, channel, source_path) VALUES"
            "('t', 's', 'm', 'transcript', '/a'), ('t', 's', 'm', 'transcript', '/b')",
        )
        _sql(
            db,
            "INSERT INTO search_index(content, kind, ref, anchor, ts) VALUES"
            "('stale usage', 'usage', 'old', '/a', 't'),"
            "('other usage', 'usage', 'keep', '/untouched', 't'),"
            "('tool', 'tool', 'Bash', '/a', 't')",
        )
        scope = UsageSearchScope()
        scope.mark("/a")
        self._reconcile(db, scope)
        got = _fts(db)
        assert ("m usage", "usage", "m", "/a", "t") in got
        assert ("other usage", "usage", "keep", "/untouched", "t") in got
        assert all(row[2] != "old" for row in got)
        assert all(row[3] != "/b" for row in got)  # /b was outside the scope
        assert _sql(db, "SELECT COUNT(*) FROM search_index WHERE kind = 'tool'") == [(1,)]

    def test_empty_scope_writes_nothing(self, tmp_path: Path) -> None:
        db = self._db(tmp_path)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
            "VALUES('t', 's', 'm', 'transcript', '/a')",
        )
        assert self._reconcile(db, UsageSearchScope()) == 0
        assert _fts(db) == []

    @pytest.mark.parametrize(
        ("model", "content", "ref"),
        [
            (False, "0 usage", "0"),
            (True, "1 usage", "1"),
            (0, "0 usage", "0"),
            (0.0, "0.0 usage", "0.0"),
            (1e20, "1.0e+20 usage", "1.0e+20"),
            ("0", "0 usage", "0"),
            (None, " usage", ""),
            ("", " usage", ""),
        ],
    )
    def test_models_render_from_committed_sqlite_values(
        self, tmp_path: Path, model: Any, content: str, ref: str
    ) -> None:
        db = self._db(tmp_path)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
            "VALUES('t', 's', ?, 'transcript', '/a')",
            (model,),
        )
        self._reconcile(db, UsageSearchScope(full=True))
        assert _fts(db) == [(content, "usage", ref, "/a", "t")]

    def test_renderer_is_pure_and_returns_none_when_ineligible(self) -> None:
        assert _usage_search_entry(1, "s", "transcript", "m", "t", "") is None
        assert _usage_search_entry(1, "s", "rollout", "m", "t", "/a") is None
        assert _usage_search_entry(1, "s", "transcript", "m", "t", "/a") == {
            "content": "m usage",
            "kind": "usage",
            "ref": "m",
            "anchor": "/a",
            "ts": "t",
        }

    def test_reconciler_never_opens_or_commits_a_transaction(self, tmp_path: Path) -> None:
        db = self._db(tmp_path)
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _reconcile_usage_search(conn, UsageSearchScope(full=True))
            assert conn.in_transaction
            conn.rollback()
        finally:
            conn.close()


def _insert_codex_append(db: Path, source: Path) -> None:
    _sql(
        db,
        "INSERT INTO raw_events(ts, session_id, host, host_basis, source_path, line_no, "
        "event_type, raw_line, parsed_json) VALUES('2026-01-01T00:00:00Z', 'cx', 'codex', "
        "'handle', ?, 999, 'event_msg', ?, ?)",
        (str(source), json.dumps({"type": "event_msg"}), json.dumps({"type": "event_msg"})),
    )


class TestIncrementalCatchUp:
    def test_codex_append_restores_collateral_transcript_search_with_zero_new_rows(
        self, ingested: tuple[Path, Path]
    ) -> None:
        db, source = ingested
        baseline = _fts(db)
        assert len(baseline) == 2
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        _insert_codex_append(db, source)  # shares the transcript observations' anchor
        before = _usage_snapshot(db)

        assert backfill_usage_incremental(db) == 0

        assert _fts(db) == baseline
        assert _usage_snapshot(db) == before

    def test_catch_up_leaves_unrelated_absent_index_sources_untouched(
        self, ingested: tuple[Path, Path], tmp_path: Path
    ) -> None:
        db, source = ingested
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
            "VALUES('t', 's', 'other', 'transcript', '/unrelated')",
        )
        _sql(
            db,
            "INSERT INTO usage_replay_holds(source_path, reason, created_at) "
            "VALUES('/unrelated', 'test', 't')",
        )
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        _insert_codex_append(db, source)
        backfill_usage_incremental(db)
        anchors = {row[3] for row in _fts(db)}
        assert anchors == {str(source)}  # /unrelated stays unindexed until a rebuild
        rebuild(db)
        assert "/unrelated" in {row[3] for row in _fts(db)}

    def test_no_work_catch_up_makes_no_search_writes(self, ingested: tuple[Path, Path]) -> None:
        db, _ = ingested
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        assert backfill_usage_incremental(db) == 0
        assert _fts(db) == []

    def test_unusable_checkpoint_skip_leaves_search_untouched(
        self, ingested: tuple[Path, Path]
    ) -> None:
        db, source = ingested
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        _sql(db, "DELETE FROM meta WHERE key = 'usage_derive_version'")
        _insert_codex_append(db, source)
        before = _usage_snapshot(db)
        backfill_usage_incremental(db)
        assert _fts(db) == []
        assert _usage_snapshot(db) == before

    def test_reconcile_failure_rolls_back_catch_up(self, ingested: tuple[Path, Path]) -> None:
        db, source = ingested
        _sql(db, "DELETE FROM search_index WHERE kind = 'usage'")
        _insert_codex_append(db, source)
        checkpoint = _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'")
        with patch.object(lifecycle, "_reconcile_usage_search", side_effect=RuntimeError("stop")):
            with pytest.raises(RuntimeError, match="stop"):
                backfill_usage_incremental(db)
        assert _fts(db) == []
        assert _sql(db, "SELECT value FROM meta WHERE key = 'usage_derive_raw_id'") == checkpoint


class TestSameKeyUpdates:
    @staticmethod
    def _db_with_snapshot(tmp_path: Path) -> tuple[Path, Path, list[str]]:
        fixture = _FIXTURES / "claude" / "transcript-changing-usage-observed.jsonl"
        records = fixture.read_text().splitlines()
        source = tmp_path / "session.jsonl"
        source.write_text("\n".join(records[:2]) + "\n")
        db = tmp_path / "history.db"
        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        backfill_usage_incremental(db)
        return db, source, records

    def test_updated_snapshot_keeps_one_entry_with_committed_values(self, tmp_path: Path) -> None:
        db, source, records = self._db_with_snapshot(tmp_path)
        assert len(_fts(db)) == 1
        with source.open("a") as handle:
            handle.write("\n".join(records[2:]) + "\n")
        backfill_raw_events(db, jsonl_files=[source], host="claude-code")
        assert backfill_usage_incremental(db) == 0  # same-key update, not a new observation
        committed = _sql(db, "SELECT model, ts, source_path FROM usage_events")
        assert len(committed) == 1
        model, ts, src = committed[0]
        assert _fts(db) == [(f"{model or ''} usage", "usage", model or "", src, ts)]

    def test_source_move_reconciles_old_and_new_anchor(self, tmp_path: Path) -> None:
        db, source, records = self._db_with_snapshot(tmp_path)
        _sql(
            db,
            "INSERT INTO usage_events(ts, session_id, model, channel, source_path) "
            "VALUES('t', 's', 'neighbor', 'transcript', '/neighbor')",
        )
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            scope = UsageSearchScope()
            scope.mark(str(source), "/neighbor")
            _reconcile_usage_search(conn, scope)
            conn.commit()
        finally:
            conn.close()
        assert {row[3] for row in _fts(db)} == {str(source), "/neighbor"}
        _sql(db, "UPDATE usage_events SET source_path = '/moved' WHERE model != 'neighbor'")
        conn = connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            scope = UsageSearchScope()
            scope.mark(str(source), "/moved")
            _reconcile_usage_search(conn, scope)
            conn.commit()
        finally:
            conn.close()
        assert {row[3] for row in _fts(db)} == {"/moved", "/neighbor"}
