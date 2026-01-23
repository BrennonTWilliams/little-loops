---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# FEAT-110: Advanced Issue History Analysis

## Summary

Extend the basic `ll-history` command (FEAT-111) with advanced analysis capabilities designed for large, long-running projects (100+ issues). Provides longitudinal trend analysis, progress trajectory tracking, technical debt health metrics, subsystem stabilization detection, comparative period analysis, and actionable recommendations. Answers the key question: "Are we making progress?"

## Prerequisites

- **FEAT-111**: Basic `ll-history summary` command (provides foundation)

## Context

Building on the basic history summary (FEAT-111), this adds deeper analysis capabilities:
- File hotspot detection (correlate issues with git commits)
- Quality metrics inference
- AI-generated insights and recommendations
- Slash command and skill for natural language access

### Primary Use Case: Large, Long-Running Projects

This feature is designed for projects with 100+ issues over extended periods (months/years) where understanding trajectory and progress is difficult. Key questions it should answer:

- **"Are we making progress?"** - Trend analysis showing improvement or degradation over time
- **"What areas are stabilizing vs problematic?"** - Subsystem health tracking
- **"Is technical debt improving?"** - Bug ratio trends, debt paydown metrics
- **"Where should we focus?"** - Data-driven recommendations for process/architecture improvements

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

#### Core Metrics (from FEAT-111)

| Category | Metrics |
|----------|---------|
| Temporal | Velocity (issues/week), completion by day/month |
| Type | BUG/ENH/FEAT counts and percentages |
| Priority | P0-P5 distribution, avg completion time by priority |
| Quality | Test/lint/types pass rates, verification gaps |
| Workflow | Discovery sources, automated vs manual ratio |
| Hotspots | Files changed in 3+ issues, top directories |

#### Advanced Metrics (FEAT-110)

| Category | Metrics |
|----------|---------|
| Trends | Velocity over time (weekly/monthly), bug ratio trend, type ratio evolution, completion rate acceleration |
| Progress | Stabilizing subsystems (no new issues in N days), recurring problem areas, improvement trajectory |
| Technical Debt | Deferred issue age, backlog growth rate (net issues/week), debt paydown ratio (maintenance vs features) |
| Comparative | Period-over-period comparison (configurable), improving vs degrading areas, anomaly detection |
| Process Health | Discovery source effectiveness, reopened issue rate, follow-up spawn rate, issue churn |
| Aging | Open issue age by priority, stale issue detection (>30 days), backlog age distribution, SLA compliance |
| Subsystem Health | Per-directory/module issue rates, stabilization tracking, problem area identification |

### Report Output (Markdown Example)

```markdown
# Issue History Analysis Report

**Generated**: 2026-01-23 | **Total Issues**: 1,247 | **Date Range**: 2025-01-15 to 2026-01-22

## Executive Summary

| Metric | Value | Trend |
|--------|-------|-------|
| Velocity | 8.3 issues/week | ↑ +12% vs prev quarter |
| Bug Ratio | 29% | ↓ -18% vs prev quarter ✓ |
| Avg Completion | 2.8 days | ↓ -15% vs prev quarter ✓ |
| Technical Debt Score | 72/100 | ↑ +8 pts vs prev quarter ✓ |
| Progress Grade | **B+** | Improving |

**Bottom Line**: Project health is improving. Bug ratio declining, velocity increasing, completion times faster.

## Progress Trajectory

### Trend Analysis (12 months)
| Period | Velocity | Bug % | ENH % | FEAT % | Avg Days |
|--------|----------|-------|-------|--------|----------|
| Q1 2025 | 6.2/wk | 45% | 38% | 17% | 4.1 |
| Q2 2025 | 7.1/wk | 38% | 42% | 20% | 3.5 |
| Q3 2025 | 7.8/wk | 33% | 44% | 23% | 3.1 |
| Q4 2025 | 8.3/wk | 29% | 46% | 25% | 2.8 |

**Interpretation**: Steady improvement across all metrics. Bug ratio decreased 36% over the year.

### Subsystem Health
| Subsystem | Issues (90d) | Trend | Status |
|-----------|--------------|-------|--------|
| `auth/` | 2 | ↓ -80% | ✅ Stabilized |
| `api/handlers/` | 18 | ↑ +40% | ⚠️ Degrading |
| `core/` | 5 | → stable | ✅ Healthy |
| `ui/components/` | 12 | ↓ -25% | 🔄 Improving |

### Recurring Problems
| Area | Occurrences | Pattern |
|------|-------------|---------|
| `api/handlers/validation.py` | 7 issues | Input validation edge cases |
| `core/cache.py` | 5 issues | Cache invalidation timing |

## Comparative Analysis (Last 30d vs Previous 30d)

| Metric | Previous | Current | Change |
|--------|----------|---------|--------|
| Issues Completed | 31 | 38 | +23% ✓ |
| Bugs Created | 14 | 9 | -36% ✓ |
| Avg Completion Time | 3.2d | 2.6d | -19% ✓ |
| Reopened Issues | 3 | 1 | -67% ✓ |

## Technical Debt Health

| Metric | Value | Assessment |
|--------|-------|------------|
| Backlog Growth | +2.1 issues/week (net) | ⚠️ Growing |
| Debt Paydown Ratio | 0.72 | More features than maintenance |
| Deferred Issues | 23 total | 8 aging >30 days |
| P0-P1 Open | 2 | Within target (<5) ✓ |

### Aging Analysis
| Priority | Open | Avg Age | >30 Days |
|----------|------|---------|----------|
| P0-P1 | 2 | 1.5d | 0 |
| P2 | 8 | 12d | 1 |
| P3-P5 | 34 | 28d | 12 |

## File Hotspots

| File | Issues | Recent | Top Issues |
|------|--------|--------|------------|
| `api/handlers/validation.py` | 12 | 4 (30d) | BUG-089, BUG-102 |
| `core/cache.py` | 8 | 2 (30d) | BUG-067, ENH-045 |
| `ui/components/DataGrid.tsx` | 7 | 1 (30d) | ENH-078, BUG-091 |

## Process Health

| Metric | Value | Benchmark |
|--------|-------|-----------|
| Discovery: Automated | 62% | ✓ Good (>50%) |
| Discovery: Manual | 38% | |
| Reopened Rate | 2.3% | ✓ Good (<5%) |
| Follow-up Spawn Rate | 8% | ✓ Acceptable (<15%) |

## Insights

1. **✓ Bug ratio improving**: Down from 45% to 29% over 12 months - indicates maturing codebase
2. **⚠️ api/handlers/ degrading**: 40% increase in issues - recommend architecture review
3. **✓ Auth module stabilized**: No new issues in 60 days after refactor
4. **⚠️ Backlog growing**: Net +2.1 issues/week - consider dedicated debt sprint
5. **✓ Process effective**: 62% automated discovery, low reopened rate

## Recommendations

### High Priority
1. **Architecture review for `api/handlers/`** - Issue rate increased 40%, 7 recurring validation problems
2. **Dedicated debt sprint** - Backlog growing, 12 issues aging >30 days

### Medium Priority
3. **Increase test coverage for hotspot files** - validation.py, cache.py have repeated issues
4. **Document cache invalidation patterns** - 5 issues related to timing

### Low Priority
5. **Consider splitting DataGrid component** - 7 issues suggest complexity
6. **Review P3-P5 prioritization** - 12 issues aging, may need reprioritization or closure
```

