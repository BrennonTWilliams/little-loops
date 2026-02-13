---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-399: Add allowed-tools to 27 commands missing tool restrictions

## Summary

27 of 36 commands (75%) lack `allowed-tools` in their frontmatter. Only 9 commands currently specify it. Per `docs/claude-code/skills.md`, `allowed-tools` restricts available tools during command execution — important for security scoping and preventing unintended side effects. The largest commands (`init` at 1142 lines, `configure` at 1044 lines) are all missing this field.

## Current Behavior

75% of commands have no tool restrictions:
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

## Commands Missing allowed-tools (27)

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
16. `manage_release.md`
17. `normalize_issues.md`
18. `prioritize_issues.md`
19. `ready_issue.md`
20. `refine_issue.md`
21. `resume.md`
22. `review_sprint.md`
23. `run_tests.md`
24. `toggle_autoprompt.md`
25. `tradeoff_review_issues.md`
26. `verify_issues.md`

Note: The 26th was listed as a final count after deduplication. The plan originally listed 27 but `review_sprint` may be a skill command.

## Commands Already Specifying allowed-tools (9)

These serve as reference for the pattern:
- `check_code.md`
- `commit.md`
- `create_loop.md`
- `create_sprint.md`
- `manage_issue.md`
- `open_pr.md`
- `scan_codebase.md`
- `scan_product.md`
- `sync_issues.md`

## Integration Map

### Files to Modify
- 27 files in `commands/` directory

### Tests
- Verify commands still function correctly after adding tool restrictions

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

- **Priority**: P3 - Security improvement across most commands
- **Effort**: Medium - Requires auditing 27 command files
- **Risk**: Low - Additive frontmatter changes, but overly restrictive tools could break commands
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding `allowed-tools` frontmatter to commands that lack it
- **Out of scope**: Changing command behavior or refactoring command content

## Labels

`enhancement`, `commands`, `security`, `configuration`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
