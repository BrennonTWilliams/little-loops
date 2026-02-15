"""Issue history analysis functions.

Provides comprehensive analysis of completed issues including summary
statistics, hotspot detection, coupling analysis, regression clustering,
test gap analysis, rejection rates, manual pattern detection, config gap
detection, agent effectiveness, complexity proxy analysis, cross-cutting
concern detection, and technical debt metrics.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from little_loops.issue_history.models import (
    AgentEffectivenessAnalysis,
    AgentOutcome,
    CompletedIssue,
    ComplexityProxy,
    ComplexityProxyAnalysis,
    ConfigGap,
    ConfigGapsAnalysis,
    CouplingAnalysis,
    CouplingPair,
    CrossCuttingAnalysis,
    CrossCuttingSmell,
    HistoryAnalysis,
    HistorySummary,
    Hotspot,
    HotspotAnalysis,
    ManualPattern,
    ManualPatternAnalysis,
    PeriodMetrics,
    RegressionAnalysis,
    RegressionCluster,
    RejectionAnalysis,
    RejectionMetrics,
    SubsystemHealth,
    TechnicalDebtMetrics,
    TestGap,
    TestGapAnalysis,
)
from little_loops.issue_history.parsing import (
    _detect_processing_agent,
    _extract_paths_from_issue,
    _extract_subsystem,
    _find_test_file,
    _parse_resolution_action,
    scan_active_issues,
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


def analyze_hotspots(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> HotspotAnalysis:
    """Identify files and directories that appear repeatedly in issues.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        HotspotAnalysis with file and directory hotspots
    """
    file_data: dict[str, dict[str, Any]] = {}  # path -> {count, ids, types}
    dir_data: dict[str, dict[str, Any]] = {}  # dir -> {count, ids, types}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        paths = _extract_paths_from_issue(content)

        for path in paths:
            # Track file hotspot
            if path not in file_data:
                file_data[path] = {"count": 0, "ids": [], "types": {}}
            file_data[path]["count"] += 1
            file_data[path]["ids"].append(issue.issue_id)
            file_data[path]["types"][issue.issue_type] = (
                file_data[path]["types"].get(issue.issue_type, 0) + 1
            )

            # Track directory hotspot
            if "/" in path:
                dir_path = "/".join(path.split("/")[:-1]) + "/"
            else:
                dir_path = "./"

            if dir_path not in dir_data:
                dir_data[dir_path] = {"count": 0, "ids": [], "types": {}}
            if issue.issue_id not in dir_data[dir_path]["ids"]:
                dir_data[dir_path]["count"] += 1
                dir_data[dir_path]["ids"].append(issue.issue_id)
                dir_data[dir_path]["types"][issue.issue_type] = (
                    dir_data[dir_path]["types"].get(issue.issue_type, 0) + 1
                )

    # Convert to Hotspot objects
    file_hotspots: list[Hotspot] = []
    for path, data in file_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        # Determine churn indicator
        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        file_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Convert directory data to Hotspot objects
    dir_hotspots: list[Hotspot] = []
    for path, data in dir_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        dir_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Sort by issue count descending
    file_hotspots.sort(key=lambda h: -h.issue_count)
    dir_hotspots.sort(key=lambda h: -h.issue_count)

    # Identify bug magnets (>60% bug ratio, at least 3 issues)
    bug_magnets = [h for h in file_hotspots if h.bug_ratio > 0.6 and h.issue_count >= 3]
    bug_magnets.sort(key=lambda h: (-h.bug_ratio, -h.issue_count))

    return HotspotAnalysis(
        file_hotspots=file_hotspots[:10],  # Top 10
        directory_hotspots=dir_hotspots[:10],  # Top 10
        bug_magnets=bug_magnets[:5],  # Top 5
    )


def analyze_coupling(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> CouplingAnalysis:
    """Identify files that frequently change together across issues.

    Uses Jaccard similarity to calculate coupling strength between file pairs.
    Files with coupling strength >= 0.3 and at least 2 co-occurrences are included.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        CouplingAnalysis with coupled pairs, clusters, and hotspots
    """
    # Build file -> set of issue IDs mapping
    file_to_issues: dict[str, set[str]] = {}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        paths = _extract_paths_from_issue(content)
        for path in paths:
            if path not in file_to_issues:
                file_to_issues[path] = set()
            file_to_issues[path].add(issue.issue_id)

    # Calculate pairwise coupling
    files = list(file_to_issues.keys())
    pairs: list[CouplingPair] = []

    for i, file_a in enumerate(files):
        for file_b in files[i + 1 :]:
            a_issues = file_to_issues[file_a]
            b_issues = file_to_issues[file_b]
            co_occur = a_issues & b_issues
            union = a_issues | b_issues

            if len(co_occur) < 2:  # Require at least 2 co-occurrences
                continue

            # Jaccard similarity
            strength = len(co_occur) / len(union) if union else 0.0

            if strength >= 0.3:  # Only include significant coupling
                pairs.append(
                    CouplingPair(
                        file_a=file_a,
                        file_b=file_b,
                        co_occurrence_count=len(co_occur),
                        coupling_strength=strength,
                        issue_ids=sorted(co_occur),
                    )
                )

    # Sort by coupling strength descending
    pairs.sort(key=lambda p: (-p.coupling_strength, -p.co_occurrence_count))

    # Build clusters using simple connected components
    clusters = _build_coupling_clusters(pairs)

    # Identify hotspots (files coupled with 3+ others)
    file_coupling_count: dict[str, int] = {}
    for pair in pairs:
        file_coupling_count[pair.file_a] = file_coupling_count.get(pair.file_a, 0) + 1
        file_coupling_count[pair.file_b] = file_coupling_count.get(pair.file_b, 0) + 1

    hotspots = [f for f, count in file_coupling_count.items() if count >= 3]
    hotspots.sort(key=lambda f: -file_coupling_count[f])

    return CouplingAnalysis(
        pairs=pairs[:20],  # Top 20 pairs
        clusters=clusters[:10],  # Top 10 clusters
        hotspots=hotspots[:10],  # Top 10 hotspots
    )


def _build_coupling_clusters(pairs: list[CouplingPair]) -> list[list[str]]:
    """Build clusters of coupled files using connected components.

    Args:
        pairs: List of coupling pairs

    Returns:
        List of file clusters (each cluster is a list of file paths)
    """
    # Build adjacency for high-coupling pairs (strength >= 0.5)
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        if pair.coupling_strength >= 0.5:
            if pair.file_a not in adjacency:
                adjacency[pair.file_a] = set()
            if pair.file_b not in adjacency:
                adjacency[pair.file_b] = set()
            adjacency[pair.file_a].add(pair.file_b)
            adjacency[pair.file_b].add(pair.file_a)

    # Find connected components
    visited: set[str] = set()
    clusters: list[list[str]] = []

    for start in adjacency:
        if start in visited:
            continue
        # BFS to find component
        cluster: list[str] = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster) >= 2:  # Only include clusters with 2+ files
            cluster.sort()
            clusters.append(cluster)

    # Sort clusters by size descending
    clusters.sort(key=lambda c: -len(c))
    return clusters


def analyze_regression_clustering(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> RegressionAnalysis:
    """Detect files where bug fixes frequently lead to new bugs.

    Uses heuristics:
    1. Temporal proximity: Bug B completed within 7 days of Bug A
    2. File overlap: Both bugs affect same file(s)

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        RegressionAnalysis with clusters of related regressions
    """
    # Filter to bugs only and sort by completion date
    bugs = [i for i in issues if i.issue_type == "BUG" and i.completed_date]
    bugs.sort(key=lambda i: i.completed_date)  # type: ignore

    if len(bugs) < 2:
        return RegressionAnalysis()

    # Extract file paths for each bug
    bug_files: dict[str, set[str]] = {}  # issue_id -> set of files
    for bug in bugs:
        if contents is not None and bug.path in contents:
            content = contents[bug.path]
            paths = _extract_paths_from_issue(content)
            bug_files[bug.issue_id] = set(paths)
        else:
            try:
                content = bug.path.read_text(encoding="utf-8")
                paths = _extract_paths_from_issue(content)
                bug_files[bug.issue_id] = set(paths)
            except Exception:
                bug_files[bug.issue_id] = set()

    # Find regression pairs (temporal proximity + file overlap)
    regression_pairs: list[tuple[CompletedIssue, CompletedIssue, set[str]]] = []

    for i, bug_a in enumerate(bugs[:-1]):
        files_a = bug_files.get(bug_a.issue_id, set())
        if not files_a:
            continue

        for bug_b in bugs[i + 1 :]:
            # Check temporal proximity (within 7 days)
            days_apart = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
            if days_apart > 7:
                break  # Bugs are sorted, no need to check further

            files_b = bug_files.get(bug_b.issue_id, set())
            if not files_b:
                continue

            # Check file overlap
            overlap = files_a & files_b
            if overlap:
                regression_pairs.append((bug_a, bug_b, overlap))

    if not regression_pairs:
        return RegressionAnalysis()

    # Group by primary file (most common overlapping file)
    file_regressions: dict[str, list[tuple[str, str, int]]] = {}  # file -> [(id_a, id_b, days)]

    for bug_a, bug_b, overlap in regression_pairs:
        days = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
        for file_path in overlap:
            if file_path not in file_regressions:
                file_regressions[file_path] = []
            file_regressions[file_path].append((bug_a.issue_id, bug_b.issue_id, days))

    # Build clusters
    clusters: list[RegressionCluster] = []

    for file_path, pairs in file_regressions.items():
        # Determine time pattern
        avg_days = sum(d for _, _, d in pairs) / len(pairs)
        if avg_days < 3:
            time_pattern = "immediate"
        elif len(pairs) >= 3:
            time_pattern = "chronic"
        else:
            time_pattern = "delayed"

        # Determine severity
        if len(pairs) >= 4:
            severity = "critical"
        elif len(pairs) >= 2:
            severity = "high"
        else:
            severity = "medium"

        # Collect related files
        related_files: set[str] = set()
        for bug_a, bug_b, _ in regression_pairs:
            if file_path in (
                bug_files.get(bug_a.issue_id, set()) & bug_files.get(bug_b.issue_id, set())
            ):
                related_files.update(bug_files.get(bug_a.issue_id, set()))
                related_files.update(bug_files.get(bug_b.issue_id, set()))
        related_files.discard(file_path)

        clusters.append(
            RegressionCluster(
                primary_file=file_path,
                regression_count=len(pairs),
                fix_bug_pairs=[(a, b) for a, b, _ in pairs],
                related_files=sorted(related_files),
                time_pattern=time_pattern,
                severity=severity,
            )
        )

    # Sort by regression count descending
    clusters.sort(key=lambda c: (-c.regression_count, c.primary_file))

    # Identify most fragile files
    most_fragile = [c.primary_file for c in clusters[:5]]

    return RegressionAnalysis(
        clusters=clusters[:10],  # Top 10
        total_regression_chains=len(regression_pairs),
        most_fragile_files=most_fragile,
    )


def analyze_test_gaps(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
) -> TestGapAnalysis:
    """Correlate bug occurrences with test coverage gaps.

    Args:
        issues: List of completed issues (unused, for API consistency)
        hotspots: Pre-computed hotspot analysis

    Returns:
        TestGapAnalysis with test coverage gap information
    """
    # Build map of source files to bug info from hotspots
    bug_files: dict[str, dict[str, Any]] = {}

    for hotspot in hotspots.file_hotspots:
        bug_count = hotspot.issue_types.get("BUG", 0)
        if bug_count > 0:
            # Filter to only BUG issue IDs
            bug_ids = [iid for iid in hotspot.issue_ids if iid.startswith("BUG-")]
            bug_files[hotspot.path] = {
                "bug_count": bug_count,
                "bug_ids": bug_ids,
            }

    if not bug_files:
        return TestGapAnalysis()

    # Analyze test coverage for each file with bugs
    gaps: list[TestGap] = []
    files_with_tests: list[int] = []  # bug counts
    files_without_tests: list[int] = []  # bug counts

    for source_file, data in bug_files.items():
        bug_count = data["bug_count"]
        bug_ids = data["bug_ids"]

        test_file = _find_test_file(source_file)
        has_test = test_file is not None

        # Calculate gap score: higher = more urgent to add tests
        # Files without tests get amplified scores
        if has_test:
            gap_score = bug_count * 1.0
            files_with_tests.append(bug_count)
        else:
            gap_score = bug_count * 10.0  # Amplify untested files
            files_without_tests.append(bug_count)

        # Determine priority based on bug count and test presence
        if not has_test and bug_count >= 5:
            priority = "critical"
        elif not has_test and bug_count >= 3:
            priority = "high"
        elif not has_test or bug_count >= 4:
            priority = "medium"
        else:
            priority = "low"

        gaps.append(
            TestGap(
                source_file=source_file,
                bug_count=bug_count,
                bug_ids=bug_ids,
                has_test_file=has_test,
                test_file_path=test_file,
                gap_score=gap_score,
                priority=priority,
            )
        )

    # Sort by gap score descending (highest priority first)
    gaps.sort(key=lambda g: (-g.gap_score, -g.bug_count))

    # Calculate averages for correlation
    avg_with_tests = sum(files_with_tests) / len(files_with_tests) if files_with_tests else 0.0
    avg_without_tests = (
        sum(files_without_tests) / len(files_without_tests) if files_without_tests else 0.0
    )

    # Identify untested bug magnets (from hotspot analysis)
    untested_magnets = [h.path for h in hotspots.bug_magnets if _find_test_file(h.path) is None]

    # Priority test targets: untested files sorted by bug count
    priority_targets = [g.source_file for g in gaps if not g.has_test_file]

    return TestGapAnalysis(
        gaps=gaps[:15],  # Top 15
        untested_bug_magnets=untested_magnets,
        files_with_tests_avg_bugs=avg_with_tests,
        files_without_tests_avg_bugs=avg_without_tests,
        priority_test_targets=priority_targets[:10],
    )


def analyze_rejection_rates(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> RejectionAnalysis:
    """Analyze rejection and invalid closure patterns.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        RejectionAnalysis with overall and grouped metrics
    """
    if not issues:
        return RejectionAnalysis()

    # Count by category
    overall = RejectionMetrics()
    by_type: dict[str, RejectionMetrics] = {}
    by_month: dict[str, RejectionMetrics] = {}
    reason_counts: dict[str, int] = {}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        category = _parse_resolution_action(content)
        overall.total_closed += 1

        # Update overall counts
        if category == "completed":
            overall.completed_count += 1
        elif category == "rejected":
            overall.rejected_count += 1
        elif category == "invalid":
            overall.invalid_count += 1
        elif category == "duplicate":
            overall.duplicate_count += 1
        elif category == "deferred":
            overall.deferred_count += 1

        # By type
        if issue.issue_type not in by_type:
            by_type[issue.issue_type] = RejectionMetrics()
        type_metrics = by_type[issue.issue_type]
        type_metrics.total_closed += 1
        if category == "rejected":
            type_metrics.rejected_count += 1
        elif category == "invalid":
            type_metrics.invalid_count += 1
        elif category == "duplicate":
            type_metrics.duplicate_count += 1
        elif category == "deferred":
            type_metrics.deferred_count += 1
        elif category == "completed":
            type_metrics.completed_count += 1

        # By month
        if issue.completed_date:
            month_key = issue.completed_date.strftime("%Y-%m")
            if month_key not in by_month:
                by_month[month_key] = RejectionMetrics()
            month_metrics = by_month[month_key]
            month_metrics.total_closed += 1
            if category == "rejected":
                month_metrics.rejected_count += 1
            elif category == "invalid":
                month_metrics.invalid_count += 1
            elif category == "duplicate":
                month_metrics.duplicate_count += 1
            elif category == "deferred":
                month_metrics.deferred_count += 1
            elif category == "completed":
                month_metrics.completed_count += 1

        # Extract reason for rejection/invalid
        if category in ("rejected", "invalid", "duplicate", "deferred"):
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip()
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # Calculate trend from monthly data
    sorted_months = sorted(by_month.keys())
    if len(sorted_months) >= 3:
        recent = sorted_months[-3:]
        rates = [by_month[m].rejection_rate + by_month[m].invalid_rate for m in recent]
        if rates[-1] < rates[0] * 0.8:
            trend = "improving"
        elif rates[-1] > rates[0] * 1.2:
            trend = "degrading"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Sort reasons by count
    common_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:10]

    return RejectionAnalysis(
        overall=overall,
        by_type=by_type,
        by_month=by_month,
        common_reasons=common_reasons,
        trend=trend,
    )


# Pattern definitions for manual activity detection
_MANUAL_PATTERNS: dict[str, dict[str, Any]] = {
    "test": {
        "patterns": [
            r"(?:pytest|python -m pytest|npm test|yarn test|jest|cargo test|go test)",
            r"(?:python -m unittest|nosetests|tox)",
        ],
        "description": "Test execution after code changes",
        "suggestion": "Add post-edit hook for automatic test runs",
        "complexity": "trivial",
    },
    "lint": {
        "patterns": [
            r"(?:ruff check|ruff format|black|isort|flake8|pylint)",
            r"(?:eslint|prettier|tslint)",
        ],
        "description": "Lint/format fixes after implementation",
        "suggestion": "Add pre-commit hook for auto-formatting",
        "complexity": "simple",
    },
    "type_check": {
        "patterns": [
            r"(?:mypy|pyright|python -m mypy)",
            r"(?:tsc|npx tsc)",
        ],
        "description": "Type checking during development",
        "suggestion": "Add mypy to pre-commit or post-edit hook",
        "complexity": "simple",
    },
    "build": {
        "patterns": [
            r"(?:npm run build|yarn build|make|cargo build|go build)",
            r"(?:python -m build|pip install -e)",
        ],
        "description": "Build steps during implementation",
        "suggestion": "Add build verification to test suite or CI",
        "complexity": "moderate",
    },
    "git": {
        "patterns": [
            r"git (?:add|commit|push|pull|checkout|branch)",
        ],
        "description": "Git operations during issue resolution",
        "suggestion": "Use /ll:commit skill for standardized commits",
        "complexity": "trivial",
    },
}

# Cross-cutting concern keywords for smell detection
_CROSS_CUTTING_KEYWORDS: dict[str, list[str]] = {
    "logging": ["log", "logger", "logging", "debug", "trace", "print"],
    "error-handling": ["error", "exception", "try", "catch", "raise", "except", "fail"],
    "validation": ["valid", "validate", "check", "assert", "verify", "sanitize"],
    "auth": ["auth", "permission", "role", "access", "token", "credential", "login"],
    "caching": ["cache", "memo", "memoize", "store", "ttl", "expire", "cached"],
}

# Suggested patterns for each cross-cutting concern type
_CONCERN_PATTERNS: dict[str, str] = {
    "logging": "decorator",
    "error-handling": "middleware",
    "validation": "decorator",
    "auth": "middleware",
    "caching": "decorator",
}


def detect_manual_patterns(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> ManualPatternAnalysis:
    """Detect recurring manual activities that could be automated.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        ManualPatternAnalysis with detected patterns
    """
    if not issues:
        return ManualPatternAnalysis()

    # Track pattern occurrences
    pattern_data: dict[str, dict[str, Any]] = {}

    for pattern_type, config in _MANUAL_PATTERNS.items():
        pattern_data[pattern_type] = {
            "count": 0,
            "issues": [],
            "commands": [],
            "config": config,
        }

    # Scan issue content for patterns
    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        for pattern_type, config in _MANUAL_PATTERNS.items():
            for pattern in config["patterns"]:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    data = pattern_data[pattern_type]
                    data["count"] += len(matches)
                    if issue.issue_id not in data["issues"]:
                        data["issues"].append(issue.issue_id)
                    # Store unique command examples
                    for match in matches:
                        if match not in data["commands"]:
                            data["commands"].append(match)

    # Build ManualPattern objects
    patterns: list[ManualPattern] = []
    total_interventions = 0
    automatable = 0

    for pattern_type, data in pattern_data.items():
        if data["count"] > 0:
            config = data["config"]
            pattern = ManualPattern(
                pattern_type=pattern_type,
                pattern_description=config["description"],
                occurrence_count=data["count"],
                affected_issues=data["issues"],
                example_commands=data["commands"][:5],
                suggested_automation=config["suggestion"],
                automation_complexity=config["complexity"],
            )
            patterns.append(pattern)
            total_interventions += data["count"]
            automatable += data["count"]

    # Sort by occurrence count descending
    patterns.sort(key=lambda p: -p.occurrence_count)

    # Build automation suggestions
    suggestions = [p.suggested_automation for p in patterns if p.occurrence_count >= 2]

    return ManualPatternAnalysis(
        patterns=patterns,
        total_manual_interventions=total_interventions,
        automatable_count=automatable,
        automation_suggestions=suggestions[:10],
    )


def detect_cross_cutting_smells(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
    contents: dict[Path, str] | None = None,
) -> CrossCuttingAnalysis:
    """Detect cross-cutting concerns scattered across the codebase.

    Identifies when issues consistently touch multiple unrelated directories,
    suggesting missing abstractions for cross-cutting concerns like logging,
    error handling, or validation.

    Args:
        issues: List of completed issues
        hotspots: Hotspot analysis results (provides directory reference)
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        CrossCuttingAnalysis with detected smells
    """
    if not issues:
        return CrossCuttingAnalysis()

    # Track concern data: {concern_type: {dirs: set, issues: list}}
    concern_data: dict[str, dict[str, Any]] = {}
    for concern_type in _CROSS_CUTTING_KEYWORDS:
        concern_data[concern_type] = {
            "directories": set(),
            "issue_ids": [],
        }

    # Get all unique directories from hotspots for scatter score calculation
    all_directories: set[str] = set()
    if hotspots.directory_hotspots:
        all_directories = {h.path for h in hotspots.directory_hotspots}

    # Analyze each issue
    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue
        content_lower = content.lower()

        # Extract paths from this issue
        paths = _extract_paths_from_issue(content)
        issue_dirs = {str(Path(p).parent) for p in paths if "/" in p or "\\" in p}
        all_directories.update(issue_dirs)

        # Check if this issue touches multiple directories (3+)
        if len(issue_dirs) < 3:
            continue

        # Check for concern keywords
        for concern_type, keywords in _CROSS_CUTTING_KEYWORDS.items():
            if any(kw in content_lower for kw in keywords):
                concern_data[concern_type]["directories"].update(issue_dirs)
                if issue.issue_id not in concern_data[concern_type]["issue_ids"]:
                    concern_data[concern_type]["issue_ids"].append(issue.issue_id)

    # Build CrossCuttingSmell objects
    smells: list[CrossCuttingSmell] = []
    total_dirs = len(all_directories) if all_directories else 1

    for concern_type, data in concern_data.items():
        if data["issue_ids"]:  # Only include concerns with detected issues
            dirs = sorted(data["directories"])
            scatter_score = len(dirs) / total_dirs if total_dirs > 0 else 0.0

            smell = CrossCuttingSmell(
                concern_type=concern_type,
                affected_directories=dirs,
                issue_count=len(data["issue_ids"]),
                issue_ids=data["issue_ids"],
                scatter_score=scatter_score,
                suggested_pattern=_CONCERN_PATTERNS.get(concern_type, "aspect"),
            )
            smells.append(smell)

    # Sort by scatter score descending
    smells.sort(key=lambda s: -s.scatter_score)

    # Identify most scattered concern
    most_scattered = smells[0].concern_type if smells else ""

    # Build consolidation opportunities
    consolidation_opportunities = []
    for smell in smells:
        if smell.scatter_score >= 0.3:  # Threshold for suggesting consolidation
            consolidation_opportunities.append(
                f"Centralize {smell.concern_type} ({smell.issue_count} issues would benefit)"
            )

    return CrossCuttingAnalysis(
        smells=smells,
        most_scattered_concern=most_scattered,
        consolidation_opportunities=consolidation_opportunities[:10],
    )


# Mapping from manual pattern types to configuration solutions
_PATTERN_TO_CONFIG: dict[str, dict[str, Any]] = {
    "test": {
        "hook_event": "PostToolUse",
        "description": "Automatic test execution after code changes",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "pytest tests/ -x -q",
      "timeout": 30000
    }]
  }]""",
    },
    "lint": {
        "hook_event": "PreToolUse",
        "description": "Automatic formatting before file writes",
        "suggested_config": """hooks/hooks.json:
  "PreToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "ruff format --check .",
      "timeout": 10000
    }]
  }]""",
    },
    "type_check": {
        "hook_event": "PostToolUse",
        "description": "Type checking after code modifications",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "mypy --fast .",
      "timeout": 30000
    }]
  }]""",
    },
    "build": {
        "hook_event": "PostToolUse",
        "description": "Build verification after changes",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "npm run build",
      "timeout": 60000
    }]
  }]""",
    },
}


