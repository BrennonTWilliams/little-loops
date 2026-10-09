"""BUG-3761: rebuild() preserves hook-written tool_events / user_corrections rows.

Live hooks write both tables directly with no raw event, so a wipe-and-replay
rebuild used to destroy their byte/latency/provenance data. Rebuild now wipes only
replay-classified rows (NULL byte columns; source 'backfill'), re-indexes the
survivors, and suppresses transcript twins of surviving live tool rows.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.history_reader.search import search
from little_loops.hooks.post_tool_use import handle as post_handle
from little_loops.hooks.types import LLHookEvent
from little_loops.session_store import (
    backfill_raw_events,
    connect,
    ensure_db,
    lifecycle,
    rebuild,
    record_correction,
)
from little_loops.session_store.writers import _backfill_tool_events, _hash_args, _index

TOOL_COLS = (
    "id, ts, session_id, tool_name, args_hash, result_size, bytes_in, bytes_out, "
    "cache_hit, agent_type, mcp_server, mcp_tool, mcp_outcome, latency_ms"
)


def _rows(db: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def _hook_tool(project: Path, session_id: str | None, tool_input: dict, name: str = "Bash") -> None:
    ll = project / ".ll"
    ll.mkdir(parents=True, exist_ok=True)
    (ll / "ll-config.json").write_text(json.dumps({"analytics": {"enabled": True}}))
    result = post_handle(
        LLHookEvent(
            host="claude-code",
            intent="post_tool_use",
            payload={
                "tool_name": name,
                "tool_input": tool_input,
                "tool_response": {"stdout": "ok"},
                "session_id": session_id,
            },
            cwd=str(project),
        )
    )
    assert result.exit_code == 0


def _transcript(path: Path, session_id: str, tool_uses: list[tuple[str, dict]]) -> None:
    lines = [
        {
            "type": "assistant",
            "sessionId": session_id,
            "timestamp": f"2026-05-22T00:00:0{i}Z",
            "message": {
                "content": [{"type": "tool_use", "name": name, "input": tool_input}],
            },
        }
        for i, (name, tool_input) in enumerate(tool_uses)
    ]
    path.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")


def _fts(db: Path, kind: str) -> list[tuple]:
    return sorted(
        _rows(db, f"SELECT content, ref, anchor, ts FROM search_index WHERE kind = '{kind}'"),
        key=repr,
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestPreservation:
    def test_live_tool_rows_survive_with_every_field_and_stay_searchable(
        self, project: Path
    ) -> None:
        db = project / ".ll" / "history.db"
        _hook_tool(project, "s1", {"command": "ls"})
        _hook_tool(project, "s1", {}, name="mcp__srv__do")  # empty input -> zero-ish bytes
        before = _rows(db, f"SELECT {TOOL_COLS} FROM tool_events ORDER BY id")
        fts_before = _fts(db, "tool")
        assert len(before) == 2 and len(fts_before) == 2

        rebuild(db)
        rebuild(db)

        assert _rows(db, f"SELECT {TOOL_COLS} FROM tool_events ORDER BY id") == before
        assert _fts(db, "tool") == fts_before
        assert any(r.ref == "mcp__srv__do" for r in search("mcp__srv__do", kind="tool", db=db))

    def test_replay_classified_tool_rows_are_wiped(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash) "
                "VALUES('2026-01-01T00:00:00Z', 'x', 'Bash', 'h')"
            )
            _index(conn, content="Bash", kind="tool", ref="Bash", anchor="/p", ts="t")
            conn.commit()
        finally:
            conn.close()
        rebuild(db)
        assert _rows(db, "SELECT COUNT(*) FROM tool_events") == [(0,)]
        assert _fts(db, "tool") == []

    def test_output_only_and_zero_byte_rows_survive(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        conn = connect(db)
        try:
            conn.executemany(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, bytes_in, bytes_out)"
                " VALUES('2026-01-01T00:00:00Z', 's', 'T', 'h', ?, ?)",
                [(0, 0), (None, 5), (3, None)],
            )
            conn.commit()
        finally:
            conn.close()
        rebuild(db)
        assert _rows(db, "SELECT bytes_in, bytes_out FROM tool_events ORDER BY id") == [
            (0, 0),
            (None, 5),
            (3, None),
        ]

    def test_live_corrections_survive_and_backfill_ones_are_replaced(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        record_correction(db, "s1", "no, actually use pytest", "user_prompt_submit")
        record_correction(db, None, "wrong, do it again", "custom")
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) "
                "VALUES('2026-01-01T00:00:00Z', 's1', 'stale replay row', 'backfill')"
            )
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) "
                "VALUES('2026-01-01T00:00:01Z', 's2', 'unknown source', NULL)"
            )
            _index(conn, content="stale replay row", kind="correction", ref="s1",
                   anchor="backfill", ts="t")  # fmt: skip
            conn.commit()
        finally:
            conn.close()
        before = _rows(db, "SELECT id, ts, session_id, content, source FROM user_corrections")
        survivors = [r for r in before if r[4] != "backfill"]

        for _ in range(3):
            rebuild(db)
            assert (
                _rows(
                    db,
                    "SELECT id, ts, session_id, content, source FROM user_corrections ORDER BY id",
                )
                == survivors
            )
            fts = _fts(db, "correction")
            assert len(fts) == 3
            assert not any(r[0] == "stale replay row" for r in fts)
        assert search("pytest", kind="correction", db=db)
        # NULL source reproduces what record_correction would pass (NULL anchor).
        assert ("unknown source", "s2", None, "2026-01-01T00:00:01Z") in _fts(db, "correction")
        # NULL session -> ref ''
        assert ("wrong, do it again", "", "custom", survivors[1][1]) in _fts(db, "correction")

    def test_correction_mining_disabled_does_not_remove_live_corrections(
        self, project: Path
    ) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        record_correction(db, "s1", "no, that is wrong", "user_prompt_submit")
        rebuild(db, config={"analytics": {"capture": {"corrections": False}}})
        assert _rows(db, "SELECT content FROM user_corrections") == [("no, that is wrong",)]
        assert len(_fts(db, "correction")) == 1


class TestTwinSuppression:
    def test_live_row_and_transcript_twin_yield_one_row(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        _hook_tool(project, "s1", {"command": "ls"})
        _hook_tool(project, "s1", {"command": "ls"})
        jsonl = project / "t.jsonl"
        _transcript(
            jsonl,
            "s1",
            [("Bash", {"command": "ls"})] * 3 + [("Read", {"path": "/x"})],
        )
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        jsonl.unlink()

        for _ in range(3):
            counts = rebuild(db)
            # 2 live Bash rows suppress 2 of 3 replay Bash blocks; Read has no live twin.
            assert counts["tools"] == 2
            rows = _rows(
                db,
                "SELECT tool_name, bytes_in IS NOT NULL FROM tool_events ORDER BY id",
            )
            assert sorted(rows) == [("Bash", 0), ("Bash", 1), ("Bash", 1), ("Read", 0)]
            assert len(_fts(db, "tool")) == 4

    def test_other_session_is_not_suppressed(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        _hook_tool(project, "s1", {"command": "ls"})
        jsonl = project / "t.jsonl"
        _transcript(jsonl, "s2", [("Bash", {"command": "ls"})])
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        assert rebuild(db)["tools"] == 1

    def test_skip_live_none_keeps_legacy_behavior(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        jsonl = project / "t.jsonl"
        _transcript(jsonl, "s1", [("Bash", {"command": "ls"})])
        conn = connect(db)
        try:
            assert _backfill_tool_events(conn, [jsonl]) == 1
            from collections import Counter

            key = ("s1", "Bash", _hash_args({"command": "ls"}))
            assert _backfill_tool_events(conn, [jsonl], skip_live=Counter({key: 1})) == 0
        finally:
            conn.close()


class TestReplayWriterContracts:
    def test_replay_binds_null_byte_columns(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        ensure_db(db)
        jsonl = project / "t.jsonl"
        _transcript(jsonl, "s1", [("Bash", {"command": "ls"})])
        conn = connect(db)
        try:
            _backfill_tool_events(conn, [jsonl])
            conn.commit()
        finally:
            conn.close()
        assert _rows(db, "SELECT bytes_in, bytes_out FROM tool_events") == [(None, None)]

    def test_hook_writes_integer_bytes_even_for_empty_input(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        _hook_tool(project, "s1", {})
        (row,) = _rows(db, "SELECT bytes_in, bytes_out FROM tool_events")
        assert isinstance(row[0], int) and isinstance(row[1], int)

    def test_mining_uses_reserved_backfill_source(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        jsonl = project / "t.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "s1",
                    "timestamp": "2026-05-22T00:00:00Z",
                    "message": {"content": "no, that is wrong"},
                }
            )
            + "\n"
        )
        backfill_raw_events(db, jsonl_files=[jsonl], since_ts=0.0)
        rebuild(db)
        assert _rows(db, "SELECT source FROM user_corrections") == [("backfill",)]


class TestRollback:
    def test_late_failure_restores_survivors_rows_and_index(self, project: Path) -> None:
        db = project / ".ll" / "history.db"
        _hook_tool(project, "s1", {"command": "ls"})
        record_correction(db, "s1", "no, wrong", "user_prompt_submit")
        tools = _rows(db, f"SELECT {TOOL_COLS} FROM tool_events")
        corrections = _rows(db, "SELECT * FROM user_corrections")
        fts = (_fts(db, "tool"), _fts(db, "correction"))
        stamp = _rows(db, "SELECT value FROM meta WHERE key = 'rebuild_derive_version'")

        with (
            patch.object(lifecycle, "_compact_sessions", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            rebuild(db)

        assert _rows(db, f"SELECT {TOOL_COLS} FROM tool_events") == tools
        assert _rows(db, "SELECT * FROM user_corrections") == corrections
        assert (_fts(db, "tool"), _fts(db, "correction")) == fts
        assert _rows(db, "SELECT value FROM meta WHERE key = 'rebuild_derive_version'") == stamp
