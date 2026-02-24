"""Issue history technical debt analysis: cross-cutting concerns, agent effectiveness, complexity."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from little_loops.issue_history.models import (
    AgentEffectivenessAnalysis,
    AgentOutcome,
    CompletedIssue,
    ComplexityProxy,
    ComplexityProxyAnalysis,
    CrossCuttingAnalysis,
    CrossCuttingSmell,
    HotspotAnalysis,
    TechnicalDebtMetrics,
)
from little_loops.issue_history.parsing import (
    _detect_processing_agent,
    _extract_paths_from_issue,
    _parse_resolution_action,
)

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
