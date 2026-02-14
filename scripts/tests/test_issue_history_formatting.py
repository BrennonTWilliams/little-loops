"""Tests for issue_history/formatting.py - text, JSON, YAML, and markdown formatters."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

from little_loops.issue_history.formatting import (
    format_analysis_json,
    format_analysis_text,
    format_analysis_yaml,
    format_summary_text,
)
from little_loops.issue_history.models import (
    AgentEffectivenessAnalysis,
    AgentOutcome,
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


def _make_base_analysis(**kwargs: object) -> HistoryAnalysis:
    """Create a minimal HistoryAnalysis for testing."""
    defaults = {
        "generated_date": date(2026, 2, 14),
        "total_completed": 50,
        "total_active": 10,
        "date_range_start": date(2026, 1, 1),
        "date_range_end": date(2026, 2, 14),
        "summary": HistorySummary(
            total_count=50,
            type_counts={"BUG": 20, "ENH": 20, "FEAT": 10},
            priority_counts={"P1": 10, "P2": 30, "P3": 10},
            discovery_counts={"scan-codebase": 30, "capture-issue": 20},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 2, 14),
        ),
    }
    defaults.update(kwargs)
    return HistoryAnalysis(**defaults)  # type: ignore[arg-type]


class TestFormatSummaryText:
    """Tests for format_summary_text."""

    def test_basic_summary(self) -> None:
        """Formats summary with type/priority/discovery counts."""
        summary = HistorySummary(
            total_count=10,
            type_counts={"BUG": 5, "ENH": 3, "FEAT": 2},
            priority_counts={"P1": 4, "P2": 6},
            discovery_counts={"scan-codebase": 7, "capture-issue": 3},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )

        output = format_summary_text(summary)

        assert "Issue History Summary" in output
        assert "Total Completed: 10" in output
        assert "BUG" in output
        assert "By Type:" in output
        assert "By Priority:" in output
        assert "By Discovery Source:" in output

    def test_summary_with_velocity(self) -> None:
        """Includes velocity when date range available."""
        summary = HistorySummary(
            total_count=10,
            type_counts={"BUG": 5},
            priority_counts={"P1": 5},
            discovery_counts={},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )

        output = format_summary_text(summary)
        assert "Velocity:" in output

    def test_summary_without_dates(self) -> None:
        """Omits velocity when no date range."""
        summary = HistorySummary(
            total_count=10,
            type_counts={"BUG": 5},
            priority_counts={"P1": 5},
            discovery_counts={},
        )

        output = format_summary_text(summary)
        assert "Date Range:" not in output


class TestFormatAnalysisJson:
    """Tests for format_analysis_json."""

    def test_json_output_parseable(self) -> None:
        """JSON output is valid JSON."""
        import json

        analysis = _make_base_analysis()
        output = format_analysis_json(analysis)
        parsed = json.loads(output)
        assert parsed["total_completed"] == 50


class TestFormatAnalysisYaml:
    """Tests for format_analysis_yaml."""

    def test_yaml_output(self) -> None:
        """YAML output contains expected data."""
        analysis = _make_base_analysis()
        output = format_analysis_yaml(analysis)
        assert "total_completed: 50" in output

    def test_yaml_fallback_to_json(self) -> None:
        """Falls back to JSON when yaml module unavailable."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return original_import(name, *args, **kwargs)

        analysis = _make_base_analysis()

        with patch("builtins.__import__", side_effect=mock_import):
            output = format_analysis_yaml(analysis)

        # Should fall back to JSON
        assert '"total_completed": 50' in output


class TestFormatAnalysisTextPeriodMetrics:
    """Tests for period metrics section in text formatter."""

    def test_period_metrics_displayed(self) -> None:
        """Period metrics section shows when data present."""
        analysis = _make_base_analysis(
            period_metrics=[
                PeriodMetrics(
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    period_label="Jan 2026",
                    total_completed=20,
                    type_counts={"BUG": 10, "ENH": 10},
                ),
                PeriodMetrics(
                    period_start=date(2026, 2, 1),
                    period_end=date(2026, 2, 14),
                    period_label="Feb 2026",
                    total_completed=15,
                    type_counts={"BUG": 5, "ENH": 10},
                ),
            ],
        )

        output = format_analysis_text(analysis)
        assert "Period Metrics" in output
        assert "Jan 2026" in output
        assert "Feb 2026" in output


