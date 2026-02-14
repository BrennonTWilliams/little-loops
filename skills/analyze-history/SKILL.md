---
description: |
  Analyze issue history to understand project health, trends, and progress. Use this skill when users ask about velocity, bug trends, technical debt, or want to know "are we making progress?"

  Trigger keywords: "analyze history", "issue history", "velocity report", "bug trends", "technical debt", "project health", "are we making progress", "issue trends", "history analysis", "how are we doing"
disable-model-invocation: true
model: haiku
allowed-tools:
  - Bash(ll-history:*)
---

# Analyze History Skill

This skill helps users understand their issue history and project health trends.

## When to Activate

Proactively offer or invoke this skill when the user:
- Asks about project velocity or completion rates
- Wants to know about bug trends or ratios
- Asks "are we making progress?"
- Inquires about technical debt health
- Wants to compare recent performance to historical
- Asks about subsystem or module health

## How to Use

Run the `ll-history` CLI command based on user needs:

### Quick Summary

For a basic summary:
```bash
ll-history summary
```

### Full Analysis

For comprehensive analysis:
```bash
ll-history analyze
```

### Markdown Report

For a shareable report:
```bash
ll-history analyze --format markdown
```

### Period Comparison

To compare recent vs previous period:
```bash
ll-history analyze --compare 30
```

### Output Formats

| Format | Command | Best For |
|--------|---------|----------|
| Text | `ll-history analyze` | Terminal viewing |
| Markdown | `ll-history analyze --format markdown` | Documentation, sharing |
| JSON | `ll-history analyze --format json` | Programmatic access |
| YAML | `ll-history analyze --format yaml` | Config, further processing |

### Period Grouping

| Period | Command | Use Case |
|--------|---------|----------|
| Weekly | `ll-history analyze --period weekly` | Short sprints |
| Monthly | `ll-history analyze --period monthly` | Default, general use |
| Quarterly | `ll-history analyze --period quarterly` | Long-term trends |

## Examples

| User Says | Action |
|-----------|--------|
| "How's our project health?" | `ll-history analyze` |
| "Show me bug trends" | `ll-history analyze --format markdown` |
| "Compare last month to previous" | `ll-history analyze --compare 30` |
| "Are we making progress?" | `ll-history analyze --format markdown` |
| "What's our velocity?" | `ll-history summary` |
| "Show quarterly trends" | `ll-history analyze --period quarterly` |

## Interpretation Guide

### Velocity Trend
- **Increasing**: Team completing more issues over time
- **Stable**: Consistent output
- **Decreasing**: May indicate blockers or complexity

### Bug Ratio Trend
- **Decreasing**: Codebase stabilizing (good)
- **Increasing**: Quality issues, may need attention
- **Stable**: Consistent quality level

### Subsystem Health
- **Improving** (down arrow): Fewer recent issues, stabilizing
- **Degrading** (up arrow): More recent issues, needs attention
- **Stable** (right arrow): Consistent issue rate

### Technical Debt Indicators
- **Backlog Growing**: More issues created than closed
- **High Aging**: Issues sitting too long without resolution
- **High Priority Open**: Critical issues need immediate attention

## Analysis Sections

The full analysis includes:

1. **Executive Summary** - Key metrics at a glance
2. **Type Distribution** - BUG/ENH/FEAT breakdown
3. **Period Trends** - Velocity and bug ratio over time
4. **Subsystem Health** - Per-directory issue tracking
5. **Technical Debt** - Backlog size, growth, aging
6. **Comparative Analysis** - Period-over-period comparison (if requested)
