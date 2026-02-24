"""Issue history analysis orchestrator.

Thin facade that coordinates all analysis sub-modules and returns
a comprehensive HistoryAnalysis result.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from little_loops.issue_history.coupling import analyze_coupling
from little_loops.issue_history.debt import (
    _calculate_debt_metrics,
    analyze_agent_effectiveness,
    analyze_complexity_proxy,
    detect_cross_cutting_smells,
)
from little_loops.issue_history.hotspots import analyze_hotspots
from little_loops.issue_history.models import (
    CompletedIssue,
    HistoryAnalysis,
    PeriodMetrics,
)
from little_loops.issue_history.parsing import scan_active_issues
from little_loops.issue_history.quality import (
    analyze_rejection_rates,
    analyze_test_gaps,
    detect_config_gaps,
    detect_manual_patterns,
)
from little_loops.issue_history.regressions import analyze_regression_clustering
from little_loops.issue_history.summary import (
    _analyze_subsystems,
    _calculate_trend,
    _group_by_period,
    calculate_summary,
)


def _load_issue_contents(issues: list[CompletedIssue]) -> dict[Path, str]:
    """Pre-load issue file contents for pipeline efficiency.

    Reads each issue file once and returns a mapping from path to content.
    Skips unreadable files silently (matching individual function behavior).

    Args:
        issues: List of completed issues to load

    Returns:
        Mapping of issue path to file content
    """
    contents: dict[Path, str] = {}
    for issue in issues:
        try:
            contents[issue.path] = issue.path.read_text(encoding="utf-8")
        except Exception:
            pass
    return contents


def calculate_analysis(
    completed_issues: list[CompletedIssue],
    issues_dir: Path | None = None,
    period_type: Literal["weekly", "monthly", "quarterly"] = "monthly",
    compare_days: int | None = None,
    project_root: Path | None = None,
) -> HistoryAnalysis:
    """Calculate comprehensive history analysis.

    Args:
        completed_issues: List of completed issues
        issues_dir: Path to .issues/ for active issue scanning
        period_type: Grouping period for trend analysis
        compare_days: Days for comparative analysis (e.g., 30 for 30d comparison)
        project_root: Project root for config gap analysis (defaults to cwd)

    Returns:
        HistoryAnalysis with all metrics
    """
    today = date.today()

    # Pre-load issue file contents once for all analysis functions
    issue_contents = _load_issue_contents(completed_issues)

    # Get base summary
    summary = calculate_summary(completed_issues)

    # Scan active issues if directory provided
    active_issues: list[tuple[Path, str, str, date | None]] = []
    if issues_dir:
        active_issues = scan_active_issues(issues_dir)

    # Calculate period metrics
    period_metrics = _group_by_period(completed_issues, period_type)

    # Determine velocity trend
    if len(period_metrics) >= 3:
        velocities = [float(p.total_completed) for p in period_metrics]
        velocity_trend = _calculate_trend(velocities)
    else:
        velocity_trend = "stable"

    # Determine bug ratio trend
    if len(period_metrics) >= 3:
        bug_ratios = [p.bug_ratio or 0.0 for p in period_metrics]
        # For bug ratio, decreasing is good (keep as-is)
        bug_ratio_trend = _calculate_trend(bug_ratios)
    else:
        bug_ratio_trend = "stable"

    # Subsystem health
    subsystem_health = _analyze_subsystems(completed_issues, contents=issue_contents)

    # Hotspot analysis
    hotspot_analysis = analyze_hotspots(completed_issues, contents=issue_contents)

    # Coupling analysis
    coupling_analysis = analyze_coupling(completed_issues, contents=issue_contents)

    # Regression clustering analysis
    regression_analysis = analyze_regression_clustering(completed_issues, contents=issue_contents)

    # Test gap analysis
    test_gap_analysis = analyze_test_gaps(completed_issues, hotspot_analysis)

    # Rejection rate analysis
    rejection_analysis = analyze_rejection_rates(completed_issues, contents=issue_contents)

    # Manual pattern analysis
    manual_pattern_analysis = detect_manual_patterns(completed_issues, contents=issue_contents)

    # Agent effectiveness analysis
    agent_effectiveness_analysis = analyze_agent_effectiveness(
        completed_issues, contents=issue_contents
    )

    # Complexity proxy analysis
    complexity_proxy_analysis = analyze_complexity_proxy(
        completed_issues, hotspot_analysis, contents=issue_contents
    )

    # Configuration gaps analysis (depends on manual_pattern_analysis)
    config_gaps_analysis = detect_config_gaps(manual_pattern_analysis, project_root)

    # Cross-cutting concern analysis (depends on hotspot_analysis)
    cross_cutting_analysis = detect_cross_cutting_smells(
        completed_issues, hotspot_analysis, contents=issue_contents
    )

    # Technical debt metrics
    debt_metrics = _calculate_debt_metrics(completed_issues, active_issues)

    # Build analysis
    analysis = HistoryAnalysis(
        generated_date=today,
        total_completed=len(completed_issues),
        total_active=len(active_issues),
        date_range_start=summary.earliest_date,
        date_range_end=summary.latest_date,
        summary=summary,
        period_metrics=period_metrics,
        velocity_trend=velocity_trend,
        bug_ratio_trend=bug_ratio_trend,
        subsystem_health=subsystem_health,
        hotspot_analysis=hotspot_analysis,
        coupling_analysis=coupling_analysis,
        regression_analysis=regression_analysis,
        test_gap_analysis=test_gap_analysis,
        rejection_analysis=rejection_analysis,
        manual_pattern_analysis=manual_pattern_analysis,
        agent_effectiveness_analysis=agent_effectiveness_analysis,
        complexity_proxy_analysis=complexity_proxy_analysis,
        config_gaps_analysis=config_gaps_analysis,
        cross_cutting_analysis=cross_cutting_analysis,
        debt_metrics=debt_metrics,
    )

    # Comparative analysis
    if compare_days:
        analysis.comparison_period = f"{compare_days}d"
        cutoff = today - timedelta(days=compare_days)
        prev_cutoff = cutoff - timedelta(days=compare_days)

        current_issues = [
            i for i in completed_issues if i.completed_date and i.completed_date >= cutoff
        ]
        previous_issues = [
            i
            for i in completed_issues
            if i.completed_date and prev_cutoff <= i.completed_date < cutoff
        ]

        if current_issues:
            current_types: dict[str, int] = {}
            for i in current_issues:
                current_types[i.issue_type] = current_types.get(i.issue_type, 0) + 1

            analysis.current_period = PeriodMetrics(
                period_start=cutoff,
                period_end=today,
                period_label=f"Last {compare_days} days",
                total_completed=len(current_issues),
                type_counts=current_types,
            )

        if previous_issues:
            prev_types: dict[str, int] = {}
            for i in previous_issues:
                prev_types[i.issue_type] = prev_types.get(i.issue_type, 0) + 1

            analysis.previous_period = PeriodMetrics(
                period_start=prev_cutoff,
                period_end=cutoff - timedelta(days=1),
                period_label=f"Previous {compare_days} days",
                total_completed=len(previous_issues),
                type_counts=prev_types,
            )

    return analysis