class TestFormatAnalysisTextSubsystemHealth:
    """Tests for subsystem health section in text formatter."""

    def test_subsystem_health_displayed(self) -> None:
        """Subsystem health section shows with trend symbols."""
        analysis = _make_base_analysis(
            subsystem_health=[
                SubsystemHealth(
                    subsystem="scripts/little_loops/parallel/",
                    total_issues=15,
                    recent_issues=5,
                    trend="degrading",
                ),
                SubsystemHealth(
                    subsystem="scripts/little_loops/fsm/",
                    total_issues=8,
                    recent_issues=1,
                    trend="improving",
                ),
            ],
        )

        output = format_analysis_text(analysis)
        assert "Subsystem Health" in output


class TestFormatAnalysisTextHotspots:
    """Tests for hotspot analysis section in text formatter."""

    def test_file_hotspots_and_bug_magnets(self) -> None:
        """File hotspots and bug magnets sections display."""
        analysis = _make_base_analysis(
            hotspot_analysis=HotspotAnalysis(
                file_hotspots=[
                    Hotspot(
                        path="src/main.py",
                        issue_count=10,
                        issue_types={"BUG": 7, "ENH": 3},
                        bug_ratio=0.7,
                        churn_indicator="high",
                    ),
                ],
                bug_magnets=[
                    Hotspot(
                        path="src/main.py",
                        issue_count=10,
                        issue_types={"BUG": 7, "ENH": 3},
                        bug_ratio=0.7,
                    ),
                ],
            ),
        )

        output = format_analysis_text(analysis)
        assert "File Hotspots" in output
        assert "HIGH CHURN" in output
        assert "Bug Magnets" in output


