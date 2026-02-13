# ENH-401: Add argument-hint to commands with arguments - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P5-ENH-401-add-argument-hint-to-commands-with-arguments.md`
- **Type**: enhancement
- **Priority**: P5
- **Action**: improve

## Current State Analysis

27 files (20 commands + 7 skills) have `arguments:` in their frontmatter but none have `argument-hint:`. The docs reference (`docs/claude-code/skills.md:179`) shows the format: `argument-hint: "[hint-text]"`.

## Desired End State

All commands and skills with `arguments:` also have an `argument-hint:` field showing the primary expected argument in brackets.

## What We're NOT Doing

- Not changing argument parsing or adding new arguments
- Not modifying commands without arguments

## Implementation

### Commands (20 files)

| File | argument-hint |
|------|---------------|
| `commands/handoff.md` | `"[context]"` |
| `commands/loop-suggester.md` | `"[messages.jsonl]"` |
| `commands/describe_pr.md` | `"[base-branch]"` |
| `commands/ready_issue.md` | `"[issue-id]"` |
| `commands/iterate_plan.md` | `"[plan-path]"` |
| `commands/manage_release.md` | `"[action] [version]"` |
| `commands/cleanup_worktrees.md` | `"[mode]"` |
| `commands/create_sprint.md` | `"[sprint-name]"` |
| `commands/open_pr.md` | `"[target-branch]"` |
| `commands/audit_architecture.md` | `"[focus-area]"` |
| `commands/run_tests.md` | `"[scope]"` |
| `commands/resume.md` | `"[prompt-file]"` |
| `commands/check_code.md` | `"[mode]"` |
| `commands/align_issues.md` | `"[category]"` |
| `commands/sync_issues.md` | `"[action] [issue-id]"` |
| `commands/verify_issues.md` | `"[issue-id]"` |
| `commands/toggle_autoprompt.md` | `"[setting]"` |
| `commands/analyze-workflows.md` | `"[messages.jsonl]"` |
| `commands/review_sprint.md` | `"[sprint-name]"` |
| `commands/refine_issue.md` | `"[issue-id]"` |

### Skills (7 files)

| File | argument-hint |
|------|---------------|
| `skills/format-issue/SKILL.md` | `"[issue-id]"` |
| `skills/audit-docs/SKILL.md` | `"[scope]"` |
| `skills/capture-issue/SKILL.md` | `"[description]"` |
| `skills/audit-claude-config/SKILL.md` | `"[scope]"` |
| `skills/manage-issue/SKILL.md` | `"[type] [action] [issue-id]"` |
| `skills/init/SKILL.md` | `"[flags]"` |
| `skills/configure/SKILL.md` | `"[area]"` |

## Verification
- Grep for `argument-hint:` to confirm all 27 files have it
- Grep for `arguments:` without `argument-hint:` to confirm none missed
