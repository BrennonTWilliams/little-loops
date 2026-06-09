"""Unit tests for evolution trigger detectors (ENH-1911)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from little_loops.config.features import EvolutionConfig
from little_loops.issue_history.evolution import detect_recurring_feedback, detect_skill_bypass
from little_loops.issue_history.models import RecurringFeedbackAnalysis, SkillBypassAnalysis


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_test_db(tmp_path: Path) -> Path:
    """Create a properly migrated test DB using ensure_db so _connect_readonly works."""
    from little_loops.session_store import ensure_db

    db = tmp_path / "test.db"
    ensure_db(db)
    return db


class TestDetectRecurringFeedback:
    """Tests for detect_recurring_feedback()."""

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when DB does not exist."""
        config = EvolutionConfig()
        result = detect_recurring_feedback(tmp_path / "nonexistent.db", config)
        assert isinstance(result, RecurringFeedbackAnalysis)
        assert result.feedbacks == []
        assert result.total_recurring_corrections == 0

    def test_empty_db_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when DB has no corrections."""
        db = _make_test_db(tmp_path)
        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config)
        assert result.feedbacks == []
        assert result.total_recurring_corrections == 0
        assert result.threshold_used == 2

    def test_single_correction_below_threshold(self, tmp_path: Path) -> None:
        """Corrections appearing only once are not surfaced."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
            (_now_ts(), "session-1", "don't do that"),
        )
        conn.commit()
        conn.close()

        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config)
        assert result.feedbacks == []

    def test_recurring_correction_surfaced(self, tmp_path: Path) -> None:
        """Corrections meeting threshold are surfaced with count and sessions."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        for i in range(3):
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, f"session-{i}", "don't add co-authored-by"),
            )
        conn.commit()
        conn.close()

        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config)
        assert len(result.feedbacks) == 1
        fb = result.feedbacks[0]
        assert fb.occurrence_count == 3
        assert result.total_recurring_corrections == 3
        assert result.threshold_used == 2

    def test_threshold_filtering(self, tmp_path: Path) -> None:
        """Only corrections meeting threshold appear; below-threshold ones are excluded."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        for i in range(3):
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, f"s-a-{i}", "always use --json flag"),
            )
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
            (ts, "s-b-0", "one-time comment"),
        )
        conn.commit()
        conn.close()

        config = EvolutionConfig(feedback_min_recurrence=3)
        result = detect_recurring_feedback(db, config)
        assert len(result.feedbacks) == 1
        assert result.feedbacks[0].occurrence_count == 3

    def test_memory_feedback_scanning(self, tmp_path: Path) -> None:
        """Memory feedback files provide candidate_rule seeds; no crash expected."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        for i in range(2):
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, f"s-{i}", "never add claude attribution"),
            )
        conn.commit()
        conn.close()

        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "feedback_no_claude_attribution.md").write_text(
            "---\nname: no-claude-attribution\n---\nNever add claude co-authored-by lines."
        )

        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config, project_root=tmp_path)
        assert len(result.feedbacks) == 1
        # candidate_rule may or may not match — just assert no crash and correct count
        assert result.feedbacks[0].occurrence_count == 2

    def test_example_sessions_populated(self, tmp_path: Path) -> None:
        """example_sessions contains session IDs for the recurring correction."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        session_ids = ["sess-alpha", "sess-beta", "sess-gamma"]
        for sid in session_ids:
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, sid, "stop adding emojis"),
            )
        conn.commit()
        conn.close()

        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config)
        assert len(result.feedbacks) == 1
        fb = result.feedbacks[0]
        assert len(fb.example_sessions) > 0
        for sid in fb.example_sessions:
            assert sid in session_ids

    def test_multiple_recurring_corrections(self, tmp_path: Path) -> None:
        """Multiple distinct recurring corrections are all surfaced."""
        db = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        for i in range(2):
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, f"s1-{i}", "correction alpha"),
            )
        for i in range(3):
            conn.execute(
                "INSERT INTO user_corrections(ts, session_id, content) VALUES (?, ?, ?)",
                (ts, f"s2-{i}", "correction beta"),
            )
        conn.commit()
        conn.close()

        config = EvolutionConfig(feedback_min_recurrence=2)
        result = detect_recurring_feedback(db, config)
        assert len(result.feedbacks) == 2
        counts = {fb.occurrence_count for fb in result.feedbacks}
        assert 2 in counts
        assert 3 in counts


