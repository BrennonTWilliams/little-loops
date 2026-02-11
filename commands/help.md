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

ISSUE DISCOVERY
---------------
/ll:capture_issue [input]
    Capture issues from conversation or natural language description
    Input: optional - analyzes conversation if omitted

/ll:scan_codebase
    Scan codebase to identify bugs, enhancements, and features

/ll:scan_product
    Scan codebase for product-focused issues based on goals document
    Requires: product.enabled in ll-config.json

/ll:audit_architecture [focus]
    Analyze codebase architecture for patterns and improvements
    Focus: large-files, integration, patterns, organization, all

    Skills: issue-workflow, issue-size-review, map-dependencies

ISSUE REFINEMENT
----------------
/ll:normalize_issues
    Find and fix issue filenames lacking valid IDs (BUG-001, etc.)

/ll:prioritize_issues
    Analyze issues and assign priority levels (P0-P5)

/ll:align_issues <category> [flags]
    Validate active issues against key documents for relevance and alignment
    Categories: architecture, product, --all
    Flags: --verbose, --dry-run
    Requires: documents.enabled in ll-config.json

/ll:refine_issue [issue_id]
    Refine issue files through interactive Q&A to improve quality

/ll:verify_issues
    Verify all issue files against current codebase state

/ll:tradeoff_review_issues
    Evaluate issues for utility vs complexity trade-offs
    Recommends implement, update, or close/defer for each issue

/ll:ready_issue [issue_id]
    Validate issue file for accuracy and auto-correct problems

    Skills: issue-size-review, map-dependencies

PLANNING & IMPLEMENTATION
--------------------------
/ll:create_sprint [name] [--issues]
    Create sprint definition with curated list of issues

/ll:manage_issue <type> <action> [issue_id]
    Autonomously manage issues - plan, implement, verify, complete
    Types: bug, feature, enhancement
    Actions: fix, implement, improve, verify

/ll:iterate_plan [plan_path]
    Iterate on existing implementation plans with updates

    CLI: ll-auto, ll-parallel, ll-sprint

SCANNING & ANALYSIS
-------------------
/ll:find_dead_code
    Analyze codebase for deprecated, unused, or dead code

/ll:analyze_log <log_file>
    Analyze ll-parallel/ll-auto log files to identify tool bugs

    Skills: product-analyzer

CODE QUALITY
------------
/ll:check_code [mode]
    Run code quality checks (lint, format, types)
    Modes: lint, format, types, all, fix

/ll:run_tests [scope] [pattern]
    Run test suites with common patterns
    Scopes: unit, integration, all, affected
    Pattern: optional pytest -k filter

/ll:audit_docs [scope]
    Audit documentation for accuracy and completeness
    Scope: full, readme, file:<path>

GIT & RELEASE
-------------
/ll:commit
    Create git commits with user approval (no Claude attribution)

/ll:open_pr [target_branch] [--draft]
    Open a pull request for the current branch
    Flags: --draft (create as draft PR)

/ll:describe_pr
    Generate comprehensive PR descriptions from branch changes

/ll:manage_release [action] [version]
    Manage releases - create git tags, generate changelogs

/ll:sync_issues [mode]
    Sync local issues with GitHub Issues (push/pull/status)
    Requires: sync.enabled in ll-config.json

/ll:cleanup_worktrees [mode]
    Clean orphaned git worktrees from interrupted runs

    CLI: ll-sync

AUTOMATION & LOOPS
------------------
/ll:create_loop
    Interactive FSM loop creation wizard

/ll:loop-suggester [file]
    Suggest FSM loops from user message history

    Skills: workflow-automation-proposer
    CLI: ll-loop

META-ANALYSIS
-------------
/ll:audit_claude_config [scope] [flags]
    Comprehensive audit of Claude Code plugin configuration
    Scope: all, global, project, hooks, mcp, agents, commands, skills
    Flags: --non-interactive, --fix

/ll:analyze-workflows [file]
    Analyze user message patterns for automation opportunities

    Skills: analyze-history
    CLI: ll-history, ll-workflows

SESSION & CONFIG
----------------
/ll:init [flags]
    Initialize little-loops configuration for a project
    Flags: --interactive, --yes, --force

/ll:configure [area]
    Interactive configuration editor

/ll:help
    List all available little-loops commands with descriptions

/ll:handoff [context]
    Generate continuation prompt for session handoff

/ll:resume [prompt_file]
    Resume from a previous session's continuation prompt

/ll:toggle_autoprompt [setting]
    Toggle automatic prompt optimization settings
    Settings: enabled, mode, confirm, status

================================================================================
Usage: /ll:<command> [arguments]

Configuration: .claude/ll-config.json
Documentation: https://github.com/BrennonTWilliams/little-loops
================================================================================
```

---

## Quick Reference Table

**Issue Discovery**: `capture_issue`, `scan_codebase`, `scan_product`, `audit_architecture`
**Issue Refinement**: `normalize_issues`, `prioritize_issues`, `align_issues`, `refine_issue`, `verify_issues`, `tradeoff_review_issues`, `ready_issue`
**Planning & Implementation**: `create_sprint`, `manage_issue`, `iterate_plan`
**Scanning & Analysis**: `find_dead_code`, `analyze_log`
**Code Quality**: `check_code`, `run_tests`, `audit_docs`
**Git & Release**: `commit`, `open_pr`, `describe_pr`, `manage_release`, `sync_issues`, `cleanup_worktrees`
**Automation & Loops**: `create_loop`, `loop-suggester`
**Meta-Analysis**: `audit_claude_config`, `analyze-workflows`
**Session & Config**: `init`, `configure`, `help`, `handoff`, `resume`, `toggle_autoprompt`

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
/ll:open_pr

# Analyze ll-parallel/ll-auto logs for tool bugs
/ll:analyze_log ll-parallel-debug.log
```

---

## Integration

This command is typically used when:
- Starting a new session to remember available commands
- Looking up command syntax and arguments
- Discovering workflow patterns

Related documentation:
- Plugin configuration: `.claude/ll-config.json`
- Issue tracking: `.issues/` directory
- Project documentation: `CONTRIBUTING.md`
