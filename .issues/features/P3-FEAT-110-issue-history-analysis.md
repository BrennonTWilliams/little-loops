---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# FEAT-110: Advanced Issue History Analysis

## Summary

Extend the basic `ll-history` command (FEAT-111) with advanced analysis: file hotspot detection via git correlation, AI-generated insights, quality metrics, and a `/ll:analyze_history` slash command with skill integration.

## Prerequisites

- **FEAT-111**: Basic `ll-history summary` command (provides foundation)

## Context

Building on the basic history summary (FEAT-111), this adds deeper analysis capabilities:
- File hotspot detection (correlate issues with git commits)
- Quality metrics inference
- AI-generated insights and recommendations
- Slash command and skill for natural language access

## Proposed Solution

### Components to Create/Extend

1. **Extend Python Module**: `scripts/little_loops/issue_history.py`
   - Add git correlation for file hotspot detection
   - Add quality metrics extraction from issue content
   - Add insight generation logic
   - Support Markdown and YAML output formats (JSON from FEAT-111)

2. **Slash Command**: `commands/analyze_history.md`
   - Arguments: `format` (markdown|yaml|json), `output` (file path)
   - Run full analysis and display report
   - Offer follow-up actions

3. **Skill**: `skills/analyze-history/SKILL.md`
   - Trigger keywords: "analyze history", "issue history", "velocity report", etc.
   - Natural language triggering for the command

4. **Extend CLI**: Add `ll-history analyze` subcommand
   - Full analysis with hotspots and insights
   - Multiple output formats

5. **Tests**: Extend `scripts/tests/test_issue_history.py`

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
- **Effort**: Medium - Builds on FEAT-111, adds ~400 lines
- **Risk**: Low - Additive feature, extends existing module
- **Depends on**: FEAT-111 must be completed first

## Implementation Plan

See: `/Users/brennon/.claude/plans/sunny-mapping-pine.md`

## Related

- **Prerequisite**: FEAT-111 (basic `ll-history summary` command)

## Labels

`feature`, `analysis`, `reporting`, `advanced`

---

**Priority**: P3 | **Created**: 2026-01-23
