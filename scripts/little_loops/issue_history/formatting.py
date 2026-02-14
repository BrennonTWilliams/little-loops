"""Issue history formatting functions.

Provides functions to format issue history summaries and analyses
as text, JSON, YAML, and Markdown.
"""

from __future__ import annotations

import json

from little_loops.issue_history.models import (
    AgentOutcome,
    HistoryAnalysis,
    HistorySummary,
)


def format_summary_text(summary: HistorySummary) -> str:
    """Format summary as human-readable text.

    Args:
        summary: HistorySummary to format

    Returns:
        Formatted text string
    """
    lines: list[str] = []

    lines.append("Issue History Summary")
    lines.append("=" * 21)
    lines.append(f"Total Completed: {summary.total_count}")

    if summary.earliest_date and summary.latest_date:
        days = summary.date_range_days or 0
        lines.append(f"Date Range: {summary.earliest_date} to {summary.latest_date} ({days} days)")
        if summary.velocity:
            lines.append(f"Velocity: {summary.velocity:.1f} issues/day")

    lines.append("")
    lines.append("By Type:")
    total = summary.total_count or 1
    for issue_type, count in summary.type_counts.items():
        pct = count * 100 // total
        lines.append(f"  {issue_type:5}: {count:3} ({pct:2}%)")

    lines.append("")
    lines.append("By Priority:")
    for priority, count in summary.priority_counts.items():
        pct = count * 100 // total
        lines.append(f"  {priority}:  {count:3} ({pct:2}%)")

    lines.append("")
    lines.append("By Discovery Source:")
    for source, count in summary.discovery_counts.items():
        pct = count * 100 // total
        lines.append(f"  {source:15}: {count:3} ({pct:2}%)")

    return "\n".join(lines)


def format_summary_json(summary: HistorySummary) -> str:
    """Format summary as JSON.

    Args:
        summary: HistorySummary to format

    Returns:
        JSON string
    """
    return json.dumps(summary.to_dict(), indent=2)


def format_analysis_json(analysis: HistoryAnalysis) -> str:
    """Format analysis as JSON.

    Args:
        analysis: HistoryAnalysis to format

    Returns:
        JSON string
    """
    return json.dumps(analysis.to_dict(), indent=2)


def format_analysis_yaml(analysis: HistoryAnalysis) -> str:
    """Format analysis as YAML.

    Args:
        analysis: HistoryAnalysis to format

    Returns:
        YAML string (falls back to JSON if yaml not available)
    """
    try:
        import yaml

        return yaml.dump(analysis.to_dict(), default_flow_style=False, sort_keys=False)
    except ImportError:
        # Fallback to JSON if yaml not available
        return format_analysis_json(analysis)


