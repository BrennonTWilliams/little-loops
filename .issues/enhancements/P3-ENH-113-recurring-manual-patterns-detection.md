---
discovered_date: 2026-01-23
discovered_by: planning
---

# ENH-113: Recurring Manual Patterns Detection

## Summary

Detect repetitive manual activities that could be automated through Claude Code hooks, skills, or agents.

## Motivation

Users often perform the same manual tasks repeatedly without realizing they could be automated:
- Running the same test commands after edits
- Applying consistent formatting fixes
- Following the same multi-step procedures

Identifying these patterns helps suggest automation opportunities.

## Proposed Implementation

### Data Structure

```python
@dataclass
class ManualPattern:
    pattern_description: str
    occurrence_count: int
    affected_issues: list[str]  # issue IDs
    suggested_automation: str   # hook, skill, or agent suggestion
    automation_complexity: str  # "trivial", "simple", "moderate"

@dataclass
class ManualPatternAnalysis:
    patterns: list[ManualPattern]
    total_manual_interventions: int
    automatable_percentage: float
```

### Analysis Function

```python
def detect_manual_patterns(issues: list[IssueHistory]) -> ManualPatternAnalysis:
    """Detect recurring manual activities that could be automated."""
    # Look for repeated test invocations
    # Identify consistent formatting/lint fix patterns
    # Find multi-step procedures that repeat
    # Match against known automatable patterns
```

### Pattern Categories

1. **Test Execution**: Same test commands across issues
2. **Lint/Format Fixes**: Repeated style corrections
3. **Build Steps**: Manual build commands
4. **Verification Steps**: Same validation procedures
5. **Git Operations**: Repeated commit/branch patterns

### Output Format

```
Manual Pattern Analysis:
  Total manual interventions detected: 45
  Potentially automatable: 67% (30/45)

  Recurring Patterns:

  1. Test execution after code changes (12 occurrences)
     Issues: BUG-045, BUG-052, ENH-078, ...
     Suggestion: Add post-edit hook for automatic test runs
     Complexity: trivial

  2. Lint fix after implementation (8 occurrences)
     Issues: FEAT-023, ENH-081, ...
     Suggestion: Add pre-commit hook for auto-formatting
     Complexity: simple

  3. Manual type checking (6 occurrences)
     Suggestion: Add mypy to pre-commit or post-edit hook
     Complexity: simple
```

## Acceptance Criteria

- [ ] `ManualPattern` dataclass captures recurring activities
- [ ] Detection covers test, lint, build, and verification patterns
- [ ] Each pattern includes actionable automation suggestion
- [ ] Complexity rating helps prioritize automation
- [ ] Output integrated into `ll-history analyze` report

## Impact

- **Priority**: P3 - Valuable for workflow optimization
- **Effort**: Medium - Requires pattern matching logic
- **Risk**: Low - Read-only analysis

## Dependencies

### Blocked By

None - Can be implemented independently

### Blocks

- ENH-115: Configuration Gaps Detection (uses pattern analysis)

## Labels

`enhancement`, `ll-history`, `process-analysis`, `automation`

---

**Priority**: P3 | **Created**: 2026-01-23
