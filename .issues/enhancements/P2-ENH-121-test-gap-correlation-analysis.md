---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-121: Test Gap Correlation Analysis

## Summary

Correlate bug occurrences with test coverage gaps by identifying code areas with high bug rates but few or no associated test files.

## Motivation

When bugs cluster in areas without corresponding tests, it indicates:
- Missing test coverage for critical code paths
- Test suite gaps that should be prioritized
- Risk areas that need defensive testing

This analysis directly informs test writing priorities.

## Proposed Implementation

### Data Structure

```python
@dataclass
class TestGap:
    source_file: str
    bug_count: int
    bug_ids: list[str]
    has_test_file: bool
    test_file_path: str | None
    test_gap_score: float  # bugs / (tests + 1), higher = worse
    priority: str  # "critical", "high", "medium", "low"

@dataclass
class TestGapAnalysis:
    gaps: list[TestGap]
    untested_bug_magnets: list[str]
    test_coverage_correlation: float  # -1 to 1
    priority_test_targets: list[str]
```

### Analysis Function

```python
def analyze_test_gaps(
    issues: list[IssueHistory],
    hotspots: HotspotAnalysis
) -> TestGapAnalysis:
    """Correlate bug occurrences with test coverage gaps."""
    # For each file in bug issues, check for corresponding test file
    # Calculate test gap score (bugs with no tests)
    # Identify untested bug magnets
    # Prioritize based on bug count and severity
```

### Test File Detection

```python
def _find_test_file(source_path: str) -> str | None:
    """Find corresponding test file for a source file."""
    # Check common patterns:
    # - tests/test_<name>.py
    # - tests/<path>/test_<name>.py
    # - <path>/test_<name>.py
    # - <path>/<name>_test.py
```

### Output Format

```
Test Gap Correlation Analysis:

  Critical Test Gaps (bugs in untested files):

  1. src/core/processor.py [CRITICAL]
     Bugs: 7 (BUG-012, BUG-018, BUG-025, ...)
     Test file: NONE FOUND
     Gap score: 7.0
     Action: Create tests/test_processor.py

  2. src/utils/validation.py [HIGH]
     Bugs: 6
     Test file: tests/test_validation.py (exists but may be incomplete)
     Gap score: 3.0
     Action: Review and expand test coverage

  Test Coverage Correlation:
    Files with tests: avg 0.8 bugs
    Files without tests: avg 3.2 bugs
    Correlation: -0.65 (more tests = fewer bugs)

  Priority Test Targets:
    1. src/core/processor.py - 7 bugs, no tests
    2. src/utils/validation.py - 6 bugs, weak tests
    3. src/legacy/compat.py - 4 bugs, no tests
```

## Acceptance Criteria

- [ ] `TestGap` dataclass captures source-test relationship
- [ ] Test file detection covers common naming patterns
- [ ] Gap score calculation weights bugs against test presence
- [ ] Correlation analysis shows test-bug relationship
- [ ] Priority ordering based on bug count and test status
- [ ] Actionable recommendations for each gap
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P2 - High value for quality improvement
- **Effort**: Medium - Requires file system checks and statistics
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-116: Hotspot Analysis (provides file extraction and bug magnet data)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `testing`

---

**Priority**: P2 | **Created**: 2026-01-23
