"""Tests for history_reader.py - typed read-only queries (ENH-1752)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.history_reader import (
    FileEvent,
    IssueEvent,
    SearchResult,
    SessionRef,
    UserCorrection,
    cost_attribution,
    find_user_corrections,
    issue_effort,
    lookup_session_metadata,
    project_digest,
    recent_file_events,
    recent_issue_velocity,
    related_issue_events,
    render_project_context,
    search,
    sessions_for_issue,
)
from little_loops.session_store import SQLiteTransport, connect, ensure_db, record_correction


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


class TestCostAttribution:
    """cost_attribution() token/cost rollup over usage_events (FEAT-2478)."""

    @staticmethod
    def _seed(db: Path) -> None:
        ensure_db(db)
        conn = connect(db)
        rows = [
            # (ts, session, model, state, in, out, cread, ccreate, cost, inv, vendor)
            (
                "2026-07-16T00:00:00Z",
                "s1",
                "claude",
                None,
                100,
                20,
                5,
                7,
                0.01,
                "inv-1",
                "anthropic",
            ),
            (
                "2026-07-16T00:00:01Z",
                "s1",
                "claude",
                None,
                200,
                40,
                10,
                14,
                0.02,
                "inv-1",
                "anthropic",
            ),
            (
                "2026-07-16T00:00:02Z",
                "s2",
                "claude",
                None,
                50,
                10,
                0,
                0,
                0.005,
                "inv-2",
                "anthropic",
            ),
        ]
        conn.executemany(
            "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
            "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
            "cost_usd, invocation_id, provider_vendor) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        assert cost_attribution(db=tmp_path / "nope.db") == []

    def test_group_by_invocation_id_sums_match_raw_totals(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed(db)
        rows = cost_attribution(group_by="gen_ai.invocation.id", db=db)
        assert len(rows) == 2  # one row per invocation
        inv1 = next(r for r in rows if r["gen_ai.invocation.id"] == "inv-1")
        # sum across the invocation's two rows == raw usage totals row-for-row
        assert inv1["gen_ai.usage.input_tokens"] == 300
        assert inv1["gen_ai.usage.output_tokens"] == 60
        assert inv1["gen_ai.usage.cache_read.input_tokens"] == 15
        assert inv1["gen_ai.usage.cache_creation.input_tokens"] == 21
        assert inv1["invocations"] == 2

    def test_group_by_vendor(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        self._seed(db)
        rows = cost_attribution(group_by="gen_ai.provider.vendor", db=db)
        assert len(rows) == 1
        assert rows[0]["gen_ai.provider.vendor"] == "anthropic"
        assert rows[0]["gen_ai.usage.input_tokens"] == 350

    def test_unsupported_group_by_raises(self, tmp_path: Path) -> None:
        import pytest

        db = tmp_path / "history.db"
        self._seed(db)
        with pytest.raises(ValueError):
            cost_attribution(group_by="'; DROP TABLE usage_events; --", db=db)


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
                    "INSERT INTO issue_events(ts, issue_id, transition) VALUES(?, ?, ?)",
                    (ts, "BUG-1", f"step_{i}"),
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


class TestProjectDigest:
    """Tests for project_digest() and render_project_context() (ENH-1907)."""

    def _insert_file_event(self, db: Path, path: str, ts: str | None = None) -> None:
        # Default to a recent timestamp so "fresh row" assertions stay inside the
        # digest's day window regardless of the wall-clock date the suite runs on.
        ts = ts or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO file_events(ts, session_id, path, op) VALUES(?, ?, ?, ?)",
                (ts, "sess-1", path, "Write"),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_issue_event(
        self, db: Path, issue_id: str, transition: str, ts: str | None = None
    ) -> None:
        ts = ts or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, issue_type, priority) "
                "VALUES(?, ?, ?, ?, ?)",
                (ts, issue_id, transition, "ENH", "P3"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_missing_db_returns_empty_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "nonexistent.db"
        digest = project_digest(db)
        assert digest.empty

    def test_empty_tables_returns_empty_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        digest = project_digest(db)
        assert digest.empty

    def test_populated_db_touched_files_section(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30)
        assert not digest.empty
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names

    def test_stale_rows_excluded_from_digest(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        old_ts = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._insert_file_event(db, "scripts/stale.py", ts=old_ts)
        digest = project_digest(db, days=5)
        assert digest.empty

    def test_completed_issues_section_done(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "ENH-999", "done")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" in section_names
        _, lines = next(s for s in digest.sections if s[0] == "completed_issues")
        assert any("ENH-999" in line for line in lines)

    def test_completed_issues_section_cancelled(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "BUG-777", "cancelled")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" in section_names

    def test_open_issues_excluded_from_completed(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_issue_event(db, "FEAT-555", "open")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "completed_issues" not in section_names

    def test_recurring_corrections_section(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        record_correction(db, "sess-1", "no Co-Authored-By trailers", "user")
        record_correction(db, "sess-2", "no Co-Authored-By trailers", "user")
        digest = project_digest(db, days=30)
        section_names = [name for name, _ in digest.sections]
        assert "recurring_corrections" in section_names

    def test_section_ordering_respected(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        self._insert_issue_event(db, "ENH-1", "done")
        digest = project_digest(db, days=30, sections=["completed_issues", "touched_files"])
        section_names = [name for name, _ in digest.sections]
        assert section_names[0] == "completed_issues"
        assert section_names[1] == "touched_files"

    def test_omitted_section_absent(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        record_correction(db, "sess-1", "some correction text", "user")
        digest = project_digest(db, days=30, sections=["touched_files"])
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names
        assert "recurring_corrections" not in section_names

    def test_empty_sections_list_renders_all_sections(self, tmp_path: Path) -> None:
        # An empty sections list is treated the same as None (the config default):
        # render all registered providers, per project_digest()'s documented contract.
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30, sections=[])
        assert not digest.empty
        section_names = [name for name, _ in digest.sections]
        assert "touched_files" in section_names

    def test_render_nonempty_digest_wraps_in_tags(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        self._insert_file_event(db, "scripts/foo.py")
        digest = project_digest(db, days=30)
        block = render_project_context(digest)
        assert block.startswith("<project_context>")
        assert block.endswith("</project_context>")
        assert "scripts/foo.py" in block

    def test_render_empty_digest_returns_empty_string(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        digest = project_digest(db)
        assert render_project_context(digest) == ""

    def test_char_cap_enforced(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        ensure_db(db)
        for i in range(30):
            self._insert_file_event(db, f"scripts/module_{i}_with_long_path_name.py")
        digest = project_digest(db, days=30)
        block = render_project_context(digest, char_cap=200)
        assert len(block) <= 200
        assert "<project_context>" in block
        assert "</project_context>" in block


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


class TestSummaryDagRetrieval:
    """Tests for ll_grep, ll_expand, ll_describe (FEAT-1712)."""

    def _make_db_with_compact_session(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with one message and one compacted leaf node."""
        from little_loops.session_store import compact_session, connect

        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                ("dag-sess", str(tmp_path / "dag-sess.jsonl")),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:00Z", "dag-sess", "architectural decision about FSM runner"),
            )
            conn.commit()
        finally:
            conn.close()
        compact_session("dag-sess", db)
        conn = connect(db)
        try:
            node_id = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='leaf' AND session_id='dag-sess'"
            ).fetchone()["id"]
        finally:
            conn.close()
        return db, node_id

    def test_ll_grep_finds_matching_messages(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_grep

        db, _ = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", db=db)
        assert len(results) >= 1
        assert any("FSM" in r.content for r in results)

    def test_ll_grep_no_match_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_grep

        db, _ = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("ZZZNOMATCH", db=db)
        assert results == []

    def test_ll_grep_attaches_summary_node_context(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_grep

        db, node_id = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", db=db)
        assert results[0].summary_id == node_id
        assert results[0].summary_kind == "leaf"

    def test_ll_grep_with_summary_id_filter(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_grep

        db, node_id = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", summary_id=node_id, db=db)
        assert len(results) >= 1

    def test_ll_grep_missing_db_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_grep

        results = ll_grep("anything", db=tmp_path / "nonexistent.db")
        assert results == []

    def test_ll_expand_returns_covered_messages(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_expand

        db, node_id = self._make_db_with_compact_session(tmp_path)
        messages = ll_expand(node_id, db=db)
        assert len(messages) >= 1
        assert any("FSM" in (m.get("content") or "") for m in messages)

    def test_ll_expand_nonexistent_node_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_expand
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        assert ll_expand(99999, db=db) == []

    def test_ll_expand_missing_db_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_expand

        assert ll_expand(1, db=tmp_path / "nonexistent.db") == []

    def test_ll_describe_returns_node_metadata(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_describe

        db, node_id = self._make_db_with_compact_session(tmp_path)
        node = ll_describe(node_id, db=db)
        assert node is not None
        assert node.id == node_id
        assert node.kind == "leaf"
        assert node.session_id == "dag-sess"
        assert node.level == 0
        assert node.content  # non-empty summary or truncation

    def test_ll_describe_nonexistent_node_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_describe
        from little_loops.session_store import ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        assert ll_describe(99999, db=db) is None

    def test_ll_describe_missing_db_returns_none(self, tmp_path: Path) -> None:
        from little_loops.history_reader import ll_describe

        assert ll_describe(1, db=tmp_path / "nonexistent.db") is None

    # -- helpers for condensed-node tests --------------------------------------

    def _make_db_with_condensed_node(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with 30 messages compacted into ≥ 2 leaves + 1 condensed node."""
        from little_loops.session_store import compact_session, connect

        session_id = "dag-condensed"
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            for i in range(30):
                ts = f"2026-01-01T00:{i:02d}:00Z"
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (ts, session_id, f"Message number {i}. auth middleware FSM test."),
                )
            conn.commit()
        finally:
            conn.close()
        config = {"history": {"compaction": {"enabled": True, "budget_tokens": 10}}}
        compact_session(session_id, db, config=config)
        conn = connect(db)
        try:
            condensed_id = conn.execute(
                "SELECT id FROM summary_nodes WHERE kind='condensed' AND session_id=?",
                (session_id,),
            ).fetchone()["id"]
        finally:
            conn.close()
        return db, condensed_id

    def test_expand_condensed_node_returns_messages(self, tmp_path: Path) -> None:
        """ll_expand(condensed_id) returns messages via two-hop traversal."""
        from little_loops.history_reader import ll_expand

        db, condensed_id = self._make_db_with_condensed_node(tmp_path)
        messages = ll_expand(condensed_id, db=db)
        assert len(messages) >= 1, (
            f"Expected condensed node {condensed_id} to expand to messages, got empty list"
        )
        assert any("auth" in (m.get("content") or "") for m in messages)

    def test_grep_with_condensed_summary_id(self, tmp_path: Path) -> None:
        """ll_grep(pattern, summary_id=condensed_id) returns matching messages."""
        from little_loops.history_reader import ll_grep

        db, condensed_id = self._make_db_with_condensed_node(tmp_path)
        results = ll_grep("FSM", summary_id=condensed_id, db=db)
        assert len(results) >= 1, (
            f"Expected grep with condensed summary_id {condensed_id} to find matches, "
            f"got empty list"
        )
        assert any("FSM" in r.content for r in results)

    # -- multi-level DAG tests (ENH-1955) ---------------------------------------

    def _make_db_with_multi_level_dag(self, tmp_path: Path) -> tuple[Path, int, int, int]:
        """Build a 3-level DAG: leaf (L0) → cross-session condensed (L1) → root (L2).

        Returns (db_path, root_id, l1_node_id, leaf_a_id).
        """
        from datetime import UTC, datetime

        from little_loops.session_store import connect, ensure_db

        db = tmp_path / "history.db"
        ensure_db(db)
        conn = connect(db)
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            # Two sessions
            for sid in ("sess-a", "sess-b"):
                conn.execute(
                    "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                    (sid, str(tmp_path / f"{sid}.jsonl")),
                )
            # 5 messages per session
            for i in range(5):
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", "sess-a", f"Session A message {i} about FSM"),
                )
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", "sess-b", f"Session B message {i} about auth"),
                )

            # Per-session leaf nodes (level 0)
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('leaf', 'Leaf A summary', 100, 'sess-a', 0, ?)",
                (now,),
            )
            leaf_a = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('leaf', 'Leaf B summary', 100, 'sess-b', 0, ?)",
                (now,),
            )
            leaf_b = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Link leaves to messages
            for row in conn.execute(
                "SELECT id FROM message_events WHERE session_id='sess-a'"
            ).fetchall():
                conn.execute(
                    "INSERT INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                    (leaf_a, row["id"]),
                )
            for row in conn.execute(
                "SELECT id FROM message_events WHERE session_id='sess-b'"
            ).fetchall():
                conn.execute(
                    "INSERT INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                    (leaf_b, row["id"]),
                )

            # Level-1 cross-session condensed node
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('condensed', 'L1 cross-session summary', 200, NULL, 1, ?)",
                (now,),
            )
            l1_node = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (l1_node, leaf_a))
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (l1_node, leaf_b))

            # Level-2 root node
            conn.execute(
                "INSERT INTO summary_nodes(kind, content, tokens, session_id, level, created_at)"
                " VALUES('condensed', 'Root project summary', 300, NULL, 2, ?)",
                (now,),
            )
            root_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE summary_nodes SET parent_id=? WHERE id=?", (root_id, l1_node))

            conn.commit()
        finally:
            conn.close()
        return db, root_id, l1_node, leaf_a

    def test_expand_root_node_returns_all_messages(self, tmp_path: Path) -> None:
        """ll_expand on a 3-level root node returns messages from all descendant leaves."""
        from little_loops.history_reader import ll_expand

        db, root_id, _, _ = self._make_db_with_multi_level_dag(tmp_path)
        messages = ll_expand(root_id, db=db)
        assert len(messages) == 10, (
            f"Expected 10 messages from root (5 sess-a + 5 sess-b), got {len(messages)}"
        )
        contents = " ".join(m.get("content", "") for m in messages)
        assert "FSM" in contents
        assert "auth" in contents

    def test_expand_intermediate_condensed_node(self, tmp_path: Path) -> None:
        """ll_expand on an L1 condensed node returns messages from its leaf children."""
        from little_loops.history_reader import ll_expand

        db, _, l1_id, _ = self._make_db_with_multi_level_dag(tmp_path)
        messages = ll_expand(l1_id, db=db)
        assert len(messages) == 10, f"Expected 10 messages from L1 node, got {len(messages)}"

    def test_grep_with_multi_level_summary_id(self, tmp_path: Path) -> None:
        """ll_grep with a 3-level root summary_id searches across all descendant leaves."""
        from little_loops.history_reader import ll_grep

        db, root_id, _, _ = self._make_db_with_multi_level_dag(tmp_path)
        # Root scope: 5 messages match FSM (sess-a), 5 match auth (sess-b)
        fsm_results = ll_grep("FSM", summary_id=root_id, db=db)
        assert len(fsm_results) == 5, f"Expected 5 FSM matches via root, got {len(fsm_results)}"
        auth_results = ll_grep("auth", summary_id=root_id, db=db)
        assert len(auth_results) == 5, f"Expected 5 auth matches via root, got {len(auth_results)}"


class TestCondensedNodesForIssue:
    """condensed_nodes_for_issue() returns level-0 condensed nodes for an issue's sessions (ENH-2231)."""

    def _seed(
        self,
        db: Path,
        *,
        issue_id: str,
        session_id: str,
        content: str,
        ts_end: str = "2026-01-10T13:00:00Z",
    ) -> None:
        """Seed issue_events + message_events + a level-0 condensed summary_node."""
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", issue_id, "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                (ts_end, session_id, "msg"),
            )
            conn.execute(
                "INSERT INTO summary_nodes"
                "(kind, content, tokens, session_id, level, ts_end, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                ("condensed", content, 100, session_id, 0, ts_end, "2026-01-10T14:00:00Z"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "nonexistent.db"
        assert condensed_nodes_for_issue("ENH-9999", db=db) == []

    def test_empty_db_returns_empty(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        ensure_db(db)
        assert condensed_nodes_for_issue("ENH-9999", db=db) == []

    def test_returns_condensed_node_for_issue(self, tmp_path: Path) -> None:
        from little_loops.history_reader import SummaryNode, condensed_nodes_for_issue

        db = tmp_path / "test.db"
        self._seed(db, issue_id="ENH-100", session_id="sess-a", content="A summary of prior work")
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert len(result) == 1
        assert isinstance(result[0], SummaryNode)
        assert result[0].kind == "condensed"
        assert "prior work" in result[0].content
        assert result[0].level == 0
        assert result[0].session_id == "sess-a"

    def test_does_not_return_other_issues_nodes(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        self._seed(db, issue_id="ENH-999", session_id="sess-b", content="Other issue summary")
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert result == []

    def test_does_not_return_leaf_nodes(self, tmp_path: Path) -> None:
        """kind='leaf' nodes are excluded; only condensed."""
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", "ENH-100", "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", "sess-c", "msg"),
            )
            conn.execute(
                "INSERT INTO summary_nodes"
                "(kind, content, tokens, session_id, level, ts_start, ts_end, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "leaf",
                    "leaf content",
                    50,
                    "sess-c",
                    0,
                    "2026-01-10T13:00:00Z",
                    "2026-01-10T13:00:00Z",
                    "2026-01-10T14:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert result == []

    def test_does_not_return_higher_level_nodes(self, tmp_path: Path) -> None:
        """level=1 cross-session condensed nodes (session_id IS NULL) are excluded."""
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?, ?, ?, ?)",
                ("2026-01-10T12:00:00Z", "ENH-100", "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", "sess-d", "msg"),
            )
            conn.execute(
                "INSERT INTO summary_nodes"
                "(kind, content, tokens, session_id, level, ts_start, ts_end, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "condensed",
                    "Cross-session summary",
                    200,
                    None,  # session_id IS NULL → cross-session
                    1,
                    "2026-01-10T12:00:00Z",
                    "2026-01-10T13:00:00Z",
                    "2026-01-10T14:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert result == []

    def test_limit_respected(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-100", "open", "2026-01-10T00:00:00Z"),
            )
            for i in range(5):
                sess = f"sess-{i:02d}"
                ts = f"2026-01-1{i}T13:00:00Z"
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (ts, sess, f"msg {i}"),
                )
                conn.execute(
                    "INSERT INTO summary_nodes"
                    "(kind, content, tokens, session_id, level, ts_end, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    ("condensed", f"summary {i}", 100, sess, 0, ts, "2026-01-10T14:00:00Z"),
                )
            conn.commit()
        finally:
            conn.close()
        result = condensed_nodes_for_issue("ENH-100", limit=2, db=db)
        assert len(result) == 2

    def test_returns_newest_first(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", "ENH-100", "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T13:00:00Z", "sess-old", "old msg"),
            )
            conn.execute(
                "INSERT INTO summary_nodes"
                "(kind, content, tokens, session_id, level, ts_end, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    "condensed",
                    "old summary",
                    50,
                    "sess-old",
                    0,
                    "2026-01-10T13:00:00Z",
                    "2026-01-10T14:00:00Z",
                ),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-12T13:00:00Z", "sess-new", "new msg"),
            )
            conn.execute(
                "INSERT INTO summary_nodes"
                "(kind, content, tokens, session_id, level, ts_end, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    "condensed",
                    "new summary",
                    50,
                    "sess-new",
                    0,
                    "2026-01-12T13:00:00Z",
                    "2026-01-10T14:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert len(result) == 2
        assert "new" in result[0].content
        assert "old" in result[1].content

    def test_content_truncated_to_node_char_cap(self, tmp_path: Path) -> None:
        from little_loops.history_reader import condensed_nodes_for_issue

        db = tmp_path / "test.db"
        self._seed(db, issue_id="ENH-100", session_id="sess-a", content="x" * 1000)
        result = condensed_nodes_for_issue("ENH-100", node_char_cap=200, db=db)
        assert len(result) == 1
        assert len(result[0].content) <= 200


class TestNewEventReaders:
    """ENH-2458/2459/2460/2462: readers for commit, test-run, and skill completion data."""

    def test_recent_skill_events_includes_completion_columns(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_skill_events
        from little_loops.session_store import record_skill_event, skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "refine-issue", "ENH-1"):
            pass
        record_skill_event(db, "s2", "refine-issue", "ENH-2")  # dispatch-only

        events = recent_skill_events("refine-issue", db=db)
        assert len(events) == 2
        # Newest first: dispatch-only row has NULL completion columns
        assert events[0].success is None
        assert events[1].success == 1
        assert events[1].exit_code == 0
        assert events[1].duration_ms is not None

    def test_summarize_skills_success_rate(self, tmp_path: Path) -> None:
        import pytest as _pytest

        from little_loops.history_reader import summarize_skills
        from little_loops.session_store import record_skill_event, skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "check-code", ""):
            pass
        with _pytest.raises(RuntimeError):
            with skill_event_context(db, "s2", "check-code", ""):
                raise RuntimeError("boom")
        record_skill_event(db, "s3", "check-code", "")  # dispatch-only, no completion

        stats = summarize_skills(db=db)
        assert len(stats) == 1
        s = stats[0]
        assert s["skill_name"] == "check-code"
        assert s["invocations"] == 3
        assert s["completions"] == 2
        assert s["successes"] == 1
        assert s["success_rate"] == 0.5

    def test_recent_commit_events_filters(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_commit_events
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "sha1", "fix BUG-1", branch="main", ts="2026-07-01T10:00:00Z")
        record_commit_event(
            db, "sha2", "Closes ENH-2458", branch="feat/x", ts="2026-07-01T11:00:00Z"
        )

        all_events = recent_commit_events(db=db)
        assert [e.commit_sha for e in all_events] == ["sha2", "sha1"]

        by_issue = recent_commit_events(issue_id="ENH-2458", db=db)
        assert len(by_issue) == 1
        assert by_issue[0].commit_sha == "sha2"

        by_branch = recent_commit_events(branch="main", db=db)
        assert len(by_branch) == 1
        assert by_branch[0].issue_id == "BUG-1"

    def test_recent_test_runs_and_pass_rate(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_test_runs
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T10:00:00Z",
            total=10,
            passed=9,
            failed=1,
            head_sha="aaa",
            branch="main",
        )
        record_test_run_event(db, ts="2026-07-01T11:00:00Z", total=0, head_sha="bbb")

        runs = recent_test_runs(db=db)
        assert len(runs) == 2
        assert runs[1].pass_rate == 0.9
        assert runs[0].pass_rate is None  # total=0 → undefined

        by_sha = recent_test_runs(head_sha="aaa", db=db)
        assert len(by_sha) == 1
        assert by_sha[0].branch == "main"

    def test_find_session_for_issue_transition(self, tmp_path: Path) -> None:
        from little_loops.history_reader import find_session_for_issue_transition

        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, session_id) "
                "VALUES('2026-07-01T10:00:00Z', 'ENH-2462', 'done', 'sess-closer')"
            )
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition) "
                "VALUES('2026-07-01T09:00:00Z', 'ENH-9', 'done')"
            )
            conn.commit()
        finally:
            conn.close()

        assert find_session_for_issue_transition("ENH-2462", "done", db=db) == "sess-closer"
        assert find_session_for_issue_transition("ENH-9", "done", db=db) is None  # legacy row
        assert find_session_for_issue_transition("ENH-404", "done", db=db) is None

    def test_related_issue_events_session_filter(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, session_id) "
                "VALUES('2026-07-01T10:00:00Z', 'ENH-2462', 'open', 'sess-a')"
            )
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, session_id) "
                "VALUES('2026-07-01T11:00:00Z', 'ENH-2462', 'done', 'sess-b')"
            )
            conn.commit()
        finally:
            conn.close()

        all_events = related_issue_events("ENH-2462", db=db)
        assert len(all_events) == 2
        assert {e.session_id for e in all_events} == {"sess-a", "sess-b"}

        only_b = related_issue_events("ENH-2462", session_id="sess-b", db=db)
        assert len(only_b) == 1
        assert only_b[0].transition == "done"

    def test_recent_orchestration_runs_filters(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        reader = getattr(history_reader, "recent_orchestration_runs", None)
        assert callable(recorder), "record_orchestration_run must exist"
        assert callable(reader), "recent_orchestration_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="batch-a",
            driver="ll-auto",
            issue_id="BUG-1",
            status="completed",
            duration_s=2.0,
            ended_at="2026-07-17T10:00:00Z",
        )
        recorder(
            db,
            run_id="batch-b",
            driver="ll-sprint",
            issue_id="BUG-2",
            status="failed",
            failure_reason="boom",
            duration_s=4.0,
            ended_at="2026-07-17T11:00:00Z",
        )

        rows = reader(db=db)
        assert [row.run_id for row in rows] == ["batch-b", "batch-a"]
        assert reader(driver="ll-auto", db=db)[0].issue_id == "BUG-1"
        assert reader(issue_id="BUG-2", db=db)[0].driver == "ll-sprint"
        assert reader(since="2026-07-17T10:30:00Z", db=db)[0].run_id == "batch-b"

    def test_aggregate_orchestration_runs(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        aggregate = getattr(history_reader, "aggregate_orchestration_runs", None)
        assert callable(recorder), "record_orchestration_run must exist"
        assert callable(aggregate), "aggregate_orchestration_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="r1",
            driver="ll-auto",
            issue_id="BUG-1",
            status="completed",
            duration_s=2.0,
        )
        recorder(
            db,
            run_id="r2",
            driver="ll-auto",
            issue_id="BUG-2",
            status="failed",
            duration_s=4.0,
        )
        stats = aggregate(group_by="driver", db=db)
        assert stats == [
            {
                "driver": "ll-auto",
                "runs": 2,
                "completed": 1,
                "success_rate": 0.5,
                "avg_duration_s": 3.0,
            }
        ]

    def test_recent_orchestration_runs_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops import history_reader

        reader = getattr(history_reader, "recent_orchestration_runs", None)
        assert callable(reader), "recent_orchestration_runs must exist"
        assert reader(db=tmp_path / "nope" / "history.db") == []

    def test_recent_loop_runs_filters(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        reader = getattr(history_reader, "recent_loop_runs", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(reader), "recent_loop_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="20260717T100000-rn-implement",
            loop_name="rn-implement",
            terminated_by="terminal",
            ended_at="2026-07-17T10:00:00Z",
        )
        recorder(
            db,
            run_id="20260717T110000-rn-refine",
            loop_name="rn-refine",
            terminated_by="error",
            ended_at="2026-07-17T11:00:00Z",
        )

        rows = reader(db=db)
        assert [row.run_id for row in rows] == [
            "20260717T110000-rn-refine",
            "20260717T100000-rn-implement",
        ]
        assert reader(loop_name="rn-implement", db=db)[0].loop_name == "rn-implement"
        assert reader(since="2026-07-17T10:30:00Z", db=db)[0].run_id == (
            "20260717T110000-rn-refine"
        )

    def test_find_loop_run(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        finder = getattr(history_reader, "find_loop_run", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(finder), "find_loop_run must exist"

        db = tmp_path / "history.db"
        recorder(db, run_id="run-1", loop_name="rn-implement", terminated_by="terminal")

        found = finder("run-1", db=db)
        assert found is not None
        assert found.loop_name == "rn-implement"
        assert finder("no-such-run", db=db) is None

    def test_aggregate_loop_runs(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        aggregate = getattr(history_reader, "aggregate_loop_runs", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(aggregate), "aggregate_loop_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db, run_id="run-1", loop_name="rn-implement", iterations=2, terminated_by="terminal"
        )
        recorder(
            db, run_id="run-2", loop_name="rn-implement", iterations=4, terminated_by="terminal"
        )

        stats = aggregate(group_by="loop_name", db=db)
        assert stats == [{"loop_name": "rn-implement", "runs": 2, "avg_iterations": 3.0}]

    def test_recent_loop_runs_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops import history_reader

        reader = getattr(history_reader, "recent_loop_runs", None)
        assert callable(reader), "recent_loop_runs must exist"
        assert reader(db=tmp_path / "nope" / "history.db") == []
        finder = getattr(history_reader, "find_loop_run", None)
        assert finder("run-1", db=tmp_path / "nope" / "history.db") is None
        aggregate = getattr(history_reader, "aggregate_loop_runs", None)
        assert aggregate(db=tmp_path / "nope" / "history.db") == []

    def test_readers_return_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import (
            find_session_for_issue_transition,
            recent_commit_events,
            recent_skill_events,
            recent_test_runs,
            summarize_skills,
        )

        db = tmp_path / "nope" / "history.db"
        # ensure_db creates on demand, so these return empty rather than raising
        assert recent_skill_events(db=db) == []
        assert summarize_skills(db=db) == []
        assert recent_commit_events(db=db) == []
        assert recent_test_runs(db=db) == []
        assert find_session_for_issue_transition("X-1", "done", db=db) is None


class TestUsageEventReaders:
    """ENH-2461: recent_usage_events / aggregate_usage over usage_events."""

    def _seed(self, db: Path, rows: list[dict]) -> None:
        ensure_db(db)
        conn = connect(db)
        try:
            for r in rows:
                conn.execute(
                    "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
                    "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, "
                    "cost_usd) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        r["ts"],
                        r.get("session_id"),
                        r.get("model"),
                        None,
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        r.get("cache_read_input_tokens", 0),
                        r.get("cache_creation_input_tokens", 0),
                        r.get("cost_usd"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def test_recent_usage_events_newest_first_and_filters(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_usage_events

        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "2026-07-01T10:00:00Z",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.1,
                },
                {
                    "ts": "2026-07-01T11:00:00Z",
                    "session_id": "b",
                    "model": "m2",
                    "input_tokens": 20,
                    "output_tokens": 2,
                    "cost_usd": 0.2,
                },
            ],
        )
        rows = recent_usage_events(db=db)
        assert [r.model for r in rows] == ["m2", "m1"]  # newest (highest id) first
        assert recent_usage_events(model="m1", db=db)[0].session_id == "a"
        assert recent_usage_events(session_id="b", db=db)[0].model == "m2"
        assert recent_usage_events(since="2026-07-01T10:30:00Z", db=db) == [
            r for r in rows if r.model == "m2"
        ]

    def test_recent_usage_events_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_usage_events

        assert recent_usage_events(db=tmp_path / "no" / "history.db") == []

    def test_aggregate_usage_by_model(self, tmp_path: Path) -> None:
        import pytest

        from little_loops.history_reader import aggregate_usage

        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "t1",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.10,
                },
                {
                    "ts": "t2",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 30,
                    "output_tokens": 3,
                    "cost_usd": 0.30,
                },
                {
                    "ts": "t3",
                    "session_id": "b",
                    "model": "m2",
                    "input_tokens": 5,
                    "output_tokens": 5,
                    "cost_usd": None,
                },
            ],
        )
        agg = aggregate_usage("model", db=db)
        by_model = {a["model"]: a for a in agg}
        assert by_model["m1"]["events"] == 2
        assert by_model["m1"]["input_tokens"] == 40
        assert by_model["m1"]["cost_usd"] == pytest.approx(0.40)
        # unpriced model rows: NULL cost sums to 0 in SQLite SUM
        assert by_model["m2"]["events"] == 1

    def test_aggregate_usage_by_session(self, tmp_path: Path) -> None:
        from little_loops.history_reader import aggregate_usage

        db = tmp_path / "history.db"
        self._seed(
            db,
            [
                {
                    "ts": "t1",
                    "session_id": "a",
                    "model": "m1",
                    "input_tokens": 10,
                    "output_tokens": 1,
                    "cost_usd": 0.1,
                },
                {
                    "ts": "t2",
                    "session_id": "a",
                    "model": "m2",
                    "input_tokens": 20,
                    "output_tokens": 2,
                    "cost_usd": 0.2,
                },
            ],
        )
        agg = aggregate_usage("session", db=db)
        assert len(agg) == 1
        assert agg[0]["session"] == "a"
        assert agg[0]["events"] == 2
        assert agg[0]["input_tokens"] == 30
