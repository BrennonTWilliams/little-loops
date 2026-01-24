---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-108: create_sprint should use Claude tools instead of bash

## Summary

The `/ll:create_sprint` command instructs Claude to use bash `find` commands for file operations, but Claude Code has specialized tools (Glob, Grep, Read) that are preferred for these operations.

## Context

Identified during audit of the `/ll:create_sprint` slash command. Using bash commands may have permission issues or different behavior compared to Claude's built-in tools.

## Current Behavior

Lines 67-69 and 78-84 in `.claude/commands/create_sprint.md` use bash `find`:
```bash
find .issues -name "*.md" -not -path "*/completed/*" | sort
```

```bash
for issue_id in "${ISSUE_ARRAY[@]}"; do
  # Search for issue file (pattern includes priority prefix, e.g., P2-BUG-001-description.md)
  if ! find .issues -name "*-${issue_id}-*.md" | grep -q .; then
    echo "Warning: Issue ${issue_id} not found"
  fi
done
```

**Anchor**: `create_sprint.md` → Sections "Option B: Interactive Category Selection" and "Validate Issues Exist"

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

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `.claude/commands/create_sprint.md`: Replaced bash `find` commands with instructions to use Claude's Glob tool
  - Section "Option B: Interactive Category Selection": Now uses Glob with pattern `.issues/**/*.md`
  - Section "3. Validate Issues Exist": Now uses Glob with pattern `.issues/**/*-{issue_id}-*.md`

### Verification Results
- Tests: N/A (documentation change only)
- Lint: N/A (markdown file)
- Types: N/A (markdown file)
