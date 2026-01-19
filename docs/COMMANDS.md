# Command Reference

Complete reference for all `/ll:` commands. Run `/ll:help` in Claude Code for an interactive version.

## Setup & Configuration

### `/ll:init`
Initialize little-loops configuration for a project.

**Flags:** `--interactive`, `--yes`, `--force`

### `/ll:help`
List all available little-loops commands with descriptions.

---

## Prompt Optimization

### `/ll:toggle_autoprompt`
Toggle automatic prompt optimization settings.

**Settings:** `enabled`, `mode`, `confirm`, `status` (default: status)

---

## Code Quality

### `/ll:check_code`
Run code quality checks (lint, format, types).

**Modes:** `lint`, `format`, `types`, `all`, `fix`

### `/ll:run_tests`
Run test suites with common patterns.

**Arguments:**
- `scope`: `unit`, `integration`, `all`, `affected`
- `pattern`: optional pytest -k filter

### `/ll:find_dead_code`
Analyze codebase for deprecated, unused, or dead code.

---

## Issue Management

### `/ll:capture_issue`
Capture issues from conversation or natural language description.

**Arguments:** `input` (optional) - natural language description

### `/ll:scan_codebase`
Scan codebase to identify bugs, enhancements, and features.

### `/ll:prioritize_issues`
Analyze issues and assign priority levels (P0-P5).

### `/ll:ready_issue`
Validate issue file for accuracy and auto-correct problems.

**Arguments:** `issue_id` (optional)

### `/ll:verify_issues`
Verify all issue files against current codebase state.

### `/ll:align_issues`
Validate active issues against key documents for alignment.

**Arguments:**
- `category`: Document category (`architecture`, `product`, or `--all`)
- `flags` (optional): `--verbose` for detailed analysis

**Prerequisites:** Configure document tracking via `/ll:init --interactive`

### `/ll:normalize_issues`
Find and fix issue filenames lacking valid IDs (BUG-001, etc.).

### `/ll:manage_issue`
Autonomously manage issues - plan, implement, verify, complete.

**Arguments:**
- `type`: `bug`, `feature`, `enhancement`
- `action`: `fix`, `implement`, `improve`, `verify`
- `issue_id` (optional)

### `/ll:iterate_plan`
Iterate on existing implementation plans with updates.

**Arguments:** `plan_path` (optional)

---

## Auditing & Analysis

### `/ll:audit_architecture`
Analyze codebase architecture for patterns and improvements.

**Focus:** `large-files`, `integration`, `patterns`, `organization`, `all`

### `/ll:audit_docs`
Audit documentation for accuracy and completeness.

**Scope:** `full`, `readme`, `file:<path>`

### `/ll:audit_claude_config`
Comprehensive audit of Claude Code plugin configuration with parallel sub-agents.

**Scope:** `all`, `global`, `project`, `hooks`, `mcp`, `agents`, `commands`, `skills`

**Flags:** `--non-interactive`, `--fix`

---

## Git & Workflow

### `/ll:commit`
Create git commits with user approval (no Claude attribution).

### `/ll:describe_pr`
Generate comprehensive PR descriptions from branch changes.

### `/ll:cleanup_worktrees`
Clean up stale git worktrees and branches from parallel processing.

**Arguments:**
- `mode`: `run` (default), `dry-run`

---

## Session Management

### `/ll:handoff`
Generate continuation prompt for session handoff.

**Arguments:**
- `context` (optional): Description of current work context

### `/ll:resume`
Resume from a previous session's continuation prompt.

**Arguments:**
- `prompt_file` (optional): Path to continuation prompt (default: `.claude/ll-continue-prompt.md`)

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `init` | Initialize project configuration |
| `help` | Show command help |
| `toggle_autoprompt` | Toggle automatic prompt optimization |
| `check_code` | Run lint, format, type checks |
| `run_tests` | Execute test suites |
| `find_dead_code` | Identify unused code |
| `capture_issue` | Capture issues from conversation or description |
| `scan_codebase` | Find issues in code |
| `prioritize_issues` | Assign P0-P5 priorities |
| `ready_issue` | Validate and fix issue files |
| `verify_issues` | Check issues against code |
| `align_issues` | Validate issues against key documents |
| `normalize_issues` | Fix issue filenames lacking valid IDs |
| `manage_issue` | Full issue lifecycle management |
| `iterate_plan` | Update implementation plans |
| `audit_architecture` | Analyze code structure |
| `audit_docs` | Check documentation accuracy |
| `audit_claude_config` | Comprehensive config audit |
| `commit` | Create git commits |
| `describe_pr` | Generate PR descriptions |
| `cleanup_worktrees` | Clean up stale worktrees and branches |
| `handoff` | Generate session handoff prompt |
| `resume` | Resume from continuation prompt |

---

## Common Workflows

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
```
