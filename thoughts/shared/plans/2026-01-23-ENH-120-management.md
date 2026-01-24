# ENH-120: Complexity Proxy Analysis - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-120-complexity-proxy-analysis.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `issue_history.py` module provides comprehensive analysis of completed issues. Currently, it includes:
- Hotspot analysis (files appearing in many issues)
- Coupling detection (files changing together)
- Regression clustering (fix->bug chains)
- Test gap correlation
- Rejection/invalid rate analysis
- Manual pattern detection
- Agent effectiveness analysis

### Key Discoveries
- `CompletedIssue` dataclass at `issue_history.py:67-87` has `completed_date` but NO `discovered_date` field
- `_parse_discovered_date()` function exists at `issue_history.py:961-987` but is only used for active issues, not completed
- `HotspotAnalysis` provides path extraction from issues via `_extract_paths_from_issue()` at line 1013
- Analysis functions follow consistent pattern: take `list[CompletedIssue]`, return `*Analysis` dataclass
- Integration happens in `calculate_analysis()` at lines 2160-2252
- Output formatting in `format_analysis_text()` at lines 2333-2665

## Desired End State

A new `analyze_complexity_proxy()` function that:
1. Calculates issue duration (discovered_date to completed_date)
2. Groups issues by affected files/directories
3. Computes average/median resolution times per path
4. Identifies outliers (>2x baseline resolution time)
5. Outputs complexity scores normalized 0-1

### How to Verify
- New tests pass for `ComplexityProxy` and `ComplexityProxyAnalysis` dataclasses
- New tests pass for `analyze_complexity_proxy()` function
- Duration calculation handles missing dates gracefully
- Output appears in `ll-history analyze` report

## What We're NOT Doing

- Not modifying existing analysis functions
- Not changing the CLI interface (uses existing `analyze` command)
- Not adding new command-line flags
- Not restructuring other dataclasses

## Problem Analysis

To calculate issue duration, we need both discovered and completed dates. Currently:
- `completed_date` is populated in `parse_completed_issue()`
- `discovered_date` is parsed by `_parse_discovered_date()` but NOT stored in `CompletedIssue`

The gap: `CompletedIssue` needs a `discovered_date` field, and `parse_completed_issue()` needs to call `_parse_discovered_date()`.

## Solution Approach

1. Add `discovered_date: date | None = None` field to `CompletedIssue`
2. Wire up `_parse_discovered_date()` in `parse_completed_issue()`
3. Define `ComplexityProxy` and `ComplexityProxyAnalysis` dataclasses
4. Implement `analyze_complexity_proxy()` function
5. Add field to `HistoryAnalysis` and integrate in `calculate_analysis()`
6. Add output section in `format_analysis_text()`
7. Add tests for new functionality

## Implementation Phases

### Phase 1: Extend CompletedIssue with discovered_date

#### Overview
Add the `discovered_date` field to enable duration calculations.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

1. Add field to `CompletedIssue` dataclass (after line 76):
```python
discovered_date: date | None = None
```

2. Update `to_dict()` method (after line 86):
```python
"discovered_date": (self.discovered_date.isoformat() if self.discovered_date else None),
```

3. Update `parse_completed_issue()` (after line 671):
```python
discovered_date = _parse_discovered_date(content)
```

4. Pass to constructor (line 682):
```python
discovered_date=discovered_date,
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Define Complexity Proxy Dataclasses

#### Overview
Create the dataclass structure for storing complexity proxy analysis results.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add after `AgentEffectivenessAnalysis` dataclass (around line 535), before `HistoryAnalysis`:

```python
@dataclass
class ComplexityProxy:
    """Duration-based complexity proxy for a file or directory."""

    path: str
    avg_resolution_days: float
    median_resolution_days: float
    issue_count: int
    slowest_issue: tuple[str, float]  # (issue_id, days)
    complexity_score: float  # normalized 0-1
    comparison_to_baseline: str  # "2.1x slower", etc.

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
```

Update `__all__` exports (after line 41):
```python
"ComplexityProxy",
"ComplexityProxyAnalysis",
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Implement analyze_complexity_proxy Function

#### Overview
Create the core analysis function that calculates duration-based complexity metrics.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add after `analyze_agent_effectiveness()` function (around line 1920), before `_calculate_debt_metrics()`:

