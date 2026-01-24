# ENH-117: Regression Clustering Analysis - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-117-regression-clustering-analysis.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `ll-history analyze` command provides comprehensive issue history analysis including hotspot detection (ENH-116), trend analysis, and technical debt metrics. The codebase already has infrastructure for:

### Key Discoveries
- `CompletedIssue` dataclass at `issue_history.py:52-74` stores issue metadata including `completed_date`, `issue_id`, and `issue_type`
- `_extract_paths_from_issue()` at `issue_history.py:595-623` extracts file paths from issue content
- `HotspotAnalysis` at `issue_history.py:203-217` provides pattern for aggregation dataclasses
- `analyze_hotspots()` at `issue_history.py:820-928` shows pattern for analysis functions
- `calculate_analysis()` at `issue_history.py:1034-1147` orchestrates all analyses
- `format_analysis_text()` at `issue_history.py:1185-1303` and `format_analysis_markdown()` at `issue_history.py:1306-1509` show output formatting patterns

### Patterns to Follow
- Dataclass with `to_dict()` method for serialization (limit lists in output)
- Analysis function taking `list[CompletedIssue]` and returning typed dataclass
- Integration via adding field to `HistoryAnalysis` and calling function in `calculate_analysis()`
- Text format: lines accumulator with section headers using `=` and `-`
- Markdown format: tables with emoji indicators

## Desired End State

A regression clustering analysis that:
1. Detects temporal patterns where bug fixes lead to new bugs
2. Identifies file overlap between sequential bugs
3. Clusters related regressions by file affinity
4. Classifies severity and time patterns
5. Outputs actionable recommendations in analysis reports

### How to Verify
- Unit tests for `RegressionCluster` and `RegressionAnalysis` dataclasses
- Unit tests for `analyze_regression_clustering()` function
- Tests for edge cases (no regressions, single issue, no dated issues)
- Integration into `ll-history analyze` output verified via formatters
- All existing tests pass

## What We're NOT Doing

- Not implementing explicit mention detection (would require full-text parsing for issue references like "caused by BUG-001")
- Not adding graph visualization of regression chains
- Not persisting regression relationships to disk
- Not integrating with HotspotAnalysis for combined severity scoring (deferred to future enhancement)

## Problem Analysis

Regression clustering requires identifying when fixing one bug leads to another bug appearing. The heuristics are:

1. **Temporal proximity**: Bug B completed within 7 days after Bug A's completion
2. **File overlap**: Both bugs affect the same file(s)
3. **Related component**: Both bugs in same directory/module

A regression chain forms when: Bug A fix -> Bug B (affecting same files, within 7 days) -> Bug C...

## Solution Approach

1. Create `RegressionCluster` dataclass to capture chain details
2. Create `RegressionAnalysis` dataclass to hold all clusters
3. Implement `analyze_regression_clustering()` that:
   - Orders bugs by completion date
   - For each pair of sequential bugs, checks file overlap and temporal proximity
   - Builds chains of related regressions
   - Classifies severity and time patterns
4. Integrate into `HistoryAnalysis` and `calculate_analysis()`
5. Add output sections to text and markdown formatters
6. Write comprehensive tests

## Implementation Phases

### Phase 1: Add Dataclasses

#### Overview
Define `RegressionCluster` and `RegressionAnalysis` dataclasses following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add dataclasses after `HotspotAnalysis` (around line 218)