class TestFormatAnalysisTextCoupling:
    """Tests for coupling analysis section in text formatter."""

    def test_coupling_pairs_and_clusters(self) -> None:
        """Coupling pairs, clusters, and hotspots display."""
        analysis = _make_base_analysis(
            coupling_analysis=CouplingAnalysis(
                pairs=[
                    CouplingPair(
                        file_a="src/a.py",
                        file_b="src/b.py",
                        co_occurrence_count=8,
                        coupling_strength=0.75,
                    ),
                ],
                clusters=[
                    ["src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"],
                ],
                hotspots=["src/a.py"],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Coupling Detection" in output
        assert "HIGH" in output
        assert "Coupling Clusters" in output
        assert "+1 more" in output
        assert "Coupling Hotspots" in output


class TestFormatAnalysisTextRegression:
    """Tests for regression analysis section in text formatter."""

    def test_regression_clusters_displayed(self) -> None:
        """Regression clusters with severity and chains display."""
        analysis = _make_base_analysis(
            regression_analysis=RegressionAnalysis(
                clusters=[
                    RegressionCluster(
                        primary_file="src/core.py",
                        regression_count=3,
                        fix_bug_pairs=[
                            ("BUG-001", "BUG-005"),
                            ("BUG-005", "BUG-010"),
                            ("BUG-010", "BUG-015"),
                            ("BUG-015", "BUG-020"),
                        ],
                        time_pattern="chronic",
                        severity="critical",
                    ),
                ],
                total_regression_chains=3,
            ),
        )

        output = format_analysis_text(analysis)
        assert "Regression Clustering" in output
        assert "CRITICAL" in output
        assert "Chain:" in output
        assert "..." in output  # >3 pairs truncation


class TestFormatAnalysisTextTestGaps:
    """Tests for test gap analysis section in text formatter."""

    def test_test_gaps_with_critical_gaps(self) -> None:
        """Test gap section shows critical gaps and targets."""
        analysis = _make_base_analysis(
            test_gap_analysis=TestGapAnalysis(
                gaps=[
                    TestGap(
                        source_file="src/no_test.py",
                        bug_count=5,
                        bug_ids=["BUG-001", "BUG-002", "BUG-003"],
                        has_test_file=False,
                        priority="critical",
                    ),
                ],
                files_with_tests_avg_bugs=1.5,
                files_without_tests_avg_bugs=4.2,
                priority_test_targets=["src/no_test.py"],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Test Gap Correlation" in output
        assert "CRITICAL" in output
        assert "NO TEST" in output
        assert "Priority Test Targets" in output


class TestFormatAnalysisTextRejection:
    """Tests for rejection analysis section in text formatter."""

    def test_rejection_analysis_displayed(self) -> None:
        """Rejection analysis shows rates and trends."""
        analysis = _make_base_analysis(
            rejection_analysis=RejectionAnalysis(
                overall=RejectionMetrics(
                    total_closed=100,
                    rejected_count=15,
                    invalid_count=10,
                    duplicate_count=5,
                    deferred_count=3,
                ),
                by_type={
                    "BUG": RejectionMetrics(
                        total_closed=40,
                        rejected_count=6,
                        invalid_count=4,
                    ),
                },
                by_month={
                    "2026-01": RejectionMetrics(
                        total_closed=50,
                        rejected_count=8,
                        invalid_count=5,
                    ),
                    "2026-02": RejectionMetrics(
                        total_closed=50,
                        rejected_count=7,
                        invalid_count=5,
                    ),
                },
                common_reasons=[("already_fixed", 10), ("duplicate", 5)],
                trend="improving",
            ),
        )

        output = format_analysis_text(analysis)
        assert "Rejection Analysis" in output
        assert "Duplicates: 5" in output
        assert "Deferred: 3" in output
        assert "By Type:" in output
        assert "Trend" in output
        assert "Common Rejection Reasons" in output


class TestFormatAnalysisTextManualPatterns:
    """Tests for manual pattern analysis section."""

    def test_manual_patterns_displayed(self) -> None:
        """Manual pattern section shows patterns and suggestions."""
        analysis = _make_base_analysis(
            manual_pattern_analysis=ManualPatternAnalysis(
                total_manual_interventions=20,
                automatable_count=12,
                patterns=[
                    ManualPattern(
                        pattern_type="test",
                        pattern_description="Manual test execution",
                        occurrence_count=8,
                        affected_issues=["BUG-001", "BUG-002", "BUG-003", "BUG-004"],
                        suggested_automation="Add CI/CD hook",
                        automation_complexity="medium",
                    ),
                ],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Manual Pattern Analysis" in output
        assert "Potentially automatable: 60%" in output
        assert "Recurring Patterns" in output
        assert "..." in output  # >3 issues truncated


class TestFormatAnalysisTextConfigGaps:
    """Tests for config gaps analysis section."""

    def test_config_gaps_displayed(self) -> None:
        """Config gaps section shows gaps and suggestions."""
        analysis = _make_base_analysis(
            config_gaps_analysis=ConfigGapsAnalysis(
                coverage_score=0.7,
                current_hooks=["pre-commit", "post-commit"],
                current_skills=["skill1", "skill2"],
                current_agents=["agent1"],
                gaps=[
                    ConfigGap(
                        gap_type="hook",
                        description="post-push sync",
                        priority="high",
                        evidence=["BUG-001", "BUG-002", "BUG-003", "BUG-004"],
                        suggested_config='hooks:\n  post-push:\n    cmd: "ll-sync push"',
                    ),
                ],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Configuration Gaps Analysis" in output
        assert "Coverage score: 70%" in output
        assert "Identified Gaps" in output
        assert "Suggested config:" in output


class TestFormatAnalysisTextAgentEffectiveness:
    """Tests for agent effectiveness section."""

    def test_agent_effectiveness_displayed(self) -> None:
        """Agent effectiveness shows success rates and recommendations."""
        analysis = _make_base_analysis(
            agent_effectiveness_analysis=AgentEffectivenessAnalysis(
                outcomes=[
                    AgentOutcome(
                        agent_name="ll-auto",
                        issue_type="BUG",
                        success_count=8,
                        failure_count=2,
                    ),
                    AgentOutcome(
                        agent_name="ll-auto",
                        issue_type="ENH",
                        success_count=2,
                        failure_count=3,
                    ),
                ],
                best_agent_by_type={"BUG": "ll-auto"},
                problematic_combinations=[
                    ("ll-auto", "ENH", "40% success rate"),
                ],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Agent Effectiveness Analysis" in output
        assert "ll-auto" in output
        assert "Recommendations" in output
        assert "underperforms" in output


class TestFormatAnalysisTextComplexity:
    """Tests for complexity proxy analysis section."""

    def test_complexity_analysis_displayed(self) -> None:
        """Complexity proxy shows file/directory complexity and outliers."""
        analysis = _make_base_analysis(
            complexity_proxy_analysis=ComplexityProxyAnalysis(
                baseline_days=5.0,
                file_complexity=[
                    ComplexityProxy(
                        path="src/complex.py",
                        avg_resolution_days=15.0,
                        median_resolution_days=12.0,
                        issue_count=8,
                        comparison_to_baseline="3.0x baseline",
                        complexity_score=0.85,
                        slowest_issue=("BUG-042", 25.0),
                    ),
                ],
                directory_complexity=[
                    ComplexityProxy(
                        path="src/complex/",
                        avg_resolution_days=10.0,
                        median_resolution_days=8.0,
                        issue_count=12,
                        comparison_to_baseline="2.0x baseline",
                        complexity_score=0.6,
                        slowest_issue=("BUG-099", 20.0),
                    ),
                ],
                complexity_outliers=["src/complex.py"],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Complexity Proxy Analysis" in output
        assert "Baseline resolution time:" in output
        assert "High Complexity Files" in output
        assert "High Complexity Directories" in output
        assert "Complexity Outliers" in output


class TestFormatAnalysisTextCrossCutting:
    """Tests for cross-cutting concern analysis section."""

    def test_cross_cutting_displayed(self) -> None:
        """Cross-cutting shows smells and consolidation opportunities."""
        analysis = _make_base_analysis(
            cross_cutting_analysis=CrossCuttingAnalysis(
                smells=[
                    CrossCuttingSmell(
                        concern_type="error_handling",
                        affected_directories=[
                            "src/a/",
                            "src/b/",
                            "src/c/",
                            "src/d/",
                        ],
                        issue_ids=["BUG-001", "BUG-002", "BUG-003", "BUG-004"],
                        issue_count=4,
                        scatter_score=0.75,
                        suggested_pattern="Centralized error handler",
                    ),
                ],
                consolidation_opportunities=[
                    "Extract common error handling into shared module",
                ],
            ),
        )

        output = format_analysis_text(analysis)
        assert "Cross-Cutting Concern Analysis" in output
        assert "HIGH SCATTER" in output
        assert "Consolidation Opportunities" in output


class TestFormatAnalysisTextTechnicalDebt:
    """Tests for technical debt section."""

    def test_debt_metrics_displayed(self) -> None:
        """Technical debt section shows backlog and growth metrics."""
        analysis = _make_base_analysis(
            debt_metrics=TechnicalDebtMetrics(
                backlog_size=25,
                backlog_growth_rate=2.5,
                high_priority_open=5,
                aging_30_plus=8,
            ),
        )

        output = format_analysis_text(analysis)
        assert "Technical Debt" in output
        assert "Backlog Size: 25" in output
        assert "Growth Rate:" in output


class TestFormatAnalysisTextComparison:
    """Tests for comparison period section."""

    def test_comparison_displayed(self) -> None:
        """Comparison section shows period-over-period change."""
        analysis = _make_base_analysis(
            comparison_period="30d",
            current_period=PeriodMetrics(
                period_start=date(2026, 1, 15),
                period_end=date(2026, 2, 14),
                period_label="Current",
                total_completed=30,
            ),
            previous_period=PeriodMetrics(
                period_start=date(2025, 12, 16),
                period_end=date(2026, 1, 14),
                period_label="Previous",
                total_completed=20,
            ),
        )

        output = format_analysis_text(analysis)
        assert "Comparison (30d)" in output
