---
discovered_commit: b20aa691700cd09e7071bc829c943e3a83876abf
discovered_branch: main
discovered_date: 2026-01-06T20:47:28Z
---

# FEAT-002: Goals/Vision Ingestion Mechanism

## Summary

Create a structured mechanism for users to define their product goals, target users, success metrics, and strategic priorities in a format that little-loops agents can parse and use for product-focused issue identification.

## Motivation

Product-focused analysis requires understanding:
- What the project is trying to achieve (vision)
- Who benefits from the project (users)
- How success is measured (metrics)
- What's prioritized vs. deprioritized (strategy)

Without structured goals, product analysis agents cannot make meaningful recommendations. This feature provides the "ground truth" that enables goal-driven issue synthesis.

## Proposed Implementation

### 1. Goals Document Schema

Create `.claude/ll-goals.md` with YAML frontmatter + markdown body:

```markdown
---
# Structured metadata for programmatic access
version: "1.0"
last_updated: 2026-01-06
review_cadence: quarterly

personas:
  - id: developer
    name: "Developer Dan"
    role: "Full-stack developer"
    priority: primary
  - id: devops
    name: "Ops Olivia"
    role: "DevOps engineer"
    priority: secondary

metrics:
  - name: "Issue resolution time"
    current: "4 hours"
    target: "< 1 hour"
    priority: high
  - name: "Codebase scan coverage"
    current: "60%"
    target: "> 90%"
    priority: medium

priorities:
  - id: automation
    name: "Maximize automation"
    rank: 1
  - id: accuracy
    name: "Improve issue accuracy"
    rank: 2
  - id: extensibility
    name: "Plugin extensibility"
    rank: 3
---

# Product Vision

## Mission Statement

[One-paragraph mission statement describing the project's purpose]

## Target Users

### Developer Dan (Primary)

**Context**: Full-stack developers working on medium-to-large codebases who need to manage technical debt while shipping features.

**Needs**:
- Automated identification of bugs and code quality issues
- Prioritized backlog that balances tech debt with features
- Confidence that issues are valid before investing time

**Pain Points**:
- Manual issue triage is time-consuming
- Hard to justify tech debt work to stakeholders
- Issues often lack context needed for quick resolution

### Ops Olivia (Secondary)

[Similar structure for secondary persona]

## Success Metrics

| Metric | Current | Target | Rationale |
|--------|---------|--------|-----------|
| Issue resolution time | 4 hours | < 1 hour | Faster feedback loops |
| False positive rate | 15% | < 5% | Trust in automated scanning |
| Codebase coverage | 60% | > 90% | Comprehensive analysis |

## Strategic Priorities

### 1. Maximize Automation
Reduce manual intervention in the issue lifecycle. Users should be able to run `ll-auto` and trust the output.

### 2. Improve Issue Accuracy
Every created issue should be valid, actionable, and correctly prioritized. False positives erode trust.

### 3. Plugin Extensibility
Enable customization for diverse project types without forking the plugin.

## Out of Scope

- **Project management**: Not replacing Jira, Linear, GitHub Issues
- **Team coordination**: No multi-user workflows or assignments
- **Deployment**: Not involved in CI/CD or release management

## Competitive Context

[Optional: How this project compares to alternatives]
```

### 2. Goals Parser Utility

Create `scripts/little_loops/goals_parser.py`:

```python
"""Parser for ll-goals.md product goals document."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class Persona:
    id: str
    name: str
    role: str
    priority: str  # "primary" | "secondary"


@dataclass
class Metric:
    name: str
    current: str
    target: str
    priority: str  # "high" | "medium" | "low"


@dataclass
class Priority:
    id: str
    name: str
    rank: int


@dataclass
class ProductGoals:
    version: str
    personas: list[Persona]
    metrics: list[Metric]
    priorities: list[Priority]
    raw_content: str  # Full markdown for LLM context

    @classmethod
    def from_file(cls, path: Path) -> Optional["ProductGoals"]:
        """Parse goals from ll-goals.md file."""
        if not path.exists():
            return None

        content = path.read_text()
        # Split frontmatter from body
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                # Parse structured data from frontmatter
                # Return ProductGoals instance
        return None
```

### 3. Goals Validation Command

Add `/ll:validate_goals` command to check goals document:

```markdown
# Validate Goals

Validates the `.claude/ll-goals.md` document for:
- YAML frontmatter syntax
- Required sections present
- Personas defined with required fields
- At least one metric with target
- Priorities ranked without gaps

Output:
- Valid: "Goals document is valid and ready for product analysis"
- Invalid: Specific errors with line numbers and fix suggestions
```

### 4. Integration Points

Goals are consumed by:
- **Product analyzer agent** (FEAT-003): Uses goals for feature gap analysis
- **Product scanning** (FEAT-004): Scores findings against strategic priorities
- **Issue templates** (ENH-005): Populates business impact fields

## Location

- **New File**: `.claude/ll-goals.md` (user-created, template provided)
- **New Module**: `scripts/little_loops/goals_parser.py`
- **New Command**: `commands/validate_goals.md`
- **Template**: `templates/ll-goals-template.md`

## Current Behavior

No mechanism exists for capturing product goals. All analysis is purely technical.

## Expected Behavior

Users can define product goals in a structured format that enables:
1. Product-focused issue identification
2. Business impact scoring
3. Goal-gap analysis
4. Strategic alignment validation

## Impact

- **Severity**: High - Core data structure for Product dimension
- **Effort**: Medium - Parser, validator, templates
- **Risk**: Low - Purely additive feature

## Dependencies

- FEAT-001: Product Analysis Opt-In Configuration (must be enabled)

## Blocked By

- FEAT-001

## Blocks

- FEAT-003: Product Analyzer Agent
- FEAT-004: Product Scanning Integration

## Labels

`feature`, `product-dimension`, `configuration`, `parser`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P2