class TestDetectSkillBypass:
    """Tests for detect_skill_bypass()."""

    def test_no_project_root_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when project_root is None."""
        db = _make_test_db(tmp_path)
        config = EvolutionConfig()
        result = detect_skill_bypass(db, config, project_root=None)
        assert isinstance(result, SkillBypassAnalysis)
        assert result.bypasses == []

    def test_missing_db_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when DB does not exist."""
        config = EvolutionConfig()
        result = detect_skill_bypass(tmp_path / "nonexistent.db", config, project_root=tmp_path)
        assert isinstance(result, SkillBypassAnalysis)
        assert result.bypasses == []

    def test_no_skills_dir_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when project has no skills directory."""
        db = _make_test_db(tmp_path)
        config = EvolutionConfig()
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        assert result.bypasses == []

    def test_no_messages_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty analysis when DB has no message_events."""
        db = _make_test_db(tmp_path)
        skills_dir = tmp_path / "skills" / "commit"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Create git commits.\nTrigger keywords: commit, git\n---\n"
        )
        config = EvolutionConfig(bypass_min_count=1)
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        assert result.bypasses == []

    def test_no_bypass_when_skill_invoked(self, tmp_path: Path) -> None:
        """No bypass counted when skill was actually invoked in the same session."""
        db = _make_test_db(tmp_path)
        skills_dir = tmp_path / "skills" / "commit"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Create git commits.\nTrigger keywords: commit, git, stage\n---\n"
        )
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        conn.execute(
            "INSERT INTO message_events(ts, session_id, content) VALUES (?, ?, ?)",
            (ts, "s-1", "commit these changes to git and stage the files"),
        )
        conn.execute(
            "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES (?, ?, ?, ?)",
            (ts, "s-1", "commit", ""),
        )
        conn.commit()
        conn.close()

        config = EvolutionConfig(bypass_min_count=1)
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        for bypass in result.bypasses:
            if bypass.skill_name == "commit":
                assert "s-1" not in bypass.example_sessions

    def test_threshold_filtering(self, tmp_path: Path) -> None:
        """Bypasses below threshold are not surfaced."""
        db = _make_test_db(tmp_path)
        skills_dir = tmp_path / "skills" / "commit"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: commit\ndescription: Create git commits.\nTrigger keywords: commit, git, stage\n---\n"
        )
        conn = sqlite3.connect(str(db))
        ts = _now_ts()
        conn.execute(
            "INSERT INTO message_events(ts, session_id, content) VALUES (?, ?, ?)",
            (ts, "s-only", "commit these changes git stage"),
        )
        conn.commit()
        conn.close()

        config = EvolutionConfig(bypass_min_count=5)
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        for bypass in result.bypasses:
            assert bypass.bypass_count >= 5

    def test_result_sorted_by_count(self, tmp_path: Path) -> None:
        """Bypasses are sorted by bypass_count descending."""
        db = _make_test_db(tmp_path)
        config = EvolutionConfig(bypass_min_count=1)
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        if len(result.bypasses) >= 2:
            for i in range(len(result.bypasses) - 1):
                assert result.bypasses[i].bypass_count >= result.bypasses[i + 1].bypass_count

    def test_returns_skill_bypass_analysis_type(self, tmp_path: Path) -> None:
        """Return type is always SkillBypassAnalysis regardless of inputs."""
        db = _make_test_db(tmp_path)
        config = EvolutionConfig()
        result = detect_skill_bypass(db, config, project_root=tmp_path)
        assert isinstance(result, SkillBypassAnalysis)
        assert result.threshold_used == config.bypass_min_count
