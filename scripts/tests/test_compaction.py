"""Tests for little_loops.compaction — instant eviction + 6-section summary (FEAT-2598)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from little_loops.compaction.instant import (
    SECTION_HEADERS,
    compute_goal_tokens,
    evict_sink_and_window,
    is_valid_cutoff,
    select_sliding_window,
    summarize_6_section,
)
from little_loops.compaction.result import (
    CompactResult,
    compact_result_for_session,
    compact_result_for_session_with_reasoning,
)
from little_loops.session_store import compact_session, connect


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _llm_response(result_text: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "result": result_text})


class TestEvictSinkAndWindow:
    """Unit tests for evict_sink_and_window() — StreamingLLM-style structural eviction."""

    def test_noop_when_messages_fit_within_sink_plus_window(self) -> None:
        messages = [{"role": "user", "content": f"m{i}"} for i in range(5)]
        result = evict_sink_and_window(messages, sink_n=4, window_n=20)
        assert result == messages

    def test_drops_middle_keeps_sink_and_window(self) -> None:
        messages = [{"role": "user", "content": f"m{i}"} for i in range(30)]
        result = evict_sink_and_window(messages, sink_n=4, window_n=5)
        contents = [m["content"] for m in result]
        # First 4 (sink) and last 5 (window) survive; middle is dropped.
        assert contents[:4] == ["m0", "m1", "m2", "m3"]
        assert contents[-5:] == ["m25", "m26", "m27", "m28", "m29"]
        assert len(contents) == 9
        assert "m15" not in contents

    def test_preserves_system_messages_unconditionally(self) -> None:
        """System/CLAUDE.md blocks must survive eviction regardless of position."""
        messages = [{"role": "system", "content": "CLAUDE.md contents"}] + [
            {"role": "user", "content": f"m{i}"} for i in range(30)
        ]
        result = evict_sink_and_window(messages, sink_n=2, window_n=2)
        assert {"role": "system", "content": "CLAUDE.md contents"} in result

    def test_preserves_message_order(self) -> None:
        messages = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        result = evict_sink_and_window(messages, sink_n=2, window_n=2)
        contents = [m["content"] for m in result]
        assert contents == sorted(contents, key=lambda c: int(c[1:]))


class TestIsValidCutoff:
    def test_boundary_indices_are_valid(self) -> None:
        messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        assert is_valid_cutoff(messages, 0) is True
        assert is_valid_cutoff(messages, len(messages)) is True

    def test_user_role_index_is_valid_cutoff(self) -> None:
        messages = [
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "b"},
        ]
        assert is_valid_cutoff(messages, 1) is True

    def test_non_user_role_index_is_invalid_cutoff(self) -> None:
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        assert is_valid_cutoff(messages, 1) is False


class TestComputeGoalTokens:
    def test_default_sliding_window_percentage(self) -> None:
        # claude-opus-4-8 -> 200_000 context window; 30% reserved -> 70% goal.
        goal = compute_goal_tokens(model="claude-opus-4-8", sliding_window_percentage=0.3)
        assert goal == int(0.7 * 200_000)

    def test_override_takes_precedence(self) -> None:
        goal = compute_goal_tokens(sliding_window_percentage=0.5, override=10_000)
        assert goal == 5_000


class TestSelectSlidingWindow:
    def test_returns_suffix_snapped_to_user_boundary(self) -> None:
        messages = [
            {"role": "user", "content": "x" * 40},
            {"role": "assistant", "content": "y" * 40},
            {"role": "user", "content": "z" * 40},
        ]
        # Tiny override forces the cutoff to land inside the tail.
        result = select_sliding_window(messages, override=15)
        assert result
        assert result[0]["role"] == "user"


class TestSummarize6Section:
    def test_produces_all_six_section_headers(self) -> None:
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0,
                stdout=_llm_response("\n".join(f"## {h}\ncontent" for h in SECTION_HEADERS)),
            )
            result = summarize_6_section(["hello", "world"])
        for header in SECTION_HEADERS:
            assert f"## {header}" in result

    def test_falls_back_to_skeleton_when_llm_call_fails(self) -> None:
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(returncode=1, stderr="boom")
            result = summarize_6_section(["hello"])
        for header in SECTION_HEADERS:
            assert f"## {header}" in result


class TestCompactResult:
    def _seed_db(self, tmp_path: Path, session_id: str) -> Path:
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            conn.commit()
        finally:
            conn.close()
        return db

    def test_none_when_no_condensed_node_exists(self, tmp_path: Path) -> None:
        session_id = "compact-result-none"
        db = self._seed_db(tmp_path, session_id)
        assert compact_result_for_session(session_id, db) is None

    def test_wraps_existing_condensed_node(self, tmp_path: Path) -> None:
        session_id = "compact-result-wrap"
        db = self._seed_db(tmp_path, session_id)
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response("A short summary.")
            )
            # Two messages so a condensed node is created alongside the leaves.
            conn = connect(db)
            try:
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    ("2026-01-01T00:00:00Z", session_id, "First message."),
                )
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    ("2026-01-01T00:01:00Z", session_id, "Second message."),
                )
                conn.commit()
            finally:
                conn.close()
            config = {"history": {"compaction": {"enabled": True, "budget_tokens": 1}}}
            compact_session(session_id, db, config=config)
        result = compact_result_for_session(session_id, db)
        assert isinstance(result, CompactResult)
        assert result.summary_message is not None
        assert result.summary_text == result.summary_message
        assert result.context_token_estimate >= 0
        assert len(result.compacted_messages) >= 1


class TestCompactResultWithReasoning:
    """FEAT-2747: assistant-inclusive counterpart to TestCompactResult."""

    def _seed_db(self, tmp_path: Path, session_id: str) -> Path:
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            conn.commit()
        finally:
            conn.close()
        return db

    def test_none_when_no_messages_exist(self, tmp_path: Path) -> None:
        session_id = "compact-with-reasoning-none"
        db = self._seed_db(tmp_path, session_id)
        assert compact_result_for_session_with_reasoning(session_id, db) is None

    def test_wraps_summary_covering_both_tables(self, tmp_path: Path) -> None:
        session_id = "compact-with-reasoning-wrap"
        db = self._seed_db(tmp_path, session_id)
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:00Z", session_id, "User asked a question."),
            )
            conn.execute(
                "INSERT INTO assistant_messages(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:05Z", session_id, "Assistant derived an answer."),
            )
            conn.commit()
        finally:
            conn.close()

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response("A short summary.")
            )
            result = compact_result_for_session_with_reasoning(session_id, db)

        assert isinstance(result, CompactResult)
        assert result.summary_message is not None
        assert result.summary_text == result.summary_message
        assert result.context_token_estimate >= 0
        assert len(result.compacted_messages) >= 1


class TestSoftThresholdSummary:
    """Soft-threshold (7,500 token) background 6-section summarizer wiring."""

    def _seed_large_session(self, tmp_path: Path, session_id: str) -> Path:
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            # Well over SOFT_THRESHOLD_TOKENS (7500 * 4 = 30000 chars).
            big_content = "word " * 8000
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:00Z", session_id, big_content),
            )
            conn.commit()
        finally:
            conn.close()
        return db

    def test_spawns_background_summary_when_enabled_and_over_threshold(
        self, tmp_path: Path
    ) -> None:
        session_id = "soft-threshold-enabled"
        db = self._seed_large_session(tmp_path, session_id)
        config = {"history": {"compaction": {"enabled": True}}}
        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0,
                stdout=_llm_response("\n".join(f"## {h}\ncontent" for h in SECTION_HEADERS)),
            )
            from little_loops.config.features import CompactionConfig
            from little_loops.session_store import _maybe_soft_threshold_summary

            conn = connect(db)
            try:
                thread = _maybe_soft_threshold_summary(
                    conn,
                    session_id,
                    db,
                    CompactionConfig.from_dict(config["history"]["compaction"]),
                )
            finally:
                conn.close()
            assert thread is not None
            thread.join(timeout=5)

        conn = connect(db)
        try:
            row = conn.execute(
                "SELECT content FROM summary_nodes"
                " WHERE session_id=? AND kind='condensed' AND level=0",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        for header in SECTION_HEADERS:
            assert f"## {header}" in row["content"]

    def test_no_thread_when_disabled(self, tmp_path: Path) -> None:
        session_id = "soft-threshold-disabled"
        db = self._seed_large_session(tmp_path, session_id)
        from little_loops.config.features import CompactionConfig
        from little_loops.session_store import _maybe_soft_threshold_summary

        conn = connect(db)
        try:
            thread = _maybe_soft_threshold_summary(
                conn, session_id, db, CompactionConfig.from_dict({"enabled": False})
            )
        finally:
            conn.close()
        assert thread is None

    def test_no_thread_when_under_threshold(self, tmp_path: Path) -> None:
        session_id = "soft-threshold-under"
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-01T00:00:00Z", session_id, "short message"),
            )
            conn.commit()
        finally:
            conn.close()
        from little_loops.config.features import CompactionConfig
        from little_loops.session_store import _maybe_soft_threshold_summary

        conn = connect(db)
        try:
            thread = _maybe_soft_threshold_summary(
                conn, session_id, db, CompactionConfig.from_dict({"enabled": True})
            )
        finally:
            conn.close()
        assert thread is None


class TestMessageEventsUnchangedRegression:
    """Regression guard: compaction must never delete message_events rows (FEAT-2598 wiring)."""

    def test_compact_session_does_not_delete_message_events(self, tmp_path: Path) -> None:
        session_id = "message-events-unchanged"
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            for i in range(10):
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", session_id, f"Message {i}."),
                )
            conn.commit()
        finally:
            conn.close()

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response("Condensed.")
            )
            config = {"history": {"compaction": {"enabled": True, "budget_tokens": 5}}}
            compact_session(session_id, db, config=config)

        conn = connect(db)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM message_events WHERE session_id=?", (session_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 10


class TestAssistantMessagesUnchangedRegression:
    """FEAT-2747 Wiring Phase step 9: assistant-inclusive compaction must not

    mutate either source table (mirrors TestMessageEventsUnchangedRegression).
    """

    def test_does_not_delete_message_events_or_assistant_messages(
        self, tmp_path: Path
    ) -> None:
        session_id = "assistant-messages-unchanged"
        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, str(tmp_path / f"{session_id}.jsonl")),
            )
            for i in range(5):
                conn.execute(
                    "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:00Z", session_id, f"User message {i}."),
                )
                conn.execute(
                    "INSERT INTO assistant_messages(ts, session_id, content) VALUES(?, ?, ?)",
                    (f"2026-01-01T00:{i:02d}:05Z", session_id, f"Assistant message {i}."),
                )
            conn.commit()
        finally:
            conn.close()

        with patch("little_loops.session_store.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed(
                returncode=0, stdout=_llm_response("Condensed.")
            )
            config = {"history": {"compaction": {"enabled": True, "budget_tokens": 5}}}
            compact_result_for_session_with_reasoning(session_id, db, config=config)

        conn = connect(db)
        try:
            me_count = conn.execute(
                "SELECT COUNT(*) FROM message_events WHERE session_id=?", (session_id,)
            ).fetchone()[0]
            am_count = conn.execute(
                "SELECT COUNT(*) FROM assistant_messages WHERE session_id=?", (session_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert me_count == 5
        assert am_count == 5
