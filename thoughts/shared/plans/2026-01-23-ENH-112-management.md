# ENH-112: Rejection/Invalid Rate Analysis - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-112-rejection-invalid-rate-analysis.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-history` module (`scripts/little_loops/issue_history.py`) provides comprehensive analysis of completed issues including hotspot detection, regression clustering, and test gap analysis. The module follows established patterns:

### Key Discoveries
- Resolution sections contain `**Action**:`, `**Status**:`, `**Reason**:`, and `**Closure**:` fields (`issue_lifecycle.py:23-117`)
- Completed issues use `**Action**: fix/implement` with `**Status**: Completed` (`issue_lifecycle.py:105-107`)
- Closed issues use `**Status**: Closed - Already Fixed` with `**Reason**: already_fixed` (`issue_lifecycle.py:59-61`)
- Existing parsing functions at `issue_history.py:459-511` handle frontmatter and completion dates
- Analysis functions return dataclasses with `to_dict()` methods for serialization
- `calculate_analysis()` at line 1410 orchestrates all analysis types
- `HistoryAnalysis` at line 335 is the container dataclass for all analysis results

### Resolution Section Formats Found

**Completion** (from `_build_completion_resolution`):
```markdown
## Resolution
- **Action**: fix
- **Completed**: YYYY-MM-DD
- **Status**: Completed
```

**Closure** (from `_build_closure_resolution`):
```markdown
## Resolution
- **Status**: Closed - Already Fixed
- **Closed**: YYYY-MM-DD
- **Reason**: already_fixed
- **Closure**: Automated (ready_issue validation)
```

## Desired End State

New analysis capability that:
1. Parses resolution action/status to categorize issue outcomes
2. Calculates rejection and invalid closure rates
3. Groups rates by issue type and time period
4. Extracts common rejection reasons
5. Integrates into the existing `ll-history analyze` report

### How to Verify
- Run `ll-history analyze` and see Rejection Analysis section in output
- Verify JSON/YAML output includes `rejection_analysis` field
- Unit tests pass for all new dataclasses and functions

## What We're NOT Doing

- Not modifying `CompletedIssue` dataclass - keeping parsing in analysis function
- Not adding CLI flags - analysis runs automatically as part of full analysis
- Not persisting parsed resolution actions - computed on-demand like other analyses
- Not changing how issues are closed/completed - read-only analysis only

## Problem Analysis

Currently there's no way to track how often issues are rejected or closed as invalid. The data exists in resolution sections but isn't parsed or analyzed. This enhancement adds read-only analysis of existing resolution data.

## Solution Approach

1. Add `_parse_resolution_action()` helper to extract resolution category from issue content
2. Create `RejectionMetrics` dataclass to hold per-type and per-month statistics
3. Create `RejectionAnalysis` container dataclass
4. Implement `analyze_rejection_rates()` function following existing patterns
5. Integrate into `HistoryAnalysis` and `calculate_analysis()`
6. Add text and markdown formatting sections
7. Add comprehensive unit tests

## Implementation Phases

### Phase 1: Add Resolution Parsing Helper

#### Overview
Add a helper function to parse resolution action from issue content, categorizing into: completed, rejected, invalid, duplicate, deferred.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `_parse_completion_date()` (around line 512)
**Changes**: Add new parsing helper function

```python
def _parse_resolution_action(content: str) -> str:
    """Extract resolution action category from issue content.

    Categorizes based on Resolution section fields:
    - "completed": Normal completion with **Action**: fix/implement
    - "rejected": Explicitly rejected (out of scope, not valid)
    - "invalid": Invalid reference or spec
    - "duplicate": Duplicate of existing issue
    - "deferred": Deferred to future work

    Args:
        content: Issue file content

    Returns:
        Resolution category string
    """
    # Look for Status field patterns
    status_match = re.search(r"\*\*Status\*\*:\s*(.+?)(?:\n|$)", content)
    if status_match:
        status = status_match.group(1).strip().lower()
        if "closed" in status:
            # Check Reason field for specific category
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip().lower()
                if "duplicate" in reason:
                    return "duplicate"
                if "invalid" in reason:
                    return "invalid"
                if "deferred" in reason:
                    return "deferred"
                if "rejected" in reason or "out of scope" in reason:
                    return "rejected"
            # Generic closed without specific reason
            return "rejected"

    # Check for Action field (normal completion)
    action_match = re.search(r"\*\*Action\*\*:\s*(.+?)(?:\n|$)", content)
    if action_match:
        return "completed"

    # Default to completed if no resolution section
    return "completed"
```

