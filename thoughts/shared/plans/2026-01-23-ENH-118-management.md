# ENH-118: Cross-Cutting Concern Smell Detection - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-118-cross-cutting-concern-smell.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The ll-history module provides comprehensive analysis of completed issues through dataclasses and analysis functions:

### Key Discoveries
- All analysis dataclasses defined in `scripts/little_loops/issue_history.py:100-640`
- `HistoryAnalysis` container at `issue_history.py:643-749` holds all sub-analyses as optional fields
- `_extract_paths_from_issue()` at `issue_history.py:1130-1156` extracts file paths from issue content
- `calculate_analysis()` at `issue_history.py:2583-2728` orchestrates all analysis functions
- `format_analysis_text()` at `issue_history.py:2766-3157` handles text output formatting
- `format_analysis_markdown()` at `issue_history.py:3160+` handles markdown output
- Pattern for keyword-based detection exists in `detect_manual_patterns()` at `issue_history.py:1962-2086`
- Exports listed in `__all__` at `issue_history.py:23-70`

### Current Patterns Being Followed
- `ManualPattern` and `ManualPatternAnalysis` dataclasses (lines 425-474) as structural model
- `detect_manual_patterns()` function as implementation pattern for keyword matching
- Existing keyword definitions in `_MANUAL_PATTERNS` dict (lines 1962-2008)

## Desired End State

A `detect_cross_cutting_smells()` function that:
1. Analyzes completed issues to identify concerns that touch multiple unrelated directories
2. Categorizes concerns by type (logging, error-handling, validation, auth, caching)
3. Calculates scatter scores based on directory spread
4. Suggests patterns for consolidation (middleware, decorator, aspect)
5. Integrates into the `ll-history analyze` output

### How to Verify
- Run `ll-history analyze` and see new "Cross-Cutting Concern Analysis" section
- Tests pass for new dataclasses and function
- Lint and type checks pass

## What We're NOT Doing

- Not implementing actual refactoring suggestions
- Not modifying any existing analysis functions
- Not changing the issue file format
- Deferring markdown formatting to separate phase if time constrained

## Problem Analysis

Cross-cutting concerns like logging, error handling, validation, auth, and caching often get scattered across the codebase when proper abstractions are missing. By analyzing which issues touch multiple unrelated directories and correlating with concern keywords, we can identify areas where consolidation would be beneficial.

## Solution Approach

1. Define `CrossCuttingSmell` and `CrossCuttingAnalysis` dataclasses
2. Implement `detect_cross_cutting_smells()` that:
   - Uses `_extract_paths_from_issue()` to get paths from each issue
   - Groups paths by directory and counts unique directories per issue
   - Filters to issues touching 3+ directories
   - Detects concern type via keyword matching in issue content
   - Calculates scatter score (unique directories / total possible)
   - Suggests patterns based on concern type
3. Add field to `HistoryAnalysis` and call in `calculate_analysis()`
4. Add text formatting in `format_analysis_text()`
5. Add tests for dataclasses and detection function

## Implementation Phases

### Phase 1: Define Dataclasses

#### Overview
Add `CrossCuttingSmell` and `CrossCuttingAnalysis` dataclasses to issue_history.py.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add dataclasses after `ComplexityProxyAnalysis` (after line 641)

```python
@dataclass
class CrossCuttingSmell:
    """A detected cross-cutting concern scattered across the codebase."""

    concern_type: str  # "logging", "error-handling", "validation", "auth", "caching"
    affected_directories: list[str] = field(default_factory=list)
    issue_count: int = 0
    issue_ids: list[str] = field(default_factory=list)
    scatter_score: float = 0.0  # higher = more scattered (0-1)
    suggested_pattern: str = ""  # "middleware", "decorator", "aspect"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "concern_type": self.concern_type,
            "affected_directories": self.affected_directories[:10],
            "issue_count": self.issue_count,
            "issue_ids": self.issue_ids[:10],
            "scatter_score": round(self.scatter_score, 2),
            "suggested_pattern": self.suggested_pattern,
        }


@dataclass
class CrossCuttingAnalysis:
    """Analysis of cross-cutting concerns scattered across the codebase."""

    smells: list[CrossCuttingSmell] = field(default_factory=list)
    most_scattered_concern: str = ""
    consolidation_opportunities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "smells": [s.to_dict() for s in self.smells],
            "most_scattered_concern": self.most_scattered_concern,
            "consolidation_opportunities": self.consolidation_opportunities[:10],
        }
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add to `__all__` exports (after line 46)

```python
    "CrossCuttingSmell",
    "CrossCuttingAnalysis",
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add to `__all__` exports (after line 62, functions section)

