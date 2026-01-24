# ENH-116: Hotspot Analysis - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-116-hotspot-analysis.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `issue_history.py` module (1240 lines) provides comprehensive issue analysis including:
- `SubsystemHealth` dataclass (`issue_history.py:156-174`) - tracks issues by directory with trend analysis
- `_extract_subsystem()` (`issue_history.py:523-543`) - extracts a single directory from issue content
- `_analyze_subsystems()` (`issue_history.py:690-737`) - aggregates by directory, calculates trends

### Key Discoveries
- Existing path extraction only captures **one directory** per issue (`_extract_subsystem`)
- `issue_discovery.py:221-242` has `_extract_file_paths()` that extracts **all file paths**
- `SubsystemHealth` tracks directories but not individual file hotspots
- Missing: bug ratio per file, issue type breakdown, churn indicators
- The analysis integrates into `calculate_analysis()` at line 889

### Patterns to Follow
- Dataclass with `to_dict()` method for serialization (`issue_history.py:49-71`)
- Dictionary-based aggregation pattern (`issue_history.py:690-737`)
- Text/Markdown formatting with tables (`issue_history.py:990-1240`)

## Desired End State

A `Hotspot` dataclass and `HotspotAnalysis` result that identifies:
1. **File hotspots** - Individual files appearing in multiple issues
2. **Directory hotspots** - Directories with high issue counts
3. **Bug magnets** - Files/directories with >60% bug ratio
4. **Churn indicators** - High/medium/low based on issue frequency

Integrated into `ll-history analyze` output in all formats (text, JSON, markdown, YAML).

### How to Verify
- `ll-history analyze` shows hotspot section in output
- Files with multiple issues correctly aggregated
- Bug ratio calculated correctly
- Output matches expected format from issue specification

## What We're NOT Doing

- Not implementing ENH-117 (regression clustering) - separate issue
- Not implementing ENH-118-121 (other derived analyses) - blocked by this
- Not changing the `SubsystemHealth` structure - new parallel structure
- Not modifying existing path extraction for subsystems - additive change

## Problem Analysis

The current subsystem analysis aggregates by directory but lacks:
1. Individual file tracking
2. Issue type breakdown per file/directory
3. Bug ratio calculation for hotspot identification
4. Churn classification

## Solution Approach

1. Create `Hotspot` dataclass to capture file-level hotspot data
2. Create `HotspotAnalysis` dataclass to hold analysis results
3. Create `_extract_paths_from_issue()` helper that extracts ALL file paths (not just directory)
4. Create `analyze_hotspots()` function that aggregates by file and directory
5. Integrate into `HistoryAnalysis` dataclass
6. Add formatting in text/markdown output

## Implementation Phases

### Phase 1: Add Data Structures

#### Overview
Define the `Hotspot` and `HotspotAnalysis` dataclasses.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add dataclasses after `SubsystemHealth` (around line 175)

```python
@dataclass
class Hotspot:
    """A file or directory that appears in multiple issues."""

    path: str
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    issue_types: dict[str, int] = field(default_factory=dict)  # {"BUG": 5, "ENH": 3}
    bug_ratio: float = 0.0  # bugs / total issues
    churn_indicator: str = "low"  # "high", "medium", "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "issue_count": self.issue_count,
            "issue_ids": self.issue_ids[:10],  # Top 10
            "issue_types": self.issue_types,
            "bug_ratio": round(self.bug_ratio, 3),
            "churn_indicator": self.churn_indicator,
        }


@dataclass
class HotspotAnalysis:
    """Analysis of files and directories appearing repeatedly in issues."""

    file_hotspots: list[Hotspot] = field(default_factory=list)
    directory_hotspots: list[Hotspot] = field(default_factory=list)
    bug_magnets: list[Hotspot] = field(default_factory=list)  # >60% bug ratio

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_hotspots": [h.to_dict() for h in self.file_hotspots],
            "directory_hotspots": [h.to_dict() for h in self.directory_hotspots],
            "bug_magnets": [h.to_dict() for h in self.bug_magnets],
        }
```

**Changes**: Update `HistoryAnalysis` dataclass (around line 219) to add hotspot field

```python
# After subsystem_health line
hotspot_analysis: HotspotAnalysis | None = None
```

**Changes**: Update `HistoryAnalysis.to_dict()` to include hotspots

```python
# In to_dict() method
"hotspot_analysis": self.hotspot_analysis.to_dict() if self.hotspot_analysis else None,
```

**Changes**: Update `__all__` to export new classes (around line 23)

