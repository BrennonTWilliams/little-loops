# FEAT-110: Advanced Issue History Analysis - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-110-issue-history-analysis.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The basic `ll-history summary` command (FEAT-111) provides foundational statistics:
- `scripts/little_loops/issue_history.py` (321 lines) - Core module with `CompletedIssue`, `HistorySummary`, parsing, and formatting
- `scripts/little_loops/cli.py:1264-1331` - `main_history()` entry point with `summary` subcommand
- `scripts/tests/test_issue_history.py` (470 lines) - Comprehensive test coverage

### Key Discoveries
- `CompletedIssue` dataclass at `issue_history.py:30-52` - Already captures issue_type, priority, discovered_by, completed_date
- `HistorySummary` at `issue_history.py:55-93` - Has computed properties (velocity, date_range_days)
- `_parse_discovered_by()` at `issue_history.py:140-166` - Parses YAML frontmatter
- `_parse_completion_date()` at `issue_history.py:169-192` - Extracts from Resolution section or mtime
- `scan_completed_issues()` at `issue_history.py:195-217` - Scans `completed/` directory
- `format_summary_text()` at `issue_history.py:266-308` - Human-readable output
- `format_summary_json()` at `issue_history.py:311-320` - JSON output with `to_dict()`
- CLI pattern at `cli.py:1264-1331` - argparse with subcommands, lazy imports

### Patterns to Follow
- Dataclass with `to_dict()` for serialization (issue_history.py)
- Separate `format_*_text()` and `format_*_json()` functions
- CLI entry points return int, use argparse with subcommands
- Skill definition pattern from `skills/capture-issue/SKILL.md`
- Test patterns with `tmp_path`, `capsys`, mock `sys.argv`

## Desired End State

A comprehensive analysis system that answers "Are we making progress?" for large projects:

1. **Extended Python Module** (`issue_history.py`)
   - Trend analysis (velocity over time, bug ratio trends)
   - Subsystem health metrics (per-directory analysis)
   - Technical debt indicators (backlog growth, aging)
   - Comparative period analysis
   - Multiple output formats (text, JSON, Markdown, YAML)

2. **CLI Subcommand** (`ll-history analyze`)
   - Full analysis with configurable options
   - `--compare` for period comparison
   - `--format` for output format selection
   - `--since/--until` for time bounding

3. **Skill** (`skills/analyze-history/SKILL.md`)
   - Natural language triggering
   - Links to `/ll:analyze_history` command (if created) or CLI

### How to Verify
- Run `ll-history analyze` produces Markdown report
- Tests cover new dataclasses and functions
- Performance: <10 seconds for 100+ issues

## What We're NOT Doing

- **NOT creating a slash command** - CLI `ll-history analyze` is sufficient; skill provides natural language access
- **NOT implementing git hotspot correlation** - Deferred to Phase 2; requires significant git integration
- **NOT adding AI-generated insights** - Deferred; focus on data analysis first
- **NOT adding caching** - Premature optimization for typical issue counts (<1000)

## Problem Analysis

FEAT-110 extends FEAT-111 to provide deeper analysis for long-running projects:
- Projects with 100+ issues need trend visibility
- Simple counts don't show improvement trajectory
- No way to identify stabilizing vs degrading subsystems
- No technical debt metrics (backlog growth, aging)

## Solution Approach

Extend `issue_history.py` with new dataclasses and analysis functions, following existing patterns. Add new `analyze` subcommand to CLI. Create skill for natural language access.

## Implementation Phases

### Phase 1: Extend Data Structures

#### Overview
Add new dataclasses to support advanced metrics without breaking existing functionality.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add to imports:
```python
from collections import defaultdict
from typing import Literal
import yaml  # For YAML output
```

Add new dataclasses after `HistorySummary`:

```python
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
            "bug_ratio": round(self.bug_ratio, 3) if self.bug_ratio else None,
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
            "debt_metrics": self.debt_metrics.to_dict() if self.debt_metrics else None,
            "comparison_period": self.comparison_period,
            "previous_period": (
                self.previous_period.to_dict() if self.previous_period else None
            ),
            "current_period": (
                self.current_period.to_dict() if self.current_period else None
            ),
        }
```

