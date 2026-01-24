---
discovered_date: 2026-01-23
discovered_by: planning
anchor: scripts/little_loops/issue_history.py::calculate_analysis
---

# ENH-116: Hotspot Analysis

## Summary

Identify files and directories that appear repeatedly in issues, indicating architectural hotspots that may need refactoring attention.

## Motivation

When the same files appear in many issues, it often indicates:
- Code that's doing too much (violating single responsibility)
- Missing abstractions causing scattered changes
- Technical debt accumulating in specific areas
- Coupling issues making changes risky

Hotspot analysis is a foundation for deeper architectural insights.

## Proposed Implementation

### Data Structure

```python
@dataclass
class Hotspot:
    path: str
    issue_count: int
    issue_ids: list[str]
    issue_types: dict[str, int]  # {"BUG": 5, "ENH": 3}
    bug_ratio: float  # bugs / total issues
    churn_indicator: str  # "high", "medium", "low"

@dataclass
class HotspotAnalysis:
    file_hotspots: list[Hotspot]
    directory_hotspots: list[Hotspot]
    bug_magnets: list[Hotspot]  # files with high bug ratio
```

### Analysis Function

```python
def analyze_hotspots(issues: list[CompletedIssue]) -> HotspotAnalysis:
    """Identify files and directories that appear repeatedly in issues."""
    # Extract file paths from issue descriptions and affected_files
    # Aggregate by file and directory
    # Calculate bug ratios and churn indicators
    # Sort by issue count
```

### Path Extraction Helper

```python
def _extract_paths_from_issue(issue: CompletedIssue) -> list[str]:
    """Extract file paths from issue description and affected_files field."""
    # Parse affected_files field
    # Extract paths from description (e.g., `path/to/file.py:123`)
    # Normalize paths
```

### Output Format

```
Hotspot Analysis:

  Top File Hotspots:
    1. src/core/processor.py     - 12 issues (7 BUG, 5 ENH) [HIGH CHURN]
    2. src/api/handlers.py       - 9 issues (4 BUG, 3 ENH, 2 FEAT)
    3. src/utils/validation.py   - 8 issues (6 BUG, 2 ENH) [BUG MAGNET]

  Top Directory Hotspots:
    1. src/core/       - 28 issues across 6 files
    2. src/api/        - 19 issues across 4 files
    3. scripts/        - 15 issues across 8 files

  Bug Magnets (>60% bug ratio):
    - src/utils/validation.py: 75% bugs (6/8)
    - src/legacy/compat.py: 67% bugs (4/6)

  Recommendation: Consider refactoring src/core/processor.py
  (highest issue count with significant bug ratio)
```

## Acceptance Criteria

- [x] `Hotspot` dataclass captures path, counts, and bug ratio
- [x] `_extract_paths_from_issue` helper extracts paths reliably
- [x] Analysis identifies both file and directory hotspots
- [x] Bug magnets highlighted (high bug-to-total ratio)
- [x] Churn indicator based on frequency
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P2 - High value foundation for architecture analysis
- **Effort**: Medium - Path extraction and aggregation
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

None - Foundation analysis

### Blocks

- ENH-117: Regression Clustering Analysis
- ENH-118: Cross-Cutting Concern Smell Detection
- ENH-119: Coupling Detection Analysis
- ENH-120: Complexity Proxy Analysis
- ENH-121: Test Gap Correlation Analysis

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `foundation`

---

**Priority**: P2 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made

- `scripts/little_loops/issue_history.py`: Added `Hotspot` and `HotspotAnalysis` dataclasses, `_extract_paths_from_issue()` helper, and `analyze_hotspots()` function
- `scripts/little_loops/issue_history.py`: Integrated hotspot analysis into `calculate_analysis()` and `HistoryAnalysis` dataclass
- `scripts/little_loops/issue_history.py`: Added hotspot sections to `format_analysis_text()` and `format_analysis_markdown()` formatters
- `scripts/tests/test_issue_history.py`: Added comprehensive tests for all new hotspot functionality

### Verification Results

- Tests: PASS (79 tests)
- Lint: PASS
- Types: PASS
