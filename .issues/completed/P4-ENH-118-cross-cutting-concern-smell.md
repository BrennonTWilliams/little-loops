---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-118: Cross-Cutting Concern Smell Detection

## Summary

Detect when issues consistently touch multiple unrelated areas, suggesting missing abstractions for cross-cutting concerns like logging, error handling, or validation.

## Motivation

When single issues frequently require changes across many unrelated files, it often indicates:
- Cross-cutting concerns scattered throughout the codebase
- Missing middleware, decorators, or aspect-oriented patterns
- Lack of proper abstraction for common functionality

Identifying these patterns helps prioritize architectural improvements.

## Proposed Implementation

### Data Structure

```python
@dataclass
class CrossCuttingSmell:
    concern_type: str  # "logging", "error-handling", "validation", "auth", "caching"
    affected_directories: list[str]
    issue_count: int
    issue_ids: list[str]
    scatter_score: float  # higher = more scattered
    suggested_pattern: str  # "middleware", "decorator", "aspect"

@dataclass
class CrossCuttingAnalysis:
    smells: list[CrossCuttingSmell]
    most_scattered_concern: str
    consolidation_opportunities: list[str]
```

### Analysis Function

```python
def detect_cross_cutting_smells(
    issues: list[IssueHistory],
    hotspots: HotspotAnalysis
) -> CrossCuttingAnalysis:
    """Detect cross-cutting concerns scattered across the codebase."""
    # For each issue, count directories touched
    # Identify issues touching 3+ unrelated directories
    # Categorize by concern type (based on keywords)
    # Calculate scatter scores
```

### Concern Detection Keywords

```python
CONCERN_KEYWORDS = {
    "logging": ["log", "logger", "logging", "debug", "trace"],
    "error-handling": ["error", "exception", "try", "catch", "raise"],
    "validation": ["valid", "validate", "check", "assert", "verify"],
    "auth": ["auth", "permission", "role", "access", "token"],
    "caching": ["cache", "memo", "store", "ttl", "expire"],
}
```

### Output Format

```
Cross-Cutting Concern Analysis:

  Detected Smells:

  1. Error Handling [HIGH SCATTER]
     Directories affected: src/api/, src/core/, src/utils/, scripts/
     Issues: BUG-023, BUG-045, ENH-078 (3 issues)
     Scatter score: 0.85
     Suggestion: Implement centralized error middleware
     Pattern: middleware or decorator

  2. Logging
     Directories affected: src/core/, src/services/
     Issues: ENH-034, ENH-056 (2 issues)
     Scatter score: 0.45
     Suggestion: Consider logging decorator or aspect

  Consolidation Opportunities:
    - Centralize error handling (3 issues would benefit)
    - Create logging abstraction (2 issues would benefit)
```

## Acceptance Criteria

- [x] `CrossCuttingSmell` dataclass captures concern details
- [x] Keyword-based concern type detection
- [x] Scatter score calculated based on directory spread
- [x] Pattern suggestions for consolidation
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P4 - Nice to have for architecture improvement
- **Effort**: Small - Keyword matching and counting
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-116: Hotspot Analysis (provides path extraction utilities)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `code-smells`

---

**Priority**: P4 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history.py`: Added `CrossCuttingSmell` and `CrossCuttingAnalysis` dataclasses
- `scripts/little_loops/issue_history.py`: Added `_CROSS_CUTTING_KEYWORDS` and `_CONCERN_PATTERNS` constants
- `scripts/little_loops/issue_history.py`: Added `detect_cross_cutting_smells()` function
- `scripts/little_loops/issue_history.py`: Integrated into `calculate_analysis()` and `format_analysis_text()`
- `scripts/tests/test_issue_history.py`: Added comprehensive tests for new functionality

### Verification Results
- Tests: PASS (199 tests, all passing)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