```python
@dataclass
class RegressionCluster:
    """A cluster of bugs where fixes led to new bugs."""

    primary_file: str  # Main file in the regression chain
    regression_count: int = 0  # Number of regression pairs
    fix_bug_pairs: list[tuple[str, str]] = field(default_factory=list)  # (fixed_id, caused_id)
    related_files: list[str] = field(default_factory=list)  # All files in chain
    time_pattern: str = "immediate"  # "immediate" (<3d), "delayed" (3-7d), "chronic" (recurring)
    severity: str = "medium"  # "critical", "high", "medium"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "primary_file": self.primary_file,
            "regression_count": self.regression_count,
            "fix_bug_pairs": self.fix_bug_pairs[:10],  # Top 10
            "related_files": self.related_files[:10],  # Top 10
            "time_pattern": self.time_pattern,
            "severity": self.severity,
        }


@dataclass
class RegressionAnalysis:
    """Analysis of regression patterns in bug fixes."""

    clusters: list[RegressionCluster] = field(default_factory=list)
    total_regression_chains: int = 0
    most_fragile_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "clusters": [c.to_dict() for c in self.clusters],
            "total_regression_chains": self.total_regression_chains,
            "most_fragile_files": self.most_fragile_files[:5],  # Top 5
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Implement Analysis Function

#### Overview
Create `analyze_regression_clustering()` function following the `analyze_hotspots()` pattern.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add function after `analyze_hotspots()` (around line 929)

```python
def analyze_regression_clustering(
    issues: list[CompletedIssue],
) -> RegressionAnalysis:
    """Detect files where bug fixes frequently lead to new bugs.

    Uses heuristics:
    1. Temporal proximity: Bug B completed within 7 days of Bug A
    2. File overlap: Both bugs affect same file(s)

    Args:
        issues: List of completed issues

    Returns:
        RegressionAnalysis with clusters of related regressions
    """
    # Filter to bugs only and sort by completion date
    bugs = [i for i in issues if i.issue_type == "BUG" and i.completed_date]
    bugs.sort(key=lambda i: i.completed_date)  # type: ignore

    if len(bugs) < 2:
        return RegressionAnalysis()

    # Extract file paths for each bug
    bug_files: dict[str, set[str]] = {}  # issue_id -> set of files
    for bug in bugs:
        try:
            content = bug.path.read_text(encoding="utf-8")
            paths = _extract_paths_from_issue(content)
            bug_files[bug.issue_id] = set(paths)
        except Exception:
            bug_files[bug.issue_id] = set()

    # Find regression pairs (temporal proximity + file overlap)
    regression_pairs: list[tuple[CompletedIssue, CompletedIssue, set[str]]] = []

    for i, bug_a in enumerate(bugs[:-1]):
        files_a = bug_files.get(bug_a.issue_id, set())
        if not files_a:
            continue

        for bug_b in bugs[i + 1:]:
            # Check temporal proximity (within 7 days)
            days_apart = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
            if days_apart > 7:
                break  # Bugs are sorted, no need to check further

            files_b = bug_files.get(bug_b.issue_id, set())
            if not files_b:
                continue

            # Check file overlap
            overlap = files_a & files_b
            if overlap:
                regression_pairs.append((bug_a, bug_b, overlap))

    if not regression_pairs:
        return RegressionAnalysis()

    # Group by primary file (most common overlapping file)
    file_regressions: dict[str, list[tuple[str, str, int]]] = {}  # file -> [(id_a, id_b, days)]

    for bug_a, bug_b, overlap in regression_pairs:
        days = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
        for file_path in overlap:
            if file_path not in file_regressions:
                file_regressions[file_path] = []
            file_regressions[file_path].append((bug_a.issue_id, bug_b.issue_id, days))

    # Build clusters
    clusters: list[RegressionCluster] = []

    for file_path, pairs in file_regressions.items():
        # Determine time pattern
        avg_days = sum(d for _, _, d in pairs) / len(pairs)
        if avg_days < 3:
            time_pattern = "immediate"
        elif len(pairs) >= 3:
            time_pattern = "chronic"
        else:
            time_pattern = "delayed"

        # Determine severity
        if len(pairs) >= 4:
            severity = "critical"
        elif len(pairs) >= 2:
            severity = "high"
        else:
            severity = "medium"

        # Collect related files
        related_files: set[str] = set()
        for bug_a, bug_b, _ in regression_pairs:
            if file_path in (bug_files.get(bug_a.issue_id, set()) &
                            bug_files.get(bug_b.issue_id, set())):
                related_files.update(bug_files.get(bug_a.issue_id, set()))
                related_files.update(bug_files.get(bug_b.issue_id, set()))
        related_files.discard(file_path)

        clusters.append(
            RegressionCluster(
                primary_file=file_path,
                regression_count=len(pairs),
                fix_bug_pairs=[(a, b) for a, b, _ in pairs],
                related_files=sorted(related_files),
                time_pattern=time_pattern,
                severity=severity,
            )
        )

    # Sort by regression count descending
    clusters.sort(key=lambda c: (-c.regression_count, c.primary_file))

    # Identify most fragile files
    most_fragile = [c.primary_file for c in clusters[:5]]

    return RegressionAnalysis(
        clusters=clusters[:10],  # Top 10
        total_regression_chains=len(regression_pairs),
        most_fragile_files=most_fragile,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 3: Integrate into HistoryAnalysis

#### Overview
Add `regression_analysis` field to `HistoryAnalysis` and call the function in `calculate_analysis()`.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add field to `HistoryAnalysis` (around line 268)
```python
    # Regression clustering analysis
    regression_analysis: RegressionAnalysis | None = None
```

**Change 2**: Add to `HistoryAnalysis.to_dict()` (around line 295)
```python
            "regression_analysis": (
                self.regression_analysis.to_dict() if self.regression_analysis else None
            ),
```

**Change 3**: Call function in `calculate_analysis()` (around line 1087, after hotspot_analysis)
```python
    # Regression clustering analysis
    regression_analysis = analyze_regression_clustering(completed_issues)
```

**Change 4**: Pass to HistoryAnalysis constructor (around line 1101)
```python
        regression_analysis=regression_analysis,
```

**Change 5**: Update `__all__` exports (around line 31)
```python
    "RegressionCluster",
    "RegressionAnalysis",
    "analyze_regression_clustering",
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 4: Add Output Formatting

#### Overview
Add regression clustering sections to text and markdown formatters.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add to `format_analysis_text()` (after hotspot section, around line 1273)
```python
    # Regression clustering analysis
    if analysis.regression_analysis:
        regression = analysis.regression_analysis

        if regression.clusters:
            lines.append("")
            lines.append("Regression Clustering")
            lines.append("-" * 20)
            lines.append(f"Total regression chains detected: {regression.total_regression_chains}")
            lines.append("")
            lines.append("Fragile Code Clusters:")
            for i, c in enumerate(regression.clusters[:5], 1):
                severity_flag = f" [{c.severity.upper()}]" if c.severity in ("critical", "high") else ""
                lines.append(f"  {i}. {c.primary_file}{severity_flag}")
                lines.append(f"     Regression count: {c.regression_count}")
                lines.append(f"     Pattern: {c.time_pattern}")
                if c.fix_bug_pairs:
                    chain = " -> ".join(
                        f"{a} fix -> {b}" for a, b in c.fix_bug_pairs[:3]
                    )
                    if len(c.fix_bug_pairs) > 3:
                        chain += " ..."
                    lines.append(f"     Chain: {chain}")
```

**Change 2**: Add to `format_analysis_markdown()` (after bug magnets section, around line 1441)
```python
    # Regression Clustering Analysis
    if analysis.regression_analysis:
        regression = analysis.regression_analysis

        if regression.clusters:
            lines.append("")
            lines.append("## Regression Clustering")
            lines.append("")
            lines.append(f"**Total regression chains detected**: {regression.total_regression_chains}")
            lines.append("")
            lines.append("Files where fixes frequently lead to new bugs:")
            lines.append("")
            lines.append("| File | Regressions | Pattern | Severity |")
            lines.append("|------|-------------|---------|----------|")
            for c in regression.clusters:
                severity_badge = (
                    "🔴" if c.severity == "critical"
                    else ("🟠" if c.severity == "high" else "🟡")
                )
                lines.append(
                    f"| `{c.primary_file}` | {c.regression_count} | {c.time_pattern} | {severity_badge} |"
                )

        if regression.most_fragile_files:
            lines.append("")
            lines.append("### Most Fragile Files")
            lines.append("")
            lines.append("Files requiring architectural attention:")
            lines.append("")
            for f in regression.most_fragile_files:
                lines.append(f"- `{f}`")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 5: Add Tests

#### Overview
Add comprehensive tests for the new regression clustering functionality.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`

Add test classes following existing patterns (after `TestAnalyzeHotspots`):

```python
class TestRegressionCluster:
    """Tests for RegressionCluster dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        cluster = RegressionCluster(
            primary_file="src/core/processor.py",
            regression_count=3,
            fix_bug_pairs=[("BUG-001", "BUG-002"), ("BUG-002", "BUG-003"), ("BUG-003", "BUG-004")],
            related_files=["src/core/state.py", "src/core/events.py"],
            time_pattern="chronic",
            severity="critical",
        )
        result = cluster.to_dict()

        assert result["primary_file"] == "src/core/processor.py"
        assert result["regression_count"] == 3
        assert result["time_pattern"] == "chronic"
        assert result["severity"] == "critical"
        assert len(result["fix_bug_pairs"]) == 3

    def test_to_dict_limits_lists(self) -> None:
        """Test that to_dict limits lists to 10 items."""
        cluster = RegressionCluster(
            primary_file="test.py",
            regression_count=15,
            fix_bug_pairs=[(f"BUG-{i:03d}", f"BUG-{i+1:03d}") for i in range(15)],
            related_files=[f"file{i}.py" for i in range(15)],
        )
        result = cluster.to_dict()

        assert len(result["fix_bug_pairs"]) == 10
        assert len(result["related_files"]) == 10


class TestRegressionAnalysis:
    """Tests for RegressionAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty data."""
        analysis = RegressionAnalysis()
        result = analysis.to_dict()

        assert result["clusters"] == []
        assert result["total_regression_chains"] == 0
        assert result["most_fragile_files"] == []

    def test_to_dict_with_clusters(self) -> None:
        """Test to_dict with clusters."""
        cluster = RegressionCluster(primary_file="test.py", regression_count=2)
        analysis = RegressionAnalysis(
            clusters=[cluster],
            total_regression_chains=1,
            most_fragile_files=["test.py"],
        )
        result = analysis.to_dict()

        assert len(result["clusters"]) == 1
        assert result["total_regression_chains"] == 1
        assert result["most_fragile_files"] == ["test.py"]


class TestAnalyzeRegressionClustering:
    """Tests for analyze_regression_clustering function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        result = analyze_regression_clustering([])
        assert result.clusters == []
        assert result.total_regression_chains == 0

    def test_no_bugs(self, tmp_path: Path) -> None:
        """Test with no bug issues."""
        issue_file = tmp_path / "P1-ENH-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="ENH",
                priority="P1",
                issue_id="ENH-001",
                completed_date=date(2026, 1, 1),
            )
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters == []

    def test_single_bug(self, tmp_path: Path) -> None:
        """Test with single bug issue."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            )
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters == []

    def test_regression_detected(self, tmp_path: Path) -> None:
        """Test detection of regression chain."""
        # Create two bugs affecting same file within 7 days
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 3),  # 2 days later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 1
        assert len(result.clusters) == 1
        assert result.clusters[0].primary_file == "src/core/processor.py"
        assert result.clusters[0].regression_count == 1
        assert ("BUG-001", "BUG-002") in result.clusters[0].fix_bug_pairs

    def test_no_regression_beyond_7_days(self, tmp_path: Path) -> None:
        """Test that bugs >7 days apart are not considered regressions."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/core/processor.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 10),  # 9 days later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 0
        assert len(result.clusters) == 0

    def test_no_regression_different_files(self, tmp_path: Path) -> None:
        """Test that bugs affecting different files are not regressions."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/core/processor.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/api/handlers.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 3),
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.total_regression_chains == 0

    def test_severity_classification(self, tmp_path: Path) -> None:
        """Test severity classification based on regression count."""
        # Create 5 bugs with same file to trigger critical severity
        issues = []
        for i in range(5):
            bug_file = tmp_path / f"P1-BUG-{i:03d}.md"
            bug_file.write_text("**File**: `src/critical.py`")
            issues.append(
                CompletedIssue(
                    path=bug_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    completed_date=date(2026, 1, 1) + timedelta(days=i),
                )
            )

        result = analyze_regression_clustering(issues)
        assert result.clusters[0].severity == "critical"

    def test_time_pattern_immediate(self, tmp_path: Path) -> None:
        """Test immediate time pattern (<3 days)."""
        bug1_file = tmp_path / "P1-BUG-001.md"
        bug1_file.write_text("**File**: `src/fast.py`")

        bug2_file = tmp_path / "P1-BUG-002.md"
        bug2_file.write_text("**File**: `src/fast.py`")

        issues = [
            CompletedIssue(
                path=bug1_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
                completed_date=date(2026, 1, 1),
            ),
            CompletedIssue(
                path=bug2_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-002",
                completed_date=date(2026, 1, 2),  # 1 day later
            ),
        ]

        result = analyze_regression_clustering(issues)
        assert result.clusters[0].time_pattern == "immediate"

    def test_most_fragile_files(self, tmp_path: Path) -> None:
        """Test most fragile files list."""
        # Create two separate regression chains
        files = [("src/fragile1.py", 0), ("src/fragile1.py", 1),
                 ("src/fragile2.py", 3), ("src/fragile2.py", 4)]
        issues = []
        for i, (file_path, day_offset) in enumerate(files):
            bug_file = tmp_path / f"P1-BUG-{i:03d}.md"
            bug_file.write_text(f"**File**: `{file_path}`")
            issues.append(
                CompletedIssue(
                    path=bug_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                    completed_date=date(2026, 1, 1) + timedelta(days=day_offset),
                )
            )

        result = analyze_regression_clustering(issues)
        assert "src/fragile1.py" in result.most_fragile_files
        assert "src/fragile2.py" in result.most_fragile_files
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `RegressionCluster.to_dict()` serialization and list limiting
- `RegressionAnalysis.to_dict()` serialization
- `analyze_regression_clustering()` with:
  - Empty input
  - No bugs (only ENH/FEAT)
  - Single bug
  - Two bugs with file overlap (regression detected)
  - Two bugs beyond 7-day window (no regression)
  - Two bugs with no file overlap (no regression)
  - Multiple regressions for severity classification
  - Time pattern detection (immediate vs delayed vs chronic)
  - Most fragile files extraction

### Integration Tests
- Verify output appears in `format_analysis_text()` result
- Verify output appears in `format_analysis_markdown()` result

## References

- Original issue: `.issues/enhancements/P2-ENH-117-regression-clustering-analysis.md`
- Related patterns: `issue_history.py:180-218` (Hotspot/HotspotAnalysis)
- Similar implementation: `issue_history.py:820-928` (analyze_hotspots)
- Test patterns: `test_issue_history.py:1105-1251` (TestAnalyzeHotspots)