```python
    "detect_cross_cutting_smells",
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add field to `HistoryAnalysis` (after line 689, after config_gaps_analysis)

```python
    # Cross-cutting concern analysis
    cross_cutting_analysis: CrossCuttingAnalysis | None = None
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add to `HistoryAnalysis.to_dict()` (after line 744, after config_gaps_analysis)

```python
            "cross_cutting_analysis": (
                self.cross_cutting_analysis.to_dict() if self.cross_cutting_analysis else None
            ),
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

---

### Phase 2: Implement Detection Function

#### Overview
Implement `detect_cross_cutting_smells()` function with keyword-based concern detection.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add concern keywords constant (before `detect_cross_cutting_smells`, after `_MANUAL_PATTERNS` around line 2008)

```python
# Cross-cutting concern keywords for smell detection
_CROSS_CUTTING_KEYWORDS: dict[str, list[str]] = {
    "logging": ["log", "logger", "logging", "debug", "trace", "print"],
    "error-handling": ["error", "exception", "try", "catch", "raise", "except", "fail"],
    "validation": ["valid", "validate", "check", "assert", "verify", "sanitize"],
    "auth": ["auth", "permission", "role", "access", "token", "credential", "login"],
    "caching": ["cache", "memo", "memoize", "store", "ttl", "expire", "cached"],
}

# Suggested patterns for each concern type
_CONCERN_PATTERNS: dict[str, str] = {
    "logging": "decorator",
    "error-handling": "middleware",
    "validation": "decorator",
    "auth": "middleware",
    "caching": "decorator",
}
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add detection function (after the constants, around line 2145)

```python
def detect_cross_cutting_smells(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
) -> CrossCuttingAnalysis:
    """Detect cross-cutting concerns scattered across the codebase.

    Args:
        issues: List of completed issues
        hotspots: Hotspot analysis results (provides path extraction reference)

    Returns:
        CrossCuttingAnalysis with detected smells
    """
    if not issues:
        return CrossCuttingAnalysis()

    # Track concern data: {concern_type: {dirs: set, issues: list}}
    concern_data: dict[str, dict[str, Any]] = {}
    for concern_type in _CROSS_CUTTING_KEYWORDS:
        concern_data[concern_type] = {
            "directories": set(),
            "issue_ids": [],
        }

    # Get all unique directories from hotspots for scatter score calculation
    all_directories: set[str] = set()
    if hotspots.directory_hotspots:
        all_directories = {h.path for h in hotspots.directory_hotspots}

    # Analyze each issue
    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8").lower()
        except Exception:
            continue

        # Extract paths from this issue
        paths = _extract_paths_from_issue(issue.path.read_text(encoding="utf-8"))
        issue_dirs = {str(Path(p).parent) for p in paths if "/" in p or "\\" in p}
        all_directories.update(issue_dirs)

        # Check if this issue touches multiple directories (3+)
        if len(issue_dirs) < 3:
            continue

        # Check for concern keywords
        for concern_type, keywords in _CROSS_CUTTING_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                concern_data[concern_type]["directories"].update(issue_dirs)
                if issue.issue_id not in concern_data[concern_type]["issue_ids"]:
                    concern_data[concern_type]["issue_ids"].append(issue.issue_id)

    # Build CrossCuttingSmell objects
    smells: list[CrossCuttingSmell] = []
    total_dirs = len(all_directories) if all_directories else 1

    for concern_type, data in concern_data.items():
        if data["issue_ids"]:  # Only include concerns with detected issues
            dirs = sorted(data["directories"])
            scatter_score = len(dirs) / total_dirs if total_dirs > 0 else 0.0

            smell = CrossCuttingSmell(
                concern_type=concern_type,
                affected_directories=dirs,
                issue_count=len(data["issue_ids"]),
                issue_ids=data["issue_ids"],
                scatter_score=scatter_score,
                suggested_pattern=_CONCERN_PATTERNS.get(concern_type, "aspect"),
            )
            smells.append(smell)

    # Sort by scatter score descending
    smells.sort(key=lambda s: -s.scatter_score)

    # Identify most scattered concern
    most_scattered = smells[0].concern_type if smells else ""

    # Build consolidation opportunities
    consolidation_opportunities = []
    for smell in smells:
        if smell.scatter_score >= 0.3:  # Threshold for suggesting consolidation
            consolidation_opportunities.append(
                f"Centralize {smell.concern_type} ({smell.issue_count} issues would benefit)"
            )

    return CrossCuttingAnalysis(
        smells=smells,
        most_scattered_concern=most_scattered,
        consolidation_opportunities=consolidation_opportunities[:10],
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

---

### Phase 3: Integrate with calculate_analysis and Formatting

#### Overview
Call the detection function from `calculate_analysis()` and add text formatting.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Call function in `calculate_analysis()` (after line 2658, after config_gaps_analysis)

```python
    # Cross-cutting concern analysis (depends on hotspot_analysis)
    cross_cutting_analysis = detect_cross_cutting_smells(completed_issues, hotspot_analysis)
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Pass to HistoryAnalysis constructor (after line 2683, after config_gaps_analysis)

