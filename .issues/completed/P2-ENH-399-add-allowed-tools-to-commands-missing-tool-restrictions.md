---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-399: Add allowed-tools to 25 commands missing tool restrictions

## Summary

25 of 36 commands (69%) lack `allowed-tools` in their frontmatter. Only 11 commands currently specify it. Per `docs/claude-code/skills.md`, `allowed-tools` restricts available tools during command execution — important for security scoping and preventing unintended side effects. The largest commands (`init` at 1142 lines, `configure` at 1044 lines) are all missing this field.

## Motivation

This enhancement would:
- Improve security by preventing unintended tool access during command execution
- Business value: Reduces risk of commands accidentally modifying files or running shell commands they should not need
- Technical debt: Ensures all 36 commands consistently specify tool restrictions per documented best practices

## Current Behavior

69% of commands have no tool restrictions:
```yaml
---
description: "..."
arguments: "..."
# no allowed-tools field
---
```

## Expected Behavior

Each command should have `allowed-tools` specifying only the tools it actually needs:
```yaml
---
description: "..."
arguments: "..."
allowed-tools: ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]
---
```

## Commands Missing allowed-tools (25)

1. `align_issues.md`
2. `audit_architecture.md`
3. `audit_claude_config.md`
4. `audit_docs.md`
5. `capture_issue.md`
6. `cleanup_worktrees.md`
7. `configure.md`
8. `describe_pr.md`
9. `find_dead_code.md`
10. `format_issue.md`
11. `handoff.md`
12. `help.md`
13. `init.md`
14. `iterate_plan.md`
15. `loop-suggester.md`
16. `normalize_issues.md`
17. `prioritize_issues.md`
18. `ready_issue.md`
19. `refine_issue.md`
20. `resume.md`
21. `review_sprint.md`
22. `run_tests.md`
23. `toggle_autoprompt.md`
24. `tradeoff_review_issues.md`
25. `verify_issues.md`

## Commands Already Specifying allowed-tools (11)

These serve as reference for the pattern:
- `analyze-workflows.md`
- `check_code.md`
- `commit.md`
- `create_loop.md`
- `create_sprint.md`
- `manage_issue.md`
- `manage_release.md`
- `open_pr.md`
- `scan_codebase.md`
- `scan_product.md`
- `sync_issues.md`

## Integration Map

### Files to Modify
- 25 files in `commands/` directory

### Tests
- N/A — command markdown frontmatter changes are not Python-testable; verified via manual invocation

### Documentation
- `.claude/CLAUDE.md` — update command list if any commands change names
- `docs/COMMANDS.md` — update command documentation for tool restriction additions

## Implementation Steps

1. For each command, read its body to determine actual tool usage
2. Categorize commands by tool profile:
   - **Read-only**: `help`, `handoff`, `resume`, `toggle_autoprompt` (Read, Glob, Grep only)
   - **Read + Bash**: `run_tests`, `cleanup_worktrees` (needs shell execution)
   - **Read + Write**: `format_issue`, `normalize_issues`, etc. (needs file creation/editing)
   - **Full access**: `init`, `configure`, `manage_release` (needs all tools)
3. Add appropriate `allowed-tools` to each command's frontmatter
4. Test representative commands from each category

## Impact

- **Priority**: P2 - Security improvement across most commands
- **Effort**: Medium - Requires auditing 25 command files
- **Risk**: Low - Additive frontmatter changes, but overly restrictive tools could break commands
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding `allowed-tools` frontmatter to commands that lack it
- **Out of scope**: Changing command behavior or refactoring command content

## Blocked By

- ~~BUG-402~~: Commands reference $ARGUMENTS inconsistently — ✅ Completed
- ~~BUG-363~~: Allowed-tools mismatch in scan commands — ✅ Completed

## Labels

`enhancement`, `commands`, `security`, `configuration`

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `commands/help.md`: Added `allowed-tools: [Read, Glob]`
- `commands/resume.md`: Added `allowed-tools: [Read]`
- `commands/toggle_autoprompt.md`: Added `allowed-tools: [Read, Edit]`
- `commands/handoff.md`: Added `allowed-tools: [Read, Write, Bash(git:*)]`
- `commands/align_issues.md`: Added `allowed-tools: [Read, Glob, Grep, Edit, Bash(git:*)]`
- `commands/format_issue.md`: Added `allowed-tools: [Read, Glob, Edit, Bash(git:*)]`
- `commands/normalize_issues.md`: Added `allowed-tools: [Read, Glob, Edit, Bash(git:*, ll-next-id:*)]`
- `commands/prioritize_issues.md`: Added `allowed-tools: [Read, Glob, Bash(git:*)]`
- `commands/verify_issues.md`: Added `allowed-tools: [Read, Glob, Grep, Edit, Bash(git:*)]`
- `commands/capture_issue.md`: Added `allowed-tools: [Read, Glob, Grep, Write, Bash(ll-next-id:*, git:*)]`
- `commands/ready_issue.md`: Added `allowed-tools: [Read, Glob, Edit, Task, Bash(git:*)]`
- `commands/refine_issue.md`: Added `allowed-tools: [Read, Glob, Edit, Task, Bash(git:*)]`
- `commands/tradeoff_review_issues.md`: Added `allowed-tools: [Read, Glob, Edit, Task, Bash(git:*)]`
- `commands/review_sprint.md`: Added `allowed-tools: [Read, Glob, Bash(ll-sprint:*)]`
- `commands/audit_architecture.md`: Added `allowed-tools: [Read, Glob, Grep, Write, Edit, Bash(ruff:*, wc:*, git:*)]`
- `commands/audit_docs.md`: Added `allowed-tools: [Read, Glob, Grep, Edit, Write, Bash(git:*)]`
- `commands/audit_claude_config.md`: Added `allowed-tools: [Read, Glob, Edit, Task, Bash(git:*)]`
- `commands/find_dead_code.md`: Added `allowed-tools: [Read, Glob, Grep, Write, Bash(ruff:*)]`
- `commands/configure.md`: Added `allowed-tools: [Read, Edit, Bash(mkdir:*)]`
- `commands/init.md`: Added `allowed-tools: [Read, Glob, Write, Edit, Bash(mkdir:*)]`
- `commands/cleanup_worktrees.md`: Added `allowed-tools: [Bash(git:*, find:*, rm:*)]`
- `commands/describe_pr.md`: Added `allowed-tools: [Read, Bash(git:*, gh:*)]`
- `commands/iterate_plan.md`: Added `allowed-tools: [Read, Edit, Task, Bash(ls:*)]`
- `commands/loop-suggester.md`: Added `allowed-tools: [Read, Write, Bash(ll-messages:*)]`
- `commands/run_tests.md`: Added `allowed-tools: [Bash(python:*, pytest:*, npm:*, cargo:*, go:*, make:*, git:*)]`

### Verification Results
- Tests: PASS (2733 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- /ll:format-issue --all --auto - 2026-02-13
- /ll:manage-issue enhancement improve ENH-399 - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: VERIFIED (counts updated to reflect current state)

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P2
