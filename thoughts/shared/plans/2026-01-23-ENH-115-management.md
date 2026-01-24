# ENH-115: Configuration Gaps Detection - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-115-configuration-gaps-detection.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `ll-history analyze` command provides comprehensive issue history analysis through the `calculate_analysis` function in `scripts/little_loops/issue_history.py`. It already includes `ManualPatternAnalysis` (from ENH-113), which detects manual patterns like test runs, lint fixes, etc.

### Key Discoveries
- `ManualPatternAnalysis` dataclass at `issue_history.py:448-471` provides the input data (manual patterns detected)
- `detect_manual_patterns()` function at `issue_history.py:1958-2033` scans issue content for patterns
- `HistoryAnalysis` aggregates all analysis results at `issue_history.py:597-696`
- `calculate_analysis()` orchestrates all analyses at `issue_history.py:2377-2516`
- Hooks configuration at `hooks/hooks.json` defines current hook events
- Agents stored in `agents/*.md`, skills in `skills/*/SKILL.md`

## Desired End State

A new `ConfigGapsAnalysis` that:
1. Reads current configuration (hooks, skills, agents)
2. Correlates manual patterns with potential automation configurations
3. Identifies gaps where manual work could be automated by config
4. Provides specific configuration suggestions with priority

### How to Verify
- `ll-history analyze` output includes "Configuration Gaps Analysis" section
- Suggestions are actionable and reference specific hook events
- Coverage score reflects automation coverage
- Tests pass for new dataclasses and function

## What We're NOT Doing

- Not modifying hooks.json or other config files (read-only analysis)
- Not implementing the actual suggested configurations (suggestions only)
- Not validating whether suggested hooks would work (feasibility analysis)

## Problem Analysis

Currently, `ManualPatternAnalysis` identifies patterns and suggests automations like "Add pre-commit hook for auto-formatting", but:
1. It doesn't check if that hook already exists
2. It doesn't provide specific configuration examples
3. It doesn't calculate overall coverage

## Solution Approach

1. Create `ConfigGap` dataclass to represent individual gaps
2. Create `ConfigGapsAnalysis` container dataclass with coverage metrics
3. Implement `detect_config_gaps()` that:
   - Loads current hooks from `hooks/hooks.json`
   - Scans for existing agents in `agents/`
   - Scans for existing skills in `skills/`
   - Maps manual patterns to potential config solutions
   - Identifies which solutions already exist vs. gaps
4. Integrate into `HistoryAnalysis` and formatting functions

## Implementation Phases

### Phase 1: Add ConfigGap and ConfigGapsAnalysis Dataclasses

#### Overview
Add the two new dataclasses after `ManualPatternAnalysis` at line 472.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add dataclasses after `ManualPatternAnalysis` (line 472)

```python
@dataclass
class ConfigGap:
    """A gap in configuration that could address recurring manual work."""

    gap_type: str  # "hook", "skill", "agent"
    description: str
    evidence: list[str] = field(default_factory=list)  # issue IDs showing the pattern
    suggested_config: str = ""  # example configuration
    priority: str = "medium"  # "high", "medium", "low"
    pattern_type: str = ""  # links back to ManualPattern.pattern_type

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gap_type": self.gap_type,
            "description": self.description,
            "evidence": self.evidence[:10],
            "suggested_config": self.suggested_config,
            "priority": self.priority,
            "pattern_type": self.pattern_type,
        }


@dataclass
class ConfigGapsAnalysis:
    """Analysis of configuration gaps based on manual pattern detection."""

    gaps: list[ConfigGap] = field(default_factory=list)
    current_hooks: list[str] = field(default_factory=list)
    current_skills: list[str] = field(default_factory=list)
    current_agents: list[str] = field(default_factory=list)
    coverage_score: float = 0.0  # 0-1, how well config covers common needs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "current_hooks": self.current_hooks,
            "current_skills": self.current_skills,
            "current_agents": self.current_agents,
            "coverage_score": round(self.coverage_score, 2),
        }
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Update `__all__` exports (around line 43)

Add after "ManualPatternAnalysis":
```python
    "ConfigGap",
    "ConfigGapsAnalysis",
