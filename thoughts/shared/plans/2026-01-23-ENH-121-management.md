# ENH-121: Test Gap Correlation Analysis - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-121-test-gap-correlation-analysis.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `issue_history.py` module (1745 lines) provides comprehensive analysis of completed issues including:
- `HotspotAnalysis` dataclass at line 206-220 for tracking file hotspots
- `analyze_hotspots()` function at line 869-977 that extracts files from issues
- `_extract_paths_from_issue()` at line 644-672 for extracting file paths from issue content
- `RegressionAnalysis` dataclass at line 246-260 for regression clustering
- Text and markdown formatting at lines 1361-1745

### Key Discoveries
- `HotspotAnalysis.bug_magnets` already identifies files with >60% bug ratio (`issue_history.py:212`)
- `_extract_paths_from_issue()` extracts source file paths from issue content (`issue_history.py:644`)
- Test file detection logic does NOT exist yet - must be added
- `HistoryAnalysis` dataclass at line 287-352 has fields for `hotspot_analysis` and `regression_analysis`
- `calculate_analysis()` at line 1206-1323 orchestrates all analysis functions

## Desired End State

A new `TestGapAnalysis` feature that:
1. Correlates bugs with test coverage by detecting corresponding test files
2. Calculates gap scores (bugs with no tests = higher scores)
3. Identifies priority test targets based on bug count and test status
4. Integrates into the existing `ll-history analyze` output

### How to Verify
- Unit tests pass for new dataclasses and functions
- Integration tests verify test file detection patterns
- `ll-history analyze` command shows test gap section in output
- Lint and type checks pass

## What We're NOT Doing

- Not implementing actual test coverage measurement (line coverage)
- Not integrating with coverage.py or similar tools
- Not modifying the CLI command arguments (uses existing `ll-history analyze`)
- Not changing how issues are parsed or scanned

## Problem Analysis

Bug clusters in areas without tests indicate:
- Missing test coverage for critical paths
- Test suite gaps needing prioritization
- Risk areas requiring defensive testing

Currently, `bug_magnets` identifies high-bug-ratio files but doesn't check for test presence. This enhancement adds test file detection to provide actionable recommendations.

## Solution Approach

1. Add `TestGap` and `TestGapAnalysis` dataclasses following existing patterns
2. Implement `_find_test_file()` helper with common test file naming patterns
3. Implement `analyze_test_gaps()` function that leverages existing `HotspotAnalysis`
4. Add `test_gap_analysis` field to `HistoryAnalysis` dataclass
5. Update `calculate_analysis()` to call `analyze_test_gaps()`
6. Add formatting in `format_analysis_text()` and `format_analysis_markdown()`
7. Add exports to `__all__`
8. Write comprehensive tests

## Implementation Phases

### Phase 1: Add Dataclasses

#### Overview
Add `TestGap` and `TestGapAnalysis` dataclasses following the established pattern from `Hotspot` and `HotspotAnalysis`.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `RegressionAnalysis` dataclass (around line 261)

