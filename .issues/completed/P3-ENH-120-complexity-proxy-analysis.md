---
discovered_date: 2026-01-23
discovered_by: planning
anchor: scripts/little_loops/issue_history.py::analyze_complexity_proxy
---

# ENH-120: Complexity Proxy Analysis

## Summary

Use issue duration and resolution difficulty as proxies for code complexity, identifying areas that consistently take longer to resolve.

## Motivation

When issues in certain areas consistently take longer to resolve, it suggests:
- High code complexity making changes difficult
- Insufficient documentation or unclear code
- Missing tests making verification time-consuming
- Technical debt accumulating in specific areas

Duration-based complexity analysis provides actionable refactoring targets.

## Proposed Implementation

### Data Structure

```python
@dataclass
class ComplexityProxy:
    path: str
    avg_resolution_days: float
    median_resolution_days: float
    issue_count: int
    slowest_issue: tuple[str, float]  # (issue_id, days)
    complexity_score: float  # normalized 0-1
    comparison_to_baseline: str  # "2x slower", "3x slower", etc.

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "avg_resolution_days": round(self.avg_resolution_days, 1),
            "median_resolution_days": round(self.median_resolution_days, 1),
            "issue_count": self.issue_count,
            "slowest_issue": self.slowest_issue,
            "complexity_score": round(self.complexity_score, 3),
            "comparison_to_baseline": self.comparison_to_baseline,
        }

@dataclass
class ComplexityProxyAnalysis:
    file_complexity: list[ComplexityProxy]
    directory_complexity: list[ComplexityProxy]
    baseline_days: float  # median across all issues
    complexity_outliers: list[str]  # files significantly above baseline

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_complexity": [c.to_dict() for c in self.file_complexity],
            "directory_complexity": [c.to_dict() for c in self.directory_complexity],
            "baseline_days": round(self.baseline_days, 1),
            "complexity_outliers": self.complexity_outliers[:10],
        }
```

### Analysis Function

```python
def analyze_complexity_proxy(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis
) -> ComplexityProxyAnalysis:
    """Use issue duration as proxy for code complexity."""
    # Calculate resolution duration for each issue
    # Group by affected files/directories
    # Calculate averages and identify outliers
    # Normalize to complexity scores
```

### Duration Calculation

**Note**: The `CompletedIssue` dataclass has `completed_date` but needs `discovered_date` to be added. The `_parse_discovered_date` function already exists in `issue_history.py:961` and parses this from YAML frontmatter.

```python
# First, add discovered_date field to CompletedIssue dataclass
# discovered_date: date | None = None  # Add after discovered_by field

def _calculate_duration_days(issue: CompletedIssue) -> float | None:
    """Calculate days from discovery to completion."""
    if not issue.completed_date or not issue.discovered_date:
        return None
    delta = issue.completed_date - issue.discovered_date
    return delta.days + (delta.seconds / 86400)  # Include fractional days
```

### Output Format

```
Complexity Proxy Analysis:
  Baseline resolution time: 2.5 days (median)

  High Complexity Files (by resolution time):

  1. src/core/processor.py
     Avg resolution: 6.8 days (2.7x baseline)
     Median: 5.2 days
     Issues: 12
     Slowest: BUG-031 (14.5 days)
     Complexity score: 0.89 [HIGH]

  2. src/legacy/compat.py
     Avg resolution: 5.1 days (2.0x baseline)
     Median: 4.8 days
     Issues: 6
     Complexity score: 0.72 [MEDIUM-HIGH]

  High Complexity Directories:

  1. src/core/ - avg 4.2 days (1.7x baseline)
  2. src/legacy/ - avg 3.8 days (1.5x baseline)

  Complexity Outliers (>2x baseline):
    - src/core/processor.py: 2.7x
    - src/legacy/compat.py: 2.0x
```

## Acceptance Criteria

- [x] Add `discovered_date: date | None = None` field to `CompletedIssue` dataclass
- [x] Wire up `_parse_discovered_date()` (already exists at line 961) to populate the new field
- [x] `ComplexityProxy` dataclass captures duration-based metrics
- [x] Duration calculation handles missing discovered/completion dates gracefully
- [x] Baseline established from median resolution time
- [x] Comparison to baseline expressed as multiplier
- [x] Outliers identified (>2x baseline)
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Valuable for refactoring prioritization
- **Effort**: Medium - Requires date parsing and statistics
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ~~ENH-116: Hotspot Analysis~~ (COMPLETED - provides `HotspotAnalysis` dataclass and path extraction utilities)

### Blocks

- ~~ENH-117: Regression Clustering Analysis~~ (COMPLETED - no longer blocked by this issue)

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `complexity`

---

**Priority**: P3 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history.py`: Added `discovered_date` field to `CompletedIssue` dataclass and wired up parsing
- `scripts/little_loops/issue_history.py`: Added `ComplexityProxy` and `ComplexityProxyAnalysis` dataclasses
- `scripts/little_loops/issue_history.py`: Implemented `analyze_complexity_proxy()` function
- `scripts/little_loops/issue_history.py`: Integrated into `calculate_analysis()` and `format_analysis_text()`
- `scripts/tests/test_issue_history.py`: Added comprehensive tests for new functionality

### Verification Results
- Tests: PASS (177 tests, all passing)
- Lint: PASS
- Types: PASS
