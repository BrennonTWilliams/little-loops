"""Tests for sessions.py: session metadata, issue events, issue effort/velocity, lifecycle/handoff, worktree summaries (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from little_loops.history_reader import (
    IssueEvent,
    SessionRef,
    handoff_frequency,
    issue_effort,
    lookup_session_metadata,
    recent_issue_velocity,
    recent_lifecycle_events,
    related_issue_events,
    sessions_for_issue,
    worktree_summary,
)
from little_loops.session_store import (
    SQLiteTransport,
    connect,
    ensure_db,
    normalize_issue_id,
    record_session_lifecycle_event,
)


class TestRelatedIssueEvents:
    """Issue-centric event queries."""

    def test_returns_matching_events(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        transport = SQLiteTransport(db)
        ts1 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        transport.send(
            {
                "event": "issue.completed",
                "issue_id": "BUG-123",
                "ts": ts1,
            }
        )
        transport.close()
        result = related_issue_events("BUG-123", db=db)
        assert len(result) >= 1
        assert isinstance(result[0], IssueEvent)
        assert result[0].issue_id == "BUG-123"
        assert result[0].transition == "done"

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = related_issue_events("NOPE-000", db=db)
        assert result == []

    def test_limit_is_respected(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for i in range(5):
                conn.execute(
                    "INSERT INTO issue_events(ts, issue_id, issue_num, transition) VALUES(?, ?, ?, ?)",
                    (ts, "BUG-1", normalize_issue_id("BUG-1"), f"step_{i}"),
                )
            conn.commit()
        finally:
            conn.close()
        result = related_issue_events("BUG-1", limit=3, db=db)
        assert len(result) == 3


class TestSessionsForIssue:
    """sessions_for_issue() queries the issue_sessions view (ENH-1711)."""

    def _setup_issue_session(self, db: Path, issue_id: str, session_id: str, jsonl: str) -> None:
        """Insert minimal rows so the issue_sessions view returns a match."""
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", issue_id, "open", "2026-01-10T00:00:00Z", None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", session_id, "working on it"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, jsonl),
            )
            conn.commit()
        finally:
            conn.close()

    def test_returns_matching_session(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._setup_issue_session(db, "ENH-1710", "sess-001", "/path/sess-001.jsonl")
        result = sessions_for_issue("ENH-1710", db=db)
        assert len(result) == 1
        assert isinstance(result[0], SessionRef)
        assert result[0].session_id == "sess-001"
        assert result[0].jsonl_path == "/path/sess-001.jsonl"
        assert result[0].issue_id == "ENH-1710"

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = sessions_for_issue("NOPE-000", db=db)
        assert result == []

    def test_excludes_sessions_outside_issue_window(self, tmp_path: Path) -> None:
        """A message before captured_at should not appear in the view."""
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", "ENH-9", "open", "2026-01-10T10:00:00Z", None),
            )
            # message BEFORE captured_at — must not match
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-09T00:00:00Z", "sess-early", "too early"),
            )
            conn.commit()
        finally:
            conn.close()
        result = sessions_for_issue("ENH-9", db=db)
        assert result == []

    def test_limit_respected(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-2", "open", "2026-01-10T00:00:00Z"),
            )
            for i in range(5):
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-10T{10 + i}:00:00Z", f"sess-{i}", "msg"),
                )
            conn.commit()
        finally:
            conn.close()
        result = sessions_for_issue("ENH-2", limit=3, db=db)
        assert len(result) == 3


class TestIssueEffort:
    """Tests for issue_effort() and recent_issue_velocity() (ENH-1905)."""

    def _setup_issue_session_direct(
        self,
        db: Path,
        issue_id: str,
        session_id: str,
        first_ts: str,
        last_ts: str,
    ) -> None:
        """Insert minimal rows so the issue_sessions view returns a match."""
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (first_ts, issue_id, "open", first_ts, None),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (first_ts, session_id, "work start"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (last_ts, session_id, "work end"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, f"/path/{session_id}.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_issue_effort_missing_db_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = issue_effort("ENH-9999", db=db)
        assert result is None

    def test_issue_effort_empty_db_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = issue_effort("ENH-9999", db=db)
        assert result is None

    def test_issue_effort_single_session_returns_zero_cycle(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._setup_issue_session_direct(
            db, "ENH-1905", "sess-001", "2026-01-10T10:00:00Z", "2026-01-10T10:00:00Z"
        )
        result = issue_effort("ENH-1905", db=db)
        assert result is not None
        assert result["session_count"] == 1
        assert result["cycle_time_days"] == 0.0

    def test_issue_effort_multi_session_correct_cycle(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        # Insert a single issue_events row covering the full window (NULL completed_at
        # so both sessions' messages fall within the view's JOIN condition).
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at, completed_at) "
                "VALUES(?, ?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-1905", "open", "2026-01-10T00:00:00Z", None),
            )
            # Session A: messages on 2026-01-10
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-a", "/path/sess-a.jsonl"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T00:00:00Z", "sess-a", "work start"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T12:00:00Z", "sess-a", "work end"),
            )
            # Session B: messages on 2026-01-12
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("sess-b", "/path/sess-b.jsonl"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-12T00:00:00Z", "sess-b", "more work"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-12T12:00:00Z", "sess-b", "done"),
            )
            conn.commit()
        finally:
            conn.close()
        result = issue_effort("ENH-1905", db=db)
        assert result is not None
        assert result["session_count"] == 2
        # cycle: from 2026-01-10T00:00:00 to 2026-01-12T12:00:00 = 2.5 days
        assert result["cycle_time_days"] is not None
        assert abs(result["cycle_time_days"] - 2.5) < 0.01

    def test_recent_issue_velocity_empty_db_returns_empty_list(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = recent_issue_velocity(db=db)
        assert result == []

    def test_recent_issue_velocity_missing_db_returns_empty_list(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = recent_issue_velocity(db=db)
        assert result == []


class TestLookupSessionMetadata:
    """Tests for lookup_session_metadata() (ENH-1943)."""

    # ------------------------------------------------------------------
    # Degradation tests (missing / empty database)
    # ------------------------------------------------------------------

    def test_degrades_when_db_missing(self, tmp_path: Path) -> None:
        """Returns {} when database file does not exist (pre-checked before ensure_db)."""
        db = tmp_path / "nonexistent.db"
        result = lookup_session_metadata("sess-001", db=db)
        assert result == {}

    def test_degrades_when_tables_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = lookup_session_metadata("sess-001", db=db)
        assert result == {
            "has_corrections": False,
            "issue_outcome": None,
            "tool_count": 0,
            "files_modified": 0,
            "loop_outcome": None,
        }

    # ------------------------------------------------------------------
    # has_corrections
    # ------------------------------------------------------------------

    def test_has_corrections_true(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "use a set for ids", "user"),
            )
            conn.commit()
        finally:
            conn.close()
        result = lookup_session_metadata("sess-a", db=db)
        assert result["has_corrections"] is True

    def test_has_corrections_false(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "use a set for ids", "user"),
            )
            conn.commit()
        finally:
            conn.close()
        # Query a different session with no corrections
        result = lookup_session_metadata("sess-other", db=db)
        assert result["has_corrections"] is False

    # ------------------------------------------------------------------
    # issue_outcome
    # ------------------------------------------------------------------

    def _setup_issue_outcome(
        self, db: Path, issue_id: str, session_id: str, transition: str, ts: str
    ) -> None:
        """Insert minimal rows so issue_sessions VIEW matches and the query finds a done issue."""
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                (ts, issue_id, transition, ts),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (ts, session_id, "work done"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, f"/path/{session_id}.jsonl"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_issue_outcome_done(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        ts = "2026-06-01T10:00:00Z"
        self._setup_issue_outcome(db, "ENH-1900", "sess-001", "done", ts)
        result = lookup_session_metadata("sess-001", db=db)
        assert result["issue_outcome"] == "done"

    def test_issue_outcome_null(self, tmp_path: Path) -> None:
        """No issue events linked to this session — issue_outcome should be None."""
        db = tmp_path / "test.db"
        ensure_db(db)
        result = lookup_session_metadata("sess-no-issues", db=db)
        assert result["issue_outcome"] is None

    # ------------------------------------------------------------------
    # tool_count
    # ------------------------------------------------------------------

    def test_tool_count(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for i in range(3):
                conn.execute(
                    "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (ts, "sess-a", f"tool_{i}", "abc123", 100),
                )
            # Different session — should not affect count
            conn.execute(
                "INSERT INTO tool_events(ts, session_id, tool_name, args_hash, result_size) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, "sess-other", "other_tool", "def456", 50),
            )
            conn.commit()
        finally:
            conn.close()
        result = lookup_session_metadata("sess-a", db=db)
        assert result["tool_count"] == 3

    # ------------------------------------------------------------------
    # files_modified
    # ------------------------------------------------------------------

    def test_files_modified_counts_write_and_create_ops(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            # "Write" (hook-written, title case) — should be counted
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "scripts/a.py", "Write"),
            )
            # "write" (lowercase) — should be counted
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "scripts/b.py", "write"),
            )
            # "create" — should be counted
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "scripts/c.py", "create"),
            )
            # "modify" — NOT counted (not in the op filter)
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "scripts/d.py", "modify"),
            )
            # Different session — should not be counted
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-other", "scripts/e.py", "Write"),
            )
            conn.commit()
        finally:
            conn.close()
        result = lookup_session_metadata("sess-a", db=db)
        assert result["files_modified"] == 3

    # ------------------------------------------------------------------
    # loop_outcome
    # ------------------------------------------------------------------

    def test_loop_outcome_always_none(self, tmp_path: Path) -> None:
        """loop_events table has no session_id column; loop_outcome is always None."""
        db = tmp_path / "test.db"
        ensure_db(db)
        result = lookup_session_metadata("sess-any", db=db)
        assert result["loop_outcome"] is None


class TestRecentLifecycleEvents:
    """ENH-2495: recent_lifecycle_events() over session_lifecycle_events."""

    def test_recent_lifecycle_events_filter_by_event(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db, session_id="s1", event="handoff_needed", ts="2026-07-19T10:00:00Z"
        )
        record_session_lifecycle_event(
            db, session_id="s1", event="compaction", ts="2026-07-19T11:00:00Z"
        )

        rows = recent_lifecycle_events(event="handoff_needed", db=db)
        assert len(rows) == 1
        assert rows[0].event == "handoff_needed"

    def test_recent_lifecycle_events_newest_first_and_detail_roundtrip(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db,
            session_id="s1",
            event="stale_ref_sweep",
            detail={"findings": 3},
            ts="2026-07-19T10:00:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id="s1",
            event="stale_ref_sweep",
            detail={"findings": 5},
            ts="2026-07-19T11:00:00Z",
        )

        rows = recent_lifecycle_events(db=db)
        assert [r.detail["findings"] for r in rows] == [5, 3]

    def test_recent_lifecycle_events_empty_on_missing_db(self, tmp_path: Path) -> None:
        assert recent_lifecycle_events(db=tmp_path / "nope" / "history.db") == []


class TestHandoffFrequency:
    """ENH-2495: handoff_frequency() counts handoff_needed rows."""

    def test_handoff_frequency_with_since_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db, session_id="s1", event="handoff_needed", ts="2026-07-19T10:00:00Z"
        )
        record_session_lifecycle_event(
            db, session_id="s1", event="compaction", ts="2026-07-19T10:30:00Z"
        )
        record_session_lifecycle_event(
            db, session_id="s1", event="handoff_needed", ts="2026-07-19T11:00:00Z"
        )

        assert handoff_frequency(db=db) == 2
        assert handoff_frequency(since="2026-07-19T10:30:00Z", db=db) == 1
        assert handoff_frequency(db=tmp_path / "nope" / "history.db") == 0


class TestWorktreeSummary:
    """ENH-2509: worktree_summary() rolls up worktree_* lifecycle events per issue."""

    def test_per_issue_rollup(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-001"},
            ts="2026-07-19T10:00:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_merge",
            detail={"issue_id": "BUG-001"},
            ts="2026-07-19T10:05:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_delete",
            detail={"issue_id": "BUG-001"},
            ts="2026-07-19T10:06:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-002"},
            ts="2026-07-19T11:00:00Z",
        )
        # Non-worktree events must not pollute the rollup.
        record_session_lifecycle_event(
            db, session_id="s1", event="handoff_needed", ts="2026-07-19T12:00:00Z"
        )

        rows = worktree_summary(db=db)
        by_issue = {r["issue_id"]: r for r in rows}
        assert by_issue["BUG-001"]["created"] == 1
        assert by_issue["BUG-001"]["merged"] == 1
        assert by_issue["BUG-001"]["deleted"] == 1
        assert by_issue["BUG-002"]["created"] == 1
        assert by_issue["BUG-002"]["merged"] == 0

    def test_issue_id_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-001"},
            ts="2026-07-19T10:00:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-002"},
            ts="2026-07-19T11:00:00Z",
        )

        rows = worktree_summary(issue_id="BUG-001", db=db)
        assert len(rows) == 1
        assert rows[0]["issue_id"] == "BUG-001"

    def test_since_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-001"},
            ts="2026-07-19T10:00:00Z",
        )
        record_session_lifecycle_event(
            db,
            session_id=None,
            event="worktree_create",
            detail={"issue_id": "BUG-002"},
            ts="2026-07-19T12:00:00Z",
        )

        rows = worktree_summary(since="2026-07-19T11:00:00Z", db=db)
        assert [r["issue_id"] for r in rows] == ["BUG-002"]

    def test_empty_on_missing_db(self, tmp_path: Path) -> None:
        assert worktree_summary(db=tmp_path / "nope" / "history.db") == []

    def test_empty_db_returns_empty_list(self, tmp_path: Path) -> None:
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        assert worktree_summary(db=db) == []