def format_analysis_text(analysis: HistoryAnalysis) -> str:
    """Format analysis as human-readable text.

    Args:
        analysis: HistoryAnalysis to format

    Returns:
        Formatted text string
    """
    lines: list[str] = []

    lines.append("Issue History Analysis")
    lines.append("=" * 22)
    lines.append(f"Generated: {analysis.generated_date}")
    lines.append(f"Completed: {analysis.total_completed}  |  Active: {analysis.total_active}")

    if analysis.date_range_start and analysis.date_range_end:
        lines.append(f"Date Range: {analysis.date_range_start} to {analysis.date_range_end}")

    # Summary
    lines.append("")
    lines.append("Summary")
    lines.append("-" * 7)
    summary = analysis.summary
    if summary.velocity:
        lines.append(f"Velocity: {summary.velocity:.2f} issues/day")
    lines.append(f"Velocity Trend: {analysis.velocity_trend}")
    lines.append(f"Bug Ratio Trend: {analysis.bug_ratio_trend}")

    # Type distribution
    lines.append("")
    lines.append("By Type:")
    total = analysis.total_completed or 1
    for issue_type, count in summary.type_counts.items():
        pct = count * 100 // total
        lines.append(f"  {issue_type:5}: {count:3} ({pct:2}%)")

    # Period metrics
    if analysis.period_metrics:
        lines.append("")
        lines.append("Period Metrics")
        lines.append("-" * 14)
        for period in analysis.period_metrics[-6:]:  # Last 6 periods
            bug_pct = f"{period.bug_ratio * 100:.0f}%" if period.bug_ratio else "N/A"
            lines.append(
                f"  {period.period_label:12}: {period.total_completed:3} completed, {bug_pct} bugs"
            )

    # Subsystem health
    if analysis.subsystem_health:
        lines.append("")
        lines.append("Subsystem Health")
        lines.append("-" * 16)
        for sub in analysis.subsystem_health[:5]:
            trend_symbol = {"improving": "↓", "degrading": "↑", "stable": "→"}.get(sub.trend, "?")
            lines.append(
                f"  {sub.subsystem:30}: {sub.total_issues:3} total, "
                f"{sub.recent_issues:2} recent {trend_symbol}"
            )

    # Hotspot analysis
    if analysis.hotspot_analysis:
        hotspots = analysis.hotspot_analysis

        if hotspots.file_hotspots:
            lines.append("")
            lines.append("File Hotspots")
            lines.append("-" * 13)
            for h in hotspots.file_hotspots[:5]:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                churn_flag = " [HIGH CHURN]" if h.churn_indicator == "high" else ""
                lines.append(f"  {h.path:40}: {h.issue_count:2} issues ({types_str}){churn_flag}")

        if hotspots.bug_magnets:
            lines.append("")
            lines.append("Bug Magnets (>60% bugs)")
            lines.append("-" * 23)
            for h in hotspots.bug_magnets:
                lines.append(
                    f"  {h.path}: {h.bug_ratio * 100:.0f}% bugs "
                    f"({h.issue_types.get('BUG', 0)}/{h.issue_count})"
                )

    # Coupling analysis
    if analysis.coupling_analysis:
        coupling = analysis.coupling_analysis

        if coupling.pairs:
            lines.append("")
            lines.append("Coupling Detection")
            lines.append("-" * 18)

            lines.append("Highly Coupled File Pairs:")
            for i, p in enumerate(coupling.pairs[:5], 1):
                strength_label = (
                    "HIGH"
                    if p.coupling_strength >= 0.7
                    else "MEDIUM"
                    if p.coupling_strength >= 0.5
                    else "LOW"
                )
                lines.append(f"  {i}. {p.file_a} <-> {p.file_b}")
                lines.append(
                    f"     Co-occurrences: {p.co_occurrence_count}, "
                    f"Strength: {p.coupling_strength:.2f} [{strength_label}]"
                )

        if coupling.clusters:
            lines.append("")
            lines.append("Coupling Clusters:")
            for i, cluster in enumerate(coupling.clusters[:3], 1):
                files_str = ", ".join(cluster[:4])
                if len(cluster) > 4:
                    files_str += f" (+{len(cluster) - 4} more)"
                lines.append(f"  {i}. [{files_str}]")

        if coupling.hotspots:
            lines.append("")
            lines.append("Coupling Hotspots (coupled with 3+ files):")
            for f in coupling.hotspots[:5]:
                lines.append(f"  - {f}")

    # Regression clustering analysis
    if analysis.regression_analysis:
        regression = analysis.regression_analysis

        if regression.clusters:
            lines.append("")
            lines.append("Regression Clustering")
            lines.append("-" * 20)
            lines.append(f"Total regression chains detected: {regression.total_regression_chains}")
            lines.append("")
            lines.append("Fragile Code Clusters:")
            for i, c in enumerate(regression.clusters[:5], 1):
                severity_flag = (
                    f" [{c.severity.upper()}]" if c.severity in ("critical", "high") else ""
                )
                lines.append(f"  {i}. {c.primary_file}{severity_flag}")
                lines.append(f"     Regression count: {c.regression_count}")
                lines.append(f"     Pattern: {c.time_pattern}")
                if c.fix_bug_pairs:
                    chain = " -> ".join(f"{a} fix -> {b}" for a, b in c.fix_bug_pairs[:3])
                    if len(c.fix_bug_pairs) > 3:
                        chain += " ..."
                    lines.append(f"     Chain: {chain}")

    # Test gap analysis
    if analysis.test_gap_analysis:
        tga = analysis.test_gap_analysis

        if tga.gaps:
            lines.append("")
            lines.append("Test Gap Correlation")
            lines.append("-" * 20)

            # Show correlation stats
            lines.append(f"  Files with tests: avg {tga.files_with_tests_avg_bugs:.1f} bugs")
            lines.append(f"  Files without tests: avg {tga.files_without_tests_avg_bugs:.1f} bugs")
            lines.append("")

            # Show critical gaps
            critical_gaps = [g for g in tga.gaps if g.priority in ("critical", "high")]
            if critical_gaps:
                lines.append("Critical Test Gaps:")
                for g in critical_gaps[:5]:
                    test_status = "NO TEST" if not g.has_test_file else g.test_file_path
                    lines.append(f"  {g.source_file} [{g.priority.upper()}]")
                    bug_ids_str = ", ".join(g.bug_ids[:3])
                    lines.append(f"     Bugs: {g.bug_count} ({bug_ids_str})")
                    lines.append(f"     Test: {test_status}")

        if tga.priority_test_targets:
            lines.append("")
            lines.append("Priority Test Targets:")
            for i, target in enumerate(tga.priority_test_targets[:5], 1):
                lines.append(f"  {i}. {target}")

    # Rejection analysis
    if analysis.rejection_analysis:
        rej = analysis.rejection_analysis
        overall = rej.overall

        if overall.total_closed > 0:
            lines.append("")
            lines.append("Rejection Analysis")
            lines.append("-" * 18)
            lines.append(
                f"  Overall rejection rate: {overall.rejection_rate * 100:.1f}% "
                f"({overall.rejected_count}/{overall.total_closed})"
            )
            lines.append(
                f"  Invalid rate: {overall.invalid_rate * 100:.1f}% "
                f"({overall.invalid_count}/{overall.total_closed})"
            )
            if overall.duplicate_count > 0:
                lines.append(f"  Duplicates: {overall.duplicate_count}")
            if overall.deferred_count > 0:
                lines.append(f"  Deferred: {overall.deferred_count}")

            # By type
            if rej.by_type:
                lines.append("")
                lines.append("  By Type:")
                for issue_type in sorted(rej.by_type.keys()):
                    metrics = rej.by_type[issue_type]
                    rate = metrics.rejection_rate + metrics.invalid_rate
                    lines.append(f"    {issue_type:5}: {rate * 100:.1f}% non-completion")

            # Trend
            if rej.by_month:
                sorted_months = sorted(rej.by_month.keys())[-6:]
                if len(sorted_months) >= 2:
                    lines.append("")
                    lines.append("  Trend (last 6 months):")
                    trend_parts = []
                    for month in sorted_months:
                        m = rej.by_month[month]
                        rate = (m.rejection_rate + m.invalid_rate) * 100
                        trend_parts.append(f"{month[-2:]}: {rate:.0f}%")
                    lines.append(f"    {', '.join(trend_parts)}")
                    trend_symbol = {"improving": "↓", "degrading": "↑", "stable": "→"}.get(
                        rej.trend, "→"
                    )
                    lines.append(f"    Direction: {rej.trend} {trend_symbol}")

            # Common reasons
            if rej.common_reasons:
                lines.append("")
                lines.append("  Common Rejection Reasons:")
                for reason, count in rej.common_reasons[:5]:
                    lines.append(f'    - "{reason}" ({count})')

    # Manual pattern analysis
    if analysis.manual_pattern_analysis:
        mpa = analysis.manual_pattern_analysis

        if mpa.patterns:
            lines.append("")
            lines.append("Manual Pattern Analysis")
            lines.append("-" * 23)
            lines.append(f"  Total manual interventions: {mpa.total_manual_interventions}")
            lines.append(
                f"  Potentially automatable: {mpa.automatable_percentage:.0f}% "
                f"({mpa.automatable_count}/{mpa.total_manual_interventions})"
            )
            lines.append("")
            lines.append("  Recurring Patterns:")

            for i, pattern in enumerate(mpa.patterns[:5], 1):
                lines.append("")
                lines.append(
                    f"  {i}. {pattern.pattern_description} ({pattern.occurrence_count} occurrences)"
                )
                issues_str = ", ".join(pattern.affected_issues[:3])
                if len(pattern.affected_issues) > 3:
                    issues_str += ", ..."
                lines.append(f"     Issues: {issues_str}")
                lines.append(f"     Suggestion: {pattern.suggested_automation}")
                lines.append(f"     Complexity: {pattern.automation_complexity}")

    # Configuration gaps analysis
    if analysis.config_gaps_analysis:
        cga = analysis.config_gaps_analysis

        lines.append("")
        lines.append("Configuration Gaps Analysis")
        lines.append("-" * 27)
        lines.append(f"  Coverage score: {cga.coverage_score * 100:.0f}%")
        lines.append(f"  Current hooks: {', '.join(cga.current_hooks) or 'none'}")
        lines.append(f"  Current skills: {len(cga.current_skills)}")
        lines.append(f"  Current agents: {len(cga.current_agents)}")

        if cga.gaps:
            lines.append("")
            lines.append("  Identified Gaps:")

            for i, gap in enumerate(cga.gaps[:5], 1):
                lines.append("")
                lines.append(f"  {i}. Missing: {gap.gap_type} for {gap.description}")
                lines.append(f"     Priority: {gap.priority}")
                issues_str = ", ".join(gap.evidence[:3])
                if len(gap.evidence) > 3:
                    issues_str += ", ..."
                lines.append(f"     Evidence: {issues_str}")
                if gap.suggested_config:
                    lines.append("     Suggested config:")
                    for config_line in gap.suggested_config.split("\n")[:4]:
                        lines.append(f"       {config_line}")

    # Agent effectiveness analysis
    if analysis.agent_effectiveness_analysis:
        aea = analysis.agent_effectiveness_analysis

        if aea.outcomes:
            lines.append("")
            lines.append("Agent Effectiveness Analysis")
            lines.append("-" * 28)

            # Group by agent
            by_agent: dict[str, list[AgentOutcome]] = {}
            for outcome in aea.outcomes:
                if outcome.agent_name not in by_agent:
                    by_agent[outcome.agent_name] = []
                by_agent[outcome.agent_name].append(outcome)

            for agent in sorted(by_agent.keys()):
                lines.append(f"  {agent}:")
                for outcome in sorted(by_agent[agent], key=lambda o: o.issue_type):
                    rate_pct = outcome.success_rate * 100
                    flag = " [!]" if outcome.total_count >= 5 and rate_pct < 50 else ""
                    lines.append(
                        f"    {outcome.issue_type:5}: {rate_pct:5.1f}% success "
                        f"({outcome.success_count}/{outcome.total_count}){flag}"
                    )

            # Recommendations
            if aea.best_agent_by_type or aea.problematic_combinations:
                lines.append("")
                lines.append("  Recommendations:")
                for issue_type, best_agent in sorted(aea.best_agent_by_type.items()):
                    lines.append(f"    - {issue_type}: best handled by {best_agent}")
                for agent, issue_type, reason in aea.problematic_combinations[:3]:
                    lines.append(f"    - {agent} underperforms for {issue_type} ({reason})")

    # Complexity proxy analysis
    if analysis.complexity_proxy_analysis:
        cpa = analysis.complexity_proxy_analysis

        lines.append("")
        lines.append("Complexity Proxy Analysis")
        lines.append("-" * 25)
        lines.append(f"  Baseline resolution time: {cpa.baseline_days:.1f} days (median)")

        if cpa.file_complexity:
            lines.append("")
            lines.append("  High Complexity Files (by resolution time):")
            for i, cp in enumerate(cpa.file_complexity[:5], 1):
                score_label = (
                    "HIGH"
                    if cp.complexity_score >= 0.7
                    else "MEDIUM"
                    if cp.complexity_score >= 0.4
                    else "LOW"
                )
                lines.append(f"  {i}. {cp.path}")
                lines.append(
                    f"     Avg: {cp.avg_resolution_days:.1f} days ({cp.comparison_to_baseline})"
                )
                lines.append(
                    f"     Median: {cp.median_resolution_days:.1f} days, Issues: {cp.issue_count}"
                )
                lines.append(
                    f"     Slowest: {cp.slowest_issue[0]} ({cp.slowest_issue[1]:.1f} days)"
                )
                lines.append(f"     Complexity score: {cp.complexity_score:.2f} [{score_label}]")

        if cpa.directory_complexity:
            lines.append("")
            lines.append("  High Complexity Directories:")
            for cp in cpa.directory_complexity[:5]:
                lines.append(
                    f"    {cp.path}: avg {cp.avg_resolution_days:.1f} days ({cp.comparison_to_baseline})"
                )

        if cpa.complexity_outliers:
            lines.append("")
            lines.append("  Complexity Outliers (>2x baseline):")
            for path in cpa.complexity_outliers[:5]:
                lines.append(f"    - {path}")

    # Cross-cutting concern analysis
    if analysis.cross_cutting_analysis:
        cca = analysis.cross_cutting_analysis

        if cca.smells:
            lines.append("")
            lines.append("Cross-Cutting Concern Analysis")
            lines.append("-" * 30)

            for i, smell in enumerate(cca.smells[:5], 1):
                scatter_label = (
                    "HIGH"
                    if smell.scatter_score >= 0.6
                    else "MEDIUM"
                    if smell.scatter_score >= 0.3
                    else "LOW"
                )
                lines.append("")
                lines.append(f"  {i}. {smell.concern_type.title()} [{scatter_label} SCATTER]")
                dirs_str = ", ".join(smell.affected_directories[:3])
                if len(smell.affected_directories) > 3:
                    dirs_str += ", ..."
                lines.append(f"     Directories: {dirs_str}")
                issues_str = ", ".join(smell.issue_ids[:3])
                if len(smell.issue_ids) > 3:
                    issues_str += ", ..."
                lines.append(f"     Issues: {issues_str} ({smell.issue_count} total)")
                lines.append(f"     Scatter score: {smell.scatter_score:.2f}")
                lines.append(f"     Suggested pattern: {smell.suggested_pattern}")

            if cca.consolidation_opportunities:
                lines.append("")
                lines.append("  Consolidation Opportunities:")
                for opp in cca.consolidation_opportunities[:5]:
                    lines.append(f"    - {opp}")

    # Technical debt
    if analysis.debt_metrics:
        lines.append("")
        lines.append("Technical Debt")
        lines.append("-" * 14)
        debt = analysis.debt_metrics
        lines.append(f"  Backlog Size: {debt.backlog_size}")
        lines.append(f"  Growth Rate: {debt.backlog_growth_rate:+.1f} issues/week")
        lines.append(f"  High Priority Open (P0-P1): {debt.high_priority_open}")
        lines.append(f"  Aging >30 days: {debt.aging_30_plus}")

    # Comparison
    if analysis.comparison_period and analysis.current_period and analysis.previous_period:
        lines.append("")
        lines.append(f"Comparison ({analysis.comparison_period})")
        lines.append("-" * 20)
        curr = analysis.current_period
        prev = analysis.previous_period

        if prev.total_completed > 0:
            change = (curr.total_completed - prev.total_completed) / prev.total_completed * 100
            lines.append(
                f"  Completed: {prev.total_completed} -> {curr.total_completed} ({change:+.0f}%)"
            )
        else:
            lines.append(f"  Completed: {prev.total_completed} -> {curr.total_completed}")

    return "\n".join(lines)


