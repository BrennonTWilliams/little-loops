---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# BUG-105: create_sprint references undefined --priority argument

## Summary

The `/ll:create-sprint` command shows an example using `--priority P0` but this argument is not defined in the command's frontmatter arguments section. The feature does not exist.

## Context

Identified during audit of the `/ll:create-sprint` slash command. The examples suggest functionality that was never implemented, misleading users.

## Current Behavior

Line 155 of `.claude/commands/create_sprint.md`:
```bash
# Create sprint with all P0 bugs
/ll:create-sprint critical-fixes --priority P0
```

But the frontmatter only defines these arguments:
```yaml
arguments:
  - name: name
    description: Sprint name (e.g., "sprint-1", "q1-bug-fixes")
    required: true
  - name: description
    description: Optional description of the sprint's purpose
    required: false
  - name: issues
    description: Comma-separated list of issue IDs to include
    required: false
```

No `--priority` argument exists.

## Expected Behavior

Either:
1. Remove the example showing `--priority P0`
2. Or implement the `--priority` argument to filter issues by priority level

Option 2 would be a useful feature enhancement - automatically selecting all issues of a given priority.

## Proposed Solution

1. For immediate fix: Remove line 155 example
2. For enhancement: Add `--priority` argument that filters active issues by priority prefix

## Impact

- **Priority**: P2 - Example shows non-existent feature
- **Effort**: Low (remove) or Medium (implement)
- **Risk**: Low - Documentation fix

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Command argument specifications |

## Labels

`bug`, `commands`, `documentation`

---

**Priority**: P2 | **Created**: 2026-01-22

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-22
- **Status**: Completed

### Changes Made
- `.claude/commands/create_sprint.md`: Removed the invalid example at lines 154-155 that referenced the undefined `--priority P0` argument

### Verification Results
- Tests: N/A (documentation change)
- Lint: PASS
- Types: PASS
