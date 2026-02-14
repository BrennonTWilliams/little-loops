---
description: List all available little-loops commands with descriptions
allowed-tools:
  - Read
  - Glob
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
/ll:capture-issue [input]
    Capture issues from conversation or natural language description
    Input: optional - analyzes conversation if omitted

/ll:scan-codebase
    Scan codebase to identify bugs, enhancements, and features

/ll:scan-product
    Scan codebase for product-focused issues based on goals document
    Requires: product.enabled in ll-config.json
    Skills: product-analyzer

/ll:audit-architecture [focus]
    Analyze codebase architecture for patterns and improvements
    Focus: large-files, integration, patterns, organization, all

    Skills: issue-workflow, issue-size-review, map-dependencies
    CLI: ll-deps

ISSUE REFINEMENT
----------------
/ll:normalize-issues
    Find and fix issue filenames lacking valid IDs (BUG-001, etc.)

/ll:prioritize-issues
    Analyze issues and assign priority levels (P0-P5)

/ll:align-issues <category> [flags]
    Validate active issues against key documents for relevance and alignment
    Categories: architecture, product, --all
    Flags: --verbose, --dry-run
    Requires: documents.enabled in ll-config.json

/ll:format-issue [issue_id]
    Format issue files to align with template v2.0 structure

/ll:refine-issue <issue_id> [flags]
    Refine issue with codebase-driven research to fill knowledge gaps
    Flags: --auto (non-interactive), --dry-run (preview)

/ll:verify-issues
    Verify all issue files against current codebase state

/ll:tradeoff-review-issues
    Evaluate issues for utility vs complexity trade-offs
    Recommends implement, update, or close/defer for each issue

/ll:ready-issue [issue_id]
    Validate issue file for accuracy and auto-correct problems

    Skills: issue-size-review, map-dependencies, confidence-check

PLANNING & IMPLEMENTATION
--------------------------
/ll:create-sprint [name] [--issues]
    Create sprint definition with curated list of issues

/ll:review-sprint [sprint_name]
    AI-guided sprint health check and optimization

/ll:manage-issue <type> <action> [issue_id]
    Autonomously manage issues - plan, implement, verify, complete
    Types: bug, feature, enhancement
    Actions: fix, implement, improve, verify

/ll:iterate-plan [plan_path]
    Iterate on existing implementation plans with updates

    CLI: ll-auto, ll-parallel, ll-sprint

SCANNING & ANALYSIS
-------------------
/ll:find-dead-code
    Analyze codebase for deprecated, unused, or dead code

CODE QUALITY
------------
/ll:check-code [mode]
    Run code quality checks (lint, format, types)
    Modes: lint, format, types, all, fix

/ll:run-tests [scope] [pattern]
    Run test suites with common patterns
    Scopes: unit, integration, all, affected
    Pattern: optional pytest -k filter

/ll:audit-docs [scope]
    Audit documentation for accuracy and completeness
    Scope: full, readme, file:<path>

GIT & RELEASE
-------------
/ll:commit
    Create git commits with user approval (no Claude attribution)

/ll:open-pr [target_branch] [--draft]
    Open a pull request for the current branch
    Flags: --draft (create as draft PR)

/ll:describe-pr
    Generate comprehensive PR descriptions from branch changes

/ll:manage-release [action] [version]
    Manage releases - create git tags, generate changelogs

/ll:sync-issues [mode]
    Sync local issues with GitHub Issues (push/pull/status)
    Requires: sync.enabled in ll-config.json

/ll:cleanup-worktrees [mode]
    Clean orphaned git worktrees from interrupted runs

    CLI: ll-sync

AUTOMATION & LOOPS
------------------
/ll:create-loop
    Interactive FSM loop creation wizard

/ll:loop-suggester [file]
    Suggest FSM loops from user message history

    Skills: workflow-automation-proposer
    CLI: ll-loop

META-ANALYSIS
-------------
/ll:audit-claude-config [scope] [flags]
    Comprehensive audit of Claude Code plugin configuration
    Scope: all, global, project, hooks, mcp, agents, commands, skills
    Flags: --non-interactive, --fix

/ll:analyze-workflows [file]
    Analyze user message patterns for automation opportunities

    Skills: analyze-history
    CLI: ll-messages, ll-history, ll-workflows

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

/ll:toggle-autoprompt [setting]
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

**Issue Discovery**: `capture-issue`, `scan-codebase`, `scan-product`, `audit-architecture`
**Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`, `refine-issue`, `verify-issues`, `tradeoff-review-issues`, `ready-issue`
**Planning & Implementation**: `create-sprint`, `review-sprint`, `manage-issue`, `iterate-plan`
**Scanning & Analysis**: `find-dead-code`
**Code Quality**: `check-code`, `run-tests`, `audit-docs`
**Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
**Automation & Loops**: `create-loop`, `loop-suggester`
**Meta-Analysis**: `audit-claude-config`, `analyze-workflows`
**Session & Config**: `init`, `configure`, `help`, `handoff`, `resume`, `toggle-autoprompt`

---

## Examples

```bash
# Get started with a new project
/ll:init

# Run all code quality checks
/ll:check-code

# Find and fix issues automatically
/ll:scan-codebase
/ll:normalize-issues
/ll:prioritize-issues
/ll:manage-issue bug fix

# Prepare for a pull request
/ll:run-tests all
/ll:check-code
/ll:commit
/ll:open-pr
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
