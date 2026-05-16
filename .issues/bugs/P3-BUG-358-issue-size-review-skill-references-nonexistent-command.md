---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-358: issue-size-review skill references nonexistent command name

## Summary

The `issue-size-review` skill references `/ll:issue-size-review` (underscores) at line 27, but the skill is registered as `ll:issue-size-review` (hyphens). No `commands/issue_size_review.md` file exists.

## Location

- **File**: `skills/issue-size-review/SKILL.md:27`

## Current Behavior

The skill documentation tells users to invoke `/ll:issue-size-review`, which does not resolve to any command.

## Expected Behavior

The reference should match the actual skill registration name: `/ll:issue-size-review`.

## Steps to Reproduce

1. Open `skills/issue-size-review/SKILL.md`
2. Read the "How to Use" section at line 27
3. Observe: The command is listed as `/ll:issue-size-review` (underscores) instead of `/ll:issue-size-review` (hyphens)

## Actual Behavior

The "How to Use" section references `/ll:issue-size-review` which does not match the registered skill name `ll:issue-size-review`.

## Proposed Solution

```diff
- /ll:issue-size-review
+ /ll:issue-size-review
```

## Impact

- **Priority**: P3
- **Effort**: Trivial - single string replacement
- **Risk**: None

## Labels

`bug`, `skills`, `documentation`

## Session Log
- `/ll:manage-issue` - 2026-02-12 - `~/.claude/projects/<project>/a622f000-6389-43e9-8498-867481f130a3.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `skills/issue-size-review/SKILL.md:27`: Changed `/ll:issue-size-review` (underscores) to `/ll:issue-size-review` (hyphens) to match registered skill name

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Types: PASS