def detect_config_gaps(
    manual_pattern_analysis: ManualPatternAnalysis,
    project_root: Path | None = None,
) -> ConfigGapsAnalysis:
    """Detect configuration gaps based on manual pattern analysis.

    Args:
        manual_pattern_analysis: Results from detect_manual_patterns()
        project_root: Project root directory (defaults to cwd)

    Returns:
        ConfigGapsAnalysis with identified gaps and coverage metrics
    """
    if project_root is None:
        project_root = Path.cwd()

    # Discover current configuration
    current_hooks: list[str] = []
    current_skills: list[str] = []
    current_agents: list[str] = []

    # Load hooks configuration
    hooks_file = project_root / "hooks" / "hooks.json"
    if hooks_file.exists():
        try:
            with open(hooks_file, encoding="utf-8") as f:
                hooks_data = json.load(f)
            current_hooks = list(hooks_data.get("hooks", {}).keys())
        except Exception:
            pass

    # Scan for agents
    agents_dir = project_root / "agents"
    if agents_dir.is_dir():
        for agent_file in agents_dir.glob("*.md"):
            current_agents.append(agent_file.stem)

    # Scan for skills
    skills_dir = project_root / "skills"
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                current_skills.append(skill_dir.name)

    # Identify gaps from manual patterns
    gaps: list[ConfigGap] = []
    covered_patterns = 0
    recognized_patterns = 0

    for pattern in manual_pattern_analysis.patterns:
        config_mapping = _PATTERN_TO_CONFIG.get(pattern.pattern_type)
        if not config_mapping:
            continue

        recognized_patterns += 1
        hook_event = config_mapping["hook_event"]

        # Check if hook event is already configured
        if hook_event in current_hooks:
            covered_patterns += 1
            continue

        # Determine priority based on occurrence count
        if pattern.occurrence_count >= 10:
            priority = "high"
        elif pattern.occurrence_count >= 5:
            priority = "medium"
        else:
            priority = "low"

        gap = ConfigGap(
            gap_type="hook",
            description=config_mapping["description"],
            evidence=pattern.affected_issues,
            suggested_config=config_mapping["suggested_config"],
            priority=priority,
            pattern_type=pattern.pattern_type,
        )
        gaps.append(gap)

    # Calculate coverage score based on recognized patterns only
    coverage_score = covered_patterns / recognized_patterns if recognized_patterns > 0 else 1.0

    # Sort gaps by priority (high first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.priority, 3))

    return ConfigGapsAnalysis(
        gaps=gaps,
        current_hooks=current_hooks,
        current_skills=current_skills,
        current_agents=current_agents,
        coverage_score=coverage_score,
    )