```python
        cross_cutting_analysis=cross_cutting_analysis,
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add formatting in `format_analysis_text()` (after line 3129, after complexity proxy section, before technical debt)

```python
    # Cross-cutting concern analysis
    if analysis.cross_cutting_analysis:
        cca = analysis.cross_cutting_analysis

        if cca.smells:
            lines.append("")
            lines.append("Cross-Cutting Concern Analysis")
            lines.append("-" * 30)

            for i, smell in enumerate(cca.smells[:5], 1):
                scatter_label = (
                    "HIGH"
                    if smell.scatter_score >= 0.6
                    else "MEDIUM"
                    if smell.scatter_score >= 0.3
                    else "LOW"
                )
                lines.append("")
                lines.append(f"  {i}. {smell.concern_type.title()} [{scatter_label} SCATTER]")
                dirs_str = ", ".join(smell.affected_directories[:3])
                if len(smell.affected_directories) > 3:
                    dirs_str += ", ..."
                lines.append(f"     Directories: {dirs_str}")
                issues_str = ", ".join(smell.issue_ids[:3])
                if len(smell.issue_ids) > 3:
                    issues_str += ", ..."
                lines.append(f"     Issues: {issues_str} ({smell.issue_count} total)")
                lines.append(f"     Scatter score: {smell.scatter_score:.2f}")
                lines.append(f"     Suggested pattern: {smell.suggested_pattern}")

            if cca.consolidation_opportunities:
                lines.append("")
                lines.append("  Consolidation Opportunities:")
                for opp in cca.consolidation_opportunities[:5]:
                    lines.append(f"    - {opp}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Run `ll-history analyze` to verify output contains new section

---

### Phase 4: Add Tests

#### Overview
Add tests for the new dataclasses and detection function.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add test classes at end of file

```python
class TestCrossCuttingSmell:
    """Tests for CrossCuttingSmell dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict conversion."""
        smell = CrossCuttingSmell(
            concern_type="logging",
            affected_directories=["src/api", "src/core", "src/utils"],
            issue_count=3,
            issue_ids=["BUG-001", "ENH-002", "BUG-003"],
            scatter_score=0.75,
            suggested_pattern="decorator",
        )
        result = smell.to_dict()

        assert result["concern_type"] == "logging"
        assert len(result["affected_directories"]) == 3
        assert result["issue_count"] == 3
        assert result["scatter_score"] == 0.75
        assert result["suggested_pattern"] == "decorator"

    def test_to_dict_limits_lists(self) -> None:
        """Test that to_dict limits list lengths to 10."""
        smell = CrossCuttingSmell(
            concern_type="error-handling",
            affected_directories=[f"dir{i}" for i in range(15)],
            issue_ids=[f"BUG-{i:03d}" for i in range(15)],
        )
        result = smell.to_dict()

        assert len(result["affected_directories"]) == 10
        assert len(result["issue_ids"]) == 10


class TestCrossCuttingAnalysis:
    """Tests for CrossCuttingAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty analysis."""
        analysis = CrossCuttingAnalysis()
        result = analysis.to_dict()

        assert result["smells"] == []
        assert result["most_scattered_concern"] == ""
        assert result["consolidation_opportunities"] == []

    def test_to_dict_with_smells(self) -> None:
        """Test to_dict with smells."""
        smell = CrossCuttingSmell(
            concern_type="logging",
            issue_count=2,
            scatter_score=0.5,
        )
        analysis = CrossCuttingAnalysis(
            smells=[smell],
            most_scattered_concern="logging",
            consolidation_opportunities=["Centralize logging (2 issues would benefit)"],
        )
        result = analysis.to_dict()

        assert len(result["smells"]) == 1
        assert result["most_scattered_concern"] == "logging"
        assert len(result["consolidation_opportunities"]) == 1


class TestDetectCrossCuttingSmells:
    """Tests for detect_cross_cutting_smells function."""

    def test_empty_issues(self) -> None:
        """Test with empty list."""
        result = detect_cross_cutting_smells([], HotspotAnalysis())
        assert result.smells == []
        assert result.most_scattered_concern == ""

    def test_issues_without_multi_directory(self, tmp_path: Path) -> None:
        """Test issues that don't touch multiple directories."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""## Changes
Fixed logging in `src/api/handler.py`.
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())
        # Should not detect smell since only 1 directory
        assert result.smells == [] or all(s.issue_count == 0 for s in result.smells)

    def test_detects_logging_concern(self, tmp_path: Path) -> None:
        """Test detection of logging concern across directories."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""## Summary
Added logging throughout the application.

## Changes Made
- `src/api/routes.py`: Added logger
- `src/core/engine.py`: Added debug logging
- `src/utils/helpers.py`: Added trace logging
- `scripts/cli.py`: Added logging setup
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())

        logging_smells = [s for s in result.smells if s.concern_type == "logging"]
        assert len(logging_smells) == 1
        assert logging_smells[0].issue_count == 1
        assert "BUG-001" in logging_smells[0].issue_ids

    def test_detects_error_handling_concern(self, tmp_path: Path) -> None:
        """Test detection of error handling concern."""
        issue_file = tmp_path / "P2-ENH-001.md"
        issue_file.write_text("""## Summary
Improved error handling across modules.

## Changes Made
- `src/api/handler.py`: Added try/except blocks
- `src/core/processor.py`: Improved exception handling
- `src/services/client.py`: Added error recovery
- `tests/test_api.py`: Added error test cases
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="ENH",
                priority="P2",
                issue_id="ENH-001",
            )
        ]
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())

        error_smells = [s for s in result.smells if s.concern_type == "error-handling"]
        assert len(error_smells) == 1
        assert error_smells[0].suggested_pattern == "middleware"

    def test_aggregates_across_issues(self, tmp_path: Path) -> None:
        """Test aggregation across multiple issues."""
        issue1 = tmp_path / "P1-BUG-001.md"
        issue1.write_text("""Added validation to `src/api/v1/routes.py`, `src/core/models.py`, `src/utils/validators.py`.""")

        issue2 = tmp_path / "P2-ENH-002.md"
        issue2.write_text("""More validation in `src/api/v2/routes.py`, `src/services/auth.py`, `tests/test_valid.py`.""")

        issues = [
            CompletedIssue(path=issue1, issue_type="BUG", priority="P1", issue_id="BUG-001"),
            CompletedIssue(path=issue2, issue_type="ENH", priority="P2", issue_id="ENH-002"),
        ]
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())

        validation_smells = [s for s in result.smells if s.concern_type == "validation"]
        if validation_smells:
            assert validation_smells[0].issue_count >= 1

    def test_file_read_error_handled(self, tmp_path: Path) -> None:
        """Test that file read errors are handled gracefully."""
        nonexistent = tmp_path / "nonexistent.md"
        issues = [
            CompletedIssue(
                path=nonexistent,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        # Should not raise
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())
        assert result is not None

    def test_smells_sorted_by_scatter_score(self, tmp_path: Path) -> None:
        """Test that smells are sorted by scatter score descending."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""
logging logging logging
error error
validation
auth auth auth auth
caching

Files: `a/f1.py`, `b/f2.py`, `c/f3.py`, `d/f4.py`
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = detect_cross_cutting_smells(issues, HotspotAnalysis())

        if len(result.smells) >= 2:
            for i in range(len(result.smells) - 1):
                assert result.smells[i].scatter_score >= result.smells[i + 1].scatter_score
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v -k "CrossCutting or detect_cross_cutting"`
- [ ] All tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test `CrossCuttingSmell.to_dict()` serialization
- Test `CrossCuttingAnalysis.to_dict()` serialization
- Test `detect_cross_cutting_smells()` with empty input
- Test detection of each concern type (logging, error-handling, validation, auth, caching)
- Test aggregation across multiple issues
- Test file read error handling
- Test scatter score sorting

### Integration Tests
- Verify `ll-history analyze` includes new section in output

## References

- Original issue: `.issues/enhancements/P4-ENH-118-cross-cutting-concern-smell.md`
- Pattern reference: `detect_manual_patterns()` at `issue_history.py:2011-2086`
- Dataclass pattern: `ManualPattern` at `issue_history.py:425-447`
- Similar implementation: `ConfigGapsAnalysis` at `issue_history.py:501-518`
