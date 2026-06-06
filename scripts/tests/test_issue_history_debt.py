"""Tests for issue_history.debt module.

Focuses on _calculate_debt_metrics (completely untested) and verifies
the module-level imports work. Avoids duplicating detect_cross_cutting_smells,
analyze_agent_effectiveness, and analyze_complexity_proxy coverage already in
test_issue_history_advanced_analytics.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.issue_history import CompletedIssue
from little_loops.issue_history.debt import _calculate_debt_metrics
from little_loops.issue_history.models import TechnicalDebtMetrics


def _make_issue(
    issue_id: str,
    issue_type: str = "BUG",
    completed_date: date | None = None,
    tmp_path: Path | None = None,
) -> CompletedIssue:
    """Build a minimal CompletedIssue for testing."""
    p = (tmp_path or Path("/tmp")) / f"P2-{issue_id}.md"
    return CompletedIssue(
        path=p,
        issue_type=issue_type,
        priority="P2",
        issue_id=issue_id,
        completed_date=completed_date,
    )


class TestCalculateDebtMetrics:
    """Unit tests for _calculate_debt_metrics function."""

    def test_empty_inputs_return_default_metrics(self) -> None:
        result = _calculate_debt_metrics([], [])
        assert isinstance(result, TechnicalDebtMetrics)
        assert result.backlog_size == 0
        assert result.high_priority_open == 0
        assert result.aging_30_plus == 0
        assert result.aging_60_plus == 0

    def test_backlog_size_counts_active_issues(self) -> None:
        active = [
            (Path("x.md"), "BUG", "P2", None),
            (Path("y.md"), "FEAT", "P3", None),
            (Path("z.md"), "ENH", "P1", None),
        ]
        result = _calculate_debt_metrics([], active)
        assert result.backlog_size == 3

    def test_high_priority_counts_p0_and_p1(self) -> None:
        active = [
            (Path("a.md"), "BUG", "P0", None),
            (Path("b.md"), "FEAT", "P1", None),
            (Path("c.md"), "ENH", "P2", None),
            (Path("d.md"), "ENH", "P3", None),
        ]
        result = _calculate_debt_metrics([], active)
        assert result.high_priority_open == 2

    def test_aging_30_plus_counts_old_issues(self) -> None:
        today = date(2026, 6, 5)
        active = [
            (Path("old.md"), "BUG", "P2", today - timedelta(days=35)),
            (Path("new.md"), "BUG", "P2", today - timedelta(days=10)),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        assert result.aging_30_plus == 1

    def test_aging_60_plus_counts_very_old_issues(self) -> None:
        today = date(2026, 6, 5)
        active = [
            (Path("a.md"), "BUG", "P2", today - timedelta(days=65)),
            (Path("b.md"), "BUG", "P2", today - timedelta(days=35)),
            (Path("c.md"), "BUG", "P2", today - timedelta(days=10)),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        assert result.aging_60_plus == 1
        assert result.aging_30_plus == 2

    def test_aging_30_boundary_exactly_30_days(self) -> None:
        today = date(2026, 6, 5)
        active = [
            (Path("exact.md"), "BUG", "P2", today - timedelta(days=30)),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        assert result.aging_30_plus == 1

    def test_aging_none_discovered_date_skipped(self) -> None:
        today = date(2026, 6, 5)
        active = [
            (Path("no_date.md"), "BUG", "P2", None),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        assert result.aging_30_plus == 0

    def test_debt_paydown_ratio_bugs_divided_by_feats(self, tmp_path: Path) -> None:
        completed = [
            _make_issue("BUG-001", issue_type="BUG", tmp_path=tmp_path),
            _make_issue("BUG-002", issue_type="BUG", tmp_path=tmp_path),
            _make_issue("FEAT-001", issue_type="FEAT", tmp_path=tmp_path),
        ]
        result = _calculate_debt_metrics(completed, [])
        assert result.debt_paydown_ratio == pytest.approx(2.0)

    def test_debt_paydown_ratio_only_bugs_no_feats(self, tmp_path: Path) -> None:
        completed = [
            _make_issue("BUG-001", issue_type="BUG", tmp_path=tmp_path),
            _make_issue("BUG-002", issue_type="BUG", tmp_path=tmp_path),
        ]
        result = _calculate_debt_metrics(completed, [])
        assert result.debt_paydown_ratio == pytest.approx(2.0)

    def test_debt_paydown_ratio_no_bugs_stays_zero(self, tmp_path: Path) -> None:
        completed = [
            _make_issue("FEAT-001", issue_type="FEAT", tmp_path=tmp_path),
        ]
        result = _calculate_debt_metrics(completed, [])
        assert result.debt_paydown_ratio == pytest.approx(0.0)

    def test_backlog_growth_rate_positive_when_created_exceeds_completed(
        self, tmp_path: Path
    ) -> None:
        today = date(2026, 6, 5)
        recent = today - timedelta(days=7)
        # 3 active issues created recently, 0 completed recently
        active = [
            (Path("a.md"), "BUG", "P2", recent),
            (Path("b.md"), "BUG", "P2", recent),
            (Path("c.md"), "BUG", "P2", recent),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            mock_date.side_effect = None
            mock_date.return_value = today
            # Also need timedelta to work
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        # backlog_growth_rate = (created_recently - completed_recently) / 4
        assert result.backlog_growth_rate == pytest.approx(3 / 4.0)

    def test_backlog_growth_rate_zero_with_no_recent_activity(self) -> None:
        today = date(2026, 6, 5)
        old_date = today - timedelta(days=60)
        active = [
            (Path("old.md"), "BUG", "P2", old_date),
        ]
        with patch("little_loops.issue_history.debt.date") as mock_date:
            mock_date.today.return_value = today
            result = _calculate_debt_metrics([], active)
        assert result.backlog_growth_rate == pytest.approx(0.0)