```python
def analyze_complexity_proxy(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
) -> ComplexityProxyAnalysis:
    """Use issue duration as proxy for code complexity.

    Areas that consistently take longer to resolve suggest higher complexity,
    insufficient documentation, or accumulated technical debt.

    Args:
        issues: List of completed issues with dates
        hotspots: Pre-computed hotspot analysis for path information

    Returns:
        ComplexityProxyAnalysis with duration-based complexity metrics
    """
    # Calculate durations for all issues with both dates
    issue_durations: dict[str, float] = {}  # issue_id -> days
    for issue in issues:
        if issue.discovered_date and issue.completed_date:
            delta = issue.completed_date - issue.discovered_date
            days = delta.days + (delta.seconds / 86400) if hasattr(delta, 'seconds') else float(delta.days)
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

    # Map issues to their affected files using hotspot data
    issue_to_files: dict[str, list[str]] = {}
    for issue in issues:
        if issue.issue_id in issue_durations:
            try:
                content = issue.path.read_text(encoding="utf-8")
                paths = _extract_paths_from_issue(content)
                if paths:
                    issue_to_files[issue.issue_id] = paths
            except Exception:
                continue

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
```

Add to `__all__` exports:
```python
"analyze_complexity_proxy",
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 4: Integrate into HistoryAnalysis and calculate_analysis

#### Overview
Wire the new analysis into the main analysis flow.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

1. Add field to `HistoryAnalysis` dataclass (after line 582, after `agent_effectiveness_analysis`):
```python
# Complexity proxy analysis
complexity_proxy_analysis: ComplexityProxyAnalysis | None = None
```

2. Update `HistoryAnalysis.to_dict()` (after line 629):
```python
"complexity_proxy_analysis": (
    self.complexity_proxy_analysis.to_dict()
    if self.complexity_proxy_analysis
    else None
),
```

3. Call in `calculate_analysis()` (after line 2227, after agent_effectiveness):
```python
# Complexity proxy analysis
complexity_proxy_analysis = analyze_complexity_proxy(completed_issues, hotspot_analysis)
```

4. Add to `HistoryAnalysis` constructor (after line 2250):
```python
complexity_proxy_analysis=complexity_proxy_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 5: Add Output Formatting

#### Overview
Add the complexity proxy section to the text output formatter.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

Add after agent effectiveness section (around line 2627), before technical debt section:

```python
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
        for i, c in enumerate(cpa.file_complexity[:5], 1):
            score_label = (
                "HIGH" if c.complexity_score >= 0.7
                else "MEDIUM" if c.complexity_score >= 0.4
                else "LOW"
            )
            lines.append(f"  {i}. {c.path}")
            lines.append(f"     Avg: {c.avg_resolution_days:.1f} days ({c.comparison_to_baseline})")
            lines.append(f"     Median: {c.median_resolution_days:.1f} days, Issues: {c.issue_count}")
            lines.append(f"     Slowest: {c.slowest_issue[0]} ({c.slowest_issue[1]:.1f} days)")
            lines.append(f"     Complexity score: {c.complexity_score:.2f} [{score_label}]")

    if cpa.directory_complexity:
        lines.append("")
        lines.append("  High Complexity Directories:")
        for c in cpa.directory_complexity[:5]:
            lines.append(f"    {c.path}: avg {c.avg_resolution_days:.1f} days ({c.comparison_to_baseline})")

    if cpa.complexity_outliers:
        lines.append("")
        lines.append("  Complexity Outliers (>2x baseline):")
        for path in cpa.complexity_outliers[:5]:
            lines.append(f"    - {path}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 6: Add Tests

#### Overview
Add comprehensive tests for the new functionality.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`

Add imports at top:
```python
from little_loops.issue_history import (
    # ... existing imports ...
    ComplexityProxy,
    ComplexityProxyAnalysis,
    analyze_complexity_proxy,
)
```

Add test classes:

