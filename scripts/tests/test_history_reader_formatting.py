"""Tests for formatting.py: ll_grep/ll_expand/ll_describe message-search formatting (ENH-2775 split from test_history_reader.py)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from little_loops.history_reader import (
    ll_describe,
    ll_expand,
    ll_grep,
)
from little_loops.session_store import (
    compact_session,
    connect,
    ensure_db,
)


class TestSummaryDagRetrieval:
    """Tests for ll_grep, ll_expand, ll_describe (FEAT-1712)."""

    def _make_db_with_compact_session(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with one message and one compacted leaf node."""

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
        db, _ = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", db=db)
        assert len(results) >= 1
        assert any("FSM" in r.content for r in results)

    def test_ll_grep_no_match_returns_empty(self, tmp_path: Path) -> None:
        db, _ = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("ZZZNOMATCH", db=db)
        assert results == []

    def test_ll_grep_attaches_summary_node_context(self, tmp_path: Path) -> None:
        db, node_id = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", db=db)
        assert results[0].summary_id == node_id
        assert results[0].summary_kind == "leaf"

    def test_ll_grep_with_summary_id_filter(self, tmp_path: Path) -> None:
        db, node_id = self._make_db_with_compact_session(tmp_path)
        results = ll_grep("FSM", summary_id=node_id, db=db)
        assert len(results) >= 1

    def test_ll_grep_missing_db_returns_empty(self, tmp_path: Path) -> None:
        results = ll_grep("anything", db=tmp_path / "nonexistent.db")
        assert results == []

    def test_ll_expand_returns_covered_messages(self, tmp_path: Path) -> None:
        db, node_id = self._make_db_with_compact_session(tmp_path)
        messages = ll_expand(node_id, db=db)
        assert len(messages) >= 1
        assert any("FSM" in (m.get("content") or "") for m in messages)

    def test_ll_expand_nonexistent_node_returns_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert ll_expand(99999, db=db) == []

    def test_ll_expand_missing_db_returns_empty(self, tmp_path: Path) -> None:
        assert ll_expand(1, db=tmp_path / "nonexistent.db") == []

    def test_ll_describe_returns_node_metadata(self, tmp_path: Path) -> None:
        db, node_id = self._make_db_with_compact_session(tmp_path)
        node = ll_describe(node_id, db=db)
        assert node is not None
        assert node.id == node_id
        assert node.kind == "leaf"
        assert node.session_id == "dag-sess"
        assert node.level == 0
        assert node.content  # non-empty summary or truncation

    def test_ll_describe_nonexistent_node_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        assert ll_describe(99999, db=db) is None

    def test_ll_describe_missing_db_returns_none(self, tmp_path: Path) -> None:
        assert ll_describe(1, db=tmp_path / "nonexistent.db") is None

    # -- helpers for condensed-node tests --------------------------------------

    def _make_db_with_condensed_node(self, tmp_path: Path) -> tuple[Path, int]:
        """Bootstrap a DB with 30 messages compacted into ≥ 2 leaves + 1 condensed node."""

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
        # Mock subprocess so _call_llm_for_summary never invokes the real
        # claude binary (caught by FEAT-3329's live-spawn guard) — mirrors
        # test_session_store_lifecycle.py::test_compact_session_condensed_node_when_multiple_leaves.
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    {"type": "result", "subtype": "success", "result": "Condensed summary."}
                ),
                stderr="",
            )
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

        db, condensed_id = self._make_db_with_condensed_node(tmp_path)
        messages = ll_expand(condensed_id, db=db)
        assert len(messages) >= 1, (
            f"Expected condensed node {condensed_id} to expand to messages, got empty list"
        )
        assert any("auth" in (m.get("content") or "") for m in messages)

    def test_grep_with_condensed_summary_id(self, tmp_path: Path) -> None:
        """ll_grep(pattern, summary_id=condensed_id) returns matching messages."""

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

        from little_loops.session_store import connect

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

        db, _, l1_id, _ = self._make_db_with_multi_level_dag(tmp_path)
        messages = ll_expand(l1_id, db=db)
        assert len(messages) == 10, f"Expected 10 messages from L1 node, got {len(messages)}"

    def test_grep_with_multi_level_summary_id(self, tmp_path: Path) -> None:
        """ll_grep with a 3-level root summary_id searches across all descendant leaves."""

        db, root_id, _, _ = self._make_db_with_multi_level_dag(tmp_path)
        # Root scope: 5 messages match FSM (sess-a), 5 match auth (sess-b)
        fsm_results = ll_grep("FSM", summary_id=root_id, db=db)
        assert len(fsm_results) == 5, f"Expected 5 FSM matches via root, got {len(fsm_results)}"
        auth_results = ll_grep("auth", summary_id=root_id, db=db)
        assert len(auth_results) == 5, f"Expected 5 auth matches via root, got {len(auth_results)}"
