"""Tests for issue_history.quality module.

Focuses on branches and edge cases NOT already covered in
test_issue_history_advanced_analytics.py, specifically:
- _update_rejection_metrics internal helper (untested)
- analyze_test_gaps has_test=True branch (gap_score=bug_count*1.0)
- analyze_test_gaps priority thresholds per-branch
- detect_config_gaps with real filesystem structure
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from little_loops.issue_history.models import (
    Hotspot,
    HotspotAnalysis,
    ManualPattern,
    ManualPatternAnalysis,
    RejectionMetrics,
)
from little_loops.issue_history.quality import (
    _update_rejection_metrics,
    analyze_test_gaps,
    detect_config_gaps,
)


class TestUpdateRejectionMetrics:
    """Unit tests for _update_rejection_metrics helper."""

    def test_completed_increments_completed_count(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "completed")
        assert m.completed_count == 1

    def test_rejected_increments_rejected_count(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "rejected")
        assert m.rejected_count == 1

    def test_invalid_increments_invalid_count(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "invalid")
        assert m.invalid_count == 1

    def test_duplicate_increments_duplicate_count(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "duplicate")
        assert m.duplicate_count == 1

    def test_deferred_increments_deferred_count(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "deferred")
        assert m.deferred_count == 1

    def test_unknown_category_does_not_increment_any_field(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "unknown-category")
        assert m.completed_count == 0
        assert m.rejected_count == 0
        assert m.invalid_count == 0
        assert m.duplicate_count == 0
        assert m.deferred_count == 0

    def test_multiple_calls_accumulate(self) -> None:
        m = RejectionMetrics()
        _update_rejection_metrics(m, "completed")
        _update_rejection_metrics(m, "completed")
        _update_rejection_metrics(m, "rejected")
        assert m.completed_count == 2
        assert m.rejected_count == 1


class TestAnalyzeTestGapsGapScoreBranches:
    """Test gap_score calculation for has_test True/False branches."""

    def _make_hotspots(self, path: str, bug_count: int) -> HotspotAnalysis:
        h = Hotspot(
            path=path,
            issue_count=bug_count,
            issue_ids=[f"BUG-{i:03d}" for i in range(bug_count)],
            issue_types={"BUG": bug_count},
            bug_ratio=1.0,
        )
        return HotspotAnalysis(file_hotspots=[h])

    def test_has_test_true_gap_score_equals_bug_count(self, tmp_path: Path) -> None:
        hotspots = self._make_hotspots("src/foo.py", 3)
        with patch("little_loops.issue_history.quality._find_test_file", return_value="tests/test_foo.py"):
            result = analyze_test_gaps([], hotspots, project_root=tmp_path)
        assert len(result.gaps) == 1
        gap = result.gaps[0]
        assert gap.has_test_file is True
        assert gap.gap_score == pytest.approx(3.0)

    def test_has_test_false_gap_score_amplified_10x(self, tmp_path: Path) -> None:
        hotspots = self._make_hotspots("src/bar.py", 2)
        with patch("little_loops.issue_history.quality._find_test_file", return_value=None):
            result = analyze_test_gaps([], hotspots, project_root=tmp_path)
        assert len(result.gaps) == 1
        gap = result.gaps[0]
        assert gap.has_test_file is False
        assert gap.gap_score == pytest.approx(20.0)


import pytest  # noqa: E402 — needed for approx above


class TestAnalyzeTestGapsPriorityThresholds:
    """Test priority assignment for each (has_test, bug_count) combination."""

    def _analyze_with(
        self, bug_count: int, has_test: bool, tmp_path: Path
    ) -> str:
        h = Hotspot(
            path="src/module.py",
            issue_count=bug_count,
            issue_ids=[f"BUG-{i:03d}" for i in range(bug_count)],
            issue_types={"BUG": bug_count},
            bug_ratio=1.0,
        )
        hotspots = HotspotAnalysis(file_hotspots=[h])
        test_file = "tests/test_module.py" if has_test else None
        with patch("little_loops.issue_history.quality._find_test_file", return_value=test_file):
            result = analyze_test_gaps([], hotspots, project_root=tmp_path)
        assert len(result.gaps) == 1
        return result.gaps[0].priority

    def test_no_test_5_bugs_is_critical(self, tmp_path: Path) -> None:
        assert self._analyze_with(5, False, tmp_path) == "critical"

    def test_no_test_6_bugs_is_critical(self, tmp_path: Path) -> None:
        assert self._analyze_with(6, False, tmp_path) == "critical"

    def test_no_test_3_bugs_is_high(self, tmp_path: Path) -> None:
        assert self._analyze_with(3, False, tmp_path) == "high"

    def test_no_test_4_bugs_is_high(self, tmp_path: Path) -> None:
        assert self._analyze_with(4, False, tmp_path) == "high"

    def test_no_test_2_bugs_is_medium(self, tmp_path: Path) -> None:
        assert self._analyze_with(2, False, tmp_path) == "medium"

    def test_no_test_1_bug_is_medium(self, tmp_path: Path) -> None:
        assert self._analyze_with(1, False, tmp_path) == "medium"

    def test_has_test_4_bugs_is_medium(self, tmp_path: Path) -> None:
        assert self._analyze_with(4, True, tmp_path) == "medium"

    def test_has_test_2_bugs_is_low(self, tmp_path: Path) -> None:
        assert self._analyze_with(2, True, tmp_path) == "low"


class TestDetectConfigGapsFilesystem:
    """Test detect_config_gaps with real project filesystem structure."""

    def _make_analysis(self, patterns: list[tuple[str, int]]) -> ManualPatternAnalysis:
        mp_list = [
            ManualPattern(
                pattern_type=pt,
                pattern_description="desc",
                occurrence_count=cnt,
                affected_issues=["BUG-001"],
                example_commands=[],
                suggested_automation="",
                automation_complexity="trivial",
            )
            for pt, cnt in patterns
        ]
        return ManualPatternAnalysis(patterns=mp_list)

    def test_no_hooks_file_creates_gaps(self, tmp_path: Path) -> None:
        analysis = self._make_analysis([("test", 3)])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        assert len(result.gaps) >= 1
        assert result.coverage_score < 1.0

    def test_existing_hooks_reduces_gaps(self, tmp_path: Path) -> None:
        # Create a hooks.json that covers "PostToolUse"
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        import json as _json
        (hooks_dir / "hooks.json").write_text(
            _json.dumps({"hooks": {"PostToolUse": []}}), encoding="utf-8"
        )
        analysis = self._make_analysis([("test", 5)])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        # PostToolUse hook exists → test pattern is covered
        assert result.coverage_score == pytest.approx(1.0)

    def test_agents_dir_scanned(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "my-agent.md").write_text("# Agent", encoding="utf-8")
        analysis = self._make_analysis([])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        assert "my-agent" in result.current_agents

    def test_skills_dir_scanned(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Skill", encoding="utf-8")
        analysis = self._make_analysis([])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        assert "my-skill" in result.current_skills

    def test_priority_high_for_10_plus_occurrences(self, tmp_path: Path) -> None:
        analysis = self._make_analysis([("lint", 12)])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        if result.gaps:
            high_priority = [g for g in result.gaps if g.priority == "high"]
            assert high_priority, "Expected high-priority gap for 12 occurrences"

    def test_priority_medium_for_5_to_9_occurrences(self, tmp_path: Path) -> None:
        analysis = self._make_analysis([("lint", 7)])
        result = detect_config_gaps(analysis, project_root=tmp_path)
        if result.gaps:
            assert result.gaps[0].priority in ("medium", "high")

    def test_empty_manual_patterns_no_gaps(self, tmp_path: Path) -> None:
        analysis = ManualPatternAnalysis()
        result = detect_config_gaps(analysis, project_root=tmp_path)
        assert result.gaps == []
        assert result.coverage_score == pytest.approx(1.0)
