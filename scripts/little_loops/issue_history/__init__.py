"""Issue history analysis and summary statistics.

Provides analysis of completed issues including:
- Type distribution (BUG, ENH, FEAT)
- Priority distribution (P0-P5)
- Discovery source breakdown
- Completion velocity metrics
- Trend analysis over time periods
- Subsystem health tracking
- Technical debt metrics

Public exports:
    # Models
    CompletedIssue: Parsed information from a completed issue file
    HistorySummary: Summary statistics for completed issues
    PeriodMetrics: Metrics for a time period
    SubsystemHealth: Health metrics for a subsystem
    Hotspot, HotspotAnalysis: File hotspot detection
    CouplingPair, CouplingAnalysis: File coupling analysis
    RegressionCluster, RegressionAnalysis: Regression clustering
    TestGap, TestGapAnalysis: Test gap detection
    RejectionMetrics, RejectionAnalysis: Issue rejection analysis
    ManualPattern, ManualPatternAnalysis: Manual pattern detection
    ConfigGap, ConfigGapsAnalysis: Config gap detection
    AgentOutcome, AgentEffectivenessAnalysis: Agent effectiveness
    TechnicalDebtMetrics: Technical debt metrics
    ComplexityProxy, ComplexityProxyAnalysis: Complexity proxy analysis
    CrossCuttingSmell, CrossCuttingAnalysis: Cross-cutting concern detection
    HistoryAnalysis: Full analysis result container

    # Parsing
    parse_completed_issue: Parse a completed issue file
    scan_completed_issues: Scan completed directory for issues
    scan_active_issues: Scan active issue directories

    # Analysis
    calculate_summary: Calculate summary statistics
    calculate_analysis: Calculate full analysis
    analyze_hotspots: Detect file hotspots
    analyze_coupling: Analyze file coupling
    analyze_regression_clustering: Cluster regressions
    analyze_test_gaps: Detect test gaps
    analyze_rejection_rates: Analyze rejection rates
    detect_manual_patterns: Detect manual patterns
    detect_config_gaps: Detect config gaps
    analyze_agent_effectiveness: Analyze agent effectiveness
    analyze_complexity_proxy: Analyze complexity proxy
    detect_cross_cutting_smells: Detect cross-cutting concerns

    # Formatting
    format_summary_text: Format summary as text
    format_summary_json: Format summary as JSON
    format_analysis_text: Format analysis as text
    format_analysis_json: Format analysis as JSON
    format_analysis_markdown: Format analysis as markdown
    format_analysis_yaml: Format analysis as YAML
"""

from little_loops.issue_history.analysis import (
    analyze_agent_effectiveness,
    analyze_complexity_proxy,
    analyze_coupling,
    analyze_hotspots,
    analyze_regression_clustering,
    analyze_rejection_rates,
    analyze_test_gaps,
    calculate_analysis,
    calculate_summary,
    detect_config_gaps,
    detect_cross_cutting_smells,
    detect_manual_patterns,
)
from little_loops.issue_history.formatting import (
    format_analysis_json,
    format_analysis_markdown,
    format_analysis_text,
    format_analysis_yaml,
    format_summary_json,
    format_summary_text,
)
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
    _parse_resolution_action,
    parse_completed_issue,
    scan_active_issues,
    scan_completed_issues,
)

__all__ = [
    # Core dataclasses
    "CompletedIssue",
    "HistorySummary",
    # Advanced analysis dataclasses
    "PeriodMetrics",
    "SubsystemHealth",
    "Hotspot",
    "HotspotAnalysis",
    "CouplingPair",
    "CouplingAnalysis",
    "RegressionCluster",
    "RegressionAnalysis",
    "TestGap",
    "TestGapAnalysis",
    "RejectionMetrics",
    "RejectionAnalysis",
    "ManualPattern",
    "ManualPatternAnalysis",
    "ConfigGap",
    "ConfigGapsAnalysis",
    "AgentOutcome",
    "AgentEffectivenessAnalysis",
    "TechnicalDebtMetrics",
    "ComplexityProxy",
    "ComplexityProxyAnalysis",
    "CrossCuttingSmell",
    "CrossCuttingAnalysis",
    "HistoryAnalysis",
    # Parsing and scanning
    "parse_completed_issue",
    "scan_completed_issues",
    "scan_active_issues",
    # Summary functions
    "calculate_summary",
    "calculate_analysis",
    "analyze_hotspots",
    "analyze_coupling",
    "analyze_regression_clustering",
    "analyze_test_gaps",
    "analyze_rejection_rates",
    "detect_manual_patterns",
    "detect_config_gaps",
    "analyze_agent_effectiveness",
    "analyze_complexity_proxy",
    "detect_cross_cutting_smells",
    # Formatting functions
    "format_summary_text",
    "format_summary_json",
    "format_analysis_text",
    "format_analysis_json",
    "format_analysis_markdown",
    "format_analysis_yaml",
    # Private functions re-exported for test access
    "_detect_processing_agent",
    "_extract_paths_from_issue",
    "_parse_resolution_action",
]
