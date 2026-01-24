"""Issue history analysis and summary statistics.

Provides analysis of completed issues including:
- Type distribution (BUG, ENH, FEAT)
- Priority distribution (P0-P5)
- Discovery source breakdown
- Completion velocity metrics
- Trend analysis over time periods
- Subsystem health tracking
- Technical debt metrics
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

__all__ = [
    # Core dataclasses
    "CompletedIssue",
    "HistorySummary",
    # Advanced analysis dataclasses
    "PeriodMetrics",
    "SubsystemHealth",
    "Hotspot",
    "HotspotAnalysis",
    "RegressionCluster",
    "RegressionAnalysis",
    "TestGap",
    "TestGapAnalysis",
    "RejectionMetrics",
    "RejectionAnalysis",
    "ManualPattern",
    "ManualPatternAnalysis",
    "TechnicalDebtMetrics",
    "HistoryAnalysis",
    # Parsing and scanning
    "parse_completed_issue",
    "scan_completed_issues",
    "scan_active_issues",
    # Summary functions
    "calculate_summary",
    "calculate_analysis",
    "analyze_hotspots",
    "analyze_regression_clustering",
    "analyze_test_gaps",
    "analyze_rejection_rates",
    "detect_manual_patterns",
    # Formatting functions
    "format_summary_text",
    "format_summary_json",
    "format_analysis_text",
    "format_analysis_json",
    "format_analysis_markdown",
    "format_analysis_yaml",
]


@dataclass
class CompletedIssue:
    """Parsed information from a completed issue file."""

    path: Path
    issue_type: str  # BUG, ENH, FEAT
    priority: str  # P0-P5
    issue_id: str  # e.g., BUG-001
    discovered_by: str | None = None
    completed_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "issue_type": self.issue_type,
            "priority": self.priority,
            "issue_id": self.issue_id,
            "discovered_by": self.discovered_by,
            "completed_date": (
                self.completed_date.isoformat() if self.completed_date else None
            ),
        }


@dataclass
class HistorySummary:
    """Summary statistics for completed issues."""

    total_count: int
    type_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)
    discovery_counts: dict[str, int] = field(default_factory=dict)
    earliest_date: date | None = None
    latest_date: date | None = None

    @property
    def date_range_days(self) -> int | None:
        """Calculate days between earliest and latest completion."""
        if self.earliest_date and self.latest_date:
            return (self.latest_date - self.earliest_date).days + 1
        return None

    @property
    def velocity(self) -> float | None:
        """Calculate issues per day."""
        if self.date_range_days and self.date_range_days > 0:
            return self.total_count / self.date_range_days
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_count": self.total_count,
            "type_counts": self.type_counts,
            "priority_counts": self.priority_counts,
            "discovery_counts": self.discovery_counts,
            "earliest_date": (
                self.earliest_date.isoformat() if self.earliest_date else None
            ),
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "date_range_days": self.date_range_days,
            "velocity": round(self.velocity, 2) if self.velocity else None,
        }


# =============================================================================
# Advanced Analysis Dataclasses (FEAT-110)
# =============================================================================


@dataclass
class PeriodMetrics:
    """Metrics for a specific time period."""

    period_start: date
    period_end: date
    period_label: str  # e.g., "Q1 2025", "Jan 2025", "Week 3"
    total_completed: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)
    avg_completion_days: float | None = None

    @property
    def bug_ratio(self) -> float | None:
        """Calculate bug percentage."""
        if self.total_completed == 0:
            return None
        bug_count = self.type_counts.get("BUG", 0)
        return bug_count / self.total_completed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            "total_completed": self.total_completed,
            "type_counts": self.type_counts,
            "priority_counts": self.priority_counts,
            "bug_ratio": round(self.bug_ratio, 3) if self.bug_ratio is not None else None,
            "avg_completion_days": (
                round(self.avg_completion_days, 1) if self.avg_completion_days else None
            ),
        }


@dataclass
class SubsystemHealth:
    """Health metrics for a subsystem (directory)."""

    subsystem: str  # Directory path
    total_issues: int = 0
    recent_issues: int = 0  # Issues in last 30 days
    issue_ids: list[str] = field(default_factory=list)
    trend: str = "stable"  # "improving", "stable", "degrading"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "subsystem": self.subsystem,
            "total_issues": self.total_issues,
            "recent_issues": self.recent_issues,
            "issue_ids": self.issue_ids[:5],  # Top 5
            "trend": self.trend,
        }


@dataclass
class Hotspot:
    """A file or directory that appears in multiple issues."""

    path: str
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    issue_types: dict[str, int] = field(default_factory=dict)  # {"BUG": 5, "ENH": 3}
    bug_ratio: float = 0.0  # bugs / total issues
    churn_indicator: str = "low"  # "high", "medium", "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "issue_count": self.issue_count,
            "issue_ids": self.issue_ids[:10],  # Top 10
            "issue_types": self.issue_types,
            "bug_ratio": round(self.bug_ratio, 3),
            "churn_indicator": self.churn_indicator,
        }


@dataclass
class HotspotAnalysis:
    """Analysis of files and directories appearing repeatedly in issues."""

    file_hotspots: list[Hotspot] = field(default_factory=list)
    directory_hotspots: list[Hotspot] = field(default_factory=list)
    bug_magnets: list[Hotspot] = field(default_factory=list)  # >60% bug ratio

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_hotspots": [h.to_dict() for h in self.file_hotspots],
            "directory_hotspots": [h.to_dict() for h in self.directory_hotspots],
            "bug_magnets": [h.to_dict() for h in self.bug_magnets],
        }


@dataclass
class RegressionCluster:
    """A cluster of bugs where fixes led to new bugs."""

    primary_file: str  # Main file in the regression chain
    regression_count: int = 0  # Number of regression pairs
    fix_bug_pairs: list[tuple[str, str]] = field(default_factory=list)  # (fixed_id, caused_id)
    related_files: list[str] = field(default_factory=list)  # All files in chain
    time_pattern: str = "immediate"  # "immediate" (<3d), "delayed" (3-7d), "chronic" (recurring)
    severity: str = "medium"  # "critical", "high", "medium"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary_file": self.primary_file,
            "regression_count": self.regression_count,
            "fix_bug_pairs": self.fix_bug_pairs[:10],  # Top 10
            "related_files": self.related_files[:10],  # Top 10
            "time_pattern": self.time_pattern,
            "severity": self.severity,
        }


@dataclass
class RegressionAnalysis:
    """Analysis of regression patterns in bug fixes."""

    clusters: list[RegressionCluster] = field(default_factory=list)
    total_regression_chains: int = 0
    most_fragile_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "clusters": [c.to_dict() for c in self.clusters],
            "total_regression_chains": self.total_regression_chains,
            "most_fragile_files": self.most_fragile_files[:5],  # Top 5
        }


@dataclass
class TestGap:
    """A source file with bugs but missing or weak test coverage."""

    source_file: str
    bug_count: int = 0
    bug_ids: list[str] = field(default_factory=list)
    has_test_file: bool = False
    test_file_path: str | None = None
    gap_score: float = 0.0  # bug_count * multiplier, higher = worse
    priority: str = "low"  # "critical", "high", "medium", "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_file": self.source_file,
            "bug_count": self.bug_count,
            "bug_ids": self.bug_ids[:10],  # Top 10
            "has_test_file": self.has_test_file,
            "test_file_path": self.test_file_path,
            "gap_score": round(self.gap_score, 2),
            "priority": self.priority,
        }


@dataclass
class TestGapAnalysis:
    """Analysis of test coverage gaps correlated with bug occurrences."""

    gaps: list[TestGap] = field(default_factory=list)
    untested_bug_magnets: list[str] = field(default_factory=list)
    files_with_tests_avg_bugs: float = 0.0
    files_without_tests_avg_bugs: float = 0.0
    priority_test_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "untested_bug_magnets": self.untested_bug_magnets[:5],
            "files_with_tests_avg_bugs": round(self.files_with_tests_avg_bugs, 2),
            "files_without_tests_avg_bugs": round(self.files_without_tests_avg_bugs, 2),
            "priority_test_targets": self.priority_test_targets[:10],
        }


@dataclass
class RejectionMetrics:
    """Metrics for rejection and invalid closure tracking."""

    total_closed: int = 0
    rejected_count: int = 0
    invalid_count: int = 0
    duplicate_count: int = 0
    deferred_count: int = 0
    completed_count: int = 0

    @property
    def rejection_rate(self) -> float:
        """Calculate rejection rate."""
        if self.total_closed == 0:
            return 0.0
        return self.rejected_count / self.total_closed

    @property
    def invalid_rate(self) -> float:
        """Calculate invalid rate."""
        if self.total_closed == 0:
            return 0.0
        return self.invalid_count / self.total_closed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_closed": self.total_closed,
            "rejected_count": self.rejected_count,
            "invalid_count": self.invalid_count,
            "duplicate_count": self.duplicate_count,
            "deferred_count": self.deferred_count,
            "completed_count": self.completed_count,
            "rejection_rate": round(self.rejection_rate, 3),
            "invalid_rate": round(self.invalid_rate, 3),
        }


@dataclass
class RejectionAnalysis:
    """Analysis of rejection and invalid closure patterns."""

    overall: RejectionMetrics = field(default_factory=RejectionMetrics)
    by_type: dict[str, RejectionMetrics] = field(default_factory=dict)
    by_month: dict[str, RejectionMetrics] = field(default_factory=dict)
    common_reasons: list[tuple[str, int]] = field(default_factory=list)
    trend: str = "stable"  # "improving", "stable", "degrading"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall": self.overall.to_dict(),
            "by_type": {k: v.to_dict() for k, v in self.by_type.items()},
            "by_month": {k: v.to_dict() for k, v in sorted(self.by_month.items())},
            "common_reasons": self.common_reasons[:10],
            "trend": self.trend,
        }


@dataclass
class ManualPattern:
    """A recurring manual activity detected across issues."""

    pattern_type: str  # "test", "lint", "build", "git", "verification"
    pattern_description: str
    occurrence_count: int = 0
    affected_issues: list[str] = field(default_factory=list)  # issue IDs
    example_commands: list[str] = field(default_factory=list)  # sample commands found
    suggested_automation: str = ""  # hook, skill, or agent suggestion
    automation_complexity: str = "simple"  # "trivial", "simple", "moderate"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pattern_type": self.pattern_type,
            "pattern_description": self.pattern_description,
            "occurrence_count": self.occurrence_count,
            "affected_issues": self.affected_issues[:10],
            "example_commands": self.example_commands[:5],
            "suggested_automation": self.suggested_automation,
            "automation_complexity": self.automation_complexity,
        }


@dataclass
class ManualPatternAnalysis:
    """Analysis of recurring manual activities that could be automated."""

    patterns: list[ManualPattern] = field(default_factory=list)
    total_manual_interventions: int = 0
    automatable_count: int = 0
    automation_suggestions: list[str] = field(default_factory=list)

    @property
    def automatable_percentage(self) -> float:
        """Calculate percentage of patterns that are automatable."""
        if self.total_manual_interventions == 0:
            return 0.0
        return self.automatable_count / self.total_manual_interventions * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "total_manual_interventions": self.total_manual_interventions,
            "automatable_count": self.automatable_count,
            "automatable_percentage": round(self.automatable_percentage, 1),
            "automation_suggestions": self.automation_suggestions[:10],
        }


@dataclass
class TechnicalDebtMetrics:
    """Technical debt health indicators."""

    backlog_size: int = 0  # Total open issues
    backlog_growth_rate: float = 0.0  # Net issues/week
    aging_30_plus: int = 0  # Issues > 30 days old
    aging_60_plus: int = 0  # Issues > 60 days old
    high_priority_open: int = 0  # P0-P1 open
    debt_paydown_ratio: float = 0.0  # maintenance vs features

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "backlog_size": self.backlog_size,
            "backlog_growth_rate": round(self.backlog_growth_rate, 2),
            "aging_30_plus": self.aging_30_plus,
            "aging_60_plus": self.aging_60_plus,
            "high_priority_open": self.high_priority_open,
            "debt_paydown_ratio": round(self.debt_paydown_ratio, 2),
        }


@dataclass
class HistoryAnalysis:
    """Complete history analysis report."""

    generated_date: date
    total_completed: int
    total_active: int
    date_range_start: date | None
    date_range_end: date | None

    # Core summary (from existing HistorySummary)
    summary: HistorySummary

    # Trend analysis
    period_metrics: list[PeriodMetrics] = field(default_factory=list)
    velocity_trend: str = "stable"  # "increasing", "stable", "decreasing"
    bug_ratio_trend: str = "stable"

    # Subsystem health
    subsystem_health: list[SubsystemHealth] = field(default_factory=list)

    # Hotspot analysis
    hotspot_analysis: HotspotAnalysis | None = None

    # Regression clustering analysis
    regression_analysis: RegressionAnalysis | None = None

    # Test gap analysis
    test_gap_analysis: TestGapAnalysis | None = None

    # Rejection analysis
    rejection_analysis: RejectionAnalysis | None = None

    # Manual pattern analysis
    manual_pattern_analysis: ManualPatternAnalysis | None = None

    # Technical debt
    debt_metrics: TechnicalDebtMetrics | None = None

    # Comparative analysis (optional)
    comparison_period: str | None = None  # e.g., "30d"
    previous_period: PeriodMetrics | None = None
    current_period: PeriodMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "generated_date": self.generated_date.isoformat(),
            "total_completed": self.total_completed,
            "total_active": self.total_active,
            "date_range_start": (
                self.date_range_start.isoformat() if self.date_range_start else None
            ),
            "date_range_end": (
                self.date_range_end.isoformat() if self.date_range_end else None
            ),
            "summary": self.summary.to_dict(),
            "period_metrics": [p.to_dict() for p in self.period_metrics],
            "velocity_trend": self.velocity_trend,
            "bug_ratio_trend": self.bug_ratio_trend,
            "subsystem_health": [s.to_dict() for s in self.subsystem_health],
            "hotspot_analysis": (
                self.hotspot_analysis.to_dict() if self.hotspot_analysis else None
            ),
            "regression_analysis": (
                self.regression_analysis.to_dict() if self.regression_analysis else None
            ),
            "test_gap_analysis": (
                self.test_gap_analysis.to_dict() if self.test_gap_analysis else None
            ),
            "rejection_analysis": (
                self.rejection_analysis.to_dict() if self.rejection_analysis else None
            ),
            "manual_pattern_analysis": (
                self.manual_pattern_analysis.to_dict()
                if self.manual_pattern_analysis
                else None
            ),
            "debt_metrics": self.debt_metrics.to_dict() if self.debt_metrics else None,
            "comparison_period": self.comparison_period,
            "previous_period": (
                self.previous_period.to_dict() if self.previous_period else None
            ),
            "current_period": (
                self.current_period.to_dict() if self.current_period else None
            ),
        }


# =============================================================================
# Parsing Functions
# =============================================================================


def parse_completed_issue(file_path: Path) -> CompletedIssue:
    """Parse a completed issue file.

    Args:
        file_path: Path to the issue markdown file

    Returns:
        CompletedIssue with parsed metadata
    """
    filename = file_path.name
    content = file_path.read_text(encoding="utf-8")

    # Extract from filename: P[0-5]-[TYPE]-[NNN]-description.md
    issue_type = "UNKNOWN"
    priority = "P5"
    issue_id = "UNKNOWN"

    # Match priority
    priority_match = re.match(r"^(P\d)", filename)
    if priority_match:
        priority = priority_match.group(1)

    # Match type and ID
    type_match = re.search(r"(BUG|ENH|FEAT)-(\d+)", filename)
    if type_match:
        issue_type = type_match.group(1)
        issue_id = f"{type_match.group(1)}-{type_match.group(2)}"

    # Parse frontmatter for discovered_by
    discovered_by = _parse_discovered_by(content)

    # Parse completion date from Resolution section or file mtime
    completed_date = _parse_completion_date(content, file_path)

    return CompletedIssue(
        path=file_path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        discovered_by=discovered_by,
        completed_date=completed_date,
    )


def _parse_discovered_by(content: str) -> str | None:
    """Extract discovered_by from YAML frontmatter.

    Args:
        content: File content

    Returns:
        discovered_by value or None
    """
    if not content.startswith("---"):
        return None

    # Find closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return None

    frontmatter = content[4 : 3 + end_match.start()]

    for line in frontmatter.split("\n"):
        if line.strip().startswith("discovered_by:"):
            value = line.split(":", 1)[1].strip()
            if value.lower() in ("null", "~", ""):
                return None
            return value

    return None


def _parse_completion_date(content: str, file_path: Path) -> date | None:
    """Extract completion date from Resolution section or file mtime.

    Args:
        content: File content
        file_path: Path for mtime fallback

    Returns:
        Completion date or None
    """
    # Try Resolution section: **Completed**: YYYY-MM-DD
    match = re.search(r"\*\*Completed\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    # Fallback to file mtime
    try:
        mtime = file_path.stat().st_mtime
        return date.fromtimestamp(mtime)
    except OSError:
        return None


def _parse_resolution_action(content: str) -> str:
    """Extract resolution action category from issue content.

    Categorizes based on Resolution section fields:
    - "completed": Normal completion with **Action**: fix/implement
    - "rejected": Explicitly rejected (out of scope, not valid)
    - "invalid": Invalid reference or spec
    - "duplicate": Duplicate of existing issue
    - "deferred": Deferred to future work

    Args:
        content: Issue file content

    Returns:
        Resolution category string
    """
    # Look for Status field patterns
    status_match = re.search(r"\*\*Status\*\*:\s*(.+?)(?:\n|$)", content)
    if status_match:
        status = status_match.group(1).strip().lower()
        if "closed" in status:
            # Check Reason field for specific category
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip().lower()
                if "duplicate" in reason:
                    return "duplicate"
                if "invalid" in reason:
                    return "invalid"
                if "deferred" in reason:
                    return "deferred"
                if "rejected" in reason or "out of scope" in reason:
                    return "rejected"
            # Generic closed without specific reason
            return "rejected"

    # Check for Action field (normal completion)
    action_match = re.search(r"\*\*Action\*\*:\s*(.+?)(?:\n|$)", content)
    if action_match:
        return "completed"

    # Default to completed if no resolution section
    return "completed"


def scan_completed_issues(completed_dir: Path) -> list[CompletedIssue]:
    """Scan completed directory for issue files.

    Args:
        completed_dir: Path to .issues/completed/

    Returns:
        List of parsed CompletedIssue objects
    """
    issues: list[CompletedIssue] = []

    if not completed_dir.exists():
        return issues

    for file_path in sorted(completed_dir.glob("*.md")):
        try:
            issue = parse_completed_issue(file_path)
            issues.append(issue)
        except Exception:
            # Skip unparseable files
            continue

    return issues


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
    discovery_counts = dict(
        sorted(discovery_counts.items(), key=lambda x: (-x[1], x[0]))
    )

    return HistorySummary(
        total_count=len(issues),
        type_counts=type_counts,
        priority_counts=priority_counts,
        discovery_counts=discovery_counts,
        earliest_date=min(dates) if dates else None,
        latest_date=max(dates) if dates else None,
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
        lines.append(
            f"Date Range: {summary.earliest_date} to {summary.latest_date} ({days} days)"
        )
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


# =============================================================================
# Advanced Analysis Functions (FEAT-110)
# =============================================================================


def _parse_discovered_date(content: str) -> date | None:
    """Extract discovered_date from YAML frontmatter.

    Args:
        content: File content

    Returns:
        discovered_date value or None
    """
    if not content.startswith("---"):
        return None

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return None

    frontmatter = content[4 : 3 + end_match.start()]

    for line in frontmatter.split("\n"):
        if line.strip().startswith("discovered_date:"):
            value = line.split(":", 1)[1].strip()
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None

    return None


def _extract_subsystem(content: str) -> str | None:
    """Extract primary subsystem/directory from issue content.

    Args:
        content: Issue file content

    Returns:
        Directory path (e.g., "scripts/little_loops/") or None
    """
    # Look for file paths in Location or common patterns
    patterns = [
        r"\*\*File\*\*:\s*`?([^`\n]+/)[^/`\n]+`?",  # **File**: path/to/file.py
        r"`([a-zA-Z_][\w/.-]+/)[^/`]+\.py`",  # `path/to/file.py`
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1)

    return None


def _extract_paths_from_issue(content: str) -> list[str]:
    """Extract all file paths from issue content.

    Args:
        content: Issue file content

    Returns:
        List of file paths found in content
    """
    patterns = [
        r"\*\*File\*\*:\s*`?([^`\n:]+)`?",  # **File**: path/to/file.py
        r"`([a-zA-Z_][\w/.-]+\.[a-z]{2,4})`",  # `path/to/file.py`
        r"(?:^|\s)([a-zA-Z_][\w/.-]+\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",  # path.py:123
    ]

    paths: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            path = match.group(1).strip()
            # Must look like a file path
            if "/" in path or path.endswith(
                (".py", ".md", ".js", ".ts", ".json", ".yaml", ".yml")
            ):
                # Normalize: remove line numbers (path.py:123 -> path.py)
                if ":" in path and path.split(":")[-1].isdigit():
                    path = ":".join(path.split(":")[:-1])
                paths.add(path)

    return sorted(paths)


def _find_test_file(source_path: str) -> str | None:
    """Find corresponding test file for a source file.

    Checks common test file naming patterns:
    - tests/test_<name>.py
    - tests/<path>/test_<name>.py
    - <path>/test_<name>.py
    - <path>/<name>_test.py
    - <path>/tests/test_<name>.py

    Args:
        source_path: Path to source file (e.g., "src/core/processor.py")

    Returns:
        Path to test file if found, None otherwise
    """
    if not source_path.endswith(".py"):
        return None  # Only check Python files for now

    path = Path(source_path)
    stem = path.stem  # filename without extension
    parent = str(path.parent) if path.parent != Path(".") else ""

    # Generate candidate test file paths
    candidates: list[str] = [
        f"tests/test_{stem}.py",
        f"{parent}/test_{stem}.py" if parent else f"test_{stem}.py",
        f"{parent}/{stem}_test.py" if parent else f"{stem}_test.py",
        f"{parent}/tests/test_{stem}.py" if parent else f"tests/test_{stem}.py",
    ]

    # Add path-aware test locations
    if parent:
        candidates.append(f"tests/{parent}/test_{stem}.py")

    # Project-specific pattern for little-loops
    # e.g., scripts/little_loops/foo.py -> scripts/tests/test_foo.py
    if source_path.startswith("scripts/little_loops/"):
        candidates.append(f"scripts/tests/test_{stem}.py")

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    return None


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
) -> list[SubsystemHealth]:
    """Analyze health by subsystem/directory.

    Args:
        issues: List of completed issues
        recent_days: Days to consider "recent"

    Returns:
        List of SubsystemHealth sorted by total issues descending
    """
    subsystems: dict[str, SubsystemHealth] = {}
    cutoff = date.today() - timedelta(days=recent_days)

    for issue in issues:
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


def analyze_hotspots(issues: list[CompletedIssue]) -> HotspotAnalysis:
    """Identify files and directories that appear repeatedly in issues.

    Args:
        issues: List of completed issues

    Returns:
        HotspotAnalysis with file and directory hotspots
    """
    file_data: dict[str, dict[str, Any]] = {}  # path -> {count, ids, types}
    dir_data: dict[str, dict[str, Any]] = {}  # dir -> {count, ids, types}

    for issue in issues:
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


def analyze_regression_clustering(
    issues: list[CompletedIssue],
) -> RegressionAnalysis:
    """Detect files where bug fixes frequently lead to new bugs.

    Uses heuristics:
    1. Temporal proximity: Bug B completed within 7 days of Bug A
    2. File overlap: Both bugs affect same file(s)

    Args:
        issues: List of completed issues

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
    avg_with_tests = (
        sum(files_with_tests) / len(files_with_tests) if files_with_tests else 0.0
    )
    avg_without_tests = (
        sum(files_without_tests) / len(files_without_tests)
        if files_without_tests
        else 0.0
    )

    # Identify untested bug magnets (from hotspot analysis)
    untested_magnets = [
        h.path for h in hotspots.bug_magnets if _find_test_file(h.path) is None
    ]

    # Priority test targets: untested files sorted by bug count
    priority_targets = [g.source_file for g in gaps if not g.has_test_file]

    return TestGapAnalysis(
        gaps=gaps[:15],  # Top 15
        untested_bug_magnets=untested_magnets,
        files_with_tests_avg_bugs=avg_with_tests,
        files_without_tests_avg_bugs=avg_without_tests,
        priority_test_targets=priority_targets[:10],
    )


