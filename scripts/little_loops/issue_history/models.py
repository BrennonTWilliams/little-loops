"""Issue history data models.

Dataclasses for issue history analysis including completed issues,
summary statistics, hotspot detection, coupling analysis, regression
clustering, test gap analysis, and technical debt metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class CompletedIssue:
    """Parsed information from a completed issue file."""

    path: Path
    issue_type: str  # BUG, ENH, FEAT
    priority: str  # P0-P5
    issue_id: str  # e.g., BUG-001
    discovered_by: str | None = None
    discovered_date: date | None = None
    completed_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "issue_type": self.issue_type,
            "priority": self.priority,
            "issue_id": self.issue_id,
            "discovered_by": self.discovered_by,
            "discovered_date": (self.discovered_date.isoformat() if self.discovered_date else None),
            "completed_date": (self.completed_date.isoformat() if self.completed_date else None),
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
            "earliest_date": (self.earliest_date.isoformat() if self.earliest_date else None),
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "date_range_days": self.date_range_days,
            "velocity": round(self.velocity, 2) if self.velocity else None,
        }


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
class CouplingPair:
    """A pair of files that frequently appear together in issues."""

    file_a: str
    file_b: str
    co_occurrence_count: int = 0
    coupling_strength: float = 0.0  # 0-1, Jaccard similarity
    issue_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_a": self.file_a,
            "file_b": self.file_b,
            "co_occurrence_count": self.co_occurrence_count,
            "coupling_strength": round(self.coupling_strength, 3),
            "issue_ids": self.issue_ids[:10],  # Top 10
        }


@dataclass
class CouplingAnalysis:
    """Analysis of files that frequently change together."""

    pairs: list[CouplingPair] = field(default_factory=list)
    clusters: list[list[str]] = field(default_factory=list)  # Groups of coupled files
    hotspots: list[str] = field(default_factory=list)  # Files coupled with 3+ others

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pairs": [p.to_dict() for p in self.pairs],
            "clusters": self.clusters[:10],  # Top 10 clusters
            "hotspots": self.hotspots[:10],  # Top 10 hotspots
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
class ConfigGap:
    """A gap in configuration that could address recurring manual work."""

    gap_type: str  # "hook", "skill", "agent"
    description: str
    evidence: list[str] = field(default_factory=list)  # issue IDs showing the pattern
    suggested_config: str = ""  # example configuration
    priority: str = "medium"  # "high", "medium", "low"
    pattern_type: str = ""  # links back to ManualPattern.pattern_type

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gap_type": self.gap_type,
            "description": self.description,
            "evidence": self.evidence[:10],
            "suggested_config": self.suggested_config,
            "priority": self.priority,
            "pattern_type": self.pattern_type,
        }


@dataclass
class ConfigGapsAnalysis:
    """Analysis of configuration gaps based on manual pattern detection."""

    gaps: list[ConfigGap] = field(default_factory=list)
    current_hooks: list[str] = field(default_factory=list)
    current_skills: list[str] = field(default_factory=list)
    current_agents: list[str] = field(default_factory=list)
    coverage_score: float = 0.0  # 0-1, how well config covers common needs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "current_hooks": self.current_hooks,
            "current_skills": self.current_skills,
            "current_agents": self.current_agents,
            "coverage_score": round(self.coverage_score, 2),
        }


@dataclass
class AgentOutcome:
    """Metrics for a single agent processing a specific issue type."""

    agent_name: str
    issue_type: str
    success_count: int = 0
    failure_count: int = 0
    rejection_count: int = 0

    @property
    def total_count(self) -> int:
        """Total issues handled."""
        return self.success_count + self.failure_count + self.rejection_count

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_name": self.agent_name,
            "issue_type": self.issue_type,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "rejection_count": self.rejection_count,
            "total_count": self.total_count,
            "success_rate": round(self.success_rate, 3),
        }


@dataclass
class AgentEffectivenessAnalysis:
    """Analysis of agent effectiveness across issue types."""

    outcomes: list[AgentOutcome] = field(default_factory=list)
    best_agent_by_type: dict[str, str] = field(default_factory=dict)
    problematic_combinations: list[tuple[str, str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "outcomes": [o.to_dict() for o in self.outcomes],
            "best_agent_by_type": self.best_agent_by_type,
            "problematic_combinations": self.problematic_combinations[:10],
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
class ComplexityProxy:
    """Duration-based complexity proxy for a file or directory."""

    path: str
    avg_resolution_days: float
    median_resolution_days: float
    issue_count: int
    slowest_issue: tuple[str, float]  # (issue_id, days)
    complexity_score: float  # normalized 0-1
    comparison_to_baseline: str  # "2.1x baseline", etc.

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "avg_resolution_days": round(self.avg_resolution_days, 1),
            "median_resolution_days": round(self.median_resolution_days, 1),
            "issue_count": self.issue_count,
            "slowest_issue": {
                "issue_id": self.slowest_issue[0],
                "days": round(self.slowest_issue[1], 1),
            },
            "complexity_score": round(self.complexity_score, 3),
            "comparison_to_baseline": self.comparison_to_baseline,
        }


@dataclass
class ComplexityProxyAnalysis:
    """Analysis using issue duration as complexity proxy."""

    file_complexity: list[ComplexityProxy] = field(default_factory=list)
    directory_complexity: list[ComplexityProxy] = field(default_factory=list)
    baseline_days: float = 0.0  # median across all issues
    complexity_outliers: list[str] = field(default_factory=list)  # files >2x baseline

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_complexity": [c.to_dict() for c in self.file_complexity[:10]],
            "directory_complexity": [c.to_dict() for c in self.directory_complexity[:10]],
            "baseline_days": round(self.baseline_days, 1),
            "complexity_outliers": self.complexity_outliers[:10],
        }


@dataclass
class CrossCuttingSmell:
    """A detected cross-cutting concern scattered across the codebase."""

    concern_type: str  # "logging", "error-handling", "validation", "auth", "caching"
    affected_directories: list[str] = field(default_factory=list)
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    scatter_score: float = 0.0  # higher = more scattered (0-1)
    suggested_pattern: str = ""  # "middleware", "decorator", "aspect"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "concern_type": self.concern_type,
            "affected_directories": self.affected_directories[:10],
            "issue_count": self.issue_count,
            "issue_ids": self.issue_ids[:10],
            "scatter_score": round(self.scatter_score, 2),
            "suggested_pattern": self.suggested_pattern,
        }


@dataclass
class CrossCuttingAnalysis:
    """Analysis of cross-cutting concerns scattered across the codebase."""

    smells: list[CrossCuttingSmell] = field(default_factory=list)
    most_scattered_concern: str = ""
    consolidation_opportunities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "smells": [s.to_dict() for s in self.smells],
            "most_scattered_concern": self.most_scattered_concern,
            "consolidation_opportunities": self.consolidation_opportunities[:10],
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

    # Coupling analysis
    coupling_analysis: CouplingAnalysis | None = None

    # Regression clustering analysis
    regression_analysis: RegressionAnalysis | None = None

    # Test gap analysis
    test_gap_analysis: TestGapAnalysis | None = None

    # Rejection analysis
    rejection_analysis: RejectionAnalysis | None = None

    # Manual pattern analysis
    manual_pattern_analysis: ManualPatternAnalysis | None = None

    # Agent effectiveness analysis
    agent_effectiveness_analysis: AgentEffectivenessAnalysis | None = None

    # Complexity proxy analysis
    complexity_proxy_analysis: ComplexityProxyAnalysis | None = None

    # Configuration gaps analysis
    config_gaps_analysis: ConfigGapsAnalysis | None = None

    # Cross-cutting concern analysis
    cross_cutting_analysis: CrossCuttingAnalysis | None = None

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
            "date_range_end": (self.date_range_end.isoformat() if self.date_range_end else None),
            "summary": self.summary.to_dict(),
            "period_metrics": [p.to_dict() for p in self.period_metrics],
            "velocity_trend": self.velocity_trend,
            "bug_ratio_trend": self.bug_ratio_trend,
            "subsystem_health": [s.to_dict() for s in self.subsystem_health],
            "hotspot_analysis": (
                self.hotspot_analysis.to_dict() if self.hotspot_analysis else None
            ),
            "coupling_analysis": (
                self.coupling_analysis.to_dict() if self.coupling_analysis else None
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
                self.manual_pattern_analysis.to_dict() if self.manual_pattern_analysis else None
            ),
            "agent_effectiveness_analysis": (
                self.agent_effectiveness_analysis.to_dict()
                if self.agent_effectiveness_analysis
                else None
            ),
            "complexity_proxy_analysis": (
                self.complexity_proxy_analysis.to_dict() if self.complexity_proxy_analysis else None
            ),
            "config_gaps_analysis": (
                self.config_gaps_analysis.to_dict() if self.config_gaps_analysis else None
            ),
            "cross_cutting_analysis": (
                self.cross_cutting_analysis.to_dict() if self.cross_cutting_analysis else None
            ),
            "debt_metrics": self.debt_metrics.to_dict() if self.debt_metrics else None,
            "comparison_period": self.comparison_period,
            "previous_period": (self.previous_period.to_dict() if self.previous_period else None),
            "current_period": (self.current_period.to_dict() if self.current_period else None),
        }
