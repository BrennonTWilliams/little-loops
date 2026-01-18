---
description: |
  Quick reference for the little-loops issue management workflow. Use this skill when users ask about issue lifecycle, workflow steps, command order, or how to manage issues effectively.

  Trigger keywords: "issue workflow", "how do I manage issues", "issue lifecycle", "what commands for issues", "issue management steps"
---

# Little Loops Issue Workflow

Quick reference for managing issues with the little-loops plugin.

## Issue Lifecycle

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌───────────┐
│ scan_codebase│────▶│prioritize    │────▶│ready_issue  │────▶│manage_issue│
│ (discover)  │     │(assign P0-P5)│     │(validate)   │     │(implement) │
└─────────────┘     └──────────────┘     └─────────────┘     └───────────┘
                                                                    │
                                                                    ▼
                                                            ┌───────────┐
                                                            │ completed/│
                                                            └───────────┘
```

## Command Sequence

### 1. Discovery Phase
```bash
/ll:scan_codebase          # Find bugs, enhancements, features
/ll:normalize_issues       # Fix any non-standard filenames
/ll:prioritize_issues      # Assign P0-P5 priorities
```

### 2. Validation Phase
```bash
/ll:ready_issue BUG-001    # Validate specific issue
/ll:ready_issue --deep     # Deep validation with sub-agents
/ll:verify_issues          # Verify all open issues
```

### 3. Implementation Phase
```bash
/ll:manage_issue bug fix              # Fix highest priority bug
/ll:manage_issue bug fix BUG-001      # Fix specific bug
/ll:manage_issue feature implement    # Implement highest priority feature
/ll:manage_issue enhancement improve  # Improve highest priority enhancement
```

### 4. Completion Phase
```bash
/ll:check_code             # Run lint, format, type checks
/ll:run_tests              # Run test suite
/ll:commit                 # Commit changes
/ll:describe_pr            # Generate PR description
```

## Flags Reference

| Flag | Commands | Effect |
|------|----------|--------|
| `--plan-only` | manage_issue | Stop after creating plan |
| `--resume` | manage_issue | Resume from checkpoint |
| `--quick` | manage_issue | Skip deep research |
| `--auto` | manage_issue | Skip research + phase gates |
| `--deep` | ready_issue | Use sub-agents for validation |

## Priority Levels

| Priority | Use For |
|----------|---------|
| P0 | Critical: production outages, security, data loss |
| P1 | High: major functionality broken |
| P2 | Medium: important improvements |
| P3 | Low: nice-to-have |
| P4 | Backlog: future consideration |
| P5 | Wishlist: ideas, long-term |

## Directory Structure

```
.issues/
├── bugs/           # BUG-NNN issues
├── features/       # FEAT-NNN issues
├── enhancements/   # ENH-NNN issues
└── completed/      # Resolved issues
```

## Quick Tips

- Always run `/ll:ready_issue` before `/ll:manage_issue`
- Use `--quick` flag for simple, well-defined issues
- Use `--auto` flag for automation scripts (ll-auto, ll-parallel)
- Phase gates pause for manual verification (skip with `--auto`)
- Issues move to `completed/` automatically when done