#### Success Criteria

**Automated Verification**:
- [ ] Unit tests pass: `python -m pytest scripts/tests/test_issue_history.py -k "test_parse_resolution" -v`

---

### Phase 2: Add Dataclasses

#### Overview
Add `RejectionMetrics` and `RejectionAnalysis` dataclasses following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `TestGapAnalysis` (around line 310)
**Changes**: Add two new dataclasses

```python
@dataclass
class RejectionMetrics:
    """Metrics for rejection and invalid closure tracking."""

    total_closed: int = 0
    rejected_count: int = 0
    invalid_count: int = 0
    duplicate_count: int = 0
    deferred_count: int = 0
    completed_count: int = 0

    @property
    def rejection_rate(self) -> float:
        """Calculate rejection rate."""
        if self.total_closed == 0:
            return 0.0
        return self.rejected_count / self.total_closed

    @property
    def invalid_rate(self) -> float:
        """Calculate invalid rate."""
        if self.total_closed == 0:
            return 0.0
        return self.invalid_count / self.total_closed

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_closed": self.total_closed,
            "rejected_count": self.rejected_count,
            "invalid_count": self.invalid_count,
            "duplicate_count": self.duplicate_count,
            "deferred_count": self.deferred_count,
            "completed_count": self.completed_count,
            "rejection_rate": round(self.rejection_rate, 3),
            "invalid_rate": round(self.invalid_rate, 3),
        }


@dataclass
class RejectionAnalysis:
    """Analysis of rejection and invalid closure patterns."""

    overall: RejectionMetrics = field(default_factory=RejectionMetrics)
    by_type: dict[str, RejectionMetrics] = field(default_factory=dict)
    by_month: dict[str, RejectionMetrics] = field(default_factory=dict)
    common_reasons: list[tuple[str, int]] = field(default_factory=list)
    trend: str = "stable"  # "improving", "stable", "degrading"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "overall": self.overall.to_dict(),
            "by_type": {k: v.to_dict() for k, v in self.by_type.items()},
            "by_month": {k: v.to_dict() for k, v in sorted(self.by_month.items())},
            "common_reasons": self.common_reasons[:10],
            "trend": self.trend,
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Unit tests pass: `python -m pytest scripts/tests/test_issue_history.py -k "TestRejectionMetrics or TestRejectionAnalysis" -v`

---

### Phase 3: Implement Analysis Function

#### Overview
Add `analyze_rejection_rates()` function to calculate rejection statistics.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `analyze_test_gaps()` (around line 1304)
**Changes**: Add new analysis function

```python
def analyze_rejection_rates(issues: list[CompletedIssue]) -> RejectionAnalysis:
    """Analyze rejection and invalid closure patterns.

    Args:
        issues: List of completed issues

    Returns:
        RejectionAnalysis with overall and grouped metrics
    """
    if not issues:
        return RejectionAnalysis()

    # Count by category
    overall = RejectionMetrics()
    by_type: dict[str, RejectionMetrics] = {}
    by_month: dict[str, RejectionMetrics] = {}
    reason_counts: dict[str, int] = {}

    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8")
        except Exception:
            continue

        category = _parse_resolution_action(content)
        overall.total_closed += 1

        # Update overall counts
        if category == "completed":
            overall.completed_count += 1
        elif category == "rejected":
            overall.rejected_count += 1
        elif category == "invalid":
            overall.invalid_count += 1
        elif category == "duplicate":
            overall.duplicate_count += 1
        elif category == "deferred":
            overall.deferred_count += 1

        # By type
        if issue.issue_type not in by_type:
            by_type[issue.issue_type] = RejectionMetrics()
        type_metrics = by_type[issue.issue_type]
        type_metrics.total_closed += 1
        if category == "rejected":
            type_metrics.rejected_count += 1
        elif category == "invalid":
            type_metrics.invalid_count += 1
        elif category == "duplicate":
            type_metrics.duplicate_count += 1
        elif category == "deferred":
            type_metrics.deferred_count += 1
        elif category == "completed":
            type_metrics.completed_count += 1

        # By month
        if issue.completed_date:
            month_key = issue.completed_date.strftime("%Y-%m")
            if month_key not in by_month:
                by_month[month_key] = RejectionMetrics()
            month_metrics = by_month[month_key]
            month_metrics.total_closed += 1
            if category == "rejected":
                month_metrics.rejected_count += 1
            elif category == "invalid":
                month_metrics.invalid_count += 1
            elif category == "duplicate":
                month_metrics.duplicate_count += 1
            elif category == "deferred":
                month_metrics.deferred_count += 1
            elif category == "completed":
                month_metrics.completed_count += 1

        # Extract reason for rejection/invalid
        if category in ("rejected", "invalid", "duplicate", "deferred"):
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip()
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # Calculate trend from monthly data
    sorted_months = sorted(by_month.keys())
    if len(sorted_months) >= 3:
        recent = sorted_months[-3:]
        rates = [by_month[m].rejection_rate + by_month[m].invalid_rate for m in recent]
        if rates[-1] < rates[0] * 0.8:
            trend = "improving"
        elif rates[-1] > rates[0] * 1.2:
            trend = "degrading"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Sort reasons by count
    common_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:10]

    return RejectionAnalysis(
        overall=overall,
        by_type=by_type,
        by_month=by_month,
        common_reasons=common_reasons,
        trend=trend,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Unit tests pass: `python -m pytest scripts/tests/test_issue_history.py -k "TestAnalyzeRejectionRates" -v`

---

### Phase 4: Integration

#### Overview
Integrate the new analysis into `HistoryAnalysis`, `calculate_analysis()`, and update `__all__` exports.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Update `__all__` (line 23)
```python
__all__ = [
    # Core dataclasses
    "CompletedIssue",
    "HistorySummary",
    # Advanced analysis dataclasses
    "PeriodMetrics",
    "SubsystemHealth",
    "Hotspot",
    "HotspotAnalysis",
    "RegressionCluster",
    "RegressionAnalysis",
    "TestGap",
    "TestGapAnalysis",
    "RejectionMetrics",      # NEW
    "RejectionAnalysis",     # NEW
    "TechnicalDebtMetrics",
    "HistoryAnalysis",
    # ... rest unchanged ...
    "analyze_rejection_rates",  # NEW - add in Summary functions section
]
```

**Change 2**: Update `HistoryAnalysis` (add field after test_gap_analysis around line 363)
```python
    # Rejection analysis
    rejection_analysis: RejectionAnalysis | None = None
```

**Change 3**: Update `HistoryAnalysis.to_dict()` (add after test_gap_analysis serialization)
```python
            "rejection_analysis": (
                self.rejection_analysis.to_dict() if self.rejection_analysis else None
            ),
```

**Change 4**: Update `calculate_analysis()` (after test_gap_analysis call around line 1465)
```python
    # Rejection rate analysis
    rejection_analysis = analyze_rejection_rates(completed_issues)
```

**Change 5**: Update `calculate_analysis()` return (add to HistoryAnalysis constructor)
```python
        rejection_analysis=rejection_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Integration test passes: `python -m pytest scripts/tests/test_issue_history.py -k "TestCalculateAnalysis" -v`
- [ ] JSON output includes rejection_analysis: `ll-history analyze --format json | python -c "import json,sys; d=json.load(sys.stdin); print('rejection_analysis' in d)"`

---

### Phase 5: Add Text and Markdown Formatting

#### Overview
Add rejection analysis sections to text and markdown output formatters.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Update `format_analysis_text()` (add after Technical Debt section, around line 1725)
```python
    # Rejection analysis
    if analysis.rejection_analysis:
        rej = analysis.rejection_analysis
        overall = rej.overall

        if overall.total_closed > 0:
            lines.append("")
            lines.append("Rejection Analysis")
            lines.append("-" * 18)
            lines.append(
                f"  Overall rejection rate: {overall.rejection_rate * 100:.1f}% "
                f"({overall.rejected_count}/{overall.total_closed})"
            )
            lines.append(
                f"  Invalid rate: {overall.invalid_rate * 100:.1f}% "
                f"({overall.invalid_count}/{overall.total_closed})"
            )
            if overall.duplicate_count > 0:
                lines.append(f"  Duplicates: {overall.duplicate_count}")
            if overall.deferred_count > 0:
                lines.append(f"  Deferred: {overall.deferred_count}")

            # By type
            if rej.by_type:
                lines.append("")
                lines.append("  By Type:")
                for issue_type in sorted(rej.by_type.keys()):
                    metrics = rej.by_type[issue_type]
                    rate = metrics.rejection_rate + metrics.invalid_rate
                    lines.append(f"    {issue_type:5}: {rate * 100:.1f}% non-completion")

            # Trend
            if rej.by_month:
                sorted_months = sorted(rej.by_month.keys())[-6:]
                if len(sorted_months) >= 2:
                    lines.append("")
                    lines.append("  Trend (last 6 months):")
                    trend_parts = []
                    for month in sorted_months:
                        m = rej.by_month[month]
                        rate = (m.rejection_rate + m.invalid_rate) * 100
                        trend_parts.append(f"{month[-2:]}: {rate:.0f}%")
                    lines.append(f"    {', '.join(trend_parts)}")
                    trend_symbol = {"improving": "↓", "degrading": "↑", "stable": "→"}.get(
                        rej.trend, "→"
                    )
                    lines.append(f"    Direction: {rej.trend} {trend_symbol}")

            # Common reasons
            if rej.common_reasons:
                lines.append("")
                lines.append("  Common Rejection Reasons:")
                for reason, count in rej.common_reasons[:5]:
                    lines.append(f"    - \"{reason}\" ({count})")
```

**Change 2**: Update `format_analysis_markdown()` (add after Technical Debt section)
```python
    # Rejection Analysis
    if analysis.rejection_analysis:
        rej = analysis.rejection_analysis
        overall = rej.overall

        if overall.total_closed > 0:
            lines.append("")
            lines.append("## Rejection Analysis")
            lines.append("")
            lines.append(
                f"**Overall rejection rate**: {overall.rejection_rate * 100:.1f}% "
                f"({overall.rejected_count}/{overall.total_closed})"
            )
            lines.append(
                f"**Invalid rate**: {overall.invalid_rate * 100:.1f}% "
                f"({overall.invalid_count}/{overall.total_closed})"
            )
            lines.append("")

            # By type table
            if rej.by_type:
                lines.append("### By Issue Type")
                lines.append("")
                lines.append("| Type | Rejected | Invalid | Total | Rate |")
                lines.append("|------|----------|---------|-------|------|")
                for issue_type in sorted(rej.by_type.keys()):
                    m = rej.by_type[issue_type]
                    rate = (m.rejection_rate + m.invalid_rate) * 100
                    lines.append(
                        f"| {issue_type} | {m.rejected_count} | {m.invalid_count} | "
                        f"{m.total_closed} | {rate:.1f}% |"
                    )
                lines.append("")

            # Trend
            if rej.by_month and len(rej.by_month) >= 2:
                lines.append("### Trend")
                lines.append("")
                sorted_months = sorted(rej.by_month.keys())[-6:]
                trend_parts = []
                for month in sorted_months:
                    m = rej.by_month[month]
                    rate = (m.rejection_rate + m.invalid_rate) * 100
                    trend_parts.append(f"{month}: {rate:.0f}%")
                lines.append(" → ".join(trend_parts))
                lines.append(f"*Trend: {rej.trend}*")
                lines.append("")

            # Common reasons
            if rej.common_reasons:
                lines.append("### Common Rejection Reasons")
                lines.append("")
                for reason, count in rej.common_reasons[:5]:
                    lines.append(f"- \"{reason}\" ({count})")
```

#### Success Criteria

**Automated Verification**:
- [ ] Text formatting test: `python -m pytest scripts/tests/test_issue_history.py -k "TestFormatAnalysisText" -v`
- [ ] Markdown formatting test: `python -m pytest scripts/tests/test_issue_history.py -k "TestFormatAnalysisMarkdown" -v`

---

### Phase 6: Add Unit Tests

#### Overview
Add comprehensive unit tests for all new functionality.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add test classes at end of file

```python
# =============================================================================
# Rejection Analysis Tests (ENH-112)
# =============================================================================


class TestParseResolutionAction:
    """Tests for _parse_resolution_action helper."""

    def test_completed_with_action(self) -> None:
        """Test normal completion with Action field."""
        content = """## Resolution

- **Action**: fix
- **Completed**: 2026-01-15
- **Status**: Completed
"""
        assert _parse_resolution_action(content) == "completed"

    def test_rejected_with_reason(self) -> None:
        """Test rejection with explicit reason."""
        content = """## Resolution

- **Status**: Closed - Rejected
- **Closed**: 2026-01-15
- **Reason**: rejected
"""
        assert _parse_resolution_action(content) == "rejected"

    def test_invalid_with_reason(self) -> None:
        """Test invalid with explicit reason."""
        content = """## Resolution

- **Status**: Closed - Invalid
- **Closed**: 2026-01-15
- **Reason**: invalid_ref
"""
        assert _parse_resolution_action(content) == "invalid"

    def test_duplicate_with_reason(self) -> None:
        """Test duplicate detection."""
        content = """## Resolution

- **Status**: Closed
- **Reason**: duplicate of BUG-001
"""
        assert _parse_resolution_action(content) == "duplicate"

    def test_deferred_with_reason(self) -> None:
        """Test deferred detection."""
        content = """## Resolution

- **Status**: Closed
- **Reason**: deferred to v2
"""
        assert _parse_resolution_action(content) == "deferred"

    def test_closed_without_reason(self) -> None:
        """Test closed without specific reason defaults to rejected."""
        content = """## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-01-15
"""
        assert _parse_resolution_action(content) == "rejected"

    def test_no_resolution_section(self) -> None:
        """Test content without resolution section defaults to completed."""
        content = """# Issue Title

Some description.
"""
        assert _parse_resolution_action(content) == "completed"


class TestRejectionMetrics:
    """Tests for RejectionMetrics dataclass."""

    def test_rates_empty(self) -> None:
        """Test rates with no data."""
        metrics = RejectionMetrics()
        assert metrics.rejection_rate == 0.0
        assert metrics.invalid_rate == 0.0

    def test_rates_calculation(self) -> None:
        """Test rate calculations."""
        metrics = RejectionMetrics(
            total_closed=100,
            rejected_count=10,
            invalid_count=5,
            completed_count=85,
        )
        assert metrics.rejection_rate == 0.1
        assert metrics.invalid_rate == 0.05

    def test_to_dict(self) -> None:
        """Test serialization."""
        metrics = RejectionMetrics(
            total_closed=100,
            rejected_count=10,
            invalid_count=5,
        )
        result = metrics.to_dict()
        assert result["total_closed"] == 100
        assert result["rejection_rate"] == 0.1
        assert result["invalid_rate"] == 0.05


class TestRejectionAnalysis:
    """Tests for RejectionAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test serialization with no data."""
        analysis = RejectionAnalysis()
        result = analysis.to_dict()
        assert result["overall"]["total_closed"] == 0
        assert result["by_type"] == {}
        assert result["by_month"] == {}

    def test_to_dict_with_data(self) -> None:
        """Test serialization with data."""
        analysis = RejectionAnalysis(
            overall=RejectionMetrics(total_closed=10, rejected_count=2),
            by_type={"BUG": RejectionMetrics(total_closed=5, rejected_count=1)},
            common_reasons=[("duplicate", 3), ("invalid", 2)],
            trend="improving",
        )
        result = analysis.to_dict()
        assert result["overall"]["total_closed"] == 10
        assert "BUG" in result["by_type"]
        assert len(result["common_reasons"]) == 2
        assert result["trend"] == "improving"


class TestAnalyzeRejectionRates:
    """Tests for analyze_rejection_rates function."""

    def test_empty_issues(self) -> None:
        """Test with empty list."""
        result = analyze_rejection_rates([])
        assert result.overall.total_closed == 0

    def test_all_completed(self, tmp_path: Path) -> None:
        """Test with all completed issues."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""## Resolution

- **Action**: fix
- **Completed**: 2026-01-15
- **Status**: Completed
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 15),
            )
        ]
        result = analyze_rejection_rates(issues)
        assert result.overall.total_closed == 1
        assert result.overall.completed_count == 1
        assert result.overall.rejected_count == 0

    def test_mixed_outcomes(self, tmp_path: Path) -> None:
        """Test with mixed completion outcomes."""
        completed = tmp_path / "P1-BUG-001.md"
        completed.write_text("- **Action**: fix\n- **Status**: Completed")

        rejected = tmp_path / "P2-BUG-002.md"
        rejected.write_text("- **Status**: Closed\n- **Reason**: rejected")

        invalid = tmp_path / "P3-ENH-001.md"
        invalid.write_text("- **Status**: Closed\n- **Reason**: invalid_ref")

        issues = [
            CompletedIssue(
                path=completed, issue_type="BUG", priority="P1",
                issue_id="BUG-001", completed_date=date(2026, 1, 15),
            ),
            CompletedIssue(
                path=rejected, issue_type="BUG", priority="P2",
                issue_id="BUG-002", completed_date=date(2026, 1, 16),
            ),
            CompletedIssue(
                path=invalid, issue_type="ENH", priority="P3",
                issue_id="ENH-001", completed_date=date(2026, 1, 17),
            ),
        ]
        result = analyze_rejection_rates(issues)
        assert result.overall.total_closed == 3
        assert result.overall.completed_count == 1
        assert result.overall.rejected_count == 1
        assert result.overall.invalid_count == 1

    def test_by_type_grouping(self, tmp_path: Path) -> None:
        """Test grouping by issue type."""
        bug = tmp_path / "P1-BUG-001.md"
        bug.write_text("- **Status**: Closed\n- **Reason**: rejected")

        enh = tmp_path / "P2-ENH-001.md"
        enh.write_text("- **Action**: improve\n- **Status**: Completed")

        issues = [
            CompletedIssue(
                path=bug, issue_type="BUG", priority="P1",
                issue_id="BUG-001", completed_date=date(2026, 1, 15),
            ),
            CompletedIssue(
                path=enh, issue_type="ENH", priority="P2",
                issue_id="ENH-001", completed_date=date(2026, 1, 16),
            ),
        ]
        result = analyze_rejection_rates(issues)
        assert "BUG" in result.by_type
        assert "ENH" in result.by_type
        assert result.by_type["BUG"].rejected_count == 1
        assert result.by_type["ENH"].completed_count == 1

    def test_by_month_grouping(self, tmp_path: Path) -> None:
        """Test grouping by month."""
        jan = tmp_path / "P1-BUG-001.md"
        jan.write_text("- **Action**: fix")

        feb = tmp_path / "P2-BUG-002.md"
        feb.write_text("- **Status**: Closed\n- **Reason**: rejected")

        issues = [
            CompletedIssue(
                path=jan, issue_type="BUG", priority="P1",
                issue_id="BUG-001", completed_date=date(2026, 1, 15),
            ),
            CompletedIssue(
                path=feb, issue_type="BUG", priority="P2",
                issue_id="BUG-002", completed_date=date(2026, 2, 15),
            ),
        ]
        result = analyze_rejection_rates(issues)
        assert "2026-01" in result.by_month
        assert "2026-02" in result.by_month

    def test_common_reasons_extracted(self, tmp_path: Path) -> None:
        """Test common reasons extraction."""
        f1 = tmp_path / "P1-BUG-001.md"
        f1.write_text("- **Status**: Closed\n- **Reason**: duplicate of BUG-100")

        f2 = tmp_path / "P2-BUG-002.md"
        f2.write_text("- **Status**: Closed\n- **Reason**: duplicate of BUG-100")

        issues = [
            CompletedIssue(
                path=f1, issue_type="BUG", priority="P1",
                issue_id="BUG-001", completed_date=date(2026, 1, 15),
            ),
            CompletedIssue(
                path=f2, issue_type="BUG", priority="P2",
                issue_id="BUG-002", completed_date=date(2026, 1, 16),
            ),
        ]
        result = analyze_rejection_rates(issues)
        assert len(result.common_reasons) > 0
        assert result.common_reasons[0][0] == "duplicate of BUG-100"
        assert result.common_reasons[0][1] == 2
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_issue_history.py -k "Rejection" -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/test_issue_history.py -v`

---

## Testing Strategy

### Unit Tests
- `_parse_resolution_action` - test all category detection paths
- `RejectionMetrics` - test rate calculations and edge cases
- `RejectionAnalysis` - test serialization and data aggregation
- `analyze_rejection_rates` - test with various issue combinations

### Integration Tests
- Verify `calculate_analysis()` includes rejection_analysis
- Verify all output formats include rejection section

## References

- Original issue: `.issues/enhancements/P3-ENH-112-rejection-invalid-rate-analysis.md`
- Similar implementation (RegressionAnalysis): `issue_history.py:226-263`
- Parsing pattern: `issue_history.py:459-511`
- Analysis function pattern: `issue_history.py:1082-1202`
- Text formatting pattern: `issue_history.py:1658-1714`
