"""Tests for summary_dag.py: Summary-DAG retrieval (FEAT-1712) (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

from pathlib import Path

from little_loops.history_reader import (
    SummaryNode,
    condensed_nodes_for_issue,
)
from little_loops.session_store import (
    connect,
    ensure_db,
)


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

        db = tmp_path / "nonexistent.db"
        assert condensed_nodes_for_issue("ENH-9999", db=db) == []

    def test_empty_db_returns_empty(self, tmp_path: Path) -> None:

        db = tmp_path / "test.db"
        ensure_db(db)
        assert condensed_nodes_for_issue("ENH-9999", db=db) == []

    def test_returns_condensed_node_for_issue(self, tmp_path: Path) -> None:

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

        db = tmp_path / "test.db"
        self._seed(db, issue_id="ENH-999", session_id="sess-b", content="Other issue summary")
        result = condensed_nodes_for_issue("ENH-100", db=db)
        assert result == []

    def test_does_not_return_leaf_nodes(self, tmp_path: Path) -> None:
        """kind='leaf' nodes are excluded; only condensed."""

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

        db = tmp_path / "test.db"
        self._seed(db, issue_id="ENH-100", session_id="sess-a", content="x" * 1000)
        result = condensed_nodes_for_issue("ENH-100", node_char_cap=200, db=db)
        assert len(result) == 1
        assert len(result[0].content) <= 200
