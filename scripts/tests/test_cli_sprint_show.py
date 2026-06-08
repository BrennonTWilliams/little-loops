"""Tests for sprint CLI rendering functions and show command.

Tests pure rendering functions (_score_suffix, _render_execution_plan,
_render_dependency_graph, _render_health_summary) and _cmd_sprint_show gaps
(--json early-exit, --skip-analysis).

Focuses on gaps not covered by existing tests in test_sprint.py
(TestSprintDependencyAnalysis already covers show with dep analysis integration).
"""

from __future__ import annotations

import argparse
import json as _json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from little_loops.cli.sprint._helpers import _render_execution_plan, _score_suffix
from little_loops.cli.sprint.show import (
    _cmd_sprint_show,
    _render_dependency_graph,
    _render_health_summary,
)
from little_loops.dependency_graph import DependencyGraph, WaveContentionNote
from little_loops.issue_parser import IssueInfo
from little_loops.sprint import Sprint, SprintManager

# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    issue_id: str = "BUG-001",
    title: str = "Test Bug",
    priority: str = "P1",
    confidence_score: int | None = None,
    outcome_confidence: int | None = None,
    blocked_by: list[str] | None = None,
    path: str | None = None,
) -> IssueInfo:
    """Create a minimal IssueInfo for rendering tests."""
    return IssueInfo(
        path=Path(path or f".issues/bugs/{priority}-{issue_id}-test.md"),
        issue_type=issue_id.split("-", 1)[0],
        priority=priority,
        issue_id=issue_id,
        title=title,
        blocked_by=blocked_by or [],
        confidence_score=confidence_score,
        outcome_confidence=outcome_confidence,
    )


def _make_dep_graph(
    issues: list[IssueInfo],
    blocked_by: dict[str, set[str]] | None = None,
    blocks: dict[str, set[str]] | None = None,
) -> DependencyGraph:
    """Create a DependencyGraph for rendering tests."""
    issue_map = {i.issue_id: i for i in issues}
    return DependencyGraph(
        issues=issue_map,
        blocked_by=blocked_by or {},
        blocks=blocks or {},
    )


# ---------------------------------------------------------------------------
# _score_suffix Tests
# ---------------------------------------------------------------------------


class TestScoreSuffix:
    """Tests for _score_suffix() pure function."""

    def test_no_scores_returns_empty(self) -> None:
        """Returns empty string when issue has no confidence scores."""
        issue = _make_issue()
        result = _score_suffix(issue)
        assert result == ""

    def test_only_confidence_score(self) -> None:
        """Returns suffix with only readiness score."""
        issue = _make_issue(confidence_score=85)
        result = _score_suffix(issue)
        assert "ready: 85" in result
        assert "conf:" not in result

    def test_only_outcome_confidence(self) -> None:
        """Returns suffix with only outcome confidence."""
        issue = _make_issue(outcome_confidence=72)
        result = _score_suffix(issue)
        assert "conf: 72" in result
        assert "ready:" not in result

    def test_both_scores(self) -> None:
        """Returns suffix with both readiness and outcome confidence."""
        issue = _make_issue(confidence_score=90, outcome_confidence=74)
        result = _score_suffix(issue)
        assert "ready: 90" in result
        assert "conf: 74" in result
        assert result.startswith(" [")
        assert result.endswith("]")

    def test_scores_on_object_with_attributes(self) -> None:
        """Works with arbitrary objects that have the right attributes."""

        class FakeIssue:
            confidence_score = 50
            outcome_confidence = None

        result = _score_suffix(FakeIssue())
        assert "ready: 50" in result

    def test_scores_on_object_missing_attributes(self) -> None:
        """Returns empty string for objects without score attributes."""

        class PlainObj:
            pass

        result = _score_suffix(PlainObj())
        assert result == ""


# ---------------------------------------------------------------------------
# _render_execution_plan Tests
# ---------------------------------------------------------------------------


