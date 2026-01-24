# ENH-119: Coupling Detection Analysis - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-119-coupling-detection-analysis.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-history analyze` command provides comprehensive analysis of completed issues, including hotspot detection, regression clustering, test gap correlation, and other metrics. The codebase already has:

### Key Discoveries
- Path extraction utility: `_extract_paths_from_issue()` at `issue_history.py:985-1013` extracts file paths from issue content using regex patterns
- Hotspot analysis: `analyze_hotspots()` at `issue_history.py:1257-1365` builds file-to-issue mappings
- Dataclass patterns: `Hotspot`/`HotspotAnalysis` at `issue_history.py:195-232` define the structure for analysis results
- Integration point: `calculate_analysis()` at `issue_history.py:2067` orchestrates all analyses
- Text formatting: `format_analysis_text()` at `issue_history.py:2251-2300` generates human-readable output

## Desired End State

Coupling Detection Analysis that:
1. Identifies files that frequently change together across issues
2. Calculates coupling strength using Jaccard similarity
3. Groups highly coupled files into clusters
4. Identifies "coupling hotspots" (files coupled with many others)
5. Provides refactoring suggestions based on coupling patterns

### How to Verify
- Unit tests pass for all new dataclasses and functions
- Integration into `ll-history analyze` output
- Running against real issue data shows meaningful coupling pairs

## What We're NOT Doing

- Not implementing visualization (deferred to future enhancement)
- Not creating new CLI commands (using existing `ll-history analyze`)
- Not modifying existing dataclasses (only adding new ones)

## Problem Analysis

Hidden coupling between files makes codebases harder to maintain. When files consistently appear together in issues, it indicates:
- Tight coupling that should be made explicit
- Missing interfaces or abstractions
- Potential module boundary violations

The coupling analysis will use co-occurrence data from issues to identify these patterns.

## Solution Approach

1. Build a file-to-issues mapping from completed issues
2. Calculate pairwise co-occurrence counts for all file pairs
3. Compute Jaccard similarity as coupling strength
4. Cluster highly coupled files using a simple threshold-based approach
5. Identify hotspots (files coupled with 3+ other files)
6. Generate refactoring suggestions based on patterns

## Implementation Phases

### Phase 1: Add Dataclasses

#### Overview
Add `CouplingPair` and `CouplingAnalysis` dataclasses following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `HotspotAnalysis` (around line 233)

```python
@dataclass
class CouplingPair:
    """A pair of files that frequently appear together in issues."""

    file_a: str
    file_b: str
    co_occurrence_count: int = 0
    coupling_strength: float = 0.0  # 0-1, Jaccard similarity
    issue_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_a": self.file_a,
            "file_b": self.file_b,
            "co_occurrence_count": self.co_occurrence_count,
            "coupling_strength": round(self.coupling_strength, 3),
            "issue_ids": self.issue_ids[:10],  # Top 10
        }


@dataclass
class CouplingAnalysis:
    """Analysis of files that frequently change together."""

    pairs: list[CouplingPair] = field(default_factory=list)
    clusters: list[list[str]] = field(default_factory=list)  # Groups of coupled files
    hotspots: list[str] = field(default_factory=list)  # Files coupled with 3+ others

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pairs": [p.to_dict() for p in self.pairs],
            "clusters": self.clusters[:10],  # Top 10 clusters
            "hotspots": self.hotspots[:10],  # Top 10 hotspots
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Implement analyze_coupling Function

#### Overview
Implement the main analysis function that calculates coupling between files.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Location**: After `analyze_hotspots()` function (around line 1366)

```python
def analyze_coupling(issues: list[CompletedIssue]) -> CouplingAnalysis:
    """Identify files that frequently change together across issues.

    Uses Jaccard similarity to calculate coupling strength between file pairs.
    Files with coupling strength >= 0.3 and at least 2 co-occurrences are included.

    Args:
        issues: List of completed issues

    Returns:
        CouplingAnalysis with coupled pairs, clusters, and hotspots
    """
    # Build file -> set of issue IDs mapping
    file_to_issues: dict[str, set[str]] = {}

    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8")
        except Exception:
            continue

        paths = _extract_paths_from_issue(content)
        for path in paths:
            if path not in file_to_issues:
                file_to_issues[path] = set()
            file_to_issues[path].add(issue.issue_id)

    # Calculate pairwise coupling
    files = list(file_to_issues.keys())
    pairs: list[CouplingPair] = []

    for i, file_a in enumerate(files):
        for file_b in files[i + 1:]:
            a_issues = file_to_issues[file_a]
            b_issues = file_to_issues[file_b]
            co_occur = a_issues & b_issues
            union = a_issues | b_issues

            if len(co_occur) < 2:  # Require at least 2 co-occurrences
                continue

            # Jaccard similarity
            strength = len(co_occur) / len(union) if union else 0.0

            if strength >= 0.3:  # Only include significant coupling
                pairs.append(
                    CouplingPair(
                        file_a=file_a,
                        file_b=file_b,
                        co_occurrence_count=len(co_occur),
                        coupling_strength=strength,
                        issue_ids=sorted(co_occur),
                    )
                )

    # Sort by coupling strength descending
    pairs.sort(key=lambda p: (-p.coupling_strength, -p.co_occurrence_count))

    # Build clusters using simple connected components
    clusters = _build_coupling_clusters(pairs)

    # Identify hotspots (files coupled with 3+ others)
    file_coupling_count: dict[str, int] = {}
    for pair in pairs:
        file_coupling_count[pair.file_a] = file_coupling_count.get(pair.file_a, 0) + 1
        file_coupling_count[pair.file_b] = file_coupling_count.get(pair.file_b, 0) + 1

    hotspots = [f for f, count in file_coupling_count.items() if count >= 3]
    hotspots.sort(key=lambda f: -file_coupling_count[f])

    return CouplingAnalysis(
        pairs=pairs[:20],  # Top 20 pairs
        clusters=clusters[:10],  # Top 10 clusters
        hotspots=hotspots[:10],  # Top 10 hotspots
    )


