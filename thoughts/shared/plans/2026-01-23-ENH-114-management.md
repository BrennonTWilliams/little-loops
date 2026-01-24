# ENH-114: Agent Effectiveness Analysis - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-114-agent-effectiveness-analysis.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `issue_history.py` module provides comprehensive analysis of completed issues including rejection rates, manual patterns, hotspots, and more. However, there is no analysis tracking which processing agents (ll-auto, ll-parallel, or manual) handled issues.

### Key Discoveries
- `_parse_resolution_action()` exists at `scripts/little_loops/issue_history.py:646-688` for categorizing completion outcomes (ENH-112 dependency satisfied)
- `RejectionMetrics`/`RejectionAnalysis` at lines 319-376 provide a pattern to follow for metrics dataclasses
- `ManualPattern`/`ManualPatternAnalysis` at lines 378-427 show another analysis pattern
- `calculate_analysis()` at lines 1820-1949 orchestrates all analyses - new analysis integrates here
- `HistoryAnalysis` dataclass at lines 454-494 contains all analysis results
- Completed issues do NOT have an explicit `processed_by` field in frontmatter or resolution sections
- Agent detection must be inferred from available metadata fields

### Agent Detection Strategy

Based on analysis of completed issues, agents can be detected from:

1. **`discovered_source` frontmatter field**: Contains log filenames like `ll-parallel-blender-agents-debug.log`
2. **Log Type field in content**: Pattern `**Log Type**: ll-parallel` or `**Log Type**: ll-auto`
3. **Tool field in content**: Pattern `**Tool**: ll-parallel` or `**Tool**: ll-auto`
4. **Default to "manual"**: When no automated agent indicators are found

This is imperfect but provides useful heuristics. The agent detected is the *source* of issue discovery/processing context, not necessarily the processor of the fix.

## Desired End State

A new analysis section in `ll-history analyze` output that shows:
- Success rates per agent per issue type
- Duration metrics per agent
- Recommendations for routing issues to most effective agents
- Warning indicators for problematic agent/issue-type combinations

### How to Verify
- Unit tests for all new dataclasses
- Unit tests for agent detection function
- Unit tests for analysis function
- Integration into `calculate_analysis()` output
- Text and markdown formatting in reports

## What We're NOT Doing

- **Not modifying issue file format** - Agent detection uses existing fields only
- **Not adding git commit analysis** - Would require significant new infrastructure
- **Not tracking processing duration** - Would require start time capture not currently available
- **Not implementing statistical significance testing** - Simple ratio comparisons are sufficient

## Problem Analysis

Users cannot currently understand which agents are most effective for different issue types. This prevents:
- Optimal issue routing decisions
- Identification of agent configuration problems
- Targeted improvements to underperforming agents

## Solution Approach

1. Create `AgentOutcome` dataclass for per-agent, per-type metrics
2. Create `AgentEffectivenessAnalysis` container dataclass
3. Implement `_detect_processing_agent()` helper to identify agent from issue metadata
4. Implement `analyze_agent_effectiveness()` function following existing patterns
5. Integrate into `HistoryAnalysis` and `calculate_analysis()`
6. Add text and markdown formatting

## Implementation Phases

### Phase 1: Add Dataclasses

#### Overview
Create the two new dataclasses for agent effectiveness analysis.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add `AgentOutcome` and `AgentEffectivenessAnalysis` dataclasses after `ManualPatternAnalysis` (around line 428)

```python
@dataclass
class AgentOutcome:
    """Metrics for a single agent processing a specific issue type."""

    agent_name: str
    issue_type: str
    success_count: int = 0
    failure_count: int = 0
    rejection_count: int = 0

    @property
    def total_count(self) -> int:
        """Total issues handled."""
        return self.success_count + self.failure_count + self.rejection_count

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_name": self.agent_name,
            "issue_type": self.issue_type,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "rejection_count": self.rejection_count,
            "total_count": self.total_count,
            "success_rate": round(self.success_rate, 3),
        }


@dataclass
class AgentEffectivenessAnalysis:
    """Analysis of agent effectiveness across issue types."""

    outcomes: list[AgentOutcome] = field(default_factory=list)
    best_agent_by_type: dict[str, str] = field(default_factory=dict)
    problematic_combinations: list[tuple[str, str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "outcomes": [o.to_dict() for o in self.outcomes],
            "best_agent_by_type": self.best_agent_by_type,
            "problematic_combinations": self.problematic_combinations[:10],
        }
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Update `__all__` to export new classes

```python
# In __all__ list, add:
"AgentOutcome",
"AgentEffectivenessAnalysis",
"analyze_agent_effectiveness",
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add `agent_effectiveness_analysis` field to `HistoryAnalysis` dataclass (after `manual_pattern_analysis`)