### CLI Options

```bash
# Full analysis with comparison
ll-history analyze --compare 30d --format markdown

# Subsystem-specific analysis
ll-history analyze --subsystem api/ --format json

# Time-bounded analysis
ll-history analyze --since 2025-06-01 --until 2025-12-31

# Progress trajectory only
ll-history analyze --trajectory --format yaml
```

## Impact

- **Priority**: P3 - Valuable but not blocking other work
- **Effort**: Medium-High - Builds on FEAT-111, adds ~600-800 lines for advanced analysis
- **Risk**: Low - Additive feature, extends existing module
- **Depends on**: FEAT-111 must be completed first
- **Value**: High for large/long-running projects - directly answers "are we making progress?"

## Implementation Considerations

### Data Requirements
- Issue files must have `discovered_date` frontmatter for temporal analysis
- Git history needed for file hotspot correlation
- Subsystem analysis requires consistent directory structure

### Performance
- For 1000+ issues, analysis should complete in <10 seconds
- Consider caching intermediate results for repeated analysis
- Streaming output for large reports

### Configuration
- Configurable comparison periods (default: 30 days)
- Configurable aging thresholds (default: 30 days = stale)
- Subsystem definitions (directory patterns to group)
- Benchmark targets (e.g., "bug ratio <30% is good")

## Implementation Plan

See: `/Users/brennon/.claude/plans/sunny-mapping-pine.md`

## Related

- **Prerequisite**: FEAT-111 (basic `ll-history summary` command)

## Labels

`feature`, `analysis`, `reporting`, `advanced`, `large-projects`, `trajectory`

---

**Priority**: P3 | **Created**: 2026-01-23 | **Updated**: 2026-01-23

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made

- `scripts/little_loops/issue_history.py`: Extended with 4 new dataclasses (PeriodMetrics, SubsystemHealth, TechnicalDebtMetrics, HistoryAnalysis), analysis functions, and 4 output formatters
- `scripts/little_loops/cli.py`: Added `analyze` subcommand to `ll-history` with `--format`, `--period`, `--compare` options
- `skills/analyze-history/SKILL.md`: Created skill for natural language access to history analysis
- `scripts/tests/test_issue_history.py`: Added 30+ tests for new functionality

### Features Implemented

1. **Trend Analysis**: Period grouping (weekly/monthly/quarterly), velocity and bug ratio trends
2. **Subsystem Health**: Per-directory issue tracking with improving/stable/degrading indicators
3. **Technical Debt Metrics**: Backlog size, growth rate, aging, high priority tracking
4. **Comparative Analysis**: Period-over-period comparison with `--compare N` flag
5. **Multiple Output Formats**: text, json, markdown, yaml

### Usage

```bash
ll-history analyze                    # Text report
ll-history analyze --format markdown  # Markdown report
ll-history analyze --compare 30       # Compare last 30 days
ll-history analyze --period quarterly # Quarterly trends
```

### Verification Results

- Tests: PASS (62 tests passed)
- Lint: PASS
- Types: PASS