```python
class TestComplexityProxy:
    """Tests for ComplexityProxy dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        proxy = ComplexityProxy(
            path="src/core/processor.py",
            avg_resolution_days=6.8,
            median_resolution_days=5.2,
            issue_count=12,
            slowest_issue=("BUG-031", 14.5),
            complexity_score=0.89,
            comparison_to_baseline="2.7x baseline",
        )
        result = proxy.to_dict()

        assert result["path"] == "src/core/processor.py"
        assert result["avg_resolution_days"] == 6.8
        assert result["median_resolution_days"] == 5.2
        assert result["issue_count"] == 12
        assert result["slowest_issue"]["issue_id"] == "BUG-031"
        assert result["slowest_issue"]["days"] == 14.5
        assert result["complexity_score"] == 0.89
        assert result["comparison_to_baseline"] == "2.7x baseline"


class TestComplexityProxyAnalysis:
    """Tests for ComplexityProxyAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty lists."""
        analysis = ComplexityProxyAnalysis()
        result = analysis.to_dict()

        assert result["file_complexity"] == []
        assert result["directory_complexity"] == []
        assert result["baseline_days"] == 0.0
        assert result["complexity_outliers"] == []

    def test_to_dict_with_data(self) -> None:
        """Test to_dict with complexity data."""
        proxy = ComplexityProxy(
            path="test.py",
            avg_resolution_days=5.0,
            median_resolution_days=4.0,
            issue_count=3,
            slowest_issue=("BUG-001", 8.0),
            complexity_score=0.5,
            comparison_to_baseline="2.0x baseline",
        )
        analysis = ComplexityProxyAnalysis(
            file_complexity=[proxy],
            baseline_days=2.5,
            complexity_outliers=["test.py"],
        )
        result = analysis.to_dict()

        assert len(result["file_complexity"]) == 1
        assert result["baseline_days"] == 2.5
        assert result["complexity_outliers"] == ["test.py"]


class TestAnalyzeComplexityProxy:
    """Tests for analyze_complexity_proxy function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        result = analyze_complexity_proxy([], HotspotAnalysis())
        assert result.file_complexity == []
        assert result.directory_complexity == []
        assert result.baseline_days == 0.0

    def test_issues_without_dates(self, tmp_path: Path) -> None:
        """Test with issues missing discovered_date."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/test.py`\n\nBug description.")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 15),
                # No discovered_date
            )
        ]

        result = analyze_complexity_proxy(issues, HotspotAnalysis())
        assert result.file_complexity == []  # No duration calculable

    def test_duration_calculation(self, tmp_path: Path) -> None:
        """Test that durations are calculated correctly."""
        # Create two issues for same file with different durations
        issues = []
        for i, (disc, comp) in enumerate([
            (date(2026, 1, 1), date(2026, 1, 5)),   # 4 days
            (date(2026, 1, 10), date(2026, 1, 20)), # 10 days
        ]):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text("**File**: `src/complex.py`\n\nBug in complex code.")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    discovered_date=disc,
                    completed_date=comp,
                )
            )

        result = analyze_complexity_proxy(issues, HotspotAnalysis())

        # Should have file complexity for src/complex.py
        assert len(result.file_complexity) == 1
        fc = result.file_complexity[0]
        assert fc.path == "src/complex.py"
        assert fc.avg_resolution_days == 7.0  # (4 + 10) / 2
        assert fc.issue_count == 2

    def test_outlier_detection(self, tmp_path: Path) -> None:
        """Test that outliers >2x baseline are detected."""
        issues = []
        # Create 3 issues: 2 fast (2 days each), 1 slow (10 days)
        durations = [
            (date(2026, 1, 1), date(2026, 1, 3), "fast1.py"),   # 2 days
            (date(2026, 1, 1), date(2026, 1, 3), "fast2.py"),   # 2 days
            (date(2026, 1, 1), date(2026, 1, 11), "slow.py"),   # 10 days
        ]
        for i, (disc, comp, file) in enumerate(durations):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text(f"**File**: `src/{file}`\n\nBug.")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    discovered_date=disc,
                    completed_date=comp,
                )
            )
        # Add duplicate issues for same files to meet 2-issue threshold
        for i, (disc, comp, file) in enumerate(durations):
            issue_file = tmp_path / f"P1-ENH-{i:03d}.md"
            issue_file.write_text(f"**File**: `src/{file}`\n\nEnhancement.")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="ENH",
                    priority="P1",
                    issue_id=f"ENH-{i:03d}",
                    discovered_date=disc,
                    completed_date=comp,
                )
            )

        result = analyze_complexity_proxy(issues, HotspotAnalysis())

        # Baseline should be 2 days (median of [2, 2, 2, 2, 10, 10])
        # slow.py at 10 days should be an outlier (>4 days = 2x baseline)
        assert "src/slow.py" in result.complexity_outliers
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `TestComplexityProxy`: Dataclass serialization
- `TestComplexityProxyAnalysis`: Container dataclass with nesting
- `TestAnalyzeComplexityProxy`: Core analysis logic

### Key Edge Cases
- Empty issues list
- Issues without discovered_date
- Issues without completed_date
- Single issue per file (below threshold)
- All issues same duration (no outliers)

## References

- Original issue: `.issues/enhancements/P3-ENH-120-complexity-proxy-analysis.md`
- Similar implementation: `analyze_hotspots()` at `issue_history.py:1283`
- Path extraction: `_extract_paths_from_issue()` at `issue_history.py:1013`
- Date parsing: `_parse_discovered_date()` at `issue_history.py:961`