```python
@dataclass
class TestGap:
    """A source file with bugs but missing or weak test coverage."""

    source_file: str
    bug_count: int = 0
    bug_ids: list[str] = field(default_factory=list)
    has_test_file: bool = False
    test_file_path: str | None = None
    gap_score: float = 0.0  # bug_count / (1 if has_test else 0.1), higher = worse
    priority: str = "low"  # "critical", "high", "medium", "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_file": self.source_file,
            "bug_count": self.bug_count,
            "bug_ids": self.bug_ids[:10],  # Top 10
            "has_test_file": self.has_test_file,
            "test_file_path": self.test_file_path,
            "gap_score": round(self.gap_score, 2),
            "priority": self.priority,
        }


@dataclass
class TestGapAnalysis:
    """Analysis of test coverage gaps correlated with bug occurrences."""

    gaps: list[TestGap] = field(default_factory=list)
    untested_bug_magnets: list[str] = field(default_factory=list)
    files_with_tests_avg_bugs: float = 0.0
    files_without_tests_avg_bugs: float = 0.0
    priority_test_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "untested_bug_magnets": self.untested_bug_magnets[:5],
            "files_with_tests_avg_bugs": round(self.files_with_tests_avg_bugs, 2),
            "files_without_tests_avg_bugs": round(self.files_without_tests_avg_bugs, 2),
            "priority_test_targets": self.priority_test_targets[:10],
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 2: Add Test File Detection

#### Overview
Implement `_find_test_file()` helper to detect corresponding test files for source files.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `_extract_paths_from_issue()` (around line 673)

```python
def _find_test_file(source_path: str) -> str | None:
    """Find corresponding test file for a source file.

    Checks common test file naming patterns:
    - tests/test_<name>.py
    - tests/<path>/test_<name>.py
    - <path>/test_<name>.py
    - <path>/<name>_test.py
    - <path>/tests/test_<name>.py

    Args:
        source_path: Path to source file (e.g., "src/core/processor.py")

    Returns:
        Path to test file if found, None otherwise
    """
    if not source_path.endswith(".py"):
        return None  # Only check Python files for now

    path = Path(source_path)
    stem = path.stem  # filename without extension
    parent = path.parent

    # Generate candidate test file paths
    candidates = [
        f"tests/test_{stem}.py",
        f"tests/{parent}/test_{stem}.py" if parent != Path(".") else None,
        f"{parent}/test_{stem}.py",
        f"{parent}/{stem}_test.py",
        f"{parent}/tests/test_{stem}.py",
        f"scripts/tests/test_{stem}.py",  # Project-specific pattern
    ]

    # Also check for module-based test paths
    # e.g., scripts/little_loops/foo.py -> scripts/tests/test_foo.py
    if "scripts/little_loops" in source_path:
        module_name = path.stem
        candidates.append(f"scripts/tests/test_{module_name}.py")

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    return None
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 3: Implement analyze_test_gaps Function

#### Overview
Implement the main analysis function that correlates bugs with test coverage.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `analyze_regression_clustering()` (around line 1100)