```

Add after "detect_manual_patterns":
```python
    "detect_config_gaps",
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/`

---

### Phase 2: Update HistoryAnalysis Dataclass

#### Overview
Add the new analysis field to `HistoryAnalysis` and its `to_dict()` method.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add field to `HistoryAnalysis` (around line 640)

After `complexity_proxy_analysis: ComplexityProxyAnalysis | None = None`:
```python
    # Configuration gaps analysis
    config_gaps_analysis: ConfigGapsAnalysis | None = None
```

**Changes**: Update `HistoryAnalysis.to_dict()` (around line 691)

After `complexity_proxy_analysis` entry:
```python
            "config_gaps_analysis": (
                self.config_gaps_analysis.to_dict() if self.config_gaps_analysis else None
            ),
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 3: Implement detect_config_gaps Function

#### Overview
Implement the core analysis function that reads configuration and identifies gaps.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add gap detection configuration (after `_MANUAL_PATTERNS`, around line 1955)

```python
# Mapping from manual pattern types to configuration solutions
_PATTERN_TO_CONFIG: dict[str, dict[str, Any]] = {
    "test": {
        "hook_event": "PostToolUse",
        "description": "Automatic test execution after code changes",
        "suggested_config": '''hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "pytest tests/ -x -q",
      "timeout": 30000
    }]
  }]''',
    },
    "lint": {
        "hook_event": "PreToolUse",
        "description": "Automatic formatting before file writes",
        "suggested_config": '''hooks/hooks.json:
  "PreToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "ruff format --check .",
      "timeout": 10000
    }]
  }]''',
    },
    "type_check": {
        "hook_event": "PostToolUse",
        "description": "Type checking after code modifications",
        "suggested_config": '''hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "mypy --fast .",
      "timeout": 30000
    }]
  }]''',
    },
    "build": {
        "hook_event": "PostToolUse",
        "description": "Build verification after changes",
        "suggested_config": '''hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "npm run build",
      "timeout": 60000
    }]
  }]''',
    },
}
```

**Changes**: Add `detect_config_gaps()` function (after `detect_manual_patterns`, around line 2035)

```python
def detect_config_gaps(
    manual_pattern_analysis: ManualPatternAnalysis,
    project_root: Path | None = None,
) -> ConfigGapsAnalysis:
    """Detect configuration gaps based on manual pattern analysis.

    Args:
        manual_pattern_analysis: Results from detect_manual_patterns()
        project_root: Project root directory (defaults to cwd)

    Returns:
        ConfigGapsAnalysis with identified gaps and coverage metrics
    """
    if project_root is None:
        project_root = Path.cwd()

    # Discover current configuration
    current_hooks: list[str] = []
    current_skills: list[str] = []
    current_agents: list[str] = []

    # Load hooks configuration
    hooks_file = project_root / "hooks" / "hooks.json"
    if hooks_file.exists():
        try:
            with open(hooks_file, encoding="utf-8") as f:
                hooks_data = json.load(f)
            current_hooks = list(hooks_data.get("hooks", {}).keys())
        except Exception:
            pass

    # Scan for agents
    agents_dir = project_root / "agents"
    if agents_dir.is_dir():
        for agent_file in agents_dir.glob("*.md"):
            current_agents.append(agent_file.stem)

    # Scan for skills
    skills_dir = project_root / "skills"
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                current_skills.append(skill_dir.name)

    # Identify gaps from manual patterns
    gaps: list[ConfigGap] = []
    covered_patterns = 0
    total_patterns = len(manual_pattern_analysis.patterns)

    for pattern in manual_pattern_analysis.patterns:
        config_mapping = _PATTERN_TO_CONFIG.get(pattern.pattern_type)
        if not config_mapping:
            continue

        hook_event = config_mapping["hook_event"]

        # Check if hook event is already configured
        if hook_event in current_hooks:
            covered_patterns += 1
            continue

        # Determine priority based on occurrence count
        if pattern.occurrence_count >= 10:
            priority = "high"
        elif pattern.occurrence_count >= 5:
            priority = "medium"
        else:
            priority = "low"

        gap = ConfigGap(
            gap_type="hook",
            description=config_mapping["description"],
            evidence=pattern.affected_issues,
            suggested_config=config_mapping["suggested_config"],
            priority=priority,
            pattern_type=pattern.pattern_type,
        )
        gaps.append(gap)

    # Calculate coverage score
    coverage_score = covered_patterns / total_patterns if total_patterns > 0 else 1.0

    # Sort gaps by priority (high first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.priority, 3))

    return ConfigGapsAnalysis(
        gaps=gaps,
        current_hooks=current_hooks,
        current_skills=current_skills,
        current_agents=current_agents,
        coverage_score=coverage_score,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/`