Update `__all__`:
```python
__all__ = [
    "CompletedIssue",
    "HistorySummary",
    "PeriodMetrics",
    "SubsystemHealth",
    "TechnicalDebtMetrics",
    "HistoryAnalysis",
    "parse_completed_issue",
    "scan_completed_issues",
    "calculate_summary",
    "calculate_analysis",
    "format_summary_text",
    "format_summary_json",
    "format_analysis_text",
    "format_analysis_json",
    "format_analysis_markdown",
    "format_analysis_yaml",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

**Manual Verification**:
- [ ] New dataclasses can be instantiated and serialized to dict

---

### Phase 2: Add Analysis Functions

#### Overview
Implement core analysis functions for trends, subsystems, and debt metrics.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add helper functions:

```python
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


def _calculate_period_label(start: date, end: date, period_type: str) -> str:
    """Generate human-readable period label.

    Args:
        start: Period start date
        end: Period end date
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
    from datetime import timedelta

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

        result.append(PeriodMetrics(
            period_start=period_start,
            period_end=period_end,
            period_label=_calculate_period_label(period_start, period_end, period_type),
            total_completed=len(period_issues),
            type_counts=dict(sorted(type_counts.items())),
            priority_counts=dict(sorted(priority_counts.items())),
        ))

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
    from datetime import timedelta

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
    from datetime import timedelta

    today = date.today()
    metrics = TechnicalDebtMetrics()

    # Backlog size
    metrics.backlog_size = len(active_issues)

    # Count aging and high priority
    for path, issue_type, priority, discovered_date in active_issues:
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
        1 for i in completed_issues
        if i.completed_date and i.completed_date >= four_weeks_ago
    )

    created_recently = sum(
        1 for _, _, _, d in active_issues
        if d and d >= four_weeks_ago
    )

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
```

Add main analysis function:

```python
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
    from datetime import timedelta

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
        velocities = [p.total_completed for p in period_metrics]
        velocity_trend = _calculate_trend(velocities)
    else:
        velocity_trend = "stable"

    # Determine bug ratio trend
    if len(period_metrics) >= 3:
        bug_ratios = [p.bug_ratio or 0.0 for p in period_metrics]
        # For bug ratio, decreasing is good (invert interpretation)
        raw_trend = _calculate_trend(bug_ratios)
        bug_ratio_trend = raw_trend  # Keep as-is; "decreasing" is positive
    else:
        bug_ratio_trend = "stable"

    # Subsystem health
    subsystem_health = _analyze_subsystems(completed_issues)

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
        debt_metrics=debt_metrics,
    )

    # Comparative analysis
    if compare_days:
        analysis.comparison_period = f"{compare_days}d"
        cutoff = today - timedelta(days=compare_days)
        prev_cutoff = cutoff - timedelta(days=compare_days)

        current_issues = [
            i for i in completed_issues
            if i.completed_date and i.completed_date >= cutoff
        ]
        previous_issues = [
            i for i in completed_issues
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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

**Manual Verification**:
- [ ] `calculate_analysis()` returns populated `HistoryAnalysis` for test data

---

### Phase 3: Add Output Formatters

#### Overview
Implement text, JSON, Markdown, and YAML output formatters for analysis results.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add formatting functions:

```python
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
        YAML string
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
            bug_pct = f"{period.bug_ratio*100:.0f}%" if period.bug_ratio else "N/A"
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
                f"  {sub.subsystem:30}: {sub.total_issues:3} total, {sub.recent_issues:2} recent {trend_symbol}"
            )

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
            lines.append(f"  Completed: {prev.total_completed} -> {curr.total_completed} ({change:+.0f}%)")
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
    lines.append(f"**Generated**: {analysis.generated_date} | "
                 f"**Total Completed**: {analysis.total_completed} | "
                 f"**Active Issues**: {analysis.total_active}")

    if analysis.date_range_start and analysis.date_range_end:
        lines.append(f"**Date Range**: {analysis.date_range_start} to {analysis.date_range_end}")

    # Executive Summary
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Value | Trend |")
    lines.append("|--------|-------|-------|")

    velocity = f"{analysis.summary.velocity:.2f}/day" if analysis.summary.velocity else "N/A"
    velocity_symbol = {"increasing": "↑", "decreasing": "↓", "stable": "→"}.get(analysis.velocity_trend, "")
    lines.append(f"| Velocity | {velocity} | {velocity_symbol} {analysis.velocity_trend} |")

    bug_count = analysis.summary.type_counts.get("BUG", 0)
    total = analysis.total_completed or 1
    bug_pct = bug_count * 100 // total
    bug_symbol = {"increasing": "↑ ⚠️", "decreasing": "↓ ✓", "stable": "→"}.get(analysis.bug_ratio_trend, "")
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
            bug_pct = f"{period.bug_ratio*100:.0f}%" if period.bug_ratio else "N/A"
            lines.append(f"| {period.period_label} | {period.total_completed} | {bug_pct} |")

    # Subsystem Health
    if analysis.subsystem_health:
        lines.append("")
        lines.append("## Subsystem Health")
        lines.append("")
        lines.append("| Subsystem | Total | Recent (30d) | Trend |")
        lines.append("|-----------|-------|--------------|-------|")
        for sub in analysis.subsystem_health:
            trend_symbol = {"improving": "↓ ✓", "degrading": "↑ ⚠️", "stable": "→"}.get(sub.trend, "")
            lines.append(f"| `{sub.subsystem}` | {sub.total_issues} | {sub.recent_issues} | {trend_symbol} |")

    # Technical Debt
    if analysis.debt_metrics:
        lines.append("")
        lines.append("## Technical Debt Health")
        lines.append("")
        debt = analysis.debt_metrics
        lines.append("| Metric | Value | Assessment |")
        lines.append("|--------|-------|------------|")

        backlog_status = "✓ Low" if debt.backlog_size < 20 else ("⚠️ High" if debt.backlog_size > 50 else "Moderate")
        lines.append(f"| Backlog Size | {debt.backlog_size} | {backlog_status} |")

        growth_status = "✓ Shrinking" if debt.backlog_growth_rate < 0 else ("⚠️ Growing" if debt.backlog_growth_rate > 2 else "Stable")
        lines.append(f"| Growth Rate | {debt.backlog_growth_rate:+.1f}/week | {growth_status} |")

        hp_status = "✓ Good" if debt.high_priority_open < 3 else "⚠️ Attention needed"
        lines.append(f"| High Priority Open | {debt.high_priority_open} | {hp_status} |")

        aging_status = "✓ Healthy" if debt.aging_30_plus < 5 else ("⚠️ Review needed" if debt.aging_30_plus > 10 else "Moderate")
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
        lines.append(f"| Completed | {prev.total_completed} | {curr.total_completed} | {change_str} |")

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

**Manual Verification**:
- [ ] `format_analysis_markdown()` produces readable Markdown output
- [ ] `format_analysis_yaml()` produces valid YAML

---

### Phase 4: Extend CLI with `analyze` Subcommand

#### Overview
Add `ll-history analyze` subcommand to the CLI.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

Update `main_history()` function (around line 1264):

```python
def main_history() -> int:
    """Entry point for ll-history command.

    Display summary statistics and analysis for completed issues.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_history import (
        calculate_analysis,
        calculate_summary,
        format_analysis_json,
        format_analysis_markdown,
        format_analysis_text,
        format_analysis_yaml,
        format_summary_json,
        format_summary_text,
        scan_completed_issues,
    )

    parser = argparse.ArgumentParser(
        prog="ll-history",
        description="Display summary statistics and analysis for completed issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary              # Show summary statistics
  %(prog)s summary --json       # Output as JSON
  %(prog)s analyze              # Full analysis report
  %(prog)s analyze --format markdown  # Markdown report
  %(prog)s analyze --compare 30 # Compare last 30 days to previous
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # summary subcommand (existing)
    summary_parser = subparsers.add_parser("summary", help="Show issue statistics")
    summary_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text",
    )
    summary_parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )

    # analyze subcommand (new)
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Full analysis with trends, subsystems, and debt metrics",
    )
    analyze_parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["text", "json", "markdown", "yaml"],
        default="text",
        help="Output format (default: text)",
    )
    analyze_parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )
    analyze_parser.add_argument(
        "-p",
        "--period",
        type=str,
        choices=["weekly", "monthly", "quarterly"],
        default="monthly",
        help="Grouping period for trends (default: monthly)",
    )
    analyze_parser.add_argument(
        "-c",
        "--compare",
        type=int,
        default=None,
        metavar="DAYS",
        help="Compare last N days to previous N days",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Determine directories
    issues_dir = args.directory or Path.cwd() / ".issues"
    completed_dir = issues_dir / "completed"

    if args.command == "summary":
        # Existing summary logic
        issues = scan_completed_issues(completed_dir)
        summary = calculate_summary(issues)

        if args.json:
            print(format_summary_json(summary))
        else:
            print(format_summary_text(summary))

        return 0

    if args.command == "analyze":
        # New analyze logic
        issues = scan_completed_issues(completed_dir)
        analysis = calculate_analysis(
            issues,
            issues_dir=issues_dir,
            period_type=args.period,
            compare_days=args.compare,
        )

        if args.format == "json":
            print(format_analysis_json(analysis))
        elif args.format == "yaml":
            print(format_analysis_yaml(analysis))
        elif args.format == "markdown":
            print(format_analysis_markdown(analysis))
        else:
            print(format_analysis_text(analysis))

        return 0

    return 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v -k history`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] `ll-history analyze --help` displays help

**Manual Verification**:
- [ ] `ll-history analyze` produces text output
- [ ] `ll-history analyze --format markdown` produces Markdown
- [ ] `ll-history analyze --compare 30` shows comparison

---

### Phase 5: Create Skill

#### Overview
Create a skill for natural language access to history analysis.

#### Changes Required

**File**: `skills/analyze-history/SKILL.md` (new file)

```markdown
---
description: |
  Analyze issue history to understand project health, trends, and progress. Use this skill when users ask about velocity, bug trends, technical debt, or want to know "are we making progress?"

  Trigger keywords: "analyze history", "issue history", "velocity report", "bug trends", "technical debt", "project health", "are we making progress", "issue trends", "history analysis"
---

# Analyze History Skill

This skill helps users understand their issue history and project health trends.

## When to Activate

Proactively offer or invoke this skill when the user:
- Asks about project velocity or completion rates
- Wants to know about bug trends or ratios
- Asks "are we making progress?"
- Inquires about technical debt health
- Wants to compare recent performance to historical
- Asks about subsystem or module health

## How to Use

Run the `ll-history` CLI command based on user needs:

### Quick Summary

For a basic summary:
```bash
ll-history summary
```

### Full Analysis

For comprehensive analysis:
```bash
ll-history analyze
```

### Markdown Report

For a shareable report:
```bash
ll-history analyze --format markdown
```

### Period Comparison

To compare recent vs previous period:
```bash
ll-history analyze --compare 30
```

### Output Formats

| Format | Command | Best For |
|--------|---------|----------|
| Text | `ll-history analyze` | Terminal viewing |
| Markdown | `ll-history analyze --format markdown` | Documentation, sharing |
| JSON | `ll-history analyze --format json` | Programmatic access |
| YAML | `ll-history analyze --format yaml` | Config, further processing |

## Examples

| User Says | Action |
|-----------|--------|
| "How's our project health?" | `ll-history analyze` |
| "Show me bug trends" | `ll-history analyze --format markdown` |
| "Compare last month to previous" | `ll-history analyze --compare 30` |
| "Are we making progress?" | `ll-history analyze --format markdown` |
| "What's our velocity?" | `ll-history summary` |

## Interpretation Guide

### Velocity Trend
- **Increasing**: Team completing more issues over time
- **Stable**: Consistent output
- **Decreasing**: May indicate blockers or complexity

### Bug Ratio Trend
- **Decreasing**: Codebase stabilizing (good)
- **Increasing**: Quality issues, may need attention
- **Stable**: Consistent quality level

### Subsystem Health
- **Improving** (↓): Fewer recent issues, stabilizing
- **Degrading** (↑): More recent issues, needs attention
- **Stable** (→): Consistent issue rate

### Technical Debt Indicators
- **Backlog Growing**: More issues created than closed
- **High Aging**: Issues sitting too long without resolution
- **High Priority Open**: Critical issues need immediate attention
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `skills/analyze-history/SKILL.md`
- [ ] Valid YAML frontmatter

**Manual Verification**:
- [ ] Skill description is clear and actionable

---

### Phase 6: Add Tests

#### Overview
Add comprehensive tests for new functionality.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`

Add new test classes at the end of the file:

```python
class TestPeriodMetrics:
    """Tests for PeriodMetrics dataclass."""

    def test_bug_ratio(self) -> None:
        """Test bug ratio calculation."""
        from little_loops.issue_history import PeriodMetrics

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=10,
            type_counts={"BUG": 3, "ENH": 5, "FEAT": 2},
        )
        assert period.bug_ratio == 0.3

    def test_bug_ratio_no_bugs(self) -> None:
        """Test bug ratio with no bugs."""
        from little_loops.issue_history import PeriodMetrics

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=5,
            type_counts={"ENH": 5},
        )
        assert period.bug_ratio == 0.0

    def test_bug_ratio_empty(self) -> None:
        """Test bug ratio with no completions."""
        from little_loops.issue_history import PeriodMetrics

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=0,
        )
        assert period.bug_ratio is None

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import PeriodMetrics

        period = PeriodMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            period_label="Jan 2026",
            total_completed=10,
            type_counts={"BUG": 3},
        )
        result = period.to_dict()
        assert result["period_start"] == "2026-01-01"
        assert result["period_label"] == "Jan 2026"
        assert result["bug_ratio"] == 0.3