```python
    # Agent effectiveness analysis
    agent_effectiveness_analysis: AgentEffectivenessAnalysis | None = None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 2: Implement Agent Detection Helper

#### Overview
Create helper function to detect which agent processed an issue.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add `_detect_processing_agent()` function after `_parse_resolution_action()` (around line 690)

```python
def _detect_processing_agent(content: str, discovered_source: str | None = None) -> str:
    """Detect which processing agent handled an issue.

    Detection strategy (in priority order):
    1. Check discovered_source field for 'll-parallel' or 'll-auto'
    2. Check content for '**Log Type**:' field
    3. Check content for '**Tool**:' field
    4. Default to 'manual'

    Args:
        content: Issue file content
        discovered_source: Optional discovered_source frontmatter value

    Returns:
        Agent name: 'll-auto', 'll-parallel', or 'manual'
    """
    # Check discovered_source first
    if discovered_source:
        source_lower = discovered_source.lower()
        if "ll-parallel" in source_lower:
            return "ll-parallel"
        if "ll-auto" in source_lower:
            return "ll-auto"

    # Check Log Type field
    log_type_match = re.search(r"\*\*Log Type\*\*:\s*(.+?)(?:\n|$)", content)
    if log_type_match:
        log_type = log_type_match.group(1).strip().lower()
        if "ll-parallel" in log_type:
            return "ll-parallel"
        if "ll-auto" in log_type:
            return "ll-auto"

    # Check Tool field
    tool_match = re.search(r"\*\*Tool\*\*:\s*(.+?)(?:\n|$)", content)
    if tool_match:
        tool = tool_match.group(1).strip().lower()
        if "ll-parallel" in tool:
            return "ll-parallel"
        if "ll-auto" in tool:
            return "ll-auto"

    # Default to manual
    return "manual"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py::TestDetectProcessingAgent -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 3: Implement Analysis Function

#### Overview
Create the main analysis function following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add `analyze_agent_effectiveness()` function after `detect_manual_patterns()` (around line 1715)

```python
def analyze_agent_effectiveness(issues: list[CompletedIssue]) -> AgentEffectivenessAnalysis:
    """Analyze agent effectiveness across issue types.

    Groups issues by processing agent and issue type, calculating
    success/failure/rejection rates for each combination.

    Args:
        issues: List of completed issues

    Returns:
        AgentEffectivenessAnalysis with outcomes and recommendations
    """
    if not issues:
        return AgentEffectivenessAnalysis()

    # Track outcomes by (agent, issue_type)
    outcomes_map: dict[tuple[str, str], AgentOutcome] = {}

    for issue in issues:
        try:
            content = issue.path.read_text(encoding="utf-8")
        except Exception:
            continue

        # Detect agent (discovered_by may contain source info in some cases)
        agent = _detect_processing_agent(content, issue.discovered_by)

        # Get resolution outcome
        resolution = _parse_resolution_action(content)

        # Get or create outcome tracker
        key = (agent, issue.issue_type)
        if key not in outcomes_map:
            outcomes_map[key] = AgentOutcome(
                agent_name=agent,
                issue_type=issue.issue_type,
            )

        outcome = outcomes_map[key]

        # Categorize outcome
        if resolution == "completed":
            outcome.success_count += 1
        elif resolution in ("rejected", "invalid", "duplicate"):
            outcome.rejection_count += 1
        else:  # deferred or other
            outcome.failure_count += 1

    # Build outcomes list
    outcomes = list(outcomes_map.values())

    # Determine best agent per issue type
    best_agent_by_type: dict[str, str] = {}
    type_agents: dict[str, list[AgentOutcome]] = {}

    for outcome in outcomes:
        if outcome.issue_type not in type_agents:
            type_agents[outcome.issue_type] = []
        type_agents[outcome.issue_type].append(outcome)

    for issue_type, agent_outcomes in type_agents.items():
        # Require minimum sample size
        significant_outcomes = [o for o in agent_outcomes if o.total_count >= 3]
        if significant_outcomes:
            best = max(significant_outcomes, key=lambda o: o.success_rate)
            best_agent_by_type[issue_type] = best.agent_name

    # Identify problematic combinations (success rate < 50% with >= 5 samples)
    problematic_combinations: list[tuple[str, str, str]] = []
    for outcome in outcomes:
        if outcome.total_count >= 5 and outcome.success_rate < 0.5:
            reason = f"{outcome.success_rate * 100:.0f}% success ({outcome.success_count}/{outcome.total_count})"
            problematic_combinations.append(
                (outcome.agent_name, outcome.issue_type, reason)
            )

    # Sort by success rate ascending (worst first)
    problematic_combinations.sort(key=lambda x: float(x[2].split("%")[0]))

    return AgentEffectivenessAnalysis(
        outcomes=sorted(outcomes, key=lambda o: (o.agent_name, o.issue_type)),
        best_agent_by_type=best_agent_by_type,
        problematic_combinations=problematic_combinations,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py::TestAnalyzeAgentEffectiveness -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 4: Integrate into calculate_analysis

#### Overview
Wire up the new analysis into the main analysis orchestrator.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add call to `analyze_agent_effectiveness()` in `calculate_analysis()` and include result in `HistoryAnalysis`

After the manual pattern analysis call (around line 1881):
```python
    # Agent effectiveness analysis
    agent_effectiveness_analysis = analyze_agent_effectiveness(completed_issues)