def _build_coupling_clusters(pairs: list[CouplingPair]) -> list[list[str]]:
    """Build clusters of coupled files using connected components.

    Args:
        pairs: List of coupling pairs

    Returns:
        List of file clusters (each cluster is a list of file paths)
    """
    # Build adjacency for high-coupling pairs (strength >= 0.5)
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        if pair.coupling_strength >= 0.5:
            if pair.file_a not in adjacency:
                adjacency[pair.file_a] = set()
            if pair.file_b not in adjacency:
                adjacency[pair.file_b] = set()
            adjacency[pair.file_a].add(pair.file_b)
            adjacency[pair.file_b].add(pair.file_a)

    # Find connected components
    visited: set[str] = set()
    clusters: list[list[str]] = []

    for start in adjacency:
        if start in visited:
            continue
        # BFS to find component
        cluster: list[str] = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster) >= 2:  # Only include clusters with 2+ files
            cluster.sort()
            clusters.append(cluster)

    # Sort clusters by size descending
    clusters.sort(key=lambda c: -len(c))
    return clusters
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 3: Integrate into HistoryAnalysis

#### Overview
Add coupling_analysis field to HistoryAnalysis and integrate into calculate_analysis().

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add field to HistoryAnalysis (around line 548, after hotspot_analysis)
```python
    # Coupling analysis
    coupling_analysis: CouplingAnalysis | None = None
```

**Change 2**: Add to to_dict() method (around line 574, after hotspot_analysis)
```python
            "coupling_analysis": (
                self.coupling_analysis.to_dict() if self.coupling_analysis else None
            ),
```

**Change 3**: Call analyze_coupling in calculate_analysis() (around line 2068, after analyze_hotspots)
```python
    # Coupling analysis
    coupling_analysis = analyze_coupling(completed_issues)
```

**Change 4**: Add to HistoryAnalysis constructor (around line 2100)
```python
        coupling_analysis=coupling_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 4: Add Text and Markdown Formatting

#### Overview
Add output formatting for coupling analysis in format_analysis_text() and format_analysis_markdown().

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add to format_analysis_text() (after hotspot analysis section, around line 2277)
```python
    # Coupling analysis
    if analysis.coupling_analysis:
        coupling = analysis.coupling_analysis

        if coupling.pairs:
            lines.append("")
            lines.append("Coupling Detection")
            lines.append("-" * 18)

            lines.append("Highly Coupled File Pairs:")
            for i, p in enumerate(coupling.pairs[:5], 1):
                strength_label = (
                    "HIGH" if p.coupling_strength >= 0.7
                    else "MEDIUM" if p.coupling_strength >= 0.5
                    else "LOW"
                )
                lines.append(f"  {i}. {p.file_a} <-> {p.file_b}")
                lines.append(
                    f"     Co-occurrences: {p.co_occurrence_count}, "
                    f"Strength: {p.coupling_strength:.2f} [{strength_label}]"
                )

        if coupling.clusters:
            lines.append("")
            lines.append("Coupling Clusters:")
            for i, cluster in enumerate(coupling.clusters[:3], 1):
                files_str = ", ".join(cluster[:4])
                if len(cluster) > 4:
                    files_str += f" (+{len(cluster) - 4} more)"
                lines.append(f"  {i}. [{files_str}]")

        if coupling.hotspots:
            lines.append("")
            lines.append("Coupling Hotspots (coupled with 3+ files):")
            for f in coupling.hotspots[:5]:
                lines.append(f"  - {f}")
