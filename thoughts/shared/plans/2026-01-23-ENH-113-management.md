# ENH-113: Recurring Manual Patterns Detection - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-113-recurring-manual-patterns-detection.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-history` module (`scripts/little_loops/issue_history.py`) provides comprehensive analysis of completed issues including hotspot detection, regression clustering, test gap correlation, and rejection rate analysis. Each analysis type follows a consistent pattern:

### Key Discoveries
- Analysis dataclasses defined at issue_history.py:189-395
- `HistoryAnalysis` container at issue_history.py:398-476 holds all analysis types
- `calculate_analysis()` at issue_history.py:1630-1755 orchestrates analysis functions
- Text formatting at issue_history.py:1793-2023
- Markdown formatting at issue_history.py:2026-2365
- Module exports at issue_history.py:23-58

### Patterns to Follow
- `TestGap`/`TestGapAnalysis` at issue_history.py:269-312 - item + container pattern
- `analyze_rejection_rates()` at issue_history.py:1421-1524 - parsing issue content for patterns
- Text output formatting at issue_history.py:1939-1992
- Markdown output formatting at issue_history.py:2244-2298

## Desired End State

A new analysis section that identifies repetitive manual activities that could be automated through hooks, skills, or agents. The analysis will:
1. Parse issue content for common command patterns (test execution, lint commands, build steps)
2. Group patterns by type and count occurrences
3. Suggest specific automation methods (hooks, skills, agents)
4. Assign complexity ratings to help prioritize automation efforts

### How to Verify
- `ll-history analyze` includes "Manual Pattern Analysis" section
- Patterns are detected from test commands, lint commands, build commands
- Each pattern includes actionable automation suggestion
- Tests pass for new dataclasses and analysis function

## What We're NOT Doing

- Not implementing the actual automation - only detecting patterns
- Not modifying hooks, skills, or agents - only suggesting them
- Not changing existing analysis functions
- Deferring machine-learning based pattern detection to future enhancement

## Problem Analysis

Users perform repetitive manual tasks during issue resolution that could be automated. By analyzing issue history, we can identify:
1. Test commands run repeatedly across issues
2. Lint/format fixes applied consistently
3. Build steps executed manually
4. Git operations following patterns

These patterns can inform automation suggestions.

## Solution Approach

Follow the established pattern for analysis types:
1. Define `ManualPattern` dataclass for individual patterns
2. Define `ManualPatternAnalysis` container dataclass
3. Implement `detect_manual_patterns()` function that parses issue content
4. Integrate into `HistoryAnalysis` and `calculate_analysis()`
5. Add text and markdown formatting sections

## Implementation Phases

### Phase 1: Define Dataclasses

#### Overview
Add `ManualPattern` and `ManualPatternAnalysis` dataclasses following the existing patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add dataclasses after `RejectionAnalysis` (around line 373)

```python
@dataclass
class ManualPattern:
    """A recurring manual activity detected across issues."""

    pattern_type: str  # "test", "lint", "build", "git", "verification"
    pattern_description: str
    occurrence_count: int = 0
    affected_issues: list[str] = field(default_factory=list)  # issue IDs
    example_commands: list[str] = field(default_factory=list)  # sample commands found
    suggested_automation: str = ""  # hook, skill, or agent suggestion
    automation_complexity: str = "simple"  # "trivial", "simple", "moderate"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pattern_type": self.pattern_type,
            "pattern_description": self.pattern_description,
            "occurrence_count": self.occurrence_count,
            "affected_issues": self.affected_issues[:10],
            "example_commands": self.example_commands[:5],
            "suggested_automation": self.suggested_automation,
            "automation_complexity": self.automation_complexity,
        }


@dataclass
class ManualPatternAnalysis:
    """Analysis of recurring manual activities that could be automated."""

    patterns: list[ManualPattern] = field(default_factory=list)
    total_manual_interventions: int = 0
    automatable_count: int = 0
    automation_suggestions: list[str] = field(default_factory=list)

    @property
    def automatable_percentage(self) -> float:
        """Calculate percentage of patterns that are automatable."""
        if self.total_manual_interventions == 0:
            return 0.0
        return self.automatable_count / self.total_manual_interventions * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "total_manual_interventions": self.total_manual_interventions,
            "automatable_count": self.automatable_count,
            "automatable_percentage": round(self.automatable_percentage, 1),
            "automation_suggestions": self.automation_suggestions[:10],
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_issue_history.py -v -k "ManualPattern"` passes
- [ ] `python -m mypy scripts/little_loops/issue_history.py` passes

---

### Phase 2: Implement Detection Function

#### Overview
Implement `detect_manual_patterns()` function that parses issue content for recurring command patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add function after `analyze_rejection_rates()` (around line 1525)