---

### Phase 4: Integrate into calculate_analysis

#### Overview
Call `detect_config_gaps()` and include results in `HistoryAnalysis`.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Update `calculate_analysis()` signature and body (around line 2377)

Update signature to accept project_root:
```python
def calculate_analysis(
    completed_issues: list[CompletedIssue],
    issues_dir: Path | None = None,
    period_type: Literal["weekly", "monthly", "quarterly"] = "monthly",
    compare_days: int | None = None,
    project_root: Path | None = None,
) -> HistoryAnalysis:
```

Update docstring:
```python
    """Calculate comprehensive history analysis.

    Args:
        completed_issues: List of completed issues
        issues_dir: Path to .issues/ for active issue scanning
        period_type: Grouping period for trend analysis
        compare_days: Days for comparative analysis (e.g., 30 for 30d comparison)
        project_root: Project root for config gap analysis (defaults to cwd)

    Returns:
        HistoryAnalysis with all metrics
    """
```

Add after `complexity_proxy_analysis = analyze_complexity_proxy(...)` (around line 2447):
```python
    # Configuration gaps analysis (depends on manual_pattern_analysis)
    config_gaps_analysis = detect_config_gaps(manual_pattern_analysis, project_root)
```

Add to `HistoryAnalysis` constructor (around line 2471):
```python
        config_gaps_analysis=config_gaps_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 5: Add Text and Markdown Formatting

#### Overview
Add output formatting for the new analysis section.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add text formatting in `format_analysis_text()` (after manual pattern section, around line 2813)

```python
    # Configuration gaps analysis
    if analysis.config_gaps_analysis:
        cga = analysis.config_gaps_analysis

        lines.append("")
        lines.append("Configuration Gaps Analysis")
        lines.append("-" * 27)
        lines.append(f"  Coverage score: {cga.coverage_score * 100:.0f}%")
        lines.append(f"  Current hooks: {', '.join(cga.current_hooks) or 'none'}")
        lines.append(f"  Current skills: {len(cga.current_skills)}")
        lines.append(f"  Current agents: {len(cga.current_agents)}")

        if cga.gaps:
            lines.append("")
            lines.append("  Identified Gaps:")

            for i, gap in enumerate(cga.gaps[:5], 1):
                lines.append("")
                lines.append(f"  {i}. Missing: {gap.gap_type} for {gap.description}")
                lines.append(f"     Priority: {gap.priority}")
                issues_str = ", ".join(gap.evidence[:3])
                if len(gap.evidence) > 3:
                    issues_str += ", ..."
                lines.append(f"     Evidence: {issues_str}")
                if gap.suggested_config:
                    lines.append("     Suggested config:")
                    for config_line in gap.suggested_config.split("\n")[:4]:
                        lines.append(f"       {config_line}")
```

**Changes**: Add markdown formatting in `format_analysis_markdown()` (after manual pattern section, around line 3263)

```python
    # Configuration Gaps Analysis
    if analysis.config_gaps_analysis:
        cga = analysis.config_gaps_analysis

        lines.append("")
        lines.append("## Configuration Gaps Analysis")
        lines.append("")
        lines.append(f"**Coverage score**: {cga.coverage_score * 100:.0f}%")
        lines.append("")
        lines.append("### Current Configuration")
        lines.append("")
        lines.append(f"- **Hooks**: {', '.join(cga.current_hooks) or 'none'}")
        lines.append(f"- **Skills**: {len(cga.current_skills)}")
        lines.append(f"- **Agents**: {len(cga.current_agents)}")

        if cga.gaps:
            lines.append("")
            lines.append("### Identified Gaps")
            lines.append("")
            lines.append("| Priority | Type | Description | Evidence |")
            lines.append("|----------|------|-------------|----------|")

            for gap in cga.gaps[:10]:
                issues_str = ", ".join(gap.evidence[:3])
                if len(gap.evidence) > 3:
                    issues_str += "..."
                lines.append(
                    f"| {gap.priority} | {gap.gap_type} | {gap.description} | {issues_str} |"
                )

            lines.append("")
            lines.append("### Suggested Configurations")
            lines.append("")
            for i, gap in enumerate(cga.gaps[:5], 1):
                if gap.suggested_config:
                    lines.append(f"**{i}. {gap.description}**")
                    lines.append("")
                    lines.append("```json")
                    lines.append(gap.suggested_config)
                    lines.append("```")
                    lines.append("")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/`

---

### Phase 6: Add Tests

#### Overview
Add tests for the new dataclasses and function.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add tests for ConfigGap, ConfigGapsAnalysis, and detect_config_gaps

```python
def test_config_gap_dataclass():
    """Test ConfigGap dataclass."""
    gap = ConfigGap(
        gap_type="hook",
        description="Automatic test execution",
        evidence=["BUG-001", "BUG-002"],
        suggested_config="hooks/hooks.json: {...}",
        priority="high",
        pattern_type="test",
    )

    assert gap.gap_type == "hook"
    assert gap.priority == "high"

    d = gap.to_dict()
    assert d["gap_type"] == "hook"
    assert len(d["evidence"]) == 2