def analyze_agent_effectiveness(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> AgentEffectivenessAnalysis:
    """Analyze agent effectiveness across issue types.

    Groups issues by processing agent and issue type, calculating
    success/failure/rejection rates for each combination.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        AgentEffectivenessAnalysis with outcomes and recommendations
    """
    if not issues:
        return AgentEffectivenessAnalysis()

    # Track outcomes by (agent, issue_type)
    outcomes_map: dict[tuple[str, str], AgentOutcome] = {}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        # Detect agent (discovered_by may contain source info in some cases)
        agent = _detect_processing_agent(content, issue.discovered_by)

        # Get resolution outcome
        resolution = _parse_resolution_action(content)

        # Get or create outcome tracker
        key = (agent, issue.issue_type)
        if key not in outcomes_map:
            outcomes_map[key] = AgentOutcome(
                agent_name=agent,
                issue_type=issue.issue_type,
            )

        outcome = outcomes_map[key]

        # Categorize outcome
        if resolution == "completed":
            outcome.success_count += 1
        elif resolution in ("rejected", "invalid", "duplicate"):
            outcome.rejection_count += 1
        else:  # deferred or other
            outcome.failure_count += 1

    # Build outcomes list
    outcomes = list(outcomes_map.values())

    # Determine best agent per issue type
    best_agent_by_type: dict[str, str] = {}
    type_agents: dict[str, list[AgentOutcome]] = {}

    for outcome in outcomes:
        if outcome.issue_type not in type_agents:
            type_agents[outcome.issue_type] = []
        type_agents[outcome.issue_type].append(outcome)

    for issue_type, agent_outcomes in type_agents.items():
        # Require minimum sample size
        significant_outcomes = [o for o in agent_outcomes if o.total_count >= 3]
        if significant_outcomes:
            best = max(significant_outcomes, key=lambda o: o.success_rate)
            best_agent_by_type[issue_type] = best.agent_name

    # Identify problematic combinations (success rate < 50% with >= 5 samples)
    problematic_combinations: list[tuple[str, str, str]] = []
    for outcome in outcomes:
        if outcome.total_count >= 5 and outcome.success_rate < 0.5:
            reason = (
                f"{outcome.success_rate * 100:.0f}% success "
                f"({outcome.success_count}/{outcome.total_count})"
            )
            problematic_combinations.append((outcome.agent_name, outcome.issue_type, reason))

    # Sort by success rate ascending (worst first)
    problematic_combinations.sort(key=lambda x: float(x[2].split("%")[0]))

    return AgentEffectivenessAnalysis(
        outcomes=sorted(outcomes, key=lambda o: (o.agent_name, o.issue_type)),
        best_agent_by_type=best_agent_by_type,
        problematic_combinations=problematic_combinations,
    )


def analyze_complexity_proxy(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
    contents: dict[Path, str] | None = None,
) -> ComplexityProxyAnalysis:
    """Use issue duration as proxy for code complexity.

    Areas that consistently take longer to resolve suggest higher complexity,
    insufficient documentation, or accumulated technical debt.

    Args:
        issues: List of completed issues with dates
        hotspots: Pre-computed hotspot analysis for path information
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        ComplexityProxyAnalysis with duration-based complexity metrics
    """
    # Calculate durations for all issues with both dates
    issue_durations: dict[str, float] = {}  # issue_id -> days
    for issue in issues:
        if issue.discovered_date and issue.completed_date:
            delta = issue.completed_date - issue.discovered_date
            days = float(delta.days)
            if days >= 0:  # Sanity check
                issue_durations[issue.issue_id] = days

    if not issue_durations:
        return ComplexityProxyAnalysis()

    # Calculate baseline (median duration)
    all_durations = sorted(issue_durations.values())
    n = len(all_durations)
    if n % 2 == 0:
        baseline_days = (all_durations[n // 2 - 1] + all_durations[n // 2]) / 2
    else:
        baseline_days = all_durations[n // 2]

    if baseline_days == 0:
        baseline_days = 1.0  # Avoid division by zero

    # Map issues to their affected files by reading issue content
    issue_to_files: dict[str, list[str]] = {}
    for issue in issues:
        if issue.issue_id in issue_durations:
            if contents is not None and issue.path in contents:
                content = contents[issue.path]
            else:
                try:
                    content = issue.path.read_text(encoding="utf-8")
                except Exception:
                    continue
            paths = _extract_paths_from_issue(content)
            if paths:
                issue_to_files[issue.issue_id] = paths

    # Aggregate durations by file
    file_durations: dict[str, list[tuple[str, float]]] = {}  # path -> [(issue_id, days), ...]
    for issue_id, files in issue_to_files.items():
        days = issue_durations[issue_id]
        for f in files:
            if f not in file_durations:
                file_durations[f] = []
            file_durations[f].append((issue_id, days))

    # Aggregate durations by directory
    dir_durations: dict[str, list[tuple[str, float]]] = {}
    for path, entries in file_durations.items():
        dir_path = "/".join(path.split("/")[:-1]) + "/" if "/" in path else "./"
        if dir_path not in dir_durations:
            dir_durations[dir_path] = []
        dir_durations[dir_path].extend(entries)

    # Build file complexity proxies
    file_complexity: list[ComplexityProxy] = []
    for path, entries in file_durations.items():
        if len(entries) < 2:  # Need at least 2 data points
            continue

        durations = [d for _, d in entries]
        avg = sum(durations) / len(durations)
        sorted_d = sorted(durations)
        median = sorted_d[len(sorted_d) // 2]
        slowest = max(entries, key=lambda x: x[1])

        # Normalize complexity score (0-1 based on how much slower than baseline)
        ratio = avg / baseline_days
        complexity_score = min(1.0, (ratio - 1) / 4)  # 5x slower = 1.0
        complexity_score = max(0.0, complexity_score)

        comparison = f"{ratio:.1f}x baseline" if ratio >= 1.5 else "near baseline"

        file_complexity.append(
            ComplexityProxy(
                path=path,
                avg_resolution_days=avg,
                median_resolution_days=median,
                issue_count=len(entries),
                slowest_issue=slowest,
                complexity_score=complexity_score,
                comparison_to_baseline=comparison,
            )
        )

    # Build directory complexity proxies
    directory_complexity: list[ComplexityProxy] = []
    for dir_path, entries in dir_durations.items():
        if len(entries) < 3:  # Need at least 3 data points for directories
            continue

        # Deduplicate by issue_id for directory-level stats
        unique_entries: dict[str, float] = {}
        for issue_id, days in entries:
            if issue_id not in unique_entries or days > unique_entries[issue_id]:
                unique_entries[issue_id] = days

        entries_list = list(unique_entries.items())
        durations = list(unique_entries.values())
        avg = sum(durations) / len(durations)
        sorted_d = sorted(durations)
        median = sorted_d[len(sorted_d) // 2]
        slowest = max(entries_list, key=lambda x: x[1])

        ratio = avg / baseline_days
        complexity_score = min(1.0, (ratio - 1) / 4)
        complexity_score = max(0.0, complexity_score)

        comparison = f"{ratio:.1f}x baseline" if ratio >= 1.5 else "near baseline"

        directory_complexity.append(
            ComplexityProxy(
                path=dir_path,
                avg_resolution_days=avg,
                median_resolution_days=median,
                issue_count=len(unique_entries),
                slowest_issue=slowest,
                complexity_score=complexity_score,
                comparison_to_baseline=comparison,
            )
        )

    # Sort by complexity score descending
    file_complexity.sort(key=lambda c: -c.complexity_score)
    directory_complexity.sort(key=lambda c: -c.complexity_score)

    # Identify outliers (>2x baseline)
    complexity_outliers = [
        c.path for c in file_complexity if c.avg_resolution_days > baseline_days * 2
    ]

    return ComplexityProxyAnalysis(
        file_complexity=file_complexity[:10],
        directory_complexity=directory_complexity[:10],
        baseline_days=baseline_days,
        complexity_outliers=complexity_outliers[:10],
    )


def _calculate_debt_metrics(
    completed_issues: list[CompletedIssue],
    active_issues: list[tuple[Path, str, str, date | None]],
) -> TechnicalDebtMetrics:
    """Calculate technical debt health metrics.

    Args:
        completed_issues: List of completed issues
        active_issues: List of active issue tuples

    Returns:
        TechnicalDebtMetrics with calculated values
    """
    today = date.today()
    metrics = TechnicalDebtMetrics()

    # Backlog size
    metrics.backlog_size = len(active_issues)

    # Count aging and high priority
    for _path, _issue_type, priority, discovered_date in active_issues:
        if priority in ("P0", "P1"):
            metrics.high_priority_open += 1

        if discovered_date:
            age = (today - discovered_date).days
            if age >= 30:
                metrics.aging_30_plus += 1
            if age >= 60:
                metrics.aging_60_plus += 1

    # Calculate backlog growth rate (issues per week)
    # Look at last 4 weeks of completions vs creations
    four_weeks_ago = today - timedelta(days=28)

    completed_recently = sum(
        1 for i in completed_issues if i.completed_date and i.completed_date >= four_weeks_ago
    )

    created_recently = sum(1 for _, _, _, d in active_issues if d and d >= four_weeks_ago)

    # Net change per week
    if completed_recently > 0 or created_recently > 0:
        metrics.backlog_growth_rate = (created_recently - completed_recently) / 4.0

    # Debt paydown ratio (bug fixes vs features)
    bug_count = sum(1 for i in completed_issues if i.issue_type == "BUG")
    feat_count = sum(1 for i in completed_issues if i.issue_type == "FEAT")

    if feat_count > 0:
        metrics.debt_paydown_ratio = bug_count / feat_count
    elif bug_count > 0:
        metrics.debt_paydown_ratio = float(bug_count)  # All maintenance

    return metrics


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