```python
# Pattern definitions for manual activity detection
_MANUAL_PATTERNS = {
    "test": {
        "patterns": [
            r"(?:pytest|python -m pytest|npm test|yarn test|jest|cargo test|go test)",
            r"(?:python -m unittest|nosetests|tox)",
        ],
        "description": "Test execution after code changes",
        "suggestion": "Add post-edit hook for automatic test runs",
        "complexity": "trivial",
    },
    "lint": {
        "patterns": [
            r"(?:ruff check|ruff format|black|isort|flake8|pylint|mypy)",
            r"(?:eslint|prettier|tslint)",
        ],
        "description": "Lint/format fixes after implementation",
        "suggestion": "Add pre-commit hook for auto-formatting",
        "complexity": "simple",
    },
    "type_check": {
        "patterns": [
            r"(?:mypy|pyright|python -m mypy)",
            r"(?:tsc|npx tsc)",
        ],
        "description": "Type checking during development",
        "suggestion": "Add mypy to pre-commit or post-edit hook",
        "complexity": "simple",
    },
    "build": {
        "patterns": [
            r"(?:npm run build|yarn build|make|cargo build|go build)",
            r"(?:python -m build|pip install -e)",
        ],
        "description": "Build steps during implementation",
        "suggestion": "Add build verification to test suite or CI",
        "complexity": "moderate",
    },
    "git": {
        "patterns": [
            r"git (?:add|commit|push|pull|checkout|branch)",
        ],
        "description": "Git operations during issue resolution",
        "suggestion": "Use /ll:commit skill for standardized commits",
        "complexity": "trivial",
    },
}


def detect_manual_patterns(issues: list[CompletedIssue]) -> ManualPatternAnalysis:
    """Detect recurring manual activities that could be automated.

    Args:
        issues: List of completed issues

    Returns:
        ManualPatternAnalysis with detected patterns
    """
    if not issues:
        return ManualPatternAnalysis()

    # Track pattern occurrences
    pattern_data: dict[str, dict[str, Any]] = {}

    for pattern_type, config in _MANUAL_PATTERNS.items():
        pattern_data[pattern_type] = {
            "count": 0,
            "issues": [],
            "commands": [],
            "config": config,
        }

    # Scan issue content for patterns
    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8")
        except Exception:
            continue

        for pattern_type, config in _MANUAL_PATTERNS.items():
            for pattern in config["patterns"]:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    data = pattern_data[pattern_type]
                    data["count"] += len(matches)
                    if issue.issue_id not in data["issues"]:
                        data["issues"].append(issue.issue_id)
                    # Store unique command examples
                    for match in matches:
                        if match not in data["commands"]:
                            data["commands"].append(match)

    # Build ManualPattern objects
    patterns: list[ManualPattern] = []
    total_interventions = 0
    automatable = 0

    for pattern_type, data in pattern_data.items():
        if data["count"] > 0:
            config = data["config"]
            pattern = ManualPattern(
                pattern_type=pattern_type,
                pattern_description=config["description"],
                occurrence_count=data["count"],
                affected_issues=data["issues"],
                example_commands=data["commands"][:5],
                suggested_automation=config["suggestion"],
                automation_complexity=config["complexity"],
            )
            patterns.append(pattern)
            total_interventions += data["count"]
            automatable += data["count"]

    # Sort by occurrence count descending
    patterns.sort(key=lambda p: -p.occurrence_count)

    # Build automation suggestions
    suggestions = [p.suggested_automation for p in patterns if p.occurrence_count >= 2]

    return ManualPatternAnalysis(
        patterns=patterns,
        total_manual_interventions=total_interventions,
        automatable_count=automatable,
        automation_suggestions=suggestions[:10],
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_issue_history.py -v -k "detect_manual_patterns"` passes
- [ ] `python -m mypy scripts/little_loops/issue_history.py` passes

---

### Phase 3: Integrate into HistoryAnalysis

#### Overview
Add `manual_pattern_analysis` field to `HistoryAnalysis` and call `detect_manual_patterns()` in `calculate_analysis()`.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add field to `HistoryAnalysis` dataclass (around line 432)
```python
    # Manual pattern analysis
    manual_pattern_analysis: ManualPatternAnalysis | None = None
```

**Change 2**: Add serialization in `HistoryAnalysis.to_dict()` (around line 468)
```python
            "manual_pattern_analysis": (
                self.manual_pattern_analysis.to_dict()
                if self.manual_pattern_analysis
                else None
            ),
```

**Change 3**: Call function in `calculate_analysis()` (around line 1690)
```python
    # Manual pattern analysis
    manual_pattern_analysis = detect_manual_patterns(completed_issues)
```

**Change 4**: Add to analysis construction (around line 1709)
```python
        manual_pattern_analysis=manual_pattern_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_issue_history.py -v` passes
- [ ] `python -m mypy scripts/little_loops/issue_history.py` passes

