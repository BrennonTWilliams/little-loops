---
discovered_date: 2026-01-23
discovered_by: planning
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
    avg_resolution_hours: float
    median_resolution_hours: float
    issue_count: int
    slowest_issue: tuple[str, float]  # (issue_id, hours)
    complexity_score: float  # normalized 0-1
    comparison_to_baseline: str  # "2x slower", "3x slower", etc.

@dataclass
class ComplexityProxyAnalysis:
    file_complexity: list[ComplexityProxy]
    directory_complexity: list[ComplexityProxy]
    baseline_hours: float  # median across all issues
    complexity_outliers: list[str]  # files significantly above baseline
```

### Analysis Function

```python
def analyze_complexity_proxy(
    issues: list[IssueHistory],
    hotspots: HotspotAnalysis
) -> ComplexityProxyAnalysis:
    """Use issue duration as proxy for code complexity."""
    # Calculate resolution duration for each issue
    # Group by affected files/directories
    # Calculate averages and identify outliers
    # Normalize to complexity scores
```

### Duration Calculation

```python
def _calculate_duration_hours(issue: IssueHistory) -> float | None:
    """Calculate hours from creation to completion."""
    if not issue.completed_date:
        return None
    delta = issue.completed_date - issue.created_date
    return delta.total_seconds() / 3600
```

### Output Format

```
Complexity Proxy Analysis:
  Baseline resolution time: 2.5 hours (median)

  High Complexity Files (by resolution time):

  1. src/core/processor.py
     Avg resolution: 6.8 hours (2.7x baseline)
     Median: 5.2 hours
     Issues: 12
     Slowest: BUG-031 (14.5 hours)
     Complexity score: 0.89 [HIGH]

  2. src/legacy/compat.py
     Avg resolution: 5.1 hours (2.0x baseline)
     Median: 4.8 hours
     Issues: 6
     Complexity score: 0.72 [MEDIUM-HIGH]

  High Complexity Directories:

  1. src/core/ - avg 4.2 hours (1.7x baseline)
  2. src/legacy/ - avg 3.8 hours (1.5x baseline)

  Complexity Outliers (>2x baseline):
    - src/core/processor.py: 2.7x
    - src/legacy/compat.py: 2.0x
```

## Acceptance Criteria

- [ ] `ComplexityProxy` dataclass captures duration-based metrics
- [ ] Duration calculation handles missing completion dates
- [ ] Baseline established from median resolution time
- [ ] Comparison to baseline expressed as multiplier
- [ ] Outliers identified (>2x baseline)
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Valuable for refactoring prioritization
- **Effort**: Medium - Requires date parsing and statistics
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-116: Hotspot Analysis (provides path extraction utilities)

### Blocks

- ENH-117: Regression Clustering Analysis (enhances severity assessment)

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `complexity`

---

**Priority**: P3 | **Created**: 2026-01-23
