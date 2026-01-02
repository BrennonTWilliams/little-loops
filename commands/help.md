---
description: List all available little-loops commands with descriptions
---

# Little Loops Help

Display all available `/ll:` commands organized by category.

## Process

Output the following command reference:

```
================================================================================
LITTLE LOOPS - Command Reference
================================================================================

SETUP & CONFIGURATION
---------------------
/ll:init [flags]
    Initialize little-loops configuration for a project
    Flags: --interactive, --yes, --force

/ll:help
    List all available little-loops commands with descriptions

CODE QUALITY
------------
/ll:check_code [mode]
    Run code quality checks (lint, format, types)
    Modes: lint, format, types, all, fix

/ll:run_tests [scope] [pattern]
    Run test suites with common patterns
    Scopes: unit, integration, all, affected

/ll:find_dead_code
    Analyze codebase for deprecated, unused, or dead code

ISSUE MANAGEMENT
----------------
/ll:scan_codebase
    Scan codebase to identify bugs, enhancements, and features

/ll:prioritize_issues
    Analyze issues and assign priority levels (P0-P5)

/ll:ready_issue [issue_id]
    Validate issue file for accuracy and auto-correct problems

/ll:verify_issues
    Verify all issue files against current codebase state

/ll:manage_issue <type> <action> [issue_id]
    Autonomously manage issues - plan, implement, verify, complete
    Types: bug, feature, enhancement
    Actions: fix, implement, improve, verify

/ll:iterate_plan [plan_path]
    Iterate on existing implementation plans with updates

AUDITING & ANALYSIS
-------------------
/ll:audit_architecture [focus]
    Analyze codebase architecture for patterns and improvements
    Focus: large-files, integration, patterns, organization, all

/ll:audit_docs [scope]
    Audit documentation for accuracy and completeness
    Scope: full, readme, file:<path>

GIT & WORKFLOW
--------------
/ll:commit
    Create git commits with user approval (no Claude attribution)

/ll:describe_pr
    Generate comprehensive PR descriptions from branch changes

================================================================================
Usage: /ll:<command> [arguments]

Configuration: .claude/ll-config.json
Documentation: https://github.com/little-loops/little-loops
================================================================================
```

---

## Quick Reference Table

| Command | Description |
|---------|-------------|
| `init` | Initialize project configuration |
| `help` | Show this help message |
| `check_code` | Run lint, format, type checks |
| `run_tests` | Execute test suites |
| `find_dead_code` | Identify unused code |
| `scan_codebase` | Find issues in code |
| `prioritize_issues` | Assign P0-P5 priorities |
| `ready_issue` | Validate and fix issue files |
| `verify_issues` | Check issues against code |
| `manage_issue` | Full issue lifecycle management |
| `iterate_plan` | Update implementation plans |
| `audit_architecture` | Analyze code structure |
| `audit_docs` | Check documentation accuracy |
| `commit` | Create git commits |
| `describe_pr` | Generate PR descriptions |

---

## Examples

```bash
# Get started with a new project
/ll:init

# Run all code quality checks
/ll:check_code

# Find and fix issues automatically
/ll:scan_codebase
/ll:prioritize_issues
/ll:manage_issue bug fix

# Prepare for a pull request
/ll:run_tests all
/ll:check_code
/ll:commit
/ll:describe_pr
```