---

### Phase 4: Add Formatting Output

#### Overview
Add text and markdown formatting sections for the manual pattern analysis.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change 1**: Add text formatting section in `format_analysis_text()` (after rejection analysis, before technical debt - around line 1993)

```python
    # Manual pattern analysis
    if analysis.manual_pattern_analysis:
        mpa = analysis.manual_pattern_analysis

        if mpa.patterns:
            lines.append("")
            lines.append("Manual Pattern Analysis")
            lines.append("-" * 23)
            lines.append(
                f"  Total manual interventions: {mpa.total_manual_interventions}"
            )
            lines.append(
                f"  Potentially automatable: {mpa.automatable_percentage:.0f}% "
                f"({mpa.automatable_count}/{mpa.total_manual_interventions})"
            )
            lines.append("")
            lines.append("  Recurring Patterns:")

            for i, pattern in enumerate(mpa.patterns[:5], 1):
                lines.append("")
                lines.append(
                    f"  {i}. {pattern.pattern_description} ({pattern.occurrence_count} occurrences)"
                )
                issues_str = ", ".join(pattern.affected_issues[:3])
                if len(pattern.affected_issues) > 3:
                    issues_str += ", ..."
                lines.append(f"     Issues: {issues_str}")
                lines.append(f"     Suggestion: {pattern.suggested_automation}")
                lines.append(f"     Complexity: {pattern.automation_complexity}")
```

**Change 2**: Add markdown formatting section in `format_analysis_markdown()` (after rejection analysis, before technical debt - around line 2298)

```python
    # Manual Pattern Analysis
    if analysis.manual_pattern_analysis:
        mpa = analysis.manual_pattern_analysis

        if mpa.patterns:
            lines.append("")
            lines.append("## Manual Pattern Analysis")
            lines.append("")
            lines.append(
                f"**Total manual interventions detected**: {mpa.total_manual_interventions}"
            )
            lines.append(
                f"**Potentially automatable**: {mpa.automatable_percentage:.0f}% "
                f"({mpa.automatable_count}/{mpa.total_manual_interventions})"
            )
            lines.append("")
            lines.append("### Recurring Patterns")
            lines.append("")
            lines.append("| Pattern | Occurrences | Affected Issues | Suggestion | Complexity |")
            lines.append("|---------|-------------|-----------------|------------|------------|")

            for pattern in mpa.patterns[:10]:
                issues_str = ", ".join(pattern.affected_issues[:3])
                if len(pattern.affected_issues) > 3:
                    issues_str += "..."
                lines.append(
                    f"| {pattern.pattern_description} | {pattern.occurrence_count} | "
                    f"{issues_str} | {pattern.suggested_automation} | "
                    f"{pattern.automation_complexity} |"
                )

            if mpa.automation_suggestions:
                lines.append("")
                lines.append("### Automation Suggestions")
                lines.append("")
                lines.append("Based on detected patterns, consider implementing:")
                lines.append("")
                for suggestion in mpa.automation_suggestions[:5]:
                    lines.append(f"- {suggestion}")
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_issue_history.py -v` passes
- [ ] `ll-history analyze` shows Manual Pattern Analysis section

---

### Phase 5: Add Module Exports

#### Overview
Add new dataclasses and function to `__all__` exports.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`

**Change**: Add to `__all__` after `RejectionAnalysis` (around line 38)
```python
    "ManualPattern",
    "ManualPatternAnalysis",
```

**Change**: Add to analysis functions section (around line 50)
```python
    "detect_manual_patterns",
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.issue_history import ManualPattern, ManualPatternAnalysis, detect_manual_patterns"` succeeds

---

### Phase 6: Write Tests

#### Overview
Add comprehensive tests for the new functionality following existing test patterns.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add test classes at end of file

