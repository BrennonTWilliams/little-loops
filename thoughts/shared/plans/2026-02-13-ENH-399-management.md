# ENH-399: Add allowed-tools to 25 commands missing tool restrictions - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-399-add-allowed-tools-to-commands-missing-tool-restrictions.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

11 of 36 commands already specify `allowed-tools` in their frontmatter. The remaining 25 commands have no tool restrictions. Existing patterns use either simple tool names (`Read`, `Glob`) or scoped Bash restrictions (`Bash(git:*)`).

## Desired End State

All 36 commands specify `allowed-tools` with the minimum set of tools each actually needs.

### How to Verify
- All 36 command files have `allowed-tools` in frontmatter
- Commands still function correctly (no tool blocked that's actually needed)

## What We're NOT Doing

- Not changing command behavior or content
- Not refactoring existing commands
- Not modifying the 11 commands that already have `allowed-tools`

## Solution Approach

Add `allowed-tools` to each command's YAML frontmatter based on analysis of what tools the command body actually uses. Follow existing patterns from the 11 reference commands.

## Implementation - Tool Assignments

Based on deep analysis of each command's body content:

### Group 1: Read-only / Minimal (3 commands)

| Command | allowed-tools |
|---------|--------------|
| `help.md` | Read, Glob |
| `resume.md` | Read |
| `toggle_autoprompt.md` | Read, Edit |

### Group 2: Read + Edit + Bash(git) - Issue file modifiers (8 commands)

| Command | allowed-tools |
|---------|--------------|
| `align_issues.md` | Read, Glob, Grep, Edit, Bash(git:*) |
| `format_issue.md` | Read, Glob, Edit, Bash(git:*) |
| `normalize_issues.md` | Read, Glob, Edit, Bash(git:*, ll-next-id:*) |
| `prioritize_issues.md` | Read, Glob, Bash(git:*) |
| `verify_issues.md` | Read, Glob, Grep, Edit, Bash(git:*) |
| `capture_issue.md` | Read, Glob, Grep, Write, Bash(ll-next-id:*, git:*) |
| `ready_issue.md` | Read, Glob, Edit, Task, Bash(git:*) |
| `refine_issue.md` | Read, Glob, Edit, Task, Bash(git:*) |

### Group 3: Read + Edit + Task - Complex analysis (2 commands)

| Command | allowed-tools |
|---------|--------------|
| `tradeoff_review_issues.md` | Read, Glob, Edit, Task, Bash(git:*) |
| `review_sprint.md` | Read, Glob, Bash(ll-sprint:*) |

### Group 4: Audit commands - Read + Write + Bash (4 commands)

| Command | allowed-tools |
|---------|--------------|
| `audit_architecture.md` | Read, Glob, Grep, Write, Edit, Bash(ruff:*, wc:*, git:*) |
| `audit_docs.md` | Read, Glob, Grep, Edit, Write, Bash(git:*) |
| `audit_claude_config.md` | Read, Glob, Edit, Task, Bash(git:*) |
| `find_dead_code.md` | Read, Glob, Grep, Write, Bash(ruff:*) |

### Group 5: Config/Init - Full access (2 commands)

| Command | allowed-tools |
|---------|--------------|
| `configure.md` | Read, Edit, Bash(mkdir:*) |
| `init.md` | Read, Glob, Write, Edit, Bash(mkdir:*) |

### Group 6: Git/PR operations (2 commands)

| Command | allowed-tools |
|---------|--------------|
| `cleanup_worktrees.md` | Bash(git:*, find:*, rm:*) |
| `describe_pr.md` | Read, Bash(git:*, gh:*) |

### Group 7: Session management (1 command)

| Command | allowed-tools |
|---------|--------------|
| `handoff.md` | Read, Write, Bash(git:*) |

### Group 8: Planning/Analysis (3 commands)

| Command | allowed-tools |
|---------|--------------|
| `iterate_plan.md` | Read, Edit, Task, Bash(ls:*) |
| `loop-suggester.md` | Read, Write, Bash(ll-messages:*) |
| `run_tests.md` | Bash(python:*, pytest:*, npm:*, cargo:*, go:*, make:*, git:*) |

## Implementation Phase

Single phase: Add `allowed-tools` to all 25 command frontmatters.

### Success Criteria

- [ ] All 25 commands have `allowed-tools` in frontmatter
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
