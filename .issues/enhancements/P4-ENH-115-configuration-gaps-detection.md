---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-115: Configuration Gaps Detection

## Summary

Identify missing hooks, skills, or agents that would address recurring manual patterns found in issue history.

## Motivation

Issue history often reveals repetitive manual work that existing Claude Code configuration could automate. By correlating manual patterns with available configuration options, we can suggest specific configuration additions.

## Proposed Implementation

### Data Structure

```python
@dataclass
class ConfigGap:
    gap_type: str  # "hook", "skill", "agent", "command"
    description: str
    evidence: list[str]  # issue IDs showing the pattern
    suggested_config: str  # example configuration
    priority: str  # "high", "medium", "low"

@dataclass
class ConfigGapsAnalysis:
    gaps: list[ConfigGap]
    current_hooks: list[str]
    current_skills: list[str]
    coverage_score: float  # 0-1, how well config covers common needs
```

### Analysis Function

```python
def detect_config_gaps(
    issues: list[IssueHistory],
    manual_patterns: ManualPatternAnalysis,
    current_config: dict
) -> ConfigGapsAnalysis:
    """Identify configuration gaps based on manual pattern analysis."""
    # Load current hooks, skills, agents from config
    # Match manual patterns to potential automations
    # Identify gaps where automation is possible but not configured
    # Generate specific configuration suggestions
```

### Gap Detection Rules

1. **Missing pre-commit hooks**: Manual lint/format fixes suggest missing hooks
2. **Missing post-edit hooks**: Manual test runs suggest missing hooks
3. **Missing skills**: Repeated multi-step procedures suggest skill creation
4. **Missing agents**: Complex recurring tasks suggest agent creation

### Output Format

```
Configuration Gaps Analysis:
  Coverage score: 65% (some common patterns not automated)

  Identified Gaps:

  1. Missing: pre-commit hook for formatting
     Evidence: 8 issues required manual format fixes
     Issues: ENH-081, BUG-052, ...
     Suggested config:
       hooks/hooks.json:
         "pre-commit": [{
           "type": "script",
           "script": "ruff format --check ."
         }]
     Priority: high

  2. Missing: post-edit hook for type checking
     Evidence: 6 issues had type errors caught late
     Suggested config:
       hooks/hooks.json:
         "post-edit": [{
           "type": "script",
           "script": "mypy --fast ."
         }]
     Priority: medium

  3. Consider: skill for database migration workflow
     Evidence: 4 issues followed same migration steps
     Priority: low
```

## Acceptance Criteria

- [ ] `ConfigGap` dataclass captures gap with evidence and suggestions
- [ ] Analysis reads current configuration to avoid duplicate suggestions
- [ ] Gap detection covers hooks, skills, and agents
- [ ] Specific configuration examples provided for each gap
- [ ] Priority based on frequency and impact
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P4 - Nice to have for configuration optimization
- **Effort**: Medium - Requires heuristic matching
- **Risk**: Low - Read-only analysis with suggestions

## Dependencies

### Blocked By

- ENH-113: Recurring Manual Patterns Detection (provides pattern data)

### Blocks

None

## Labels

`enhancement`, `ll-history`, `claude-config-analysis`, `automation`

---

**Priority**: P4 | **Created**: 2026-01-23