```

In the `HistoryAnalysis` constructor (around line 1903):
```python
        agent_effectiveness_analysis=agent_effectiveness_analysis,
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`

---

### Phase 5: Add Output Formatting

#### Overview
Add text and markdown formatting for the new analysis section.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add text formatting in `format_analysis_text()` (after manual pattern section, around line 2220)

```python
    # Agent effectiveness analysis
    if analysis.agent_effectiveness_analysis:
        aea = analysis.agent_effectiveness_analysis

        if aea.outcomes:
            lines.append("")
            lines.append("Agent Effectiveness Analysis")
            lines.append("-" * 28)

            # Group by agent
            by_agent: dict[str, list[AgentOutcome]] = {}
            for outcome in aea.outcomes:
                if outcome.agent_name not in by_agent:
                    by_agent[outcome.agent_name] = []
                by_agent[outcome.agent_name].append(outcome)

            for agent in sorted(by_agent.keys()):
                lines.append(f"  {agent}:")
                for outcome in sorted(by_agent[agent], key=lambda o: o.issue_type):
                    rate_pct = outcome.success_rate * 100
                    flag = " [!]" if outcome.total_count >= 5 and rate_pct < 50 else ""
                    lines.append(
                        f"    {outcome.issue_type:5}: {rate_pct:5.1f}% success "
                        f"({outcome.success_count}/{outcome.total_count}){flag}"
                    )

            # Recommendations
            if aea.best_agent_by_type or aea.problematic_combinations:
                lines.append("")
                lines.append("  Recommendations:")
                for issue_type, best_agent in sorted(aea.best_agent_by_type.items()):
                    lines.append(f"    - {issue_type}: best handled by {best_agent}")
                for agent, issue_type, reason in aea.problematic_combinations[:3]:
                    lines.append(
                        f"    - {agent} underperforms for {issue_type} ({reason})"
                    )
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add markdown formatting in `format_analysis_markdown()` (after manual pattern section)

```python
    # Agent effectiveness analysis
    if analysis.agent_effectiveness_analysis:
        aea = analysis.agent_effectiveness_analysis

        if aea.outcomes:
            lines.append("")
            lines.append("## Agent Effectiveness Analysis")
            lines.append("")
            lines.append("| Agent | Type | Success Rate | Completed | Rejected | Failed |")
            lines.append("|-------|------|--------------|-----------|----------|--------|")

            for outcome in sorted(aea.outcomes, key=lambda o: (o.agent_name, o.issue_type)):
                rate_pct = outcome.success_rate * 100
                flag = " ⚠️" if outcome.total_count >= 5 and rate_pct < 50 else ""
                lines.append(
                    f"| {outcome.agent_name} | {outcome.issue_type} | "
                    f"{rate_pct:.1f}%{flag} | {outcome.success_count} | "
                    f"{outcome.rejection_count} | {outcome.failure_count} |"
                )

            # Recommendations
            if aea.best_agent_by_type or aea.problematic_combinations:
                lines.append("")
                lines.append("### Recommendations")
                lines.append("")
                for issue_type, best_agent in sorted(aea.best_agent_by_type.items()):
                    lines.append(f"- **{issue_type}**: Best handled by `{best_agent}`")
                for agent, issue_type, reason in aea.problematic_combinations[:3]:
                    lines.append(f"- **{agent}** underperforms for {issue_type} ({reason})")
```

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Add to `to_dict()` method of `HistoryAnalysis` dataclass