def analyze_rejection_rates(issues: list[CompletedIssue]) -> RejectionAnalysis:
    """Analyze rejection and invalid closure patterns.

    Args:
        issues: List of completed issues

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


def detect_manual_patterns(issues: list[CompletedIssue]) -> ManualPatternAnalysis:
    """Detect recurring manual activities that could be automated.

    Args:
        issues: List of completed issues

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


def scan_active_issues(issues_dir: Path) -> list[tuple[Path, str, str, date | None]]:
    """Scan active issue directories.

    Args:
        issues_dir: Path to .issues/ directory

    Returns:
        List of (path, issue_type, priority, discovered_date) tuples
    """
    results: list[tuple[Path, str, str, date | None]] = []

    for category_dir in ["bugs", "features", "enhancements"]:
        category_path = issues_dir / category_dir
        if not category_path.exists():
            continue

        for file_path in category_path.glob("*.md"):
            filename = file_path.name

            # Extract priority
            priority = "P5"
            priority_match = re.match(r"^(P\d)", filename)
            if priority_match:
                priority = priority_match.group(1)

            # Extract type
            issue_type = "UNKNOWN"
            type_match = re.search(r"(BUG|ENH|FEAT)", filename)
            if type_match:
                issue_type = type_match.group(1)

            # Extract discovered date from content
            discovered_date = None
            try:
                content = file_path.read_text(encoding="utf-8")
                discovered_date = _parse_discovered_date(content)
            except Exception:
                pass

            results.append((file_path, issue_type, priority, discovered_date))

    return results


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
        1
        for i in completed_issues
        if i.completed_date and i.completed_date >= four_weeks_ago
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
) -> HistoryAnalysis:
    """Calculate comprehensive history analysis.

    Args:
        completed_issues: List of completed issues
        issues_dir: Path to .issues/ for active issue scanning
        period_type: Grouping period for trend analysis
        compare_days: Days for comparative analysis (e.g., 30 for 30d comparison)

    Returns:
        HistoryAnalysis with all metrics
    """
    today = date.today()

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
    subsystem_health = _analyze_subsystems(completed_issues)

    # Hotspot analysis
    hotspot_analysis = analyze_hotspots(completed_issues)

    # Regression clustering analysis
    regression_analysis = analyze_regression_clustering(completed_issues)

    # Test gap analysis
    test_gap_analysis = analyze_test_gaps(completed_issues, hotspot_analysis)

    # Rejection rate analysis
    rejection_analysis = analyze_rejection_rates(completed_issues)

    # Manual pattern analysis
    manual_pattern_analysis = detect_manual_patterns(completed_issues)

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
        regression_analysis=regression_analysis,
        test_gap_analysis=test_gap_analysis,
        rejection_analysis=rejection_analysis,
        manual_pattern_analysis=manual_pattern_analysis,
        debt_metrics=debt_metrics,
    )

    # Comparative analysis
    if compare_days:
        analysis.comparison_period = f"{compare_days}d"
        cutoff = today - timedelta(days=compare_days)
        prev_cutoff = cutoff - timedelta(days=compare_days)

        current_issues = [
            i
            for i in completed_issues
            if i.completed_date and i.completed_date >= cutoff
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


# =============================================================================
# Analysis Formatting Functions (FEAT-110)
# =============================================================================


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
            trend_symbol = {"improving": "↓", "degrading": "↑", "stable": "→"}.get(
                sub.trend, "?"
            )
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
                types_str = ", ".join(
                    f"{k}:{v}" for k, v in sorted(h.issue_types.items())
                )
                churn_flag = " [HIGH CHURN]" if h.churn_indicator == "high" else ""
                lines.append(
                    f"  {h.path:40}: {h.issue_count:2} issues ({types_str}){churn_flag}"
                )

        if hotspots.bug_magnets:
            lines.append("")
            lines.append("Bug Magnets (>60% bugs)")
            lines.append("-" * 23)
            for h in hotspots.bug_magnets:
                lines.append(
                    f"  {h.path}: {h.bug_ratio * 100:.0f}% bugs "
                    f"({h.issue_types.get('BUG', 0)}/{h.issue_count})"
                )

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
            lines.append(
                f"  Files without tests: avg {tga.files_without_tests_avg_bugs:.1f} bugs"
            )
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
            lines.append(
                f"  Total manual interventions: {mpa.total_manual_interventions}"
            )
            lines.append(
                f"  Potentially automatable: {mpa.automatable_percentage:.0f}% "
                f"({mpa.automatable_count}/{mpa.total_manual_interventions})"
            )
            lines.append("")
            lines.append("  Recurring Patterns:")

            for i, pattern in enumerate(mpa.patterns[:5], 1):
                lines.append("")
                lines.append(
                    f"  {i}. {pattern.pattern_description} "
                    f"({pattern.occurrence_count} occurrences)"
                )
                issues_str = ", ".join(pattern.affected_issues[:3])
                if len(pattern.affected_issues) > 3:
                    issues_str += ", ..."
                lines.append(f"     Issues: {issues_str}")
                lines.append(f"     Suggestion: {pattern.suggested_automation}")
                lines.append(f"     Complexity: {pattern.automation_complexity}")

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
            change = (
                (curr.total_completed - prev.total_completed) / prev.total_completed * 100
            )
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
        lines.append(
            f"**Date Range**: {analysis.date_range_start} to {analysis.date_range_end}"
        )

    # Executive Summary
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Value | Trend |")
    lines.append("|--------|-------|-------|")

    velocity = (
        f"{analysis.summary.velocity:.2f}/day" if analysis.summary.velocity else "N/A"
    )
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
            lines.append(
                f"| {period.period_label} | {period.total_completed} | {bug_pct_str} |"
            )

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
                types_str = ", ".join(
                    f"{k}:{v}" for k, v in sorted(h.issue_types.items())
                )
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
                types_str = ", ".join(
                    f"{k}:{v}" for k, v in sorted(h.issue_types.items())
                )
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
                    "🔴"
                    if c.severity == "critical"
                    else ("🟠" if c.severity == "high" else "🟡")
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
            lines.append(
                "| Pattern | Occurrences | Affected Issues | Suggestion | Complexity |"
            )
            lines.append(
                "|---------|-------------|-----------------|------------|------------|"
            )

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
            change = (
                (curr.total_completed - prev.total_completed) / prev.total_completed * 100
            )
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