class TestRenderExecutionPlan:
    """Tests for _render_execution_plan() pure function."""

    def test_empty_waves_returns_empty_string(self) -> None:
        """Empty waves list produces empty string."""
        dep_graph = _make_dep_graph([])
        result = _render_execution_plan([], dep_graph)
        assert result == ""

    def test_single_wave_single_issue(self) -> None:
        """Single wave with one issue renders correctly."""
        issue = _make_issue("BUG-001", "Fix critical crash", "P0")
        dep_graph = _make_dep_graph([issue])
        waves = [[issue]]

        result = _render_execution_plan(waves, dep_graph)

        assert "Execution Plan" in result
        assert "1 issue" in result
        assert "1 wave" in result
        assert "BUG-001" in result
        assert "Fix critical crash" in result
        assert "P0" in result

    def test_single_wave_multiple_issues(self) -> None:
        """Single wave with multiple issues shows parallel grouping."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1")
        dep_graph = _make_dep_graph([bug, feat])
        waves = [[bug, feat]]

        result = _render_execution_plan(waves, dep_graph)

        assert "Execution Plan" in result
        assert "2 issues" in result
        assert "1 wave" in result
        assert "BUG-001" in result
        assert "FEAT-010" in result

    def test_multi_wave_serial(self) -> None:
        """Multiple waves show serial dependency structure."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1", blocked_by=["BUG-001"])
        dep_graph = _make_dep_graph(
            [bug, feat],
            blocked_by={"FEAT-010": {"BUG-001"}},
            blocks={"BUG-001": {"FEAT-010"}},
        )
        waves = [[bug], [feat]]

        result = _render_execution_plan(waves, dep_graph)

        assert "2 issues" in result
        assert "2 waves" in result
        assert "Wave 1" in result
        assert "Wave 2" in result
        assert "blocked by: BUG-001" in result

    def test_contention_notes_render_serialized(self) -> None:
        """Contention sub-waves show serialized steps."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1")
        dep_graph = _make_dep_graph([bug, feat])

        note = WaveContentionNote(
            contended_paths=["src/shared.py"],
            sub_wave_index=0,
            total_sub_waves=2,
            parent_wave_index=0,
        )
        note2 = WaveContentionNote(
            contended_paths=["src/shared.py"],
            sub_wave_index=1,
            total_sub_waves=2,
            parent_wave_index=0,
        )
        waves = [[bug], [feat]]

        result = _render_execution_plan(waves, dep_graph, [note, note2])

        assert "serialized" in result
        assert "Step 1/2" in result
        assert "Step 2/2" in result
        assert "Contended files: src/shared.py" in result

    def test_issue_with_scores_renders_suffix(self) -> None:
        """Issues with confidence scores show score suffix inline."""
        issue = _make_issue(
            "BUG-001", "Fix crash", "P0", confidence_score=85, outcome_confidence=72
        )
        dep_graph = _make_dep_graph([issue])
        waves = [[issue]]

        result = _render_execution_plan(waves, dep_graph)

        assert "ready: 85" in result
        assert "conf: 72" in result


# ---------------------------------------------------------------------------
# _render_dependency_graph Tests
# ---------------------------------------------------------------------------


class TestRenderDependencyGraph:
    """Tests for _render_dependency_graph() pure function."""

    def test_empty_waves_returns_empty(self) -> None:
        """No waves produces empty string."""
        dep_graph = _make_dep_graph([])
        result = _render_dependency_graph([], dep_graph)
        assert result == ""

    def test_single_wave_returns_empty(self) -> None:
        """Single wave (no dependencies to show) produces empty string."""
        issue = _make_issue("BUG-001", "Fix crash", "P0")
        dep_graph = _make_dep_graph([issue])
        waves = [[issue]]

        result = _render_dependency_graph(waves, dep_graph)
        assert result == ""

    def test_waves_without_edges_returns_empty(self) -> None:
        """Multiple waves without actual dependency edges produce empty string."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1")
        # No blocked_by edges between them
        dep_graph = _make_dep_graph([bug, feat])
        waves = [[bug], [feat]]

        result = _render_dependency_graph(waves, dep_graph)
        assert result == ""

    def test_simple_chain_renders_arrow(self) -> None:
        """A simple dependency chain renders with arrow notation."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1", blocked_by=["BUG-001"])
        dep_graph = _make_dep_graph(
            [bug, feat],
            blocked_by={"FEAT-010": {"BUG-001"}},
            blocks={"BUG-001": {"FEAT-010"}},
        )
        waves = [[bug], [feat]]

        result = _render_dependency_graph(waves, dep_graph)

        assert "Dependency Graph" in result
        assert "BUG-001" in result
        assert "FEAT-010" in result
        assert "──→" in result
        assert "blocks" in result.lower() or "Legend" in result


# ---------------------------------------------------------------------------
# _render_health_summary Tests
# ---------------------------------------------------------------------------


class TestRenderHealthSummary:
    """Tests for _render_health_summary() pure function."""

    def test_ok_single_issue(self) -> None:
        """Single issue with no cycles produces OK status."""
        issue = _make_issue("BUG-001", "Fix crash", "P0")
        waves = [[issue]]

        result = _render_health_summary(waves, None, False, set())

        assert "OK" in result
        assert "1 issue" in result
        assert "1 wave" in result

    def test_blocked_by_cycles(self) -> None:
        """Cycles produce BLOCKED status."""
        waves: list[list[Any]] = []

        result = _render_health_summary(waves, None, True, set())

        assert "BLOCKED" in result
        assert "cycle" in result.lower()

    def test_warning_for_invalid_issues(self) -> None:
        """Missing issues produce WARNING status."""
        waves: list[list[Any]] = []

        result = _render_health_summary(waves, None, False, {"MISSING-001"})

        assert "WARNING" in result
        assert "1 issue" in result
        assert "not found" in result.lower()

    def test_multi_wave_parallelizable(self) -> None:
        """Multiple waves show wave count."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        feat = _make_issue("FEAT-010", "Add feature", "P1")
        waves = [[bug], [feat]]

        result = _render_health_summary(waves, None, False, set())

        assert "2 issues" in result
        assert "2 waves" in result

    def test_review_for_unsatisfied_deps(self) -> None:
        """Unsatisfied high-confidence proposals produce REVIEW status."""
        bug = _make_issue("BUG-001", "Fix crash", "P0")
        waves = [[bug]]

        # Create a mock dep_report with unsatisfied proposals
        mock_proposal = MagicMock()
        mock_proposal.target_id = "FEAT-010"
        mock_proposal.source_id = "BUG-001"
        mock_proposal.confidence = 0.8

        mock_report = MagicMock()
        mock_report.proposals = [mock_proposal]

        # issue_to_wave: target not in waves at all → novel
        issue_to_wave = {"BUG-001": 0}

        result = _render_health_summary(
            waves, None, False, set(), dep_report=mock_report, issue_to_wave=issue_to_wave
        )

        assert "REVIEW" in result
        assert "dependency" in result.lower()


