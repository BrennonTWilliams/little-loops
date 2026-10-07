"""BUG-3766: rebuild() preserves live skill_events rows and their completion fields.

The prompt hook (``record_skill_event``) and ``ll-action`` (``skill_event_context``)
write ``skill_events`` directly with no raw event to replay. v61 added a nullable
``origin`` column; rebuild wipes only ``origin = 'transcript'`` rows, classifies
NULL-origin historical rows conservatively, re-indexes survivors and lets each eligible
hook survivor suppress one replay twin (same session/name/args, within 1 second).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.history_reader.search import search
from little_loops.session_store import (
    backfill_raw_events,
    connect,
    ensure_db,
    lifecycle,
    rebuild,
    record_skill_event,
    skill_event_context,
)
from little_loops.session_store.writers import (
    SkillReplaySurvivor,
    _backfill_skill_events,
    _index,
)

COLS = "id, ts, session_id, skill_name, args, exit_code, success, duration_ms, origin"


def _rows(db: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _skills(db: Path) -> list[tuple]:
    return _rows(db, f"SELECT {COLS} FROM skill_events ORDER BY id")


def _fts(db: Path) -> list[tuple]:
    return sorted(
        _rows(db, "SELECT content, ref, anchor, ts FROM search_index WHERE kind = 'skill'"),
        key=repr,
    )


def _insert(
    db: Path,
    ts: str,
    sid: str | None,
    name: str | None,
    args: str = "",
    *,
    origin: str | None = None,
    completion: tuple[int | None, int | None, int | None] = (None, None, None),
    anchor: str | None = "",
    index: bool = True,
) -> int:
    """Insert a raw skill row (and optional search entry) as an older version would have."""
    ensure_db(db)
    conn = connect(db)
    try:
        cur = conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args, exit_code, success, "
            "duration_ms, origin) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, sid, name, args, *completion, origin),
        )
        if index:
            _index(
                conn,
                content=name or "",
                kind="skill",
                ref=sid or "",
                anchor=name if anchor == "" else anchor,
                ts=ts,
            )
        conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid
    finally:
        conn.close()


def _transcript(path: Path, entries: list[tuple[str, str, str, str]]) -> None:
    """entries: (session_id, timestamp, skill, args)."""
    lines = [
        {
            "type": "user",
            "sessionId": sid,
            "timestamp": ts,
            "message": {
                "content": f"<command-name>/ll:{name}</command-name>\n"
                f"<command-args>{args}</command-args>"
            },
        }
        for sid, ts, name, args in entries
    ]
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


def _ingest(db: Path, path: Path) -> None:
    backfill_raw_events(db, jsonl_files=[path], since_ts=0.0)


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".ll" / "history.db"
    path.parent.mkdir()
    ensure_db(path)
    return path


class TestLivePreservation:
    def test_both_writers_survive_with_completion_fields_and_search(self, db: Path) -> None:
        record_skill_event(db, "s1", "ready-issue", "review-target")
        with skill_event_context(db, session_id="s1", skill_name="ready-issue", args="x") as c:
            c.exit_code = 7
        before = _skills(db)
        fts = _fts(db)
        assert [r[8] for r in before] == ["prompt_hook", "skill_host"]
        assert before[1][5:8] == (7, 0, before[1][7]) and before[1][7] is not None
        assert len(fts) == 2

        for _ in range(3):
            rebuild(db)

        assert _skills(db) == before
        assert _fts(db) == fts
        assert any(r.ref == "s1" for r in search("ready-issue", kind="skill", db=db))

    def test_survives_with_pruned_raw_sources(self, db: Path, tmp_path: Path) -> None:
        record_skill_event(db, "s1", "ready-issue", "a")
        src = tmp_path / "t.jsonl"
        _transcript(src, [("s2", "2026-05-22T00:00:00Z", "commit", "")])
        _ingest(db, src)
        _rows(db, "SELECT 1")
        conn = sqlite3.connect(str(db))
        conn.execute("DELETE FROM raw_events")
        conn.commit()
        conn.close()
        live = [r for r in _skills(db) if r[8] == "prompt_hook"]
        rebuild(db)
        assert [r for r in _skills(db) if r[8] == "prompt_hook"] == live
        assert not [r for r in _skills(db) if r[8] == "transcript"]

    def test_in_flight_context_completes_original_row_after_rebuild(self, db: Path) -> None:
        with skill_event_context(db, session_id="s1", skill_name="commit", args="") as c:
            before = _skills(db)
            assert before[0][5] is None
            rebuild(db)
            assert [r[0] for r in _skills(db)] == [before[0][0]]
            c.exit_code = 3
        row = _skills(db)[0]
        assert row[0] == before[0][0] and row[5] == 3 and row[6] == 0 and row[8] == "skill_host"

    def test_orphan_search_entries_vanish_and_missing_are_restored(self, db: Path) -> None:
        record_skill_event(db, "s1", "commit", "")
        fts = _fts(db)
        conn = sqlite3.connect(str(db))
        conn.execute("DELETE FROM search_index WHERE kind = 'skill'")
        conn.commit()
        conn.close()
        _index_orphan(db)
        rebuild(db)
        assert _fts(db) == fts


def _index_orphan(db: Path) -> None:
    conn = connect(db)
    try:
        _index(conn, content="ghost", kind="skill", ref="z", anchor="ghost", ts="t")
        conn.commit()
    finally:
        conn.close()


class TestTranscriptReplay:
    def test_transcript_rows_replaced_not_accumulated(self, db: Path, tmp_path: Path) -> None:
        src = tmp_path / "t.jsonl"
        _transcript(src, [("s9", "2026-05-22T00:00:00Z", "commit", "msg")])
        _ingest(db, src)
        for _ in range(3):
            result = rebuild(db)
            assert result["skill_events"] == 1
        rows = _skills(db)
        assert len(rows) == 1 and rows[0][8] == "transcript"
        assert len(_fts(db)) == 1

    def test_hook_twin_suppressed_once_and_replay_only_remains(
        self, db: Path, tmp_path: Path
    ) -> None:
        record_skill_event(db, "s1", "commit", "msg")
        live_ts = _skills(db)[0][1]
        src = tmp_path / "t.jsonl"
        _transcript(
            src,
            [
                ("s1", live_ts, "commit", "msg"),
                ("s1", live_ts, "commit", "msg"),  # M<N: second has no survivor
                ("s2", "2026-05-22T00:00:00Z", "commit", "other"),
            ],
        )
        _ingest(db, src)
        result = rebuild(db)
        assert result["skill_events"] == 2
        origins = sorted(r[8] for r in _skills(db))
        assert origins == ["prompt_hook", "transcript", "transcript"]
        again = rebuild(db)
        assert again["skill_events"] == 2
        assert len(_skills(db)) == 3


class TestSuppressionMatrix:
    def _survivor(self, ts: str, *, sid: str = "s1", args: str = "a") -> SkillReplaySurvivor:
        from little_loops.session_store.writers import _parse_aware_ts

        parsed = _parse_aware_ts(ts)
        assert parsed is not None
        return SkillReplaySurvivor(1, sid, "commit", args, parsed)

    def _replay(
        self,
        tmp_path: Path,
        survivors: list[SkillReplaySurvivor] | None,
        ts: str,
        *,
        sid: str = "s1",
        args: str = "a",
    ) -> int:
        src = tmp_path / "r.jsonl"
        _transcript(src, [(sid, ts, "commit", args)])
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            "CREATE TABLE skill_events(id INTEGER PRIMARY KEY, ts, session_id, skill_name,"
            " args, exit_code, success, duration_ms, origin);"
            "CREATE VIRTUAL TABLE search_index USING fts5(content, kind UNINDEXED,"
            " ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED);"
        )
        return _backfill_skill_events(conn, [src], skip_live=survivors)

    @pytest.mark.parametrize(
        ("replay_ts", "suppressed"),
        [
            ("2026-05-22T00:00:00Z", True),
            ("2026-05-22T00:00:01Z", True),  # 1s boundary inclusive
            ("2026-05-21T23:59:59.000Z", True),
            ("2026-05-22T01:00:01+01:00", True),  # offset form of 00:00:01Z
            ("2026-05-22T00:00:01.500Z", False),
            ("2026-05-22T00:00:02Z", False),
            ("2026-05-22T00:00:00", False),  # naive
            ("garbage", False),
            ("", False),
        ],
    )
    def test_timestamp_window(self, tmp_path: Path, replay_ts: str, suppressed: bool) -> None:
        survivors = [self._survivor("2026-05-22T00:00:00Z")]
        assert self._replay(tmp_path, survivors, replay_ts) == (0 if suppressed else 1)

    def test_different_args_and_sessions_never_suppress(self, tmp_path: Path) -> None:
        survivors = [self._survivor("2026-05-22T00:00:00Z")]
        assert self._replay(tmp_path, survivors, "2026-05-22T00:00:00Z", args="b") == 1
        assert self._replay(tmp_path, survivors, "2026-05-22T00:00:00Z", sid="s2") == 1

    def test_no_survivors_inserts_everything(self, tmp_path: Path) -> None:
        assert self._replay(tmp_path, None, "2026-05-22T00:00:00Z") == 1
        assert self._replay(tmp_path, [], "2026-05-22T00:00:00Z") == 1

    def test_nearest_then_lowest_id_consumed_once(self, tmp_path: Path) -> None:
        src = tmp_path / "r.jsonl"
        _transcript(
            src,
            [
                ("s1", "2026-05-22T00:00:00Z", "commit", "a"),
                ("s1", "2026-05-22T00:00:00Z", "commit", "a"),
                ("s1", "2026-05-22T00:00:00Z", "commit", "a"),
            ],
        )
        a = self._survivor("2026-05-22T00:00:00Z")
        b = SkillReplaySurvivor(2, "s1", "commit", "a", a.ts)
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            "CREATE TABLE skill_events(id INTEGER PRIMARY KEY, ts, session_id, skill_name,"
            " args, exit_code, success, duration_ms, origin);"
            "CREATE VIRTUAL TABLE search_index USING fts5(content, kind UNINDEXED,"
            " ref UNINDEXED, anchor UNINDEXED, ts UNINDEXED);"
        )
        assert _backfill_skill_events(conn, [src], skip_live=[a, b]) == 1

    def test_non_hook_rows_never_become_survivors(self, db: Path, tmp_path: Path) -> None:
        ts = "2026-05-22T00:00:00Z"
        _insert(db, ts, "s1", "commit", "a", origin="skill_host")
        _insert(db, ts, "s1", "commit", "a", origin="future-origin")
        _insert(db, ts, "s1", "commit", "a", origin="prompt_hook", completion=(0, 1, 5))
        _insert(db, ts, None, "commit", "a", origin="prompt_hook")
        _insert(db, ts, "s1", "commit", "a", origin="prompt_hook")  # eligible
        src = tmp_path / "t.jsonl"
        _transcript(src, [("s1", ts, "commit", "a")] * 2)
        _ingest(db, src)
        rebuild(db)
        # exactly one replay twin suppressed (the single eligible survivor)
        assert sum(1 for r in _skills(db) if r[8] == "transcript") == 1


class TestLegacyClassification:
    TS = "2026-05-22T00:00:00Z"

    def _origin(self, db: Path, row_id: int) -> str | None:
        return _rows(db, f"SELECT origin FROM skill_events WHERE id = {row_id}")[0][0]

    def test_completion_evidence_wins_even_with_path_anchor_and_zero(self, db: Path) -> None:
        a = _insert(
            db, self.TS, "s1", "commit", origin=None, completion=(0, 1, 0), anchor="/p.jsonl"
        )
        b = _insert(db, "2026-05-22T00:00:09Z", "s1", "commit", completion=(None, None, 0))
        rebuild(db)
        assert self._origin(db, a) == "skill_host"
        assert self._origin(db, b) == "skill_host"

    def test_unique_path_anchor_is_transcript_and_replaced(self, db: Path) -> None:
        row = _insert(db, self.TS, "s1", "commit", anchor="/home-less/proj/x.jsonl")
        rebuild(db)
        assert _rows(db, f"SELECT COUNT(*) FROM skill_events WHERE id = {row}") == [(0,)]

    def test_name_only_anchor_is_legacy_and_stays_legacy(self, db: Path) -> None:
        row = _insert(db, self.TS, "s1", "commit")
        for _ in range(3):
            rebuild(db)
            assert self._origin(db, row) == "legacy"
        assert len(_fts(db)) == 1

    @pytest.mark.parametrize("case", ["both", "dup_fts", "dup_base", "missing", "null_name"])
    def test_ambiguous_evidence_becomes_legacy(self, db: Path, case: str) -> None:
        if case == "both":
            row = _insert(db, self.TS, "s1", "commit", anchor="/p.jsonl")
            conn = connect(db)
            _index(conn, content="commit", kind="skill", ref="s1", anchor="commit", ts=self.TS)
            conn.commit()
            conn.close()
        elif case == "dup_fts":
            row = _insert(db, self.TS, "s1", "commit", anchor="/p.jsonl")
            conn = connect(db)
            _index(conn, content="commit", kind="skill", ref="s1", anchor="/q.jsonl", ts=self.TS)
            conn.commit()
            conn.close()
        elif case == "dup_base":
            row = _insert(db, self.TS, "s1", "commit", anchor="/p.jsonl")
            _insert(db, self.TS, "s1", "commit", anchor="/p.jsonl")
        elif case == "missing":
            row = _insert(db, self.TS, "s1", "commit", index=False)
        else:
            row = _insert(db, self.TS, "s1", None, anchor="/p.jsonl")
        rebuild(db)
        assert self._origin(db, row) == "legacy"

    def test_explicit_origins_never_reclassified(self, db: Path) -> None:
        keep = _insert(db, self.TS, "s1", "commit", origin="future", anchor="/p.jsonl")
        rebuild(db)
        assert self._origin(db, keep) == "future"

    def test_stale_null_insert_after_first_classification_is_classified_later(
        self, db: Path
    ) -> None:
        first = _insert(db, self.TS, "s1", "commit")
        rebuild(db)
        late = _insert(db, "2026-05-22T00:00:30Z", "s1", "commit", completion=(0, 1, 2))
        rebuild(db)
        assert self._origin(db, first) == "legacy"
        assert self._origin(db, late) == "skill_host"

    def test_legacy_survivor_with_raw_twin_does_not_accumulate(
        self, db: Path, tmp_path: Path
    ) -> None:
        _insert(db, self.TS, "s1", "commit", "msg")
        src = tmp_path / "t.jsonl"
        _transcript(src, [("s1", self.TS, "commit", "msg")])
        _ingest(db, src)
        rebuild(db)
        count = len(_skills(db))
        assert count == 2  # accepted bounded duplicate
        for _ in range(2):
            rebuild(db)
            assert len(_skills(db)) == count


class TestSchema:
    def test_origin_column_nullable_no_default(self, db: Path) -> None:
        info = {r[1]: r for r in _rows(db, "PRAGMA table_info(skill_events)")}
        _cid, _name, ctype, notnull, default, _pk = info["origin"]
        assert ctype == "TEXT" and notnull == 0 and default is None

    def test_backfill_without_suppression_stamps_transcript(self, tmp_path: Path) -> None:
        src = tmp_path / "t.jsonl"
        _transcript(src, [("s1", "2026-05-22T00:00:00Z", "commit", "")])
        ensure_db(tmp_path / "h.db")
        conn = connect(tmp_path / "h.db")
        try:
            assert _backfill_skill_events(conn, [src]) == 1
            assert [tuple(r) for r in conn.execute("SELECT origin FROM skill_events")] == [
                ("transcript",)
            ]
        finally:
            conn.close()


class TestRollback:
    def test_late_failure_restores_rows_origins_search_and_stamp(self, db: Path) -> None:
        record_skill_event(db, "s1", "commit", "a")
        legacy = _insert(db, "2026-05-22T00:00:00Z", "s1", "commit")
        before = _skills(db)
        fts = _fts(db)
        stamp = _rows(db, "SELECT value FROM meta WHERE key = 'rebuild_derive_version'")

        with (
            patch.object(lifecycle, "_compact_sessions", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            rebuild(db)

        assert _skills(db) == before
        assert [r[8] for r in _skills(db) if r[0] == legacy] == [None]
        assert _fts(db) == fts
        assert _rows(db, "SELECT value FROM meta WHERE key = 'rebuild_derive_version'") == stamp


class TestMigrationAndDeriveVersion:
    def test_v60_store_upgrades_with_null_origins_until_rebuild(self, db: Path) -> None:
        conn = sqlite3.connect(str(db))
        conn.execute("ALTER TABLE skill_events DROP COLUMN origin")
        conn.execute("UPDATE meta SET value = '60' WHERE key = 'schema_version'")
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) "
            "VALUES('2026-05-22T00:00:00Z', 's1', 'commit', '')"
        )
        conn.commit()
        conn.close()
        ensure_db(db)
        ensure_db(db)  # repeat is a no-op
        assert _rows(db, "SELECT origin FROM skill_events") == [(None,)]
        assert _rows(db, "SELECT value FROM meta WHERE key = 'schema_version'") == [("61",)]
        rebuild(db)
        assert _rows(db, "SELECT origin FROM skill_events") == [("legacy",)]

    def test_bug3761_stamped_store_is_stale_then_current_after_rebuild(self, db: Path) -> None:
        record_skill_event(db, "s1", "commit", "")
        rebuild(db)
        assert lifecycle.rebuild_needed(db).status == "current"
        conn = sqlite3.connect(str(db))
        conn.execute("UPDATE meta SET value = 'bug3761-v1' WHERE key = 'rebuild_derive_version'")
        conn.commit()
        conn.close()
        assert lifecycle.rebuild_needed(db).status == "stale"
        rebuild(db)
        assert lifecycle.rebuild_needed(db).status == "current"
        assert [r[8] for r in _skills(db)] == ["prompt_hook"]
