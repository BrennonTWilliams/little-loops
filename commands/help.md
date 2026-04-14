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

/ll:scan-codebase [flags]
    Scan codebase to identify bugs, enhancements, and features
    Flags: --quick, --deep, --focus [area]

/ll:scan-product
    Scan codebase for product-focused issues based on goals document
    Requires: product.enabled in ll-config.json
    Skills: product-analyzer

/ll:audit-architecture [focus] [flags]
    Analyze codebase architecture for patterns and improvements
    Focus: large-files, integration, patterns, organization, all
    Flags: --deep

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

/ll:wire-issue <issue_id> [flags]
    Trace full codebase wiring for a refined issue — finds missing callers,
    registrations, docs, and tests the implementation plan must touch
    Flags: --auto (non-interactive), --dry-run (preview)

/ll:verify-issues
    Verify all issue files against current codebase state

/ll:tradeoff-review-issues
    Evaluate issues for utility vs complexity trade-offs
    Recommends implement, update, or close/defer for each issue

/ll:audit-issue-conflicts [flags]
    Scan all open issues for conflicting requirements, objectives, or
    architectural decisions — outputs a ranked conflict report
    Flags: --auto (non-interactive), --dry-run (report only)

/ll:ready-issue [issue_id]
    Validate issue file for accuracy and auto-correct problems

    Skills: issue-size-review, map-dependencies, confidence-check

PLANNING & IMPLEMENTATION
--------------------------
/ll:create-sprint [name] [--issues]
    Create sprint definition with curated list of issues

/ll:review-sprint [sprint_name]
    AI-guided sprint health check and optimization

/ll:manage-issue <type> <action> [issue_id] [flags]
    Autonomously manage issues - plan, implement, verify, complete
    Types: bug, feature, enhancement
    Actions: fix, implement, improve, verify
    Flags: --plan-only, --dry-run, --resume, --gates, --quick

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

/ll:update-docs [--since <date|git-ref>] [--fix]
    Identify stale/missing docs from git commits and completed issues since a date
    Default since: last commit touching a doc file (or .ll/ll-update-docs.watermark)

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

/ll:create-eval-from-issues <issue-id> [issue-id...]
    Generate a ready-to-run FSM eval harness YAML from one or more issue IDs
    Synthesizes execute prompt and llm_structured evaluation criteria from issue context
    Output: .loops/eval-harness-<slug>.yaml (validated before writing)

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
    CLI: ll-messages, ll-history, ll-workflows, ll-issues

/ll:improve-claude-md [flags]
    Rewrite CLAUDE.md using <important if="condition"> blocks for scoped instruction attention
    Flags: --dry-run (preview without writing), --file <path> (default: .claude/CLAUDE.md)

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

/ll:update [flags]
    Update little-loops plugin and pip package to the latest version
    Flags: --plugin, --package, --all, --dry-run

/ll:publish <version|patch|minor|major> [--dry-run]
    Bump version in all source files (maintainers only — project-local .claude/commands/, not shipped)

CLI TOOLS (pip install little-loops)
------------------------------------
ll-auto           Process all backlog issues sequentially in priority order
ll-parallel       Process issues concurrently using isolated git worktrees
ll-sprint         Define and execute curated issue sets with dependency-aware ordering
ll-loop           Execute FSM-based automation loops
ll-workflows      Identify multi-step workflow patterns from user message history
ll-messages       Extract user messages from Claude Code logs
ll-history        View issue statistics, analysis, and generate docs from history
ll-deps           Cross-issue dependency analysis and validation
ll-sync           Sync local issues with GitHub Issues
ll-issues         Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status)
ll-verify-docs    Verify documented counts match actual file counts
ll-check-links    Check markdown documentation for broken links
ll-gitignore      Suggest and apply .gitignore patterns based on untracked files
ll-create-extension Scaffold a new little-loops extension project
ll-generate-schemas Regenerate JSON Schema files for all LLEvent types (maintainer tool)

================================================================================
Usage: /ll:<command> [arguments] [flags]

FLAG CONVENTIONS
----------------
Flags are optional modifiers passed after arguments. Common flags:

  --quick       Reduce analysis depth for faster results
  --deep        Increase thoroughness, accept longer execution
  --focus X     Narrow scope to area X (e.g., security, performance)
  --dry-run     Show what would happen without making changes
  --auto        Non-interactive mode (no prompts)
  --verbose     Include detailed output
  --all         Process all items instead of single item

Not all commands support all flags. Check each command's documentation.

Configuration: .ll/ll-config.json
Documentation: https://github.com/BrennonTWilliams/little-loops
================================================================================
```

---

## Quick Reference Table

**Issue Discovery**: `capture-issue`, `scan-codebase`, `scan-product`, `audit-architecture`
**Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`, `refine-issue`, `wire-issue`, `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `audit-issue-conflicts`
**Planning & Implementation**: `create-sprint`, `review-sprint`, `manage-issue`, `iterate-plan`
**Scanning & Analysis**: `find-dead-code`
**Code Quality**: `check-code`, `run-tests`, `audit-docs`, `update-docs`
**Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
**Automation & Loops**: `create-loop`, `create-eval-from-issues`, `loop-suggester`
**Meta-Analysis**: `audit-claude-config`, `analyze-workflows`, `improve-claude-md`
**Session & Config**: `init`, `configure`, `help`, `handoff`, `resume`, `toggle-autoprompt`, `update`, `publish` *(maintainers only — project-local)*

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
- Plugin configuration: `.ll/ll-config.json`
- Issue tracking: `.issues/` directory
- Project documentation: `CONTRIBUTING.md`
