---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-119: Coupling Detection Analysis

## Summary

Identify files that frequently change together based on issue history, revealing hidden coupling that may indicate architectural problems.

## Motivation

When certain files consistently appear together in issues, it suggests:
- Tight coupling that should be made explicit
- Missing interfaces or abstractions
- Potential module boundary violations
- Candidates for refactoring into cohesive units

Understanding coupling helps guide architectural improvements.

## Proposed Implementation

### Data Structure

```python
@dataclass
class CouplingPair:
    file_a: str
    file_b: str
    co_occurrence_count: int
    coupling_strength: float  # 0-1, based on co-occurrence ratio
    issue_ids: list[str]
    coupling_type: str  # "structural", "temporal", "logical"

@dataclass
class CouplingAnalysis:
    pairs: list[CouplingPair]
    highly_coupled_clusters: list[list[str]]  # groups of tightly coupled files
    coupling_hotspots: list[str]  # files coupled with many others
    suggested_refactorings: list[str]
```

### Analysis Function

```python
def analyze_coupling(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis
) -> CouplingAnalysis:
    """Identify files that frequently change together."""
    # Build co-occurrence matrix using _extract_paths_from_issue()
    # Calculate coupling strength (co-occur / total appearances)
    # Cluster highly coupled files
    # Identify coupling hotspots (files coupled with many others)
```

### Coupling Strength Calculation

```python
def _calculate_coupling_strength(
    file_a: str,
    file_b: str,
    file_to_issues: dict[str, set[str]]
) -> float:
    """Calculate coupling strength between two files."""
    a_issues = file_to_issues.get(file_a, set())
    b_issues = file_to_issues.get(file_b, set())
    co_occur = len(a_issues & b_issues)
    # Jaccard similarity
    return co_occur / len(a_issues | b_issues) if a_issues | b_issues else 0
```

### Output Format

```
Coupling Detection Analysis:

  Highly Coupled File Pairs:

  1. src/core/processor.py <-> src/core/state.py
     Co-occurrences: 8 issues
     Coupling strength: 0.73 [HIGH]
     Issues: BUG-012, BUG-018, ENH-034, ...
     Suggestion: Consider merging or extracting shared interface

  2. src/api/handlers.py <-> src/api/middleware.py
     Co-occurrences: 5 issues
     Coupling strength: 0.56 [MEDIUM]
     Suggestion: Review interface boundaries

  Coupling Clusters:
    Cluster 1: [processor.py, state.py, events.py] - 0.65 avg strength
    Cluster 2: [handlers.py, middleware.py] - 0.56 avg strength

  Coupling Hotspots (coupled with 3+ files):
    - src/core/processor.py: coupled with 5 other files
    - src/utils/helpers.py: coupled with 4 other files
```

## Acceptance Criteria

- [x] `CouplingPair` dataclass captures file pair relationships
- [x] Coupling strength based on Jaccard similarity
- [x] Clusters identified for groups of coupled files
- [x] Hotspots flagged for files coupled with many others
- [ ] Refactoring suggestions based on coupling patterns (deferred - not implemented)
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Valuable for architecture understanding
- **Effort**: Medium - Co-occurrence matrix and clustering
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ~~ENH-116: Hotspot Analysis (provides path extraction utilities)~~ **COMPLETED**

### Blocks

None

## Labels

`enhancement`, `ll-history`, `architecture-analysis`, `coupling`

---

**Priority**: P3 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history.py`: Added CouplingPair and CouplingAnalysis dataclasses, analyze_coupling() and _build_coupling_clusters() functions, integrated into calculate_analysis() and HistoryAnalysis, added text and markdown formatting
- `scripts/tests/test_issue_history.py`: Added 11 comprehensive tests for coupling detection

### Verification Results
- Tests: PASS (168 tests)
- Lint: PASS
- Types: PASS
- Format: PASS

### Notes
- Refactoring suggestions were deferred as not essential for the core coupling detection feature
- Coupling strength uses Jaccard similarity with threshold >= 0.3 and minimum 2 co-occurrences
- Clusters use connected components with strength >= 0.5 threshold