In the `to_dict()` method, add:
```python
            "agent_effectiveness_analysis": (
                self.agent_effectiveness_analysis.to_dict()
                if self.agent_effectiveness_analysis
                else None
            ),
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Run `ll-history analyze --format=text` shows agent effectiveness section
- [ ] Run `ll-history analyze --format=markdown` shows agent effectiveness table

---

### Phase 6: Add Unit Tests

#### Overview
Add comprehensive tests following existing patterns.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Add test classes for new functionality

```python
class TestAgentOutcome:
    """Tests for AgentOutcome dataclass."""

    def test_rates_empty(self) -> None:
        """Test rates with no data."""
        outcome = AgentOutcome(agent_name="ll-auto", issue_type="BUG")
        assert outcome.total_count == 0
        assert outcome.success_rate == 0.0

    def test_rates_calculation(self) -> None:
        """Test rate calculations."""
        outcome = AgentOutcome(
            agent_name="ll-auto",
            issue_type="BUG",
            success_count=8,
            failure_count=1,
            rejection_count=1,
        )
        assert outcome.total_count == 10
        assert outcome.success_rate == 0.8

    def test_to_dict(self) -> None:
        """Test serialization."""
        outcome = AgentOutcome(
            agent_name="ll-parallel",
            issue_type="ENH",
            success_count=5,
            failure_count=0,
            rejection_count=0,
        )
        result = outcome.to_dict()
        assert result["agent_name"] == "ll-parallel"
        assert result["issue_type"] == "ENH"
        assert result["success_rate"] == 1.0


class TestAgentEffectivenessAnalysis:
    """Tests for AgentEffectivenessAnalysis dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test serialization with no data."""
        analysis = AgentEffectivenessAnalysis()
        result = analysis.to_dict()
        assert result["outcomes"] == []
        assert result["best_agent_by_type"] == {}
        assert result["problematic_combinations"] == []

    def test_to_dict_with_data(self) -> None:
        """Test serialization with data."""
        analysis = AgentEffectivenessAnalysis(
            outcomes=[
                AgentOutcome("ll-auto", "BUG", success_count=10),
            ],
            best_agent_by_type={"BUG": "ll-auto"},
            problematic_combinations=[("ll-parallel", "FEAT", "40% success")],
        )
        result = analysis.to_dict()
        assert len(result["outcomes"]) == 1
        assert result["best_agent_by_type"]["BUG"] == "ll-auto"


class TestDetectProcessingAgent:
    """Tests for _detect_processing_agent function."""

    def test_detected_from_discovered_source_parallel(self) -> None:
        """Test detection from discovered_source field."""
        result = _detect_processing_agent("", "ll-parallel-blender-agents-debug.log")
        assert result == "ll-parallel"

    def test_detected_from_discovered_source_auto(self) -> None:
        """Test detection from discovered_source field."""
        result = _detect_processing_agent("", "ll-auto-run-2026-01-01.log")
        assert result == "ll-auto"

    def test_detected_from_log_type_field(self) -> None:
        """Test detection from Log Type field in content."""
        content = "**Log Type**: ll-parallel\n"
        result = _detect_processing_agent(content, None)
        assert result == "ll-parallel"

    def test_detected_from_tool_field(self) -> None:
        """Test detection from Tool field in content."""
        content = "**Tool**: ll-auto\n"
        result = _detect_processing_agent(content, None)
        assert result == "ll-auto"

    def test_default_to_manual(self) -> None:
        """Test default to manual when no indicators."""
        result = _detect_processing_agent("Regular issue content", None)
        assert result == "manual"

    def test_discovered_source_takes_priority(self) -> None:
        """Test that discovered_source is checked first."""
        content = "**Tool**: ll-auto\n"
        result = _detect_processing_agent(content, "ll-parallel-debug.log")
        assert result == "ll-parallel"


