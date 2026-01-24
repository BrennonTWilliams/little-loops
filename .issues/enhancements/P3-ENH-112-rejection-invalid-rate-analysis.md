---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-112: Rejection/Invalid Rate Analysis

## Summary

Add analysis capability to track rejection and invalid closure rates across issues, identifying patterns that indicate process problems or unclear requirements.

## Motivation

When issues are frequently closed as "rejected" or "invalid", it signals problems upstream:
- Unclear issue templates leading to poorly-specified work
- Misalignment between issue creators and implementers
- Premature issue creation before proper investigation

Tracking these rates over time helps identify systemic process issues.

## Proposed Implementation

### Data Structure

```python
@dataclass
class RejectionMetrics:
    total_closed: int
    rejected_count: int
    invalid_count: int
    rejection_rate: float  # rejected / total_closed
    invalid_rate: float    # invalid / total_closed
    by_type: dict[str, float]  # rejection rate per issue type
    by_month: dict[str, float]  # rejection rate trend
    common_rejection_reasons: list[tuple[str, int]]  # (reason, count)
```

### Analysis Function

```python
def analyze_rejection_rates(issues: list[IssueHistory]) -> RejectionMetrics:
    """Analyze rejection and invalid closure patterns."""
    # Parse resolution_action field to identify rejections
    # Group by time period and issue type
    # Extract and categorize rejection reasons
```

### Helper Function

```python
def _parse_resolution_action(action: str | None) -> str:
    """Parse resolution action into categories: completed, rejected, invalid, duplicate, deferred."""
```

### Output Format

```
Rejection Analysis:
  Overall rejection rate: 8.5% (17/200)
  Invalid rate: 3.0% (6/200)

  By Type:
    BUG:  5.2% rejected
    FEAT: 12.1% rejected
    ENH:  7.8% rejected

  Trend (last 6 months):
    Oct: 15.0%  Nov: 10.2%  Dec: 8.5%  Jan: 5.1%  (improving)

  Common Rejection Reasons:
    - "duplicate of existing issue" (5)
    - "out of scope" (4)
    - "insufficient information" (3)
```

## Acceptance Criteria

- [ ] `RejectionMetrics` dataclass captures rejection/invalid statistics
- [ ] `_parse_resolution_action` helper categorizes resolution types
- [ ] Analysis shows breakdown by issue type
- [ ] Monthly trend shows direction of change
- [ ] Common rejection reasons extracted from resolution notes
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Useful for process improvement
- **Effort**: Small - Straightforward data extraction
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

None - Can be implemented independently

### Blocks

- ENH-114: Agent Effectiveness Analysis (uses `_parse_resolution_action`)

## Labels

`enhancement`, `ll-history`, `process-analysis`, `metrics`

---

**Priority**: P3 | **Created**: 2026-01-23