def format_analysis_markdown(analysis: HistoryAnalysis) -> str:
    """Format analysis as Markdown report.

    Args:
        analysis: HistoryAnalysis to format

    Returns:
        Markdown string
    """
    lines: list[str] = []

    lines.append("# Issue History Analysis Report")
    lines.append("")
    lines.append(
        f"**Generated**: {analysis.generated_date} | "
        f"**Total Completed**: {analysis.total_completed} | "
        f"**Active Issues**: {analysis.total_active}"
    )

    if analysis.date_range_start and analysis.date_range_end:
        lines.append(f"**Date Range**: {analysis.date_range_start} to {analysis.date_range_end}")

    # Executive Summary
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Value | Trend |")
    lines.append("|--------|-------|-------|")

    velocity = f"{analysis.summary.velocity:.2f}/day" if analysis.summary.velocity else "N/A"
    velocity_symbol = {"increasing": "↑", "decreasing": "↓", "stable": "→"}.get(
        analysis.velocity_trend, ""
    )
    lines.append(f"| Velocity | {velocity} | {velocity_symbol} {analysis.velocity_trend} |")

    bug_count = analysis.summary.type_counts.get("BUG", 0)
    total = analysis.total_completed or 1
    bug_pct = bug_count * 100 // total
    bug_symbol = {"increasing": "↑ ⚠️", "decreasing": "↓ ✓", "stable": "→"}.get(
        analysis.bug_ratio_trend, ""
    )
    lines.append(f"| Bug Ratio | {bug_pct}% | {bug_symbol} |")

    if analysis.debt_metrics:
        growth = analysis.debt_metrics.backlog_growth_rate
        growth_status = "↓ ✓" if growth < 0 else ("→" if growth == 0 else "↑ ⚠️")
        lines.append(f"| Backlog Growth | {growth:+.1f}/week | {growth_status} |")

    # Type Distribution
    lines.append("")
    lines.append("## Type Distribution")
    lines.append("")
    lines.append("| Type | Count | Percentage |")
    lines.append("|------|-------|------------|")
    for issue_type, count in analysis.summary.type_counts.items():
        pct = count * 100 // total
        lines.append(f"| {issue_type} | {count} | {pct}% |")

    # Period Trends
    if analysis.period_metrics:
        lines.append("")
        lines.append("## Period Trends")
        lines.append("")
        lines.append("| Period | Completed | Bug % |")
        lines.append("|--------|-----------|-------|")
        for period in analysis.period_metrics[-8:]:  # Last 8
            bug_pct_str = f"{period.bug_ratio * 100:.0f}%" if period.bug_ratio else "N/A"
            lines.append(f"| {period.period_label} | {period.total_completed} | {bug_pct_str} |")

    # Subsystem Health
    if analysis.subsystem_health:
        lines.append("")
        lines.append("## Subsystem Health")
        lines.append("")
        lines.append("| Subsystem | Total | Recent (30d) | Trend |")
        lines.append("|-----------|-------|--------------|-------|")
        for sub in analysis.subsystem_health:
            trend_symbol = {"improving": "↓ ✓", "degrading": "↑ ⚠️", "stable": "→"}.get(
                sub.trend, ""
            )
            lines.append(
                f"| `{sub.subsystem}` | {sub.total_issues} | {sub.recent_issues} | {trend_symbol} |"
            )

    # Hotspot Analysis
    if analysis.hotspot_analysis:
        hotspots = analysis.hotspot_analysis

        if hotspots.file_hotspots:
            lines.append("")
            lines.append("## File Hotspots")
            lines.append("")
            lines.append("| File | Issues | Types | Churn |")
            lines.append("|------|--------|-------|-------|")
            for h in hotspots.file_hotspots:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                churn_badge = (
                    "🔥"
                    if h.churn_indicator == "high"
                    else ("⚡" if h.churn_indicator == "medium" else "")
                )
                lines.append(f"| `{h.path}` | {h.issue_count} | {types_str} | {churn_badge} |")

        if hotspots.directory_hotspots:
            lines.append("")
            lines.append("## Directory Hotspots")
            lines.append("")
            lines.append("| Directory | Issues | Types |")
            lines.append("|-----------|--------|-------|")
            for h in hotspots.directory_hotspots[:5]:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                lines.append(f"| `{h.path}` | {h.issue_count} | {types_str} |")

        if hotspots.bug_magnets:
            lines.append("")
            lines.append("## Bug Magnets")
            lines.append("")
            lines.append("Files with >60% bug ratio that may need refactoring attention:")
            lines.append("")
            lines.append("| File | Bug Ratio | Bugs/Total |")
            lines.append("|------|-----------|------------|")
            for h in hotspots.bug_magnets:
                lines.append(
                    f"| `{h.path}` | {h.bug_ratio * 100:.0f}% | "
                    f"{h.issue_types.get('BUG', 0)}/{h.issue_count} |"
                )

    # Coupling Analysis
    if analysis.coupling_analysis:
        coupling = analysis.coupling_analysis

        if coupling.pairs:
            lines.append("")
            lines.append("## Coupling Detection")
            lines.append("")
            lines.append("Files that frequently change together across issues:")
            lines.append("")
            lines.append("| File A | File B | Co-occurrences | Strength |")
            lines.append("|--------|--------|----------------|----------|")
            for p in coupling.pairs[:10]:
                strength_badge = (
                    "🔴"
                    if p.coupling_strength >= 0.7
                    else ("🟠" if p.coupling_strength >= 0.5 else "🟡")
                )
                lines.append(
                    f"| `{p.file_a}` | `{p.file_b}` | {p.co_occurrence_count} | "
                    f"{p.coupling_strength:.2f} {strength_badge} |"
                )

        if coupling.clusters:
            lines.append("")
            lines.append("### Coupling Clusters")
            lines.append("")
            lines.append("Groups of tightly coupled files (consider consolidating):")
            lines.append("")
            for i, cluster in enumerate(coupling.clusters[:5], 1):
                files_str = ", ".join(f"`{f}`" for f in cluster[:5])
                if len(cluster) > 5:
                    files_str += f" (+{len(cluster) - 5} more)"
                lines.append(f"{i}. {files_str}")

        if coupling.hotspots:
            lines.append("")
            lines.append("### Coupling Hotspots")
            lines.append("")
            lines.append("Files coupled with 3+ other files (potential abstraction candidates):")
            lines.append("")
            for f in coupling.hotspots[:5]:
                lines.append(f"- `{f}`")

    # Regression Clustering Analysis
    if analysis.regression_analysis:
        regression = analysis.regression_analysis

        if regression.clusters:
            lines.append("")
            lines.append("## Regression Clustering")
            lines.append("")
            lines.append(
                f"**Total regression chains detected**: {regression.total_regression_chains}"
            )
            lines.append("")
            lines.append("Files where fixes frequently lead to new bugs:")
            lines.append("")
            lines.append("| File | Regressions | Pattern | Severity |")
            lines.append("|------|-------------|---------|----------|")
            for c in regression.clusters:
                severity_badge = (
                    "🔴" if c.severity == "critical" else ("🟠" if c.severity == "high" else "🟡")
                )
                lines.append(
                    f"| `{c.primary_file}` | {c.regression_count} | "
                    f"{c.time_pattern} | {severity_badge} |"
                )

        if regression.most_fragile_files:
            lines.append("")
            lines.append("### Most Fragile Files")
            lines.append("")
            lines.append("Files requiring architectural attention:")
            lines.append("")
            for f in regression.most_fragile_files:
                lines.append(f"- `{f}`")

    # Test Gap Analysis
    if analysis.test_gap_analysis:
        tga = analysis.test_gap_analysis

        if tga.gaps:
            lines.append("")
            lines.append("## Test Gap Correlation")
            lines.append("")
            lines.append("Correlating bug occurrences with test coverage gaps:")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Files with tests | avg {tga.files_with_tests_avg_bugs:.1f} bugs |")
            lines.append(
                f"| Files without tests | avg {tga.files_without_tests_avg_bugs:.1f} bugs |"
            )
            lines.append("")

            # Critical gaps table
            critical_gaps = [g for g in tga.gaps if g.priority in ("critical", "high")]
            if critical_gaps:
                lines.append("### Critical Test Gaps")
                lines.append("")
                lines.append("Files with high bug counts but missing tests:")
                lines.append("")
                lines.append("| File | Bugs | Priority | Test Status | Action |")
                lines.append("|------|------|----------|-------------|--------|")
                for g in critical_gaps[:10]:
                    priority_badge = "🔴" if g.priority == "critical" else "🟠"
                    test_status = f"`{g.test_file_path}`" if g.has_test_file else "NONE"
                    action = "Review coverage" if g.has_test_file else "Create test file"
                    lines.append(
                        f"| `{g.source_file}` | {g.bug_count} | {priority_badge} | "
                        f"{test_status} | {action} |"
                    )

        if tga.priority_test_targets:
            lines.append("")
            lines.append("### Priority Test Targets")
            lines.append("")
            lines.append("Files recommended for new test creation (ordered by bug count):")
            lines.append("")
            for target in tga.priority_test_targets[:10]:
                lines.append(f"- `{target}`")

    # Rejection Analysis
    if analysis.rejection_analysis:
        rej = analysis.rejection_analysis
        overall = rej.overall

        if overall.total_closed > 0:
            lines.append("")
            lines.append("## Rejection Analysis")
            lines.append("")
            lines.append(
                f"**Overall rejection rate**: {overall.rejection_rate * 100:.1f}% "
                f"({overall.rejected_count}/{overall.total_closed})"
            )
            lines.append(
                f"**Invalid rate**: {overall.invalid_rate * 100:.1f}% "
                f"({overall.invalid_count}/{overall.total_closed})"
            )
            lines.append("")

            # By type table
            if rej.by_type:
                lines.append("### By Issue Type")
                lines.append("")
                lines.append("| Type | Rejected | Invalid | Total | Rate |")
                lines.append("|------|----------|---------|-------|------|")
                for issue_type in sorted(rej.by_type.keys()):
                    m = rej.by_type[issue_type]
                    rate = (m.rejection_rate + m.invalid_rate) * 100
                    lines.append(
                        f"| {issue_type} | {m.rejected_count} | {m.invalid_count} | "
                        f"{m.total_closed} | {rate:.1f}% |"
                    )
                lines.append("")

            # Trend
            if rej.by_month and len(rej.by_month) >= 2:
                lines.append("### Trend")
                lines.append("")
                sorted_months = sorted(rej.by_month.keys())[-6:]
                trend_parts = []
                for month in sorted_months:
                    m = rej.by_month[month]
                    rate = (m.rejection_rate + m.invalid_rate) * 100
                    trend_parts.append(f"{month}: {rate:.0f}%")
                lines.append(" → ".join(trend_parts))
                lines.append(f"*Trend: {rej.trend}*")
                lines.append("")

            # Common reasons
            if rej.common_reasons:
                lines.append("### Common Rejection Reasons")
                lines.append("")
                for reason, count in rej.common_reasons[:5]:
                    lines.append(f'- "{reason}" ({count})')

    # Manual Pattern Analysis
    if analysis.manual_pattern_analysis:
        mpa = analysis.manual_pattern_analysis

        if mpa.patterns:
            lines.append("")
            lines.append("## Manual Pattern Analysis")
            lines.append("")
            lines.append(
                f"**Total manual interventions detected**: {mpa.total_manual_interventions}"
            )
            lines.append(
                f"**Potentially automatable**: {mpa.automatable_percentage:.0f}% "
                f"({mpa.automatable_count}/{mpa.total_manual_interventions})"
            )
            lines.append("")
            lines.append("### Recurring Patterns")
            lines.append("")
            lines.append("| Pattern | Occurrences | Affected Issues | Suggestion | Complexity |")
            lines.append("|---------|-------------|-----------------|------------|------------|")

            for pattern in mpa.patterns[:10]:
                issues_str = ", ".join(pattern.affected_issues[:3])
                if len(pattern.affected_issues) > 3:
                    issues_str += "..."
                lines.append(
                    f"| {pattern.pattern_description} | {pattern.occurrence_count} | "
                    f"{issues_str} | {pattern.suggested_automation} | "
                    f"{pattern.automation_complexity} |"
                )

            if mpa.automation_suggestions:
                lines.append("")
                lines.append("### Automation Suggestions")
                lines.append("")
                lines.append("Based on detected patterns, consider implementing:")
                lines.append("")
                for suggestion in mpa.automation_suggestions[:5]:
                    lines.append(f"- {suggestion}")

    # Configuration Gaps Analysis
    if analysis.config_gaps_analysis:
        cga = analysis.config_gaps_analysis

        lines.append("")
        lines.append("## Configuration Gaps Analysis")
        lines.append("")
        lines.append(f"**Coverage score**: {cga.coverage_score * 100:.0f}%")
        lines.append("")
        lines.append("### Current Configuration")
        lines.append("")
        lines.append(f"- **Hooks**: {', '.join(cga.current_hooks) or 'none'}")
        lines.append(f"- **Skills**: {len(cga.current_skills)}")
        lines.append(f"- **Agents**: {len(cga.current_agents)}")

        if cga.gaps:
            lines.append("")
            lines.append("### Identified Gaps")
            lines.append("")
            lines.append("| Priority | Type | Description | Evidence |")
            lines.append("|----------|------|-------------|----------|")

            for gap in cga.gaps[:10]:
                issues_str = ", ".join(gap.evidence[:3])
                if len(gap.evidence) > 3:
                    issues_str += "..."
                lines.append(
                    f"| {gap.priority} | {gap.gap_type} | {gap.description} | {issues_str} |"
                )

            lines.append("")
            lines.append("### Suggested Configurations")
            lines.append("")
            for i, gap in enumerate(cga.gaps[:5], 1):
                if gap.suggested_config:
                    lines.append(f"**{i}. {gap.description}**")
                    lines.append("")
                    lines.append("```json")
                    lines.append(gap.suggested_config)
                    lines.append("```")
                    lines.append("")

    # Agent Effectiveness Analysis
    if analysis.agent_effectiveness_analysis:
        aea = analysis.agent_effectiveness_analysis

        if aea.outcomes:
            lines.append("")
            lines.append("## Agent Effectiveness Analysis")
            lines.append("")
            lines.append("| Agent | Type | Success Rate | Completed | Rejected | Failed |")
            lines.append("|-------|------|--------------|-----------|----------|--------|")

            for outcome in sorted(aea.outcomes, key=lambda o: (o.agent_name, o.issue_type)):
                rate_pct = outcome.success_rate * 100
                flag = " ⚠️" if outcome.total_count >= 5 and rate_pct < 50 else ""
                lines.append(
                    f"| {outcome.agent_name} | {outcome.issue_type} | "
                    f"{rate_pct:.1f}%{flag} | {outcome.success_count} | "
                    f"{outcome.rejection_count} | {outcome.failure_count} |"
                )

            # Recommendations
            if aea.best_agent_by_type or aea.problematic_combinations:
                lines.append("")
                lines.append("### Recommendations")
                lines.append("")
                for issue_type, best_agent in sorted(aea.best_agent_by_type.items()):
                    lines.append(f"- **{issue_type}**: Best handled by `{best_agent}`")
                for agent, issue_type, reason in aea.problematic_combinations[:3]:
                    lines.append(f"- **{agent}** underperforms for {issue_type} ({reason})")

    # Technical Debt
    if analysis.debt_metrics:
        lines.append("")
        lines.append("## Technical Debt Health")
        lines.append("")
        debt = analysis.debt_metrics
        lines.append("| Metric | Value | Assessment |")
        lines.append("|--------|-------|------------|")

        backlog_status = (
            "✓ Low"
            if debt.backlog_size < 20
            else ("⚠️ High" if debt.backlog_size > 50 else "Moderate")
        )
        lines.append(f"| Backlog Size | {debt.backlog_size} | {backlog_status} |")

        growth_status = (
            "✓ Shrinking"
            if debt.backlog_growth_rate < 0
            else ("⚠️ Growing" if debt.backlog_growth_rate > 2 else "Stable")
        )
        lines.append(f"| Growth Rate | {debt.backlog_growth_rate:+.1f}/week | {growth_status} |")

        hp_status = "✓ Good" if debt.high_priority_open < 3 else "⚠️ Attention needed"
        lines.append(f"| High Priority Open | {debt.high_priority_open} | {hp_status} |")

        aging_status = (
            "✓ Healthy"
            if debt.aging_30_plus < 5
            else ("⚠️ Review needed" if debt.aging_30_plus > 10 else "Moderate")
        )
        lines.append(f"| Aging >30 days | {debt.aging_30_plus} | {aging_status} |")

    # Comparison
    if analysis.comparison_period and analysis.current_period and analysis.previous_period:
        lines.append("")
        lines.append(f"## Comparative Analysis (Last {analysis.comparison_period})")
        lines.append("")
        curr = analysis.current_period
        prev = analysis.previous_period

        lines.append("| Metric | Previous | Current | Change |")
        lines.append("|--------|----------|---------|--------|")

        if prev.total_completed > 0:
            change = (curr.total_completed - prev.total_completed) / prev.total_completed * 100
            change_str = f"{change:+.0f}%"
        else:
            change_str = "N/A"
        lines.append(
            f"| Completed | {prev.total_completed} | {curr.total_completed} | {change_str} |"
        )

        prev_bugs = prev.type_counts.get("BUG", 0)
        curr_bugs = curr.type_counts.get("BUG", 0)
        if prev_bugs > 0:
            bug_change = (curr_bugs - prev_bugs) / prev_bugs * 100
            bug_change_str = f"{bug_change:+.0f}%"
            if bug_change < 0:
                bug_change_str += " ✓"
        else:
            bug_change_str = "N/A"
        lines.append(f"| Bugs Fixed | {prev_bugs} | {curr_bugs} | {bug_change_str} |")

    return "\n".join(lines)
