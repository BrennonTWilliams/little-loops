---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-108: ll_create_sprint should use Claude tools instead of bash

## Summary

The `/ll:ll_create_sprint` command instructs Claude to use bash `find` commands for file operations, but Claude Code has specialized tools (Glob, Grep, Read) that are preferred for these operations.

## Context

Identified during audit of the `/ll:ll_create_sprint` slash command. Using bash commands may have permission issues or different behavior compared to Claude's built-in tools.

## Current Behavior

Lines 62-63 and 74-77 use bash `find`:
```bash
find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | sort
```

```bash
for issue_id in "${ISSUE_ARRAY[@]}"; do
  if ! find {{config.issues.base_dir}} -name "${issue_id}-*.md" | grep -q .; then
```

## Expected Behavior

Use Claude's built-in tools:

```markdown
Use the Glob tool to find active issues:
- Pattern: `.issues/**/*.md`
- Exclude: `.issues/completed/**`

Use the Glob tool to validate each issue exists:
- Pattern: `.issues/**/*-{issue_id}-*.md`
```

## Proposed Solution

Replace bash file operations with Claude tool instructions:

1. Replace `find ... -name "*.md"` with Glob tool
2. Replace validation loop with Glob pattern matching
3. Keep bash only for actual shell operations (git commands, etc.)

## Impact

- **Priority**: P4 - Best practice, current approach still works
- **Effort**: Low - Text updates in command documentation
- **Risk**: Low - Documentation change only

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Tool usage preferences |

## Labels

`enhancement`, `commands`, `best-practices`

---

**Priority**: P4 | **Created**: 2026-01-22
