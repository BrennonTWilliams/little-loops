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
    issues: list[IssueHistory],
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

- [ ] `RegressionCluster` dataclass captures regression chain details
- [ ] Analysis detects temporal and file-based regression patterns
- [ ] Severity classification based on chain length and frequency
- [ ] Time patterns identified (immediate vs chronic)
- [ ] Related files included in cluster analysis
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P2 - High value for identifying technical debt
- **Effort**: Medium - Requires temporal and relationship analysis
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-116: Hotspot Analysis (provides file extraction utilities)
- ENH-120: Complexity Proxy Analysis (enhances severity assessment)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `technical-debt`

---

**Priority**: P2 | **Created**: 2026-01-23
