"""Issue history summary and period metrics analysis."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from little_loops.issue_history.models import (
    CompletedIssue,
    HistorySummary,
    PeriodMetrics,
    SubsystemHealth,
)
from little_loops.issue_history.parsing import _extract_subsystem


def calculate_summary(issues: list[CompletedIssue]) -> HistorySummary:
    """Calculate summary statistics from issues.

    Args:
        issues: List of CompletedIssue objects

    Returns:
        HistorySummary with calculated statistics
    """
    type_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    discovery_counts: dict[str, int] = {}
    dates: list[date] = []

    for issue in issues:
        # Count by type
        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

        # Count by priority
        priority_counts[issue.priority] = priority_counts.get(issue.priority, 0) + 1

        # Count by discovery source
        source = issue.discovered_by or "unknown"
        discovery_counts[source] = discovery_counts.get(source, 0) + 1

        # Collect dates
        if issue.completed_date:
            dates.append(issue.completed_date)

    # Sort counts for consistent output
    type_counts = dict(sorted(type_counts.items()))
    priority_counts = dict(sorted(priority_counts.items()))
    discovery_counts = dict(sorted(discovery_counts.items(), key=lambda x: (-x[1], x[0])))

    return HistorySummary(
        total_count=len(issues),
        type_counts=type_counts,
        priority_counts=priority_counts,
        discovery_counts=discovery_counts,
        earliest_date=min(dates) if dates else None,
        latest_date=max(dates) if dates else None,
    )


def _calculate_period_label(start: date, period_type: str) -> str:
    """Generate human-readable period label.

    Args:
        start: Period start date
        period_type: "weekly", "monthly", "quarterly"

    Returns:
        Label like "Q1 2025", "Jan 2025", "Week 3 2025"
    """
    if period_type == "quarterly":
        quarter = (start.month - 1) // 3 + 1
        return f"Q{quarter} {start.year}"
    elif period_type == "monthly":
        return start.strftime("%b %Y")
    else:  # weekly
        week_num = start.isocalendar()[1]
        return f"Week {week_num} {start.year}"


def _group_by_period(
    issues: list[CompletedIssue],
    period_type: Literal["weekly", "monthly", "quarterly"] = "monthly",
) -> list[PeriodMetrics]:
    """Group issues by time period and calculate metrics.

    Args:
        issues: List of completed issues with dates
        period_type: Grouping period

    Returns:
        List of PeriodMetrics sorted by date ascending
    """
    # Filter issues with dates
    dated_issues = [i for i in issues if i.completed_date]
    if not dated_issues:
        return []

    # Sort by date
    dated_issues.sort(key=lambda i: i.completed_date)  # type: ignore

    # Determine period boundaries
    periods: dict[str, list[CompletedIssue]] = defaultdict(list)

    for issue in dated_issues:
        completed = issue.completed_date
        assert completed is not None

        if period_type == "quarterly":
            quarter = (completed.month - 1) // 3
            period_start = date(completed.year, quarter * 3 + 1, 1)
        elif period_type == "monthly":
            period_start = date(completed.year, completed.month, 1)
        else:  # weekly
            # Start of week (Monday)
            period_start = completed - timedelta(days=completed.weekday())

        key = period_start.isoformat()
        periods[key].append(issue)

    # Calculate metrics for each period
    result: list[PeriodMetrics] = []
    for period_key in sorted(periods.keys()):
        period_issues = periods[period_key]
        period_start = date.fromisoformat(period_key)

        # Calculate period end
        if period_type == "quarterly":
            month = period_start.month + 3
            year = period_start.year
            if month > 12:
                month = 1
                year += 1
            period_end = date(year, month, 1) - timedelta(days=1)
        elif period_type == "monthly":
            month = period_start.month + 1
            year = period_start.year
            if month > 12:
                month = 1
                year += 1
            period_end = date(year, month, 1) - timedelta(days=1)
        else:  # weekly
            period_end = period_start + timedelta(days=6)

        # Count types and priorities
        type_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}

        for issue in period_issues:
            type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1
            priority_counts[issue.priority] = priority_counts.get(issue.priority, 0) + 1

        result.append(
            PeriodMetrics(
                period_start=period_start,
                period_end=period_end,
                period_label=_calculate_period_label(period_start, period_type),
                total_completed=len(period_issues),
                type_counts=dict(sorted(type_counts.items())),
                priority_counts=dict(sorted(priority_counts.items())),
            )
        )

    return result


def _calculate_trend(values: list[float]) -> str:
    """Determine trend from a series of values.

    Args:
        values: Time-ordered series of values

    Returns:
        "increasing", "decreasing", or "stable"
    """
    if len(values) < 3:
        return "stable"

    # Simple linear regression slope
    n = len(values)
    sum_x = sum(range(n))
    sum_y = sum(values)
    sum_xy = sum(i * v for i, v in enumerate(values))
    sum_x2 = sum(i * i for i in range(n))

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return "stable"

    slope = (n * sum_xy - sum_x * sum_y) / denominator

    # Normalize slope by average value
    avg = sum_y / n if n > 0 else 1
    if avg == 0:
        avg = 1
    normalized_slope = slope / avg

    if normalized_slope > 0.05:
        return "increasing"
    elif normalized_slope < -0.05:
        return "decreasing"
    return "stable"


def _analyze_subsystems(
    issues: list[CompletedIssue],
    recent_days: int = 30,
    contents: dict[Path, str] | None = None,
) -> list[SubsystemHealth]:
    """Analyze health by subsystem/directory.

    Args:
        issues: List of completed issues
        recent_days: Days to consider "recent"
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        List of SubsystemHealth sorted by total issues descending
    """
    subsystems: dict[str, SubsystemHealth] = {}
    cutoff = date.today() - timedelta(days=recent_days)

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        subsystem = _extract_subsystem(content)
        if not subsystem:
            continue

        if subsystem not in subsystems:
            subsystems[subsystem] = SubsystemHealth(subsystem=subsystem)

        health = subsystems[subsystem]
        health.total_issues += 1
        health.issue_ids.append(issue.issue_id)

        if issue.completed_date and issue.completed_date >= cutoff:
            health.recent_issues += 1

    # Calculate trends based on recent vs historical ratio
    for health in subsystems.values():
        if health.total_issues >= 5:
            recent_ratio = health.recent_issues / health.total_issues
            if recent_ratio > 0.5:
                health.trend = "degrading"
            elif recent_ratio < 0.2:
                health.trend = "improving"

    # Sort by total issues descending
    result = sorted(subsystems.values(), key=lambda s: -s.total_issues)
    return result[:10]  # Top 10