```python
class TestManualPattern:
    """Tests for ManualPattern dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        pattern = ManualPattern(
            pattern_type="test",
            pattern_description="Test execution after code changes",
            occurrence_count=5,
            affected_issues=["BUG-001", "BUG-002", "ENH-003"],
            example_commands=["pytest", "python -m pytest"],
            suggested_automation="Add post-edit hook for automatic test runs",
            automation_complexity="trivial",
        )
        result = pattern.to_dict()

        assert result["pattern_type"] == "test"
        assert result["pattern_description"] == "Test execution after code changes"
        assert result["occurrence_count"] == 5
        assert len(result["affected_issues"]) == 3
        assert result["automation_complexity"] == "trivial"

    def test_to_dict_limits_lists(self) -> None:
        """Test that to_dict limits affected_issues and example_commands."""
        pattern = ManualPattern(
            pattern_type="test",
            pattern_description="Test execution",
            occurrence_count=15,
            affected_issues=[f"BUG-{i:03d}" for i in range(15)],
            example_commands=[f"cmd{i}" for i in range(10)],
        )
        result = pattern.to_dict()

        assert len(result["affected_issues"]) == 10
        assert len(result["example_commands"]) == 5


class TestManualPatternAnalysis:
    """Tests for ManualPatternAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test to_dict with empty analysis."""
        analysis = ManualPatternAnalysis()
        result = analysis.to_dict()

        assert result["patterns"] == []
        assert result["total_manual_interventions"] == 0
        assert result["automatable_count"] == 0
        assert result["automatable_percentage"] == 0.0

    def test_automatable_percentage(self) -> None:
        """Test automatable_percentage calculation."""
        analysis = ManualPatternAnalysis(
            total_manual_interventions=100,
            automatable_count=67,
        )
        assert analysis.automatable_percentage == 67.0

    def test_automatable_percentage_zero_total(self) -> None:
        """Test automatable_percentage with zero total."""
        analysis = ManualPatternAnalysis(
            total_manual_interventions=0,
            automatable_count=0,
        )
        assert analysis.automatable_percentage == 0.0


class TestDetectManualPatterns:
    """Tests for detect_manual_patterns function."""

    def test_empty_issues(self) -> None:
        """Test with empty list."""
        result = detect_manual_patterns([])
        assert result.total_manual_interventions == 0
        assert result.patterns == []

    def test_detects_pytest(self, tmp_path: Path) -> None:
        """Test detection of pytest commands."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""## Changes Made

Ran `pytest tests/` to verify the fix.
Also executed `python -m pytest -v` for verbose output.
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = detect_manual_patterns(issues)

        assert result.total_manual_interventions >= 2
        test_patterns = [p for p in result.patterns if p.pattern_type == "test"]
        assert len(test_patterns) == 1
        assert test_patterns[0].occurrence_count >= 2
        assert "BUG-001" in test_patterns[0].affected_issues

    def test_detects_lint_commands(self, tmp_path: Path) -> None:
        """Test detection of lint/format commands."""
        issue_file = tmp_path / "P2-ENH-001.md"
        issue_file.write_text("""## Implementation

Ran `ruff check scripts/` and `ruff format scripts/` to fix issues.
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="ENH",
                priority="P2",
                issue_id="ENH-001",
            )
        ]
        result = detect_manual_patterns(issues)

        lint_patterns = [p for p in result.patterns if p.pattern_type == "lint"]
        assert len(lint_patterns) == 1
        assert lint_patterns[0].occurrence_count >= 2

    def test_detects_multiple_patterns(self, tmp_path: Path) -> None:
        """Test detection of multiple pattern types."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("""## Implementation

1. Ran `pytest` to identify failing tests
2. Ran `mypy scripts/` for type checking
3. Ran `ruff format` to fix formatting
""")
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = detect_manual_patterns(issues)

        pattern_types = {p.pattern_type for p in result.patterns}
        assert "test" in pattern_types
        assert "type_check" in pattern_types
        assert "lint" in pattern_types

    def test_aggregates_across_issues(self, tmp_path: Path) -> None:
        """Test pattern aggregation across multiple issues."""
        issue1 = tmp_path / "P1-BUG-001.md"
        issue1.write_text("Ran `pytest` to verify.")

        issue2 = tmp_path / "P2-BUG-002.md"
        issue2.write_text("Executed `pytest tests/` to check.")

        issues = [
            CompletedIssue(
                path=issue1,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            ),
            CompletedIssue(
                path=issue2,
                issue_type="BUG",
                priority="P2",
                issue_id="BUG-002",
            ),
        ]
        result = detect_manual_patterns(issues)

        test_patterns = [p for p in result.patterns if p.pattern_type == "test"]
        assert len(test_patterns) == 1
        assert test_patterns[0].occurrence_count >= 2
        assert "BUG-001" in test_patterns[0].affected_issues
        assert "BUG-002" in test_patterns[0].affected_issues

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
        result = detect_manual_patterns(issues)
        assert result.total_manual_interventions == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_issue_history.py -v -k "ManualPattern or detect_manual"` passes

---

## Testing Strategy

### Unit Tests
- `ManualPattern.to_dict()` serialization
- `ManualPatternAnalysis.to_dict()` serialization
- `ManualPatternAnalysis.automatable_percentage` calculation
- `detect_manual_patterns()` with various input scenarios

### Integration Tests
- Full `calculate_analysis()` includes manual pattern analysis
- Text and markdown formatting include new section

## References

- Original issue: `.issues/enhancements/P3-ENH-113-recurring-manual-patterns-detection.md`
- Similar implementation: `TestGap`/`TestGapAnalysis` at issue_history.py:269-312
- Analysis function pattern: `analyze_rejection_rates()` at issue_history.py:1421-1524
- Text formatting pattern: issue_history.py:1939-1992
- Markdown formatting pattern: issue_history.py:2244-2298