class TestAnalyzeAgentEffectiveness:
    """Tests for analyze_agent_effectiveness function."""

    def test_empty_issues(self) -> None:
        """Test with empty list."""
        result = analyze_agent_effectiveness([])
        assert result.outcomes == []

    def test_single_completed_issue(self, tmp_path: Path) -> None:
        """Test with single completed issue."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text(
            "**Log Type**: ll-auto\n\n## Resolution\n\n- **Action**: fix\n"
        )
        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = analyze_agent_effectiveness(issues)
        assert len(result.outcomes) == 1
        assert result.outcomes[0].agent_name == "ll-auto"
        assert result.outcomes[0].success_count == 1

    def test_grouped_by_agent_and_type(self, tmp_path: Path) -> None:
        """Test grouping by agent and type."""
        issue1 = tmp_path / "P1-BUG-001.md"
        issue1.write_text("**Tool**: ll-auto\n- **Action**: fix")

        issue2 = tmp_path / "P1-BUG-002.md"
        issue2.write_text("**Tool**: ll-auto\n- **Action**: fix")

        issue3 = tmp_path / "P1-ENH-001.md"
        issue3.write_text("**Tool**: ll-auto\n- **Action**: improve")

        issues = [
            CompletedIssue(path=issue1, issue_type="BUG", priority="P1", issue_id="BUG-001"),
            CompletedIssue(path=issue2, issue_type="BUG", priority="P1", issue_id="BUG-002"),
            CompletedIssue(path=issue3, issue_type="ENH", priority="P1", issue_id="ENH-001"),
        ]
        result = analyze_agent_effectiveness(issues)

        # Should have 2 outcomes: (ll-auto, BUG) and (ll-auto, ENH)
        assert len(result.outcomes) == 2

        bug_outcome = next(o for o in result.outcomes if o.issue_type == "BUG")
        assert bug_outcome.success_count == 2

        enh_outcome = next(o for o in result.outcomes if o.issue_type == "ENH")
        assert enh_outcome.success_count == 1

    def test_rejection_counted(self, tmp_path: Path) -> None:
        """Test that rejections are counted correctly."""
        issue_file = tmp_path / "P1-BUG-001.md"
        issue_file.write_text("- **Status**: Closed\n- **Reason**: rejected")

        issues = [
            CompletedIssue(
                path=issue_file,
                issue_type="BUG",
                priority="P1",
                issue_id="BUG-001",
            )
        ]
        result = analyze_agent_effectiveness(issues)
        assert result.outcomes[0].rejection_count == 1
        assert result.outcomes[0].success_count == 0

    def test_best_agent_requires_minimum_samples(self, tmp_path: Path) -> None:
        """Test that best_agent_by_type requires minimum sample size."""
        # Create only 2 issues (below threshold of 3)
        for i in range(2):
            issue = tmp_path / f"P1-BUG-{i:03d}.md"
            issue.write_text("**Tool**: ll-auto\n- **Action**: fix")

        issues = [
            CompletedIssue(
                path=tmp_path / f"P1-BUG-{i:03d}.md",
                issue_type="BUG",
                priority="P1",
                issue_id=f"BUG-{i:03d}",
            )
            for i in range(2)
        ]
        result = analyze_agent_effectiveness(issues)

        # Should not have best agent due to low sample size
        assert "BUG" not in result.best_agent_by_type

    def test_problematic_combination_detected(self, tmp_path: Path) -> None:
        """Test problematic combinations are detected."""
        # Create 6 issues with 2 success and 4 failures for ll-auto BUG
        for i in range(6):
            issue = tmp_path / f"P1-BUG-{i:03d}.md"
            if i < 2:
                issue.write_text("**Tool**: ll-auto\n- **Action**: fix")
            else:
                issue.write_text("**Tool**: ll-auto\n- **Status**: Closed\n- **Reason**: rejected")

        issues = [
            CompletedIssue(
                path=tmp_path / f"P1-BUG-{i:03d}.md",
                issue_type="BUG",
                priority="P1",
                issue_id=f"BUG-{i:03d}",
            )
            for i in range(6)
        ]
        result = analyze_agent_effectiveness(issues)

        # Should have problematic combination (33% success < 50%)
        assert len(result.problematic_combinations) == 1
        assert result.problematic_combinations[0][0] == "ll-auto"
        assert result.problematic_combinations[0][1] == "BUG"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- `AgentOutcome` dataclass properties and serialization
- `AgentEffectivenessAnalysis` dataclass serialization
- `_detect_processing_agent()` with various input patterns
- `analyze_agent_effectiveness()` with empty, single, and mixed issues
- Grouping by agent and type
- Rejection vs completion counting
- Best agent determination with minimum sample thresholds
- Problematic combination detection

### Integration Tests
- Run `ll-history analyze` on real completed issues directory
- Verify output includes agent effectiveness section
- Verify markdown formatting is valid

## References

- Original issue: `.issues/enhancements/P3-ENH-114-agent-effectiveness-analysis.md`
- Dependency: `.issues/completed/P3-ENH-112-rejection-invalid-rate-analysis.md`
- Similar dataclass pattern: `scripts/little_loops/issue_history.py:319-376` (RejectionMetrics/RejectionAnalysis)
- Similar analysis function: `scripts/little_loops/issue_history.py:1484-1587` (analyze_rejection_rates)
- Test patterns: `scripts/tests/test_issue_history.py:1877-2093` (rejection analysis tests)