```python
"Hotspot",
"HotspotAnalysis",
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Module imports: `python -c "from little_loops.issue_history import Hotspot, HotspotAnalysis"`

---

### Phase 2: Add Path Extraction Helper

#### Overview
Create helper function to extract all file paths from issue content.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add helper function after `_extract_subsystem()` (around line 544)

```python
def _extract_paths_from_issue(content: str) -> list[str]:
    """Extract all file paths from issue content.

    Args:
        content: Issue file content

    Returns:
        List of file paths found in content
    """
    # Match common file path patterns
    patterns = [
        r"\*\*File\*\*:\s*`?([^`\n:]+)`?",  # **File**: path/to/file.py
        r"`([a-zA-Z_][\w/.-]+\.[a-z]{2,4})`",  # `path/to/file.py`
        r"(?:^|\s)([a-zA-Z_][\w/.-]+\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",  # path.py or path.py:123
    ]

    paths: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            path = match.group(1).strip()
            # Must look like a file path (has extension)
            if "/" in path or path.endswith((".py", ".md", ".js", ".ts", ".json", ".yaml", ".yml")):
                # Normalize: remove line numbers (path.py:123 -> path.py)
                if ":" in path and path.split(":")[-1].isdigit():
                    path = ":".join(path.split(":")[:-1])
                paths.add(path)

    return sorted(paths)
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Unit test passes: `python -m pytest scripts/tests/test_issue_history.py -k "extract_paths" -v`

---

### Phase 3: Add Hotspot Analysis Function

#### Overview
Create the main analysis function that aggregates issues by file and directory.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add analysis function after `_analyze_subsystems()` (around line 738)

```python
def analyze_hotspots(issues: list[CompletedIssue]) -> HotspotAnalysis:
    """Identify files and directories that appear repeatedly in issues.

    Args:
        issues: List of completed issues

    Returns:
        HotspotAnalysis with file and directory hotspots
    """
    file_data: dict[str, dict[str, Any]] = {}  # path -> {count, ids, types}
    dir_data: dict[str, dict[str, Any]] = {}  # dir -> {count, ids, types}

    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8")
        except Exception:
            continue

        paths = _extract_paths_from_issue(content)

        for path in paths:
            # Track file hotspot
            if path not in file_data:
                file_data[path] = {"count": 0, "ids": [], "types": {}}
            file_data[path]["count"] += 1
            file_data[path]["ids"].append(issue.issue_id)
            file_data[path]["types"][issue.issue_type] = (
                file_data[path]["types"].get(issue.issue_type, 0) + 1
            )

            # Track directory hotspot
            if "/" in path:
                dir_path = "/".join(path.split("/")[:-1]) + "/"
            else:
                dir_path = "./"

            if dir_path not in dir_data:
                dir_data[dir_path] = {"count": 0, "ids": [], "types": {}}
            if issue.issue_id not in dir_data[dir_path]["ids"]:
                dir_data[dir_path]["count"] += 1
                dir_data[dir_path]["ids"].append(issue.issue_id)
                dir_data[dir_path]["types"][issue.issue_type] = (
                    dir_data[dir_path]["types"].get(issue.issue_type, 0) + 1
                )

    # Convert to Hotspot objects
    file_hotspots: list[Hotspot] = []
    for path, data in file_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        # Determine churn indicator
        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        file_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Convert directory data to Hotspot objects
    dir_hotspots: list[Hotspot] = []
    for path, data in dir_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        dir_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Sort by issue count descending
    file_hotspots.sort(key=lambda h: -h.issue_count)
    dir_hotspots.sort(key=lambda h: -h.issue_count)

    # Identify bug magnets (>60% bug ratio, at least 3 issues)
    bug_magnets = [
        h for h in file_hotspots if h.bug_ratio > 0.6 and h.issue_count >= 3
    ]
    bug_magnets.sort(key=lambda h: (-h.bug_ratio, -h.issue_count))

    return HotspotAnalysis(
        file_hotspots=file_hotspots[:10],  # Top 10
        directory_hotspots=dir_hotspots[:10],  # Top 10
        bug_magnets=bug_magnets[:5],  # Top 5
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 4: Integrate into calculate_analysis

#### Overview
Call the hotspot analysis function in the main analysis function.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add hotspot analysis call in `calculate_analysis()` after subsystem analysis (around line 890)

```python
# After: subsystem_health = _analyze_subsystems(completed_issues)
# Add:
hotspot_analysis = analyze_hotspots(completed_issues)
```

**Changes**: Update `HistoryAnalysis` construction (around line 905) to include hotspots

```python
# Add to HistoryAnalysis construction:
hotspot_analysis=hotspot_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`

---

### Phase 5: Add Text Output Formatting

#### Overview
Add hotspot section to text output formatter.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add hotspot section in `format_analysis_text()` after subsystem health (around line 1050)

```python
    # After subsystem health section, add:

    # Hotspot analysis
    if analysis.hotspot_analysis:
        hotspots = analysis.hotspot_analysis

        if hotspots.file_hotspots:
            lines.append("")
            lines.append("File Hotspots")
            lines.append("-" * 13)
            for h in hotspots.file_hotspots[:5]:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                churn_flag = " [HIGH CHURN]" if h.churn_indicator == "high" else ""
                lines.append(f"  {h.path:40}: {h.issue_count:2} issues ({types_str}){churn_flag}")

        if hotspots.bug_magnets:
            lines.append("")
            lines.append("Bug Magnets (>60% bugs)")
            lines.append("-" * 23)
            for h in hotspots.bug_magnets:
                lines.append(f"  {h.path}: {h.bug_ratio*100:.0f}% bugs ({h.issue_types.get('BUG', 0)}/{h.issue_count})")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 6: Add Markdown Output Formatting

