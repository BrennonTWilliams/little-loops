"""Tests for search.py: full-text search, correction, and file-event queries (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.history_reader import (
    FileEvent,
    SearchResult,
    UserCorrection,
    find_user_corrections,
    recent_file_events,
    related_issue_events,
    search,
    sessions_for_issue,
)
from little_loops.session_store import (
    SQLiteTransport,
    connect,
    ensure_db,
    record_correction,
)


class TestMissingDatabase:
    """All functions return empty lists when the database is absent."""

    def test_find_user_corrections_missing_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = find_user_corrections("anything", db=db)
        assert result == []

    def test_recent_file_events_missing_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = recent_file_events("something", db=db)
        assert result == []

    def test_search_missing_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = search("anything", db=db)
        assert result == []

    def test_related_issue_events_missing_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = related_issue_events("BUG-9999", db=db)
        assert result == []

    def test_sessions_for_issue_missing_db(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        result = sessions_for_issue("ENH-9999", db=db)
        assert result == []


class TestEmptyTables:
    """All functions return empty lists when tables exist but are empty."""

    def test_find_user_corrections_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = find_user_corrections("anything", db=db)
        assert result == []

    def test_recent_file_events_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = recent_file_events("something.py", db=db)
        assert result == []

    def test_search_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = search("anything", db=db)
        assert result == []

    def test_related_issue_events_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = related_issue_events("BUG-9999", db=db)
        assert result == []

    def test_sessions_for_issue_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = sessions_for_issue("ENH-9999", db=db)
        assert result == []


class TestStaleRowFiltering:
    """Stale rows (>30 days) are excluded by default, included with include_stale=True."""

    def _insert_old_correction(self, db: Path, topic: str, days_old: int) -> None:
        conn = connect(db)
        try:
            ts = (datetime.now(UTC) - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-1", f"fix the {topic} bug", "user"),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_old_file_event(self, db: Path, path: str, days_old: int) -> None:
        conn = connect(db)
        try:
            ts = (datetime.now(UTC) - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (ts, "sess-1", path, "modify", "BUG-1", "abc123"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_fresh_correction_is_included(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        self._insert_old_correction(db, "rate-limit", days_old=5)
        result = find_user_corrections("rate-limit", db=db)
        assert len(result) == 1
        assert isinstance(result[0], UserCorrection)
        assert "rate-limit" in result[0].content

    def test_stale_correction_excluded_by_default(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        self._insert_old_correction(db, "rate-limit", days_old=40)
        result = find_user_corrections("rate-limit", db=db)
        assert result == []

    def test_stale_correction_included_when_asked(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        self._insert_old_correction(db, "rate-limit", days_old=40)
        result = find_user_corrections("rate-limit", include_stale=True, db=db)
        assert len(result) == 1

    def test_stale_file_event_excluded(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        self._insert_old_file_event(db, "scripts/main.py", days_old=40)
        result = recent_file_events("main.py", db=db)
        assert result == []

    def test_stale_file_event_included_when_asked(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        self._insert_old_file_event(db, "scripts/main.py", days_old=40)
        result = recent_file_events("main.py", include_stale=True, db=db)
        assert len(result) == 1


class TestFindUserCorrections:
    """Topic-filtered user correction queries."""

    def test_exact_topic_match(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-a", "use a set for ids", "user"),
            )
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-b", "don't sort all items", "user"),
            )
            conn.commit()
        finally:
            conn.close()
        result = find_user_corrections("set", db=db)
        assert len(result) == 1
        assert result[0].session_id == "sess-a"

    def test_topic_filter_is_like_match(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, ?)",
                (ts, "sess-1", "the rate_limit function is wrong", "user"),
            )
            conn.commit()
        finally:
            conn.close()
        result = find_user_corrections("rate", db=db)
        assert len(result) == 1
        result = find_user_corrections("zzzzz", db=db)
        assert result == []

    def test_limit_is_respected(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            for i in range(5):
                conn.execute(
                    "INSERT INTO user_corrections(ts, session_id, content, source) "
                    "VALUES(?, ?, ?, ?)",
                    (ts, f"sess-{i}", f"fix issue {i}", "user"),
                )
            conn.commit()
        finally:
            conn.close()
        result = find_user_corrections("fix", limit=3, db=db)
        assert len(result) == 3


class TestRecentFileEvents:
    """Path-filtered file event queries."""

    def test_path_like_match(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (ts, "s1", "scripts/main.py", "modify", "BUG-1", "abc"),
            )
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (ts, "s2", "scripts/utils.py", "modify", "BUG-2", "def"),
            )
            conn.commit()
        finally:
            conn.close()
        result = recent_file_events("main", db=db)
        assert len(result) == 1
        assert isinstance(result[0], FileEvent)
        assert result[0].path == "scripts/main.py"
        assert result[0].issue_id == "BUG-1"


class TestSearch:
    """FTS5 search with optional kind filter."""

    def test_search_returns_ranked_results(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "ratelimit", "state": "execute"})
        transport.send({"event": "state_enter", "loop_name": "ratelimit-fast", "state": "verify"})
        transport.close()
        result = search("ratelimit", db=db)
        assert len(result) >= 1
        assert isinstance(result[0], SearchResult)
        assert "ratelimit" in result[0].content

    def test_search_with_kind_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        transport = SQLiteTransport(db)
        transport.send({"event": "state_enter", "loop_name": "deploy-check", "state": "wait"})
        transport.send(
            {
                "event": "issue.completed",
                "issue_id": "BUG-99",
                "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        transport.close()
        result = search("deploy", kind="loop", db=db)
        assert len(result) >= 1
        assert all(r.kind == "loop" for r in result)

    def test_search_invalid_query_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        result = search("", db=db)
        assert result == []

    def test_search_hyphenated_id_matches(self, tmp_path: Path) -> None:
        """A hyphenated issue ID must match literally, not be parsed as an FTS
        column-filter/negation operator (BUG-2651)."""
        db = tmp_path / "test.db"
        record_correction(db, "sess-1", "Fixed BUG-490 in the parser", "user")
        result = search("BUG-490", kind="correction", db=db)
        assert len(result) >= 1
        assert "BUG-490" in result[0].content

    def test_search_hyphenated_id_unfiltered(self, tmp_path: Path) -> None:
        """Same fix must apply to the kind-less MATCH branch (BUG-2651)."""
        db = tmp_path / "test.db"
        record_correction(db, "sess-2", "Notes about ENH-2589 rollout", "user")
        result = search("ENH-2589", db=db)
        assert len(result) >= 1
        assert "ENH-2589" in result[0].content
