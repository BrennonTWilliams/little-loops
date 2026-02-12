---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-358: issue-size-review skill references nonexistent command name

## Summary

The `issue-size-review` skill references `/ll:issue_size_review` (underscores) at line 27, but the skill is registered as `ll:issue-size-review` (hyphens). No `commands/issue_size_review.md` file exists.

## Location

- **File**: `skills/issue-size-review/SKILL.md:27`

## Current Behavior

The skill documentation tells users to invoke `/ll:issue_size_review`, which does not resolve to any command.

## Expected Behavior

The reference should match the actual skill registration name: `/ll:issue-size-review`.

## Fix

```diff
- /ll:issue_size_review
+ /ll:issue-size-review
```

## Impact

- **Priority**: P3
- **Effort**: Trivial - single string replacement
- **Risk**: None

## Labels

`bug`, `skills`, `documentation`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
