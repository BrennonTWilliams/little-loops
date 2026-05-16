---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-117: Regression Clustering Analysis

## Summary

Detect files where fixes frequently lead to new bugs, indicating fragile code that may need architectural attention.

## Motivation

When fixing a bug in file A leads to a new bug in the same file (or closely related files), it indicates:
- Hidden dependencies and coupling
- Missing test coverage
- Overly complex code with many edge cases
- Architectural issues requiring deeper refactoring

Regression clustering helps identify code that's becoming unmaintainable.

## Proposed Implementation

### Data Structure

```python
@dataclass
class RegressionCluster:
    primary_file: str
    regression_count: int
    fix_bug_pairs: list[tuple[str, str]]  # (fixed_bug_id, caused_bug_id)
    related_files: list[str]  # files affected in regression chain
    time_pattern: str  # "immediate", "delayed", "chronic"
    severity: str  # "critical", "high", "medium"

@dataclass
class RegressionAnalysis:
    clusters: list[RegressionCluster]
    total_regression_chains: int
    most_fragile_files: list[str]
```

### Analysis Function

```python
def analyze_regression_clustering(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis
) -> RegressionAnalysis:
    """Detect files where fixes frequently cause new bugs."""
    # Order issues by completion date
    # For each BUG, check if it mentions fixing a previous bug
    # Identify files that appear in fix-then-break patterns
    # Cluster related regressions
```

### Regression Detection Heuristics

1. **Temporal proximity**: Bug B created within 7 days of Bug A's fix
2. **File overlap**: Both bugs affect same file(s)
3. **Explicit mention**: Bug B references Bug A in description
4. **Related component**: Bugs in same directory/module

### Output Format

```
Regression Clustering Analysis:
  Total regression chains detected: 8

  Fragile Code Clusters:

  1. src/core/processor.py [CRITICAL]
     Regression count: 4
     Pattern: chronic (recurring over 3+ months)
     Chain: BUG-012 fix -> BUG-018 -> BUG-025 -> BUG-031
     Related files: src/core/state.py, src/core/events.py
     Recommendation: Major refactoring needed

  2. src/api/handlers.py [HIGH]
     Regression count: 2
     Pattern: immediate (bugs within days of fixes)
     Chain: BUG-045 fix -> BUG-047
     Recommendation: Add integration tests

  Summary:
    Most fragile: src/core/processor.py (4 regression chains)
    Total files in regression patterns: 6
```

## Acceptance Criteria

- [x] `RegressionCluster` dataclass captures regression chain details
- [x] Analysis detects temporal and file-based regression patterns
- [x] Severity classification based on chain length and frequency
- [x] Time patterns identified (immediate vs chronic)
- [x] Related files included in cluster analysis
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P2 - High value for identifying technical debt
- **Effort**: Medium - Requires temporal and relationship analysis
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-116: Hotspot Analysis (provides file extraction utilities) ✅ Completed

### Optional Enhancements

- ENH-120: Complexity Proxy Analysis (can enhance severity assessment, not required)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `technical-debt`

---

**Priority**: P2 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made

- `scripts/little_loops/issue_history.py`: Added `RegressionCluster` and `RegressionAnalysis` dataclasses for regression pattern tracking
- `scripts/little_loops/issue_history.py`: Implemented `analyze_regression_clustering()` function using temporal proximity and file overlap heuristics
- `scripts/little_loops/issue_history.py`: Integrated regression analysis into `HistoryAnalysis` dataclass and `calculate_analysis()` function
- `scripts/little_loops/issue_history.py`: Added regression clustering sections to `format_analysis_text()` and `format_analysis_markdown()` formatters
- `scripts/tests/test_issue_history.py`: Added comprehensive tests for all new regression clustering functionality (13 test cases)

### Verification Results

- Tests: PASS (92 tests)
- Lint: PASS
- Types: PASS
