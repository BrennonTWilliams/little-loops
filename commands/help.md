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

PROMPT OPTIMIZATION
-------------------
/ll:toggle_autoprompt [setting]
    Toggle automatic prompt optimization settings
    Settings: enabled, mode, confirm, status (default: status)

CODE QUALITY
------------
/ll:check_code [mode]
    Run code quality checks (lint, format, types)
    Modes: lint, format, types, all, fix

/ll:run_tests [scope] [pattern]
    Run test suites with common patterns
    Scopes: unit, integration, all, affected
    Pattern: optional pytest -k filter

/ll:find_dead_code
    Analyze codebase for deprecated, unused, or dead code

ISSUE MANAGEMENT
----------------
/ll:capture_issue [input]
    Capture issues from conversation or natural language description
    Input: optional - analyzes conversation if omitted

/ll:scan_codebase
    Scan codebase to identify bugs, enhancements, and features

/ll:prioritize_issues
    Analyze issues and assign priority levels (P0-P5)

/ll:ready_issue [issue_id]
    Validate issue file for accuracy and auto-correct problems

/ll:verify_issues
    Verify all issue files against current codebase state

/ll:normalize_issues
    Find and fix issue filenames lacking valid IDs (BUG-001, etc.)

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

/ll:audit_claude_config [scope] [flags]
    Comprehensive audit of Claude Code plugin configuration with parallel sub-agents
    Scope: all, global, project, hooks, mcp, agents, commands, skills
    Flags: --non-interactive, --fix

/ll:analyze_log <log_file>
    Analyze ll-parallel/ll-auto log files to identify tool bugs
    Creates/reopens issues in this plugin's .issues/ directory

SESSION MANAGEMENT
------------------
/ll:handoff [context]
    Generate continuation prompt for session handoff
    Context: optional description of current work

/ll:resume [prompt_file]
    Resume from a previous session's continuation prompt
    File: optional path (default: .claude/ll-continue-prompt.md)

GIT & WORKFLOW
--------------
/ll:commit
    Create git commits with user approval (no Claude attribution)

/ll:describe_pr
    Generate comprehensive PR descriptions from branch changes

================================================================================
Usage: /ll:<command> [arguments]

Configuration: .claude/ll-config.json
Documentation: https://github.com/BrennonTWilliams/little-loops
================================================================================
```

---

## Quick Reference Table

| Command | Description |
|---------|-------------|
| `init` | Initialize project configuration |
| `help` | Show this help message |
| `toggle_autoprompt` | Toggle automatic prompt optimization |
| `check_code` | Run lint, format, type checks |
| `run_tests` | Execute test suites |
| `find_dead_code` | Identify unused code |
| `capture_issue` | Capture issues from conversation or description |
| `scan_codebase` | Find issues in code |
| `prioritize_issues` | Assign P0-P5 priorities |
| `ready_issue` | Validate and fix issue files |
| `verify_issues` | Check issues against code |
| `normalize_issues` | Fix issue filenames lacking valid IDs |
| `manage_issue` | Full issue lifecycle management |
| `iterate_plan` | Update implementation plans |
| `audit_architecture` | Analyze code structure |
| `audit_docs` | Check documentation accuracy |
| `audit_claude_config` | Comprehensive config audit with parallel agents |
| `analyze_log` | Analyze ll-parallel/ll-auto logs for tool bugs |
| `handoff` | Generate continuation prompt for session handoff |
| `resume` | Resume from previous session's continuation prompt |
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
/ll:normalize_issues
/ll:prioritize_issues
/ll:manage_issue bug fix

# Prepare for a pull request
/ll:run_tests all
/ll:check_code
/ll:commit
/ll:describe_pr

# Analyze ll-parallel/ll-auto logs for tool bugs
/ll:analyze_log ll-parallel-debug.log
```