class TestSubsystemHealth:
    """Tests for SubsystemHealth dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import SubsystemHealth

        health = SubsystemHealth(
            subsystem="scripts/little_loops/",
            total_issues=10,
            recent_issues=3,
            issue_ids=["BUG-001", "BUG-002"],
            trend="improving",
        )
        result = health.to_dict()
        assert result["subsystem"] == "scripts/little_loops/"
        assert result["trend"] == "improving"


class TestTechnicalDebtMetrics:
    """Tests for TechnicalDebtMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import TechnicalDebtMetrics

        debt = TechnicalDebtMetrics(
            backlog_size=25,
            backlog_growth_rate=1.5,
            aging_30_plus=8,
            high_priority_open=2,
        )
        result = debt.to_dict()
        assert result["backlog_size"] == 25
        assert result["backlog_growth_rate"] == 1.5


class TestHistoryAnalysis:
    """Tests for HistoryAnalysis dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        from little_loops.issue_history import HistoryAnalysis, HistorySummary

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(total_count=50),
        )
        result = analysis.to_dict()
        assert result["generated_date"] == "2026-01-23"
        assert result["total_completed"] == 50


class TestCalculateAnalysis:
    """Tests for calculate_analysis function."""

    def test_empty_issues(self) -> None:
        """Test analysis with no issues."""
        from little_loops.issue_history import calculate_analysis

        analysis = calculate_analysis([])
        assert analysis.total_completed == 0
        assert analysis.period_metrics == []

    def test_with_issues(self, tmp_path: Path) -> None:
        """Test analysis with sample issues."""
        from little_loops.issue_history import CompletedIssue, calculate_analysis

        issues = [
            CompletedIssue(
                path=tmp_path / "P1-BUG-001.md",
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 10),
            ),
            CompletedIssue(
                path=tmp_path / "P2-ENH-002.md",
                issue_type="ENH",
                priority="P2",
                issue_id="ENH-002",
                completed_date=date(2026, 1, 15),
            ),
        ]

        analysis = calculate_analysis(issues)
        assert analysis.total_completed == 2
        assert analysis.summary.type_counts["BUG"] == 1

    def test_with_comparison(self, tmp_path: Path) -> None:
        """Test analysis with comparison period."""
        from little_loops.issue_history import CompletedIssue, calculate_analysis

        today = date.today()
        issues = [
            CompletedIssue(
                path=tmp_path / "P1-BUG-001.md",
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=today,
            ),
        ]

        analysis = calculate_analysis(issues, compare_days=30)
        assert analysis.comparison_period == "30d"


class TestFormatAnalysis:
    """Tests for analysis formatting functions."""

    def test_format_analysis_text(self) -> None:
        """Test text formatting."""
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_text,
        )

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(
                total_count=50,
                type_counts={"BUG": 20, "ENH": 30},
            ),
        )

        text = format_analysis_text(analysis)
        assert "Issue History Analysis" in text
        assert "Completed: 50" in text
        assert "BUG" in text

    def test_format_analysis_json(self) -> None:
        """Test JSON formatting."""
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_json,
        )

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=None,
            date_range_end=None,
            summary=HistorySummary(total_count=50),
        )

        json_str = format_analysis_json(analysis)
        data = json.loads(json_str)
        assert data["total_completed"] == 50

    def test_format_analysis_markdown(self) -> None:
        """Test Markdown formatting."""
        from little_loops.issue_history import (
            HistoryAnalysis,
            HistorySummary,
            format_analysis_markdown,
        )

        analysis = HistoryAnalysis(
            generated_date=date(2026, 1, 23),
            total_completed=50,
            total_active=10,
            date_range_start=date(2026, 1, 1),
            date_range_end=date(2026, 1, 23),
            summary=HistorySummary(
                total_count=50,
                type_counts={"BUG": 20},
            ),
        )

        md = format_analysis_markdown(analysis)
        assert "# Issue History Analysis Report" in md
        assert "| Metric |" in md


class TestAnalyzeArgumentParsing:
    """Tests for ll-history analyze argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        # summary
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)

        # analyze
        analyze_parser = subparsers.add_parser("analyze")
        analyze_parser.add_argument(
            "-f", "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
        )
        analyze_parser.add_argument("-d", "--directory", type=Path, default=None)
        analyze_parser.add_argument(
            "-p", "--period",
            type=str,
            choices=["weekly", "monthly", "quarterly"],
            default="monthly",
        )
        analyze_parser.add_argument("-c", "--compare", type=int, default=None)

        return parser.parse_args(args)

    def test_analyze_default(self) -> None:
        """Test analyze with defaults."""
        args = self._parse_history_args(["analyze"])
        assert args.command == "analyze"
        assert args.format == "text"
        assert args.period == "monthly"
        assert args.compare is None

    def test_analyze_format_markdown(self) -> None:
        """Test --format markdown."""
        args = self._parse_history_args(["analyze", "--format", "markdown"])
        assert args.format == "markdown"

    def test_analyze_compare(self) -> None:
        """Test --compare flag."""
        args = self._parse_history_args(["analyze", "--compare", "30"])
        assert args.compare == 30

    def test_analyze_period_quarterly(self) -> None:
        """Test --period quarterly."""
        args = self._parse_history_args(["analyze", "--period", "quarterly"])
        assert args.period == "quarterly"


class TestMainHistoryAnalyze:
    """Integration tests for ll-history analyze."""

    def test_main_history_analyze_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Issue History Analysis" in captured.out

    def test_main_history_analyze_markdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format markdown."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "markdown", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "# Issue History Analysis Report" in captured.out

    def test_main_history_analyze_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format json."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "json", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_completed" in data
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_history.py`

**Manual Verification**:
- [ ] Test coverage is comprehensive

---

## Testing Strategy

### Unit Tests
- New dataclasses: `to_dict()`, computed properties
- Analysis functions: empty input, normal input, edge cases
- Formatting functions: each format produces valid output

### Integration Tests
- CLI `analyze` subcommand with different flags
- End-to-end with temp directory and sample issues

### Edge Cases
- Empty completed directory
- No dated issues (velocity N/A)
- Single issue (no trends)
- Issues without subsystem info

## References

- Original issue: `.issues/features/P3-FEAT-110-issue-history-analysis.md`
- Existing module: `scripts/little_loops/issue_history.py`
- Existing tests: `scripts/tests/test_issue_history.py`
- CLI patterns: `scripts/little_loops/cli.py:1264-1331`
- Skill patterns: `skills/capture-issue/SKILL.md`