```python
def analyze_test_gaps(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
) -> TestGapAnalysis:
    """Correlate bug occurrences with test coverage gaps.

    Args:
        issues: List of completed issues
        hotspots: Pre-computed hotspot analysis

    Returns:
        TestGapAnalysis with test coverage gap information
    """
    # Build map of source files to bug info from hotspots
    bug_files: dict[str, dict[str, Any]] = {}

    for hotspot in hotspots.file_hotspots:
        bug_count = hotspot.issue_types.get("BUG", 0)
        if bug_count > 0:
            # Filter to only BUG issue IDs
            bug_ids = [
                iid for iid in hotspot.issue_ids
                if iid.startswith("BUG-")
            ]
            bug_files[hotspot.path] = {
                "bug_count": bug_count,
                "bug_ids": bug_ids,
            }

    if not bug_files:
        return TestGapAnalysis()

    # Analyze test coverage for each file with bugs
    gaps: list[TestGap] = []
    files_with_tests: list[int] = []  # bug counts
    files_without_tests: list[int] = []  # bug counts

    for source_file, data in bug_files.items():
        bug_count = data["bug_count"]
        bug_ids = data["bug_ids"]

        test_file = _find_test_file(source_file)
        has_test = test_file is not None

        # Calculate gap score: higher = more urgent to add tests
        # Files without tests get amplified scores
        if has_test:
            gap_score = bug_count * 1.0
            files_with_tests.append(bug_count)
        else:
            gap_score = bug_count * 10.0  # Amplify untested files
            files_without_tests.append(bug_count)

        # Determine priority based on bug count and test presence
        if not has_test and bug_count >= 5:
            priority = "critical"
        elif not has_test and bug_count >= 3:
            priority = "high"
        elif not has_test or bug_count >= 4:
            priority = "medium"
        else:
            priority = "low"

        gaps.append(
            TestGap(
                source_file=source_file,
                bug_count=bug_count,
                bug_ids=bug_ids,
                has_test_file=has_test,
                test_file_path=test_file,
                gap_score=gap_score,
                priority=priority,
            )
        )

    # Sort by gap score descending (highest priority first)
    gaps.sort(key=lambda g: (-g.gap_score, -g.bug_count))

    # Calculate averages for correlation
    avg_with_tests = (
        sum(files_with_tests) / len(files_with_tests)
        if files_with_tests else 0.0
    )
    avg_without_tests = (
        sum(files_without_tests) / len(files_without_tests)
        if files_without_tests else 0.0
    )

    # Identify untested bug magnets (from hotspot analysis)
    untested_magnets = [
        h.path for h in hotspots.bug_magnets
        if _find_test_file(h.path) is None
    ]

    # Priority test targets: untested files sorted by bug count
    priority_targets = [
        g.source_file for g in gaps
        if not g.has_test_file
    ]

    return TestGapAnalysis(
        gaps=gaps[:15],  # Top 15
        untested_bug_magnets=untested_magnets,
        files_with_tests_avg_bugs=avg_with_tests,
        files_without_tests_avg_bugs=avg_without_tests,
        priority_test_targets=priority_targets[:10],
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 4: Integrate into HistoryAnalysis

#### Overview
Add `test_gap_analysis` field to `HistoryAnalysis` and update `calculate_analysis()` to call it.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add field to `HistoryAnalysis` dataclass (around line 311, after `regression_analysis`)
```python
    # Test gap analysis
    test_gap_analysis: TestGapAnalysis | None = None
```

**Change 2**: Update `to_dict()` method in `HistoryAnalysis` (around line 343)
```python
            "test_gap_analysis": (
                self.test_gap_analysis.to_dict() if self.test_gap_analysis else None
            ),
```

**Change 3**: Update `calculate_analysis()` function (after line 1258, after regression_analysis)
```python
    # Test gap analysis
    test_gap_analysis = analyze_test_gaps(completed_issues, hotspot_analysis)
```

**Change 4**: Add to analysis construction (around line 1277)
```python
        test_gap_analysis=test_gap_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 5: Add Output Formatting

#### Overview
Add test gap analysis sections to text and markdown formatters.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add to `format_analysis_text()` (after regression clustering section, around line 1473)
```python
    # Test gap analysis
    if analysis.test_gap_analysis:
        tga = analysis.test_gap_analysis

        if tga.gaps:
            lines.append("")
            lines.append("Test Gap Correlation")
            lines.append("-" * 20)

            # Show correlation stats
            lines.append(f"  Files with tests: avg {tga.files_with_tests_avg_bugs:.1f} bugs")
            lines.append(f"  Files without tests: avg {tga.files_without_tests_avg_bugs:.1f} bugs")
            lines.append("")

            # Show critical gaps
            critical_gaps = [g for g in tga.gaps if g.priority in ("critical", "high")]
            if critical_gaps:
                lines.append("Critical Test Gaps:")
                for g in critical_gaps[:5]:
                    test_status = "NO TEST" if not g.has_test_file else g.test_file_path
                    lines.append(f"  {g.source_file} [{g.priority.upper()}]")
                    lines.append(f"     Bugs: {g.bug_count} ({', '.join(g.bug_ids[:3])})")
                    lines.append(f"     Test: {test_status}")

        if tga.priority_test_targets:
            lines.append("")
            lines.append("Priority Test Targets:")
            for i, target in enumerate(tga.priority_test_targets[:5], 1):
                lines.append(f"  {i}. {target}")
```

