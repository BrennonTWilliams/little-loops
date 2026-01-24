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

- [ ] `AgentOutcome` dataclass captures per-agent statistics
- [ ] Analysis groups by agent name and issue type
- [ ] Success rate calculation accounts for rejections vs failures
- [ ] Duration tracking shows efficiency differences
- [ ] Recommendations based on statistical patterns
- [ ] Output integrated into `ll-history analyze` report

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
