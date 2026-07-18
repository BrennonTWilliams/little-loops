---
name: analyze-history
description: Use when asked about project health, velocity, bug trends, or whether we're making progress.
disable-model-invocation: true
model: haiku
allowed-tools:
  - Bash(ll-history:*)
metadata:
  short-description: Use when asked about project health, velocity, bug trends, or whether we're maki
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

### Documentation Synthesis

Generate architecture documentation from completed issue history:
```bash
ll-history export "authentication"
```

Write to a file with a specific format:
```bash
ll-history export "sprint system" --output docs/arch/sprint.md --format structured
```

Filter by date or issue type:
```bash
ll-history export "API layer" --since 2026-01-01 --type ENH
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
| "Generate docs about the sprint system" | `ll-history export "sprint system"` |
| "Document our auth changes since January" | `ll-history export "authentication" --since 2026-01-01` |

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
2. **Type Distribution** - BUG/ENH/FEAT/EPIC breakdown
3. **Period Trends** - Velocity and bug ratio over time
4. **Subsystem Health** - Per-directory issue tracking
5. **Technical Debt** - Backlog size, growth, aging
6. **Comparative Analysis** - Period-over-period comparison (if requested)

## Evolution Triggers

When `.ll/history.db` is available, `analyze-history` includes an **Evolution Triggers** section with two subsections:

### Recurring Corrections
User corrections that have recurred ≥ `history.evolution.feedback_min_recurrence` times (default: 2) across sessions. Each entry includes:
- **Topic**: content excerpt or cluster key
- **Count**: number of times this correction recurred
- **Example Sessions**: up to 5 session IDs where the correction appeared
- **Candidate Rule**: proposed CLAUDE.md rule text (seeded from matching `memory/feedback_*` files)

**Rule Candidates** — the recurring corrections most likely to become permanent CLAUDE.md rules — are listed separately for easy copy-paste into CLAUDE.md.

### Skill Bypasses
Skills where the user performed the work manually instead of invoking the skill, detected by matching user message content against skill keyword sets. Requires ≥ 2 keyword tokens to match (conservative to reduce false positives). Each entry includes:
- **Skill**: the bypassed skill name
- **Bypass Count**: number of sessions with bypass signal
- **Example Sessions**: up to 5 session IDs
- **Suggested Improvement**: recommendation to sharpen trigger keywords or lighten the skill

**Configuration**: `history.evolution.feedback_min_recurrence` and `history.evolution.bypass_min_count` in `.ll/ll-config.json` control the thresholds.
