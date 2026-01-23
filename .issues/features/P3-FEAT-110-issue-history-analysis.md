---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# FEAT-110: Issue History Analysis Command

## Summary

Add a new `/ll:analyze_history` slash command with supporting Python module to analyze completed issues in `.issues/completed/` and identify patterns, quality metrics, workflow effectiveness, file hotspots, and improvement opportunities.

## Context

With 116+ completed issues, the project has accumulated significant historical data that could provide valuable insights into:
- Development velocity and trends
- Code quality patterns
- Workflow effectiveness
- Architecture hotspots (frequently changed files)
- Process improvement opportunities

Currently there's no way to analyze this data systematically.

## Proposed Solution

### Components to Create

1. **Python Module**: `scripts/little_loops/issue_history_analyzer.py`
   - Parse completed issues and extract completion metadata
   - Calculate temporal, type, priority, quality, workflow, and hotspot metrics
   - Generate insights and recommendations
   - Support Markdown, YAML, and JSON output formats

2. **Slash Command**: `commands/analyze_history.md`
   - Arguments: `format` (markdown|yaml|json), `output` (file path)
   - Run analysis and display report
   - Offer follow-up actions

3. **Skill**: `skills/analyze-history/SKILL.md`
   - Trigger keywords: "analyze history", "issue history", "velocity report", etc.
   - Natural language triggering for the command

4. **CLI Entry Point**: `ll-history` command
   - Standalone command-line interface

5. **Tests**: `scripts/tests/test_issue_history_analyzer.py`

### Analysis Categories

| Category | Metrics |
|----------|---------|
| Temporal | Velocity (issues/week), trends, completion by day/month |
| Type | BUG/ENH/FEAT counts and percentages |
| Priority | P0-P5 distribution, avg completion time by priority |
| Quality | Test/lint/types pass rates, verification gaps |
| Workflow | Discovery sources, automated vs manual ratio |
| Hotspots | Files changed in 3+ issues, top directories |

### Report Output (Markdown Example)

```
# Issue History Analysis Report

**Generated**: 2026-01-23 | **Issues**: 116 | **Date Range**: 2026-01-06 to 2026-01-22

## Executive Summary
- Velocity: 8.3 issues/week
- Quality Score: 94% (tests passing)

## Type Distribution
| Type | Count | % |
|------|-------|---|
| BUG | 42 | 36% |
| ENH | 51 | 44% |
| FEAT | 23 | 20% |

## File Hotspots
| File | Count | Issues |
|------|-------|--------|
| scripts/little_loops/issue_lifecycle.py | 8 | BUG-009, ... |

## Insights
- High bug ratio (36%): Consider increasing test coverage
- issue_lifecycle.py hotspot (8 issues): Consider refactoring

## Recommendations
- Add tests to frequently changed files
- Review ENH dominance (44%)
```

## Impact

- **Priority**: P3 - Valuable but not blocking other work
- **Effort**: Medium - ~4 files, ~600 lines total
- **Risk**: Low - Additive feature, no modifications to existing behavior

## Implementation Plan

See: `/Users/brennon/.claude/plans/sunny-mapping-pine.md`

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`feature`, `analysis`, `reporting`

---

**Priority**: P3 | **Created**: 2026-01-23