# ---------------------------------------------------------------------------
# _cmd_sprint_show Tests (gap coverage)
# ---------------------------------------------------------------------------


class TestCmdSprintShow:
    """Tests for _cmd_sprint_show — gaps not covered by TestSprintDependencyAnalysis."""

    @staticmethod
    def _setup_show_project(tmp_path: Path) -> tuple[SprintManager, str]:
        """Create a temp project with a sprint and issues for show command."""
        # Create issues
        issues_dir = tmp_path / ".issues"
        for category in ["bugs", "features", "enhancements"]:
            (issues_dir / category).mkdir(parents=True, exist_ok=True)

        (issues_dir / "bugs" / "P1-BUG-001-test-bug.md").write_text(
            "---\nstatus: open\n---\n# BUG-001: Test Bug\n\n## Summary\nFix this bug."
        )

        # Create config
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        config_data = {
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {
                    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                    "features": {
                        "prefix": "FEAT",
                        "dir": "features",
                        "action": "implement",
                    },
                    "enhancements": {
                        "prefix": "ENH",
                        "dir": "enhancements",
                        "action": "improve",
                    },
                },
            },
        }
        (config_dir / "ll-config.json").write_text(_json.dumps(config_data))

        # Create sprint
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir(exist_ok=True)
        Sprint(
            name="test-sprint",
            description="A test sprint",
            issues=["BUG-001"],
            created="2026-06-01T00:00:00Z",
        ).save(sprints_dir)

        from little_loops.config import BRConfig

        config = BRConfig(tmp_path)
        manager = SprintManager(sprints_dir=sprints_dir, config=config)
        return manager, "test-sprint"

    def test_show_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--json flag produces valid JSON with expected keys."""
        manager, sprint_name = self._setup_show_project(tmp_path)

        args = argparse.Namespace(
            sprint=sprint_name,
            json=True,
            skip_analysis=True,
        )

        # Inject config into manager attributes if needed
        result = _cmd_sprint_show(args, manager)

        assert result == 0
        captured = capsys.readouterr()
        data = _json.loads(captured.out)
        assert data["name"] == "test-sprint"
        assert "issues" in data
        assert "waves" in data
        assert "has_cycles" in data

    def test_show_skip_analysis(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """--skip-analysis flag suppresses dependency analysis output."""
        manager, sprint_name = self._setup_show_project(tmp_path)

        args = argparse.Namespace(
            sprint=sprint_name,
            json=False,
            skip_analysis=True,
        )

        result = _cmd_sprint_show(args, manager)
        assert result == 0

        captured = capsys.readouterr()
        assert "Sprint:" in captured.out
        assert "test-sprint" in captured.out

    def test_show_not_found_returns_1(self, tmp_path: Path) -> None:
        """Non-existent sprint returns exit code 1."""
        sprints_dir = tmp_path / ".sprints"
        sprints_dir.mkdir(exist_ok=True)
        manager = SprintManager(sprints_dir=sprints_dir)

        args = argparse.Namespace(
            sprint="nonexistent",
            json=False,
            skip_analysis=True,
        )

        result = _cmd_sprint_show(args, manager)
        assert result == 1

    def test_show_sprint_not_found_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-existent sprint prints error message."""
        manager, _ = self._setup_show_project(tmp_path)

        args = argparse.Namespace(
            sprint="nonexistent",
            json=False,
            skip_analysis=True,
        )

        result = _cmd_sprint_show(args, manager)
        assert result == 1

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "not found" in captured.err.lower()
