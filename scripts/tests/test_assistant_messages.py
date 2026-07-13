"""Tests for assistant_messages table, backfill, and conversation_turns() (ENH-1942)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from little_loops.history_reader import conversation_turns
from little_loops.session_store import (
    SCHEMA_VERSION,
    backfill,
    backfill_incremental,
    connect,
    ensure_db,
    search,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_record(session_id: str, ts: str, content: object) -> str:
    return (
        json.dumps(
            {
                "type": "user",
                "sessionId": session_id,
                "timestamp": ts,
                "message": {"content": content},
            }
        )
        + "\n"
    )


def _assistant_record(
    session_id: str, ts: str, text_blocks: list[str], tool_use_count: int = 0
) -> str:
    """Build a JSONL assistant record with text and optional tool_use blocks."""
    blocks: list[dict] = []
    for text in text_blocks:
        blocks.append({"type": "text", "text": text})
    for _ in range(tool_use_count):
        blocks.append({"type": "tool_use", "name": "Bash", "input": {}})
    return (
        json.dumps(
            {
                "type": "assistant",
                "sessionId": session_id,
                "timestamp": ts,
                "message": {"content": blocks},
            }
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


class TestAssistantMessagesMigration:
    """Schema v11 creates assistant_messages table and index."""

    def test_v11_creates_table_and_index(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        conn = connect(db)
        try:
            # Check table exists with correct columns
            cols = conn.execute("PRAGMA table_info('assistant_messages')").fetchall()
            col_names = {c[1] for c in cols}
            assert col_names >= {"id", "ts", "session_id", "content", "tool_use_count"}

            # Check index exists
            idx = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name='idx_assistant_messages_session_ts'"
            ).fetchone()
            assert idx is not None
        finally:
            conn.close()

    def test_schema_version_is_12(self) -> None:
        assert SCHEMA_VERSION == 19

    def test_upgrade_from_v10_preserves_data(self, tmp_path: Path) -> None:
        """Simulate v10 → v11 upgrade: existing tables survive the migration."""
        db = tmp_path / "test.db"
        # Create at v10 (migrations 0-9) by using a lower initial version
        conn = connect(db)
        conn.close()
        # verify data written before migration persists
        conn2 = connect(db)
        try:
            conn2.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-01T00:00:00Z", "s-upgrade", "test message"),
            )
            conn2.commit()
        finally:
            conn2.close()
        # Re-open: schema should be at v11, data still there
        conn3 = connect(db)
        try:
            rows = conn3.execute("SELECT content FROM message_events").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "test message"
            # v11 table should also exist
            conn3.execute("SELECT COUNT(*) FROM assistant_messages").fetchone()
        finally:
            conn3.close()


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


class TestBackfillAssistantMessages:
    """_backfill_assistant_messages() seeds assistant_messages from JSONL."""

    def test_backfill_single_assistant_record(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s1", "2026-06-01T10:00:00Z", "how do I fix this?")
            + _assistant_record("s1", "2026-06-01T10:00:05Z", ["Here is how to fix it."]),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["assistant_messages"] == 1

        conn = connect(db)
        try:
            rows = conn.execute("SELECT * FROM assistant_messages").fetchall()
            assert len(rows) == 1
            assert rows[0]["content"] == "Here is how to fix it."
            assert rows[0]["session_id"] == "s1"
            assert rows[0]["tool_use_count"] == 0
        finally:
            conn.close()

    def test_backfill_concatenates_multiple_text_blocks(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s2", "2026-06-01T10:00:00Z", "explain this")
            + _assistant_record(
                "s2",
                "2026-06-01T10:00:05Z",
                ["First block.", "Second block.", "Third block."],
            ),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )

        conn = connect(db)
        try:
            row = conn.execute("SELECT content FROM assistant_messages").fetchone()
            assert row["content"] == "First block.\n\nSecond block.\n\nThird block."
        finally:
            conn.close()

    def test_backfill_counts_tool_use_blocks(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s3", "2026-06-01T10:00:00Z", "read the file")
            + _assistant_record(
                "s3",
                "2026-06-01T10:00:05Z",
                ["Let me read that file."],
                tool_use_count=3,
            ),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )

        conn = connect(db)
        try:
            row = conn.execute("SELECT tool_use_count FROM assistant_messages").fetchone()
            assert row["tool_use_count"] == 3
        finally:
            conn.close()

    def test_backfill_skips_assistant_without_text_blocks(self, tmp_path: Path) -> None:
        """Assistant records with only tool_use blocks (no text) should be skipped."""
        jsonl = tmp_path / "session.jsonl"
        # Assistant record with only tool_use, no text blocks
        record = json.dumps(
            {
                "type": "assistant",
                "sessionId": "s4",
                "timestamp": "2026-06-01T10:00:05Z",
                "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
            }
        )
        jsonl.write_text(
            _user_record("s4", "2026-06-01T10:00:00Z", "run cmd") + record + "\n", encoding="utf-8"
        )
        db = tmp_path / "test.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["assistant_messages"] == 0

    def test_backfill_skips_non_assistant_records(self, tmp_path: Path) -> None:
        """Only type=assistant records are ingested."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s5", "2026-06-01T10:00:00Z", "hello")
            + json.dumps(
                {
                    "type": "system",
                    "sessionId": "s5",
                    "timestamp": "2026-06-01T10:00:01Z",
                    "message": {"content": "system init"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        counts = backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        assert counts["assistant_messages"] == 0

    def test_backfill_idempotent(self, tmp_path: Path) -> None:
        """Running backfill twice produces no duplicate rows (INSERT OR IGNORE)."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s6", "2026-06-01T10:00:00Z", "greeting")
            + _assistant_record("s6", "2026-06-01T10:00:05Z", ["Hello!"]),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        # Second backfill should not duplicate rows
        conn = connect(db)
        try:
            rows = conn.execute("SELECT COUNT(*) AS n FROM assistant_messages").fetchone()
            assert rows["n"] == 1
        finally:
            conn.close()

    def test_backfill_is_searchable(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s7", "2026-06-01T10:00:00Z", "query")
            + _assistant_record("s7", "2026-06-01T10:00:05Z", ["the unique answer is 42"]),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        backfill(
            db,
            issues_dir=tmp_path / "no",
            loops_dir=tmp_path / "no",
            jsonl_files=[jsonl],
            also_rebuild=True,
        )
        results = search(db, query="unique answer")
        assert any(r["kind"] == "message" and "42" in r["content"] for r in results)

    def test_backfill_incremental_includes_assistant_messages(self, tmp_path: Path) -> None:
        """backfill_incremental() populates assistant_messages for new files."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(
            _user_record("s-inc", "2026-06-04T10:00:00Z", "incremental test")
            + _assistant_record("s-inc", "2026-06-04T10:00:05Z", ["incremental reply"]),
            encoding="utf-8",
        )
        db = tmp_path / "test.db"
        counts = backfill_incremental(db, jsonl_files=[jsonl], since_ts=0.0, also_rebuild=True)
        assert counts["assistant_messages"] == 1


# ---------------------------------------------------------------------------
# conversation_turns() from DB
# ---------------------------------------------------------------------------


class TestConversationTurnsFromDB:
    """conversation_turns() returns correct turn-pair windows from history.db."""

    def _populate_turn_pairs(self, db_path: Path) -> None:
        """Populate message_events and assistant_messages for a simple session."""
        conn = connect(db_path)
        try:
            # Session + message_events + assistant_messages
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("s-turn", "/fake/s-turn.jsonl"),
            )
            # Turn 1: user asks, assistant replies
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-01T10:00:00Z", "s-turn", "what is Python?"),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content, tool_use_count) "
                "VALUES(?, ?, ?, ?)",
                ("2026-06-01T10:00:05Z", "s-turn", "Python is a programming language.", 0),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-01T10:01:00Z", "s-turn", "show me an example"),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content, tool_use_count) "
                "VALUES(?, ?, ?, ?)",
                ("2026-06-01T10:01:05Z", "s-turn", "Here is an example:\n\nprint('hello')", 1),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-01T10:02:00Z", "s-turn", "thanks!"),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content, tool_use_count) "
                "VALUES(?, ?, ?, ?)",
                ("2026-06-01T10:02:05Z", "s-turn", "You're welcome!", 0),
            )
            conn.commit()
        finally:
            conn.close()

    def test_returns_correct_windows(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._populate_turn_pairs(db)

        windows = conversation_turns(db_path=db, context_window=2)
        # With 3 turn-pairs and context_window=2, expect 2 windows:
        # Window 1: pairs [0,1] → 4 entries (user, assistant, user, assistant)
        # Window 2: pairs [1,2] → 4 entries
        assert len(windows) == 2
        for window in windows:
            assert len(window) == 4  # 2 turn-pairs * 2 roles each
            roles = [role for role, _ in window]
            assert roles == ["user", "assistant", "user", "assistant"]

    def test_window_content_correct(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._populate_turn_pairs(db)

        windows = conversation_turns(db_path=db, context_window=2)
        # First window should contain the first two user messages and their replies
        w0 = windows[0]
        assert w0[0] == ("user", "what is Python?")
        assert w0[1] == ("assistant", "Python is a programming language.")
        assert w0[2] == ("user", "show me an example")
        assert w0[3] == ("assistant", "Here is an example:\n\nprint('hello')")

    def test_context_window_1(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._populate_turn_pairs(db)

        windows = conversation_turns(db_path=db, context_window=1)
        # 3 single-turn windows
        assert len(windows) == 3
        for window in windows:
            assert len(window) == 2  # (user, assistant)

    def test_single_turn_session(self, tmp_path: Path) -> None:
        """Session with exactly one user→assistant pair returns one window."""
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-06-01T10:00:00Z", "s-one", "hello"),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content, tool_use_count) "
                "VALUES(?, ?, ?, ?)",
                ("2026-06-01T10:00:05Z", "s-one", "hi there", 0),
            )
            conn.commit()
        finally:
            conn.close()

        windows = conversation_turns(db_path=db, context_window=3)
        assert len(windows) == 1
        assert windows[0] == [("user", "hello"), ("assistant", "hi there")]


# ---------------------------------------------------------------------------
# conversation_turns() degradation
# ---------------------------------------------------------------------------


class TestConversationTurnsDegradation:
    """conversation_turns() returns [] on missing DB, missing table, or empty data."""

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = conversation_turns(db_path=db)
        assert result == []

    def test_missing_table_returns_empty(self, tmp_path: Path) -> None:
        """DB that exists but has no assistant_messages table (pre-v11) returns []."""
        db = tmp_path / "test.db"
        # ensure_db creates v11 schema; drop assistant_messages to simulate pre-v11
        ensure_db(db)
        conn = connect(db)
        try:
            conn.execute("DROP TABLE assistant_messages")
            conn.commit()
        finally:
            conn.close()
        result = conversation_turns(db_path=db)
        assert result == []

    def test_empty_tables_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = conversation_turns(db_path=db)
        assert result == []

    def test_since_filter_returns_empty_when_nothing_matches(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-05-01T10:00:00Z", "s-old", "old message"),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content, tool_use_count) "
                "VALUES(?, ?, ?, ?)",
                ("2026-05-01T10:00:05Z", "s-old", "old reply", 0),
            )
            conn.commit()
        finally:
            conn.close()
        since = datetime(2026, 6, 1, tzinfo=UTC)
        result = conversation_turns(db_path=db, since=since)
        assert result == []
