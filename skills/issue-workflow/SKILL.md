---
description: |
  Quick reference for the little-loops issue management workflow. Use this skill when users ask about issue lifecycle, workflow steps, command order, or how to manage issues effectively.

  Trigger keywords: "issue workflow", "how do I manage issues", "issue lifecycle", "what commands for issues", "issue management steps"
---

# Little Loops Issue Workflow

Quick reference for managing issues with the little-loops plugin.

## Issue Lifecycle

```
                        /ll:scan_codebase
                        /ll:scan_product
                        /ll:capture_issue
                        /ll:audit_architecture
                               │
                               ▼
                        ┌─────────────┐
                        │  Discovered  │◀──────────────────┐
                        └──────┬──────┘                    │
                               │ /ll:prioritize_issues     │ Fix issue file
                               ▼                           │
                        ┌─────────────┐                    │
                        │ Prioritized  │                    │
                        └──────┬──────┘                    │
                               │ /ll:ready_issue           │
                               ▼                           │
                        ┌─────────────┐                    │
                        │  Validating  │                    │
                        └──┬───┬───┬──┘                    │
              READY ◀──────┘   │   └──────▶ CLOSE          │
                │         NOT_READY           │             │
                │              │              ▼             │
                │              └───────▶ completed/         │
                ▼                                           │
         ┌─────────────┐                                    │
         │  InProgress  │ /ll:manage_issue                  │
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
/ll:scan_codebase              # Find bugs, enhancements, features (technical)
/ll:scan_product               # Find issues from product goals perspective
/ll:capture_issue "desc"       # Capture issue from conversation or description
/ll:audit_architecture [focus] # Analyze architecture for patterns and improvements
```

### 2. Refinement Phase
```bash
/ll:normalize_issues           # Fix invalid issue filenames
/ll:prioritize_issues          # Assign P0-P5 priorities
/ll:align_issues <category>   # Validate issues against key documents
/ll:format_issue [id]          # Align issue with template v2.0 structure
/ll:refine_issue [id]          # Enrich issue with codebase research findings
/ll:verify_issues              # Verify all issues against current codebase
/ll:tradeoff_review_issues     # Evaluate utility vs complexity trade-offs
/ll:ready_issue [id]           # Final validation before implementation
```

### 3. Planning & Implementation Phase
```bash
/ll:create_sprint [name]       # Create sprint with curated issue list
/ll:manage_issue bug fix       # Fix highest priority bug
/ll:manage_issue bug fix BUG-001        # Fix specific bug
/ll:manage_issue feature implement      # Implement highest priority feature
/ll:manage_issue enhancement improve    # Improve highest priority enhancement
/ll:iterate_plan [path]        # Update existing implementation plans
```

### 4. Completion Phase
```bash
/ll:check_code                 # Run lint, format, type checks
/ll:run_tests                  # Run test suite
/ll:commit                     # Commit changes
/ll:describe_pr                # Generate PR description
/ll:open_pr                    # Open pull request
```

## manage_issue Reference

| Parameter | Values |
|-----------|--------|
| Types | `bug`, `feature`, `enhancement` |
| Actions | `fix`, `implement`, `improve`, `verify` |

## ready_issue Sub-Skills

`ready_issue` runs these validation skills automatically:

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

Install: `pip install -e "./scripts[dev]"`

## Directory Structure

```
.issues/
├── bugs/           # BUG-NNN issues
├── features/       # FEAT-NNN issues
├── enhancements/   # ENH-NNN issues
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

- Run refinement commands (`normalize`, `prioritize`, `align`, `format`, `refine`, `verify`) before `ready_issue`
- Always run `/ll:ready_issue` before `/ll:manage_issue`
- Use `/ll:create_sprint` to group related issues for focused execution
- Use `/ll:tradeoff_review_issues` to prune low-value issues before sprints
- Issues move to `completed/` automatically when done
- Use CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`) for batch processing