**Change 2**: Add to `format_analysis_markdown()` (after regression clustering section, around line 1678)
```python
    # Test Gap Analysis
    if analysis.test_gap_analysis:
        tga = analysis.test_gap_analysis

        if tga.gaps:
            lines.append("")
            lines.append("## Test Gap Correlation")
            lines.append("")
            lines.append("Correlating bug occurrences with test coverage gaps:")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Files with tests | avg {tga.files_with_tests_avg_bugs:.1f} bugs |")
            lines.append(f"| Files without tests | avg {tga.files_without_tests_avg_bugs:.1f} bugs |")
            lines.append("")

            # Critical gaps table
            critical_gaps = [g for g in tga.gaps if g.priority in ("critical", "high")]
            if critical_gaps:
                lines.append("### Critical Test Gaps")
                lines.append("")
                lines.append("Files with high bug counts but missing tests:")
                lines.append("")
                lines.append("| File | Bugs | Priority | Test Status | Action |")
                lines.append("|------|------|----------|-------------|--------|")
                for g in critical_gaps[:10]:
                    priority_badge = "🔴" if g.priority == "critical" else "🟠"
                    test_status = f"`{g.test_file_path}`" if g.has_test_file else "NONE"
                    action = "Review coverage" if g.has_test_file else "Create test file"
                    lines.append(
                        f"| `{g.source_file}` | {g.bug_count} | {priority_badge} | "
                        f"{test_status} | {action} |"
                    )

        if tga.priority_test_targets:
            lines.append("")
            lines.append("### Priority Test Targets")
            lines.append("")
            lines.append("Files recommended for new test creation (ordered by bug count):")
            lines.append("")
            for target in tga.priority_test_targets[:10]:
                lines.append(f"- `{target}`")
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

---

### Phase 6: Update Exports and Tests

#### Overview
Add new symbols to `__all__` and write comprehensive tests.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add to `__all__` list (around line 32)
```python
    "TestGap",
    "TestGapAnalysis",
    "analyze_test_gaps",
