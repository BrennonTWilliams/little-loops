---
description: Use when asked about the issue lifecycle, command order for issues, or how to manage issues.
model: haiku
---

# Little Loops Issue Workflow

Quick reference for managing issues with the little-loops plugin.

## Issue Lifecycle

```
                        /ll:scan-codebase
                        /ll:scan-product
                        /ll:capture-issue
                        /ll:audit-architecture
                               │
                               ▼
                        ┌─────────────┐
                        │  Discovered  │◀──────────────────┐
                        └──────┬──────┘                    │
                               │ /ll:prioritize-issues     │ Fix issue file
                               ▼                           │
                        ┌─────────────┐                    │
                        │ Prioritized  │                    │
                        └──────┬──────┘                    │
                               │ /ll:ready-issue           │
                               ▼                           │
                        ┌─────────────┐                    │
                        │  Validating  │                    │
                        └──┬───┬───┬──┘                    │
              READY ◀──────┘   │   └──────▶ CLOSE          │
                │         NOT_READY           │             │
                │              │              ▼             │
                │              └───────▶ completed/         │
                │                                           │
                │  DEFER ──────────────▶ deferred/          │
                ▼                                           │
         ┌─────────────┐                                    │
         │  InProgress  │ /ll:manage-issue                  │
         └──────┬──────┘                                    │
                │ Implementation done                       │
                ▼                                           │
         ┌─────────────┐                                    │
         │  Verifying   │                                   │
         └──┬────────┬─┘                                    │
            │        │                                      │
   Tests pass     Tests fail ──▶ Create follow-up ──────────┘
            │
            ▼
      ┌───────────┐
      │ Completed  │ ──▶ .issues/completed/
      └───────────┘
```

## Command Sequence

### 1. Discovery Phase
```bash
/ll:scan-codebase              # Find bugs, enhancements, features (technical)
/ll:scan-product               # Find issues from product goals perspective
/ll:capture-issue "desc"       # Capture issue from conversation or description
/ll:audit-architecture [focus] # Analyze architecture for patterns and improvements
```

### 2. Refinement Phase
```bash
/ll:normalize-issues           # Fix invalid issue filenames
/ll:prioritize-issues          # Assign P0-P5 priorities
/ll:align-issues <category>   # Validate issues against key documents
/ll:format-issue [id]          # Align issue with template v2.0 structure
/ll:refine-issue [id]          # Enrich issue with codebase research findings
/ll:decide-issue [id]          # Resolve competing implementation options (if decision_needed: true)
/ll:verify-issues              # Verify all issues against current codebase
/ll:tradeoff-review-issues     # Evaluate utility vs complexity trade-offs
/ll:ready-issue [id]           # Final validation before implementation
```

> **Stuck on readiness?** If `/ll:ready-issue` returns `NOT_READY` after 2+ refinement passes:
> - **Unresolved options (score_ambiguity ≤ 10)**: Run `/ll:decide-issue [id]` — competing implementation options are blocking readiness; selecting one clears the ambiguity.
> - **Issue too large (score_ambiguity > 10)**: Run `/ll:issue-size-review [id]` — a persistent readiness gap often means the issue is too large or poorly scoped, not just under-researched.

### 3. Planning & Implementation Phase
```bash
/ll:create-sprint [name]       # Create sprint with curated issue list
/ll:manage-issue bug fix       # Fix highest priority bug
/ll:manage-issue bug fix BUG-001        # Fix specific bug
/ll:manage-issue feature implement      # Implement highest priority feature
/ll:manage-issue enhancement improve    # Improve highest priority enhancement
/ll:iterate-plan [path]        # Update existing implementation plans
```

### 4. Completion Phase
```bash
/ll:check-code                 # Run lint, format, type checks
/ll:run-tests                  # Run test suite
/ll:commit                     # Commit changes
/ll:describe-pr                # Generate PR description
/ll:open-pr                    # Open pull request
```

## manage-issue Reference

| Parameter | Values |
|-----------|--------|
| Types | `bug`, `feature`, `enhancement` |
| Actions | `fix`, `implement`, `improve`, `verify` |

## ready-issue Sub-Skills

`ready-issue` runs these validation skills automatically:

| Skill | Purpose |
|-------|---------|
| `issue-size-review` | Check if issue is too large, propose decomposition |
| `map-dependencies` | Discover cross-issue dependencies via file overlap |
| `confidence-check` | Pre-implementation readiness score (0-100) |

## Priority Levels

| Priority | Use For |
|----------|---------|
| P0 | Critical: production outages, security, data loss |
| P1 | High: major functionality broken |
| P2 | Medium: important improvements |
| P3 | Low: nice-to-have |
| P4 | Backlog: future consideration |
| P5 | Wishlist: ideas, long-term |

P0 issues are processed sequentially before P1-P5 parallel work begins.

## CLI Tools

Automation layer for batch and parallel issue processing:

| Tool | Description |
|------|-------------|
| `ll-auto` | Automated sequential issue processing |
| `ll-parallel` | Parallel issue processing with git worktrees |
| `ll-sprint` | Sprint-based issue processing |
| `ll-loop` | FSM-based automation loop execution |

Install: `pip install little-loops`

## Directory Structure

```
.issues/
├── bugs/           # BUG-NNN issues
├── features/       # FEAT-NNN issues
├── enhancements/   # ENH-NNN issues
├── epics/          # EPIC-NNN coordination containers
└── completed/      # Resolved issues
```

## Related Skills

| Skill | Purpose |
|-------|---------|
| `issue-size-review` | Evaluate issue size/complexity, propose decomposition |
| `map-dependencies` | Discover and validate cross-issue dependencies |
| `confidence-check` | Pre-implementation readiness validation |
| `product-analyzer` | Analyze codebase against product goals |
| `analyze-history` | Issue history trends, velocity, project health |

## Quick Tips

- Run refinement commands (`normalize`, `prioritize`, `align`, `format`, `refine`, `verify`) before `ready-issue`
- Always run `/ll:ready-issue` before `/ll:manage-issue`
- Use `/ll:create-sprint` to group related issues for focused execution
- Use `/ll:tradeoff-review-issues` to prune low-value issues before sprints
- Issues move to `completed/` automatically when done
- Use CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) for batch processing
