---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-114: Agent Effectiveness Analysis

## Summary

Analyze completion rates and outcomes when issues are handled by different agents (ll-auto, ll-parallel, manual) to identify which agent types are most effective for different issue categories.

## Motivation

Understanding which agents perform best for specific issue types enables:
- Better routing decisions for new issues
- Identification of agent configuration problems
- Optimization of agent prompts and capabilities

## Proposed Implementation

### Data Structure

```python
@dataclass
class AgentOutcome:
    agent_name: str
    issue_type: str
    success_count: int
    failure_count: int
    rejection_count: int
    avg_duration_hours: float
    success_rate: float

@dataclass
class AgentEffectivenessAnalysis:
    outcomes_by_agent: dict[str, list[AgentOutcome]]
    best_agent_by_type: dict[str, str]  # issue_type -> recommended agent
    problematic_combinations: list[tuple[str, str, str]]  # (agent, type, reason)
```

### Analysis Function

```python
def analyze_agent_effectiveness(issues: list[IssueHistory]) -> AgentEffectivenessAnalysis:
    """Analyze success rates by agent and issue type."""
    # Group issues by processing agent
    # Calculate success/failure rates per agent per type
    # Identify statistically significant patterns
    # Use _parse_resolution_action from ENH-112
```

### Agent Detection

Identify agent from:
- `processed_by` field in issue history
- Git commit messages mentioning ll-auto/ll-parallel
- Resolution notes indicating manual processing

### Output Format

```
Agent Effectiveness Analysis:

  ll-auto:
    BUG:  85% success (34/40), avg 2.3h
    ENH:  72% success (18/25), avg 3.1h
    FEAT: 45% success (9/20), avg 5.2h  [!]

  ll-parallel:
    BUG:  82% success (41/50), avg 1.8h
    ENH:  78% success (28/36), avg 2.4h
    FEAT: 65% success (13/20), avg 3.8h

  manual:
    BUG:  95% success (19/20), avg 4.5h
    FEAT: 90% success (27/30), avg 6.2h

  Recommendations:
    - Route FEAT issues to manual or ll-parallel (ll-auto underperforms)
    - ll-parallel is fastest for BUG issues
    - Consider ll-auto prompt improvements for FEAT handling
```

## Acceptance Criteria

- [x] `AgentOutcome` dataclass captures per-agent statistics
- [x] Analysis groups by agent name and issue type
- [x] Success rate calculation accounts for rejections vs failures
- [ ] Duration tracking shows efficiency differences (deferred - requires start time capture)
- [x] Recommendations based on statistical patterns
- [x] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Valuable for optimization
- **Effort**: Medium - Requires agent detection and statistics
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

- ENH-112: Rejection/Invalid Rate Analysis (provides `_parse_resolution_action`)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `claude-config-analysis`, `agents`

---

**Priority**: P3 | **Created**: 2026-01-23

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_history.py`:
  - Added `AgentOutcome` dataclass with success_rate and total_count computed properties (lines 433-465)
  - Added `AgentEffectivenessAnalysis` dataclass with outcomes, best_agent_by_type, and problematic_combinations (lines 468-482)
  - Added `agent_effectiveness_analysis` field to `HistoryAnalysis` dataclass (line 545)
  - Added `_detect_processing_agent()` helper to identify agent from discovered_source, Log Type, or Tool fields (lines 754-797)
  - Added `analyze_agent_effectiveness()` function that groups by agent/type and identifies best agents and problematic combinations (lines 1826-1912)
  - Integrated into `calculate_analysis()` (lines 2081-2104)
  - Added text formatting in `format_analysis_text()` (lines 2421-2456)
  - Added markdown table formatting in `format_analysis_markdown()` (lines 2807-2845)
  - Updated `to_dict()` serialization for JSON/YAML output (lines 589-593)
- `scripts/tests/test_issue_history.py`:
  - Added 19 unit tests covering dataclasses, agent detection, and analysis function (lines 2362-2635)

### Verification Results
- Tests: PASS (157 tests in test_issue_history.py, 1632 overall)
- Lint: PASS
- Types: PASS

### Implementation Notes
- Duration tracking deferred - would require capturing issue start times which aren't currently available
- Agent detection uses heuristics based on discovered_source, **Log Type**, and **Tool** fields
- Minimum sample size of 3 required for best_agent recommendations
- Minimum sample size of 5 with <50% success rate to flag problematic combinations