```

**File**: `scripts/tests/test_issue_history.py`

**Change 1**: Add imports
```python
from little_loops.issue_history import (
    # ... existing imports ...
    TestGap,
    TestGapAnalysis,
    analyze_test_gaps,
)
```

**Change 2**: Add test classes

```python
class TestTestGap:
    """Tests for TestGap dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        gap = TestGap(
            source_file="src/core/processor.py",
            bug_count=5,
            bug_ids=["BUG-001", "BUG-002", "BUG-003", "BUG-004", "BUG-005"],
            has_test_file=False,
            test_file_path=None,
            gap_score=50.0,
            priority="critical",
        )
        result = gap.to_dict()

        assert result["source_file"] == "src/core/processor.py"
        assert result["bug_count"] == 5
        assert result["has_test_file"] is False
        assert result["gap_score"] == 50.0
        assert result["priority"] == "critical"

    def test_to_dict_with_test_file(self) -> None:
        """Test to_dict with existing test file."""
        gap = TestGap(
            source_file="src/utils/helper.py",
            bug_count=2,
            bug_ids=["BUG-010", "BUG-011"],
            has_test_file=True,
            test_file_path="tests/test_helper.py",
            gap_score=2.0,
            priority="low",
        )
        result = gap.to_dict()

        assert result["has_test_file"] is True
        assert result["test_file_path"] == "tests/test_helper.py"


class TestTestGapAnalysis:
    """Tests for TestGapAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty analysis."""
        analysis = TestGapAnalysis()
        result = analysis.to_dict()

        assert result["gaps"] == []
        assert result["untested_bug_magnets"] == []
        assert result["files_with_tests_avg_bugs"] == 0.0
        assert result["files_without_tests_avg_bugs"] == 0.0
        assert result["priority_test_targets"] == []

    def test_to_dict_with_data(self) -> None:
        """Test to_dict with populated data."""
        gap = TestGap(
            source_file="src/core.py",
            bug_count=3,
            bug_ids=["BUG-001"],
            has_test_file=False,
            gap_score=30.0,
            priority="high",
        )
        analysis = TestGapAnalysis(
            gaps=[gap],
            untested_bug_magnets=["src/core.py"],
            files_with_tests_avg_bugs=1.5,
            files_without_tests_avg_bugs=4.2,
            priority_test_targets=["src/core.py"],
        )
        result = analysis.to_dict()

        assert len(result["gaps"]) == 1
        assert result["files_with_tests_avg_bugs"] == 1.5
        assert result["files_without_tests_avg_bugs"] == 4.2


class TestAnalyzeTestGaps:
    """Tests for analyze_test_gaps function."""

    def test_empty_hotspots(self) -> None:
        """Test with empty hotspot analysis."""
        hotspots = HotspotAnalysis()
        result = analyze_test_gaps([], hotspots)

        assert result.gaps == []
        assert result.priority_test_targets == []

    def test_no_bugs_in_hotspots(self) -> None:
        """Test with hotspots that have no bugs."""
        hotspots = HotspotAnalysis(
            file_hotspots=[
                Hotspot(
                    path="src/feature.py",
                    issue_count=3,
                    issue_ids=["ENH-001", "ENH-002", "ENH-003"],
                    issue_types={"ENH": 3},
                )
            ]
        )
        result = analyze_test_gaps([], hotspots)

        assert result.gaps == []

    def test_with_bug_hotspots(self, tmp_path: Path) -> None:
        """Test with hotspots containing bugs."""
        hotspots = HotspotAnalysis(
            file_hotspots=[
                Hotspot(
                    path="src/problematic.py",
                    issue_count=5,
                    issue_ids=["BUG-001", "BUG-002", "BUG-003", "ENH-001", "ENH-002"],
                    issue_types={"BUG": 3, "ENH": 2},
                    bug_ratio=0.6,
                )
            ],
            bug_magnets=[
                Hotspot(
                    path="src/problematic.py",
                    issue_count=5,
                    issue_ids=["BUG-001", "BUG-002", "BUG-003"],
                    issue_types={"BUG": 3},
                    bug_ratio=0.6,
                )
            ],
        )

        result = analyze_test_gaps([], hotspots)

        assert len(result.gaps) >= 1
        assert result.gaps[0].source_file == "src/problematic.py"
        assert result.gaps[0].bug_count == 3
        assert result.gaps[0].has_test_file is False  # No test file exists
        assert "src/problematic.py" in result.untested_bug_magnets

    def test_priority_classification(self) -> None:
        """Test priority classification based on bug count and test presence."""
        # File with 5+ bugs and no test -> critical
        hotspots = HotspotAnalysis(
            file_hotspots=[
                Hotspot(
                    path="src/critical.py",
                    issue_count=5,
                    issue_ids=["BUG-001", "BUG-002", "BUG-003", "BUG-004", "BUG-005"],
                    issue_types={"BUG": 5},
                )
            ]
        )
        result = analyze_test_gaps([], hotspots)

        assert result.gaps[0].priority == "critical"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Type check passes: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `TestGap.to_dict()` serialization
- `TestGapAnalysis.to_dict()` serialization
- `analyze_test_gaps()` with empty input
- `analyze_test_gaps()` with bugs only (no ENH)
- `analyze_test_gaps()` priority classification thresholds

### Integration Tests
- End-to-end `calculate_analysis()` includes test_gap_analysis
- Output formatting includes test gap section
- JSON/YAML serialization of test gap analysis

## References

- Original issue: `.issues/enhancements/P2-ENH-121-test-gap-correlation-analysis.md`
- Hotspot dataclass pattern: `scripts/little_loops/issue_history.py:183-203`
- Regression analysis pattern: `scripts/little_loops/issue_history.py:223-260`
- analyze_hotspots function: `scripts/little_loops/issue_history.py:869-977`
- Test patterns: `scripts/tests/test_issue_history.py:1108-1254`
