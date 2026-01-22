---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# BUG-104: ll_create_sprint examples show wrong command name

## Summary

The examples in `/ll:ll_create_sprint` show `/ll:create-sprint` (hyphen, no extra `ll`) but the actual command filename is `ll_create_sprint.md`, making the command `/ll:ll_create_sprint`. Users following the examples will get command-not-found errors.

## Context

Identified during audit of the `/ll:ll_create_sprint` slash command. The mismatch between documented examples and actual command name causes confusion and failed invocations.

## Current Behavior

Line 149 of `.claude/commands/ll_create_sprint.md`:
```bash
# Create sprint with explicit issue list
/ll:create-sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"
```

But the command file is named `ll_create_sprint.md`, so the actual invocation is:
```bash
/ll:ll_create_sprint sprint-1 ...
```

## Expected Behavior

Either:
1. Rename the command file to `create_sprint.md` (so invocation is `/ll:create_sprint`)
2. Or update all examples to use `/ll:ll_create_sprint`

Option 1 is preferred as it follows the pattern of other commands and removes the redundant `ll_` prefix.

## Proposed Solution

Rename `.claude/commands/ll_create_sprint.md` to `.claude/commands/create_sprint.md` and update examples to use `/ll:create_sprint` consistently.

## Impact

- **Priority**: P2 - Examples don't work
- **Effort**: Low - File rename and text updates
- **Risk**: Low - No code changes needed

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Command naming conventions |

## Labels

`bug`, `commands`, `documentation`, `naming`

---

**Priority**: P2 | **Created**: 2026-01-22