#### Overview
Add hotspot section to markdown output formatter.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add hotspot section in `format_analysis_markdown()` after subsystem health (around line 1172)

```python
    # After subsystem health section, add:

    # Hotspot Analysis
    if analysis.hotspot_analysis:
        hotspots = analysis.hotspot_analysis

        if hotspots.file_hotspots:
            lines.append("")
            lines.append("## File Hotspots")
            lines.append("")
            lines.append("| File | Issues | Types | Churn |")
            lines.append("|------|--------|-------|-------|")
            for h in hotspots.file_hotspots:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                churn_badge = "🔥" if h.churn_indicator == "high" else ("⚡" if h.churn_indicator == "medium" else "")
                lines.append(f"| `{h.path}` | {h.issue_count} | {types_str} | {churn_badge} |")

        if hotspots.directory_hotspots:
            lines.append("")
            lines.append("## Directory Hotspots")
            lines.append("")
            lines.append("| Directory | Issues | Types |")
            lines.append("|-----------|--------|-------|")
            for h in hotspots.directory_hotspots[:5]:
                types_str = ", ".join(f"{k}:{v}" for k, v in sorted(h.issue_types.items()))
                lines.append(f"| `{h.path}` | {h.issue_count} | {types_str} |")

        if hotspots.bug_magnets:
            lines.append("")
            lines.append("## Bug Magnets")
            lines.append("")
            lines.append("Files with >60% bug ratio that may need refactoring attention:")
            lines.append("")
            lines.append("| File | Bug Ratio | Bugs/Total |")
            lines.append("|------|-----------|------------|")
            for h in hotspots.bug_magnets:
                lines.append(f"| `{h.path}` | {h.bug_ratio*100:.0f}% | {h.issue_types.get('BUG', 0)}/{h.issue_count} |")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 7: Add Unit Tests

#### Overview
Add comprehensive tests for the new hotspot functionality.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add test class for Hotspot dataclass

```python
class TestHotspot:
    """Tests for Hotspot dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        from little_loops.issue_history import Hotspot

        hotspot = Hotspot(
            path="src/core/processor.py",
            issue_count=5,
            issue_ids=["BUG-001", "BUG-002", "ENH-003", "BUG-004", "ENH-005"],
            issue_types={"BUG": 3, "ENH": 2},
            bug_ratio=0.6,
            churn_indicator="high",
        )
        result = hotspot.to_dict()

        assert result["path"] == "src/core/processor.py"
        assert result["issue_count"] == 5
        assert result["bug_ratio"] == 0.6
        assert result["churn_indicator"] == "high"
        assert result["issue_types"] == {"BUG": 3, "ENH": 2}

    def test_to_dict_limits_issue_ids(self) -> None:
        """Test that to_dict limits issue_ids to 10."""
        from little_loops.issue_history import Hotspot

        hotspot = Hotspot(
            path="test.py",
            issue_count=15,
            issue_ids=[f"BUG-{i:03d}" for i in range(15)],
        )
        result = hotspot.to_dict()

        assert len(result["issue_ids"]) == 10
```

**Changes**: Add test class for path extraction

```python
class TestExtractPathsFromIssue:
    """Tests for _extract_paths_from_issue function."""

    def test_extract_file_path_pattern(self) -> None:
        """Test extracting **File**: pattern."""
        from little_loops.issue_history import _extract_paths_from_issue

        content = "**File**: `scripts/little_loops/cli.py`"
        paths = _extract_paths_from_issue(content)
        assert "scripts/little_loops/cli.py" in paths

    def test_extract_backtick_pattern(self) -> None:
        """Test extracting backtick file paths."""
        from little_loops.issue_history import _extract_paths_from_issue

        content = "The bug is in `src/core/processor.py` and `src/utils/helper.py`"
        paths = _extract_paths_from_issue(content)
        assert "src/core/processor.py" in paths
        assert "src/utils/helper.py" in paths

    def test_extract_path_with_line_number(self) -> None:
        """Test extracting paths with line numbers."""
        from little_loops.issue_history import _extract_paths_from_issue

        content = "See scripts/cli.py:123 for the issue"
        paths = _extract_paths_from_issue(content)
        assert "scripts/cli.py" in paths
        assert "scripts/cli.py:123" not in paths  # Line number stripped

    def test_no_paths_found(self) -> None:
        """Test with no file paths."""
        from little_loops.issue_history import _extract_paths_from_issue

        content = "This is a general issue with no specific files."
        paths = _extract_paths_from_issue(content)
        assert paths == []
```

**Changes**: Add test class for hotspot analysis

```python
class TestAnalyzeHotspots:
    """Tests for analyze_hotspots function."""

    def test_empty_issues(self) -> None:
        """Test with empty issues list."""
        from little_loops.issue_history import analyze_hotspots

        result = analyze_hotspots([])
        assert result.file_hotspots == []
        assert result.directory_hotspots == []
        assert result.bug_magnets == []

    def test_single_issue(self, tmp_path: Path) -> None:
        """Test with a single issue containing file paths."""
        from little_loops.issue_history import CompletedIssue, analyze_hotspots

        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("**File**: `src/core/processor.py`\n\nBug in processor.")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]

        result = analyze_hotspots(issues)
        assert len(result.file_hotspots) == 1
        assert result.file_hotspots[0].path == "src/core/processor.py"
        assert result.file_hotspots[0].issue_count == 1

    def test_bug_magnet_detection(self, tmp_path: Path) -> None:
        """Test detection of bug magnets (>60% bug ratio)."""
        from little_loops.issue_history import CompletedIssue, analyze_hotspots

        # Create 4 issues for same file: 3 bugs, 1 enhancement
        issues = []
        for i, issue_type in enumerate(["BUG", "BUG", "BUG", "ENH"]):
            issue_file = tmp_path / f"P1-{issue_type}-{i:03d}.md"
            issue_file.write_text("**File**: `src/problematic.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type=issue_type,
                    priority="P1",
                    issue_id=f"{issue_type}-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        assert len(result.bug_magnets) == 1
        assert result.bug_magnets[0].path == "src/problematic.py"
        assert result.bug_magnets[0].bug_ratio == 0.75  # 3/4

    def test_churn_indicator(self, tmp_path: Path) -> None:
        """Test churn indicator assignment."""
        from little_loops.issue_history import CompletedIssue, analyze_hotspots

        # Create 5 issues for high churn
        issues = []
        for i in range(5):
            issue_file = tmp_path / f"P1-BUG-{i:03d}.md"
            issue_file.write_text("**File**: `src/churny.py`")
            issues.append(
                CompletedIssue(
                    path=issue_file,
                    issue_type="BUG",
                    priority="P1",
                    issue_id=f"BUG-{i:03d}",
                )
            )

        result = analyze_hotspots(issues)
        assert result.file_hotspots[0].churn_indicator == "high"
```

**Changes**: Update imports at top of test file

```python
from little_loops.issue_history import (
    CompletedIssue,
    HistorySummary,
    Hotspot,
    HotspotAnalysis,
    calculate_summary,
    format_summary_json,
    format_summary_text,
    parse_completed_issue,
    scan_completed_issues,
)
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Coverage adequate: `python -m pytest scripts/tests/test_issue_history.py --cov=little_loops.issue_history`

---

## Testing Strategy

### Unit Tests
- `Hotspot` dataclass serialization
- `HotspotAnalysis` dataclass serialization
- `_extract_paths_from_issue()` with various patterns
- `analyze_hotspots()` with empty, single, and multiple issues
- Bug magnet detection threshold
- Churn indicator assignment

### Integration Tests
- Full analysis pipeline with hotspots
- Output formatters include hotspot sections
- CLI `ll-history analyze` shows hotspots

## References

- Original issue: `.issues/enhancements/P2-ENH-116-hotspot-analysis.md`
- Similar pattern: `_analyze_subsystems()` at `issue_history.py:690-737`
- Path extraction pattern: `issue_discovery.py:221-242`
- Dataclass pattern: `SubsystemHealth` at `issue_history.py:156-174`