def test_config_gaps_analysis_dataclass():
    """Test ConfigGapsAnalysis dataclass."""
    analysis = ConfigGapsAnalysis(
        gaps=[
            ConfigGap(
                gap_type="hook",
                description="Test hook",
                priority="high",
            )
        ],
        current_hooks=["SessionStart", "Stop"],
        current_skills=["skill1"],
        current_agents=["agent1"],
        coverage_score=0.65,
    )

    assert len(analysis.gaps) == 1
    assert analysis.coverage_score == 0.65

    d = analysis.to_dict()
    assert d["coverage_score"] == 0.65
    assert len(d["current_hooks"]) == 2


def test_detect_config_gaps_empty():
    """Test detect_config_gaps with empty manual patterns."""
    from little_loops.issue_history import detect_config_gaps, ManualPatternAnalysis

    mpa = ManualPatternAnalysis()
    result = detect_config_gaps(mpa)

    assert result.coverage_score == 1.0
    assert len(result.gaps) == 0


def test_detect_config_gaps_with_patterns(tmp_path):
    """Test detect_config_gaps identifies gaps from patterns."""
    from little_loops.issue_history import (
        detect_config_gaps,
        ManualPattern,
        ManualPatternAnalysis,
    )

    # Create a hooks.json with one hook
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    hooks_file = hooks_dir / "hooks.json"
    hooks_file.write_text('{"hooks": {"SessionStart": []}}')

    # Create patterns that should trigger gaps
    mpa = ManualPatternAnalysis(
        patterns=[
            ManualPattern(
                pattern_type="test",
                pattern_description="Test execution",
                occurrence_count=8,
                affected_issues=["BUG-001", "BUG-002"],
            ),
            ManualPattern(
                pattern_type="lint",
                pattern_description="Lint fixes",
                occurrence_count=5,
                affected_issues=["ENH-001"],
            ),
        ],
        total_manual_interventions=13,
        automatable_count=13,
    )

    result = detect_config_gaps(mpa, project_root=tmp_path)

    assert len(result.current_hooks) == 1
    assert "SessionStart" in result.current_hooks
    assert len(result.gaps) == 2
    assert result.gaps[0].priority == "high"  # test has 8 occurrences
    assert result.gaps[1].priority == "medium"  # lint has 5 occurrences
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/tests/`

---

## Testing Strategy

### Unit Tests
- `ConfigGap` dataclass creation and serialization
- `ConfigGapsAnalysis` dataclass with coverage score calculation
- `detect_config_gaps()` with empty input
- `detect_config_gaps()` with patterns that match existing hooks (coverage)
- `detect_config_gaps()` with patterns that have no matching hooks (gaps)

### Integration Tests
- End-to-end: `ll-history analyze` output includes new section

## References

- Original issue: `.issues/enhancements/P4-ENH-115-configuration-gaps-detection.md`
- ManualPatternAnalysis: `issue_history.py:448-471`
- detect_manual_patterns: `issue_history.py:1958-2033`
- calculate_analysis: `issue_history.py:2377-2516`
- format_analysis_text: `issue_history.py:2554-2903`
- format_analysis_markdown: `issue_history.py:2919+`