```

**Change 2**: Add to format_analysis_markdown() (similar location in markdown formatter)

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Format passes: `ruff format --check scripts/`

---

### Phase 5: Add Tests

#### Overview
Add comprehensive tests for coupling detection following existing test patterns.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`

Add test classes after TestAnalyzeHotspots:

```python
class TestCouplingPair:
    """Tests for CouplingPair dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        pair = CouplingPair(
            file_a="src/a.py",
            file_b="src/b.py",
            co_occurrence_count=5,
            coupling_strength=0.75,
            issue_ids=["BUG-001", "BUG-002"],
        )
        result = pair.to_dict()

        assert result["file_a"] == "src/a.py"
        assert result["file_b"] == "src/b.py"
        assert result["co_occurrence_count"] == 5
        assert result["coupling_strength"] == 0.75
        assert result["issue_ids"] == ["BUG-001", "BUG-002"]


class TestCouplingAnalysis:
    """Tests for CouplingAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty analysis."""
        analysis = CouplingAnalysis()
        result = analysis.to_dict()

        assert result["pairs"] == []
        assert result["clusters"] == []
        assert result["hotspots"] == []


class TestAnalyzeCoupling:
    """Tests for analyze_coupling function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        result = analyze_coupling([])
        assert result.pairs == []
        assert result.clusters == []
        assert result.hotspots == []

    def test_coupling_detected(self, tmp_path: Path) -> None:
        """Test detection of coupled files."""
        # Create 3 issues where src/a.py and src/b.py appear together
        issues = []
        for i in range(3):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text(
                "**File**: `src/a.py`\n**File**: `src/b.py`\nBug in both."
            )
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_coupling(issues)
        assert len(result.pairs) >= 1
        pair = result.pairs[0]
        assert {pair.file_a, pair.file_b} == {"src/a.py", "src/b.py"}
        assert pair.co_occurrence_count == 3
        assert pair.coupling_strength == 1.0  # Perfect coupling

    def test_no_coupling_single_occurrence(self, tmp_path: Path) -> None:
        """Test that single co-occurrence is not reported."""
        # Files appear together only once
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/a.py`\n**File**: `src/b.py`")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]

        result = analyze_coupling(issues)
        assert len(result.pairs) == 0  # Requires 2+ co-occurrences

    def test_coupling_hotspot_detection(self, tmp_path: Path) -> None:
        """Test detection of coupling hotspots."""
        # Create issues where src/hub.py is coupled with 4 different files
        issues = []
        for i, other_file in enumerate(["a.py", "b.py", "c.py", "d.py"]):
            for j in range(2):  # 2 issues per pair
                issue_file = tmp_path / f"P1-BUG-{i:02d}{j}.md"
                issue_file.write_text(
                    f"**File**: `src/hub.py`\n**File**: `src/{other_file}`"
                )
                issues.append(
                    CompletedIssue(
                        path=issue_file,
                        issue_type="BUG",
                        priority="P1",
                        issue_id=f"BUG-{i:02d}{j}",
                    )
                )

        result = analyze_coupling(issues)
        assert "src/hub.py" in result.hotspots
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v -k coupling`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- CouplingPair.to_dict() serialization
- CouplingAnalysis.to_dict() serialization with empty and populated data
- analyze_coupling() with empty input
- analyze_coupling() detecting coupled files
- analyze_coupling() filtering out low co-occurrence pairs
- analyze_coupling() detecting hotspots
- _build_coupling_clusters() forming correct clusters

### Integration Tests
- End-to-end formatting of coupling analysis in text output
- End-to-end formatting in JSON output
- Integration with calculate_analysis()

## References

- Original issue: `.issues/enhancements/P3-ENH-119-coupling-detection-analysis.md`
- Hotspot analysis pattern: `issue_history.py:1257-1365`
- Dataclass pattern: `issue_history.py:195-232`
- Text formatting pattern: `issue_history.py:2251-2300`
