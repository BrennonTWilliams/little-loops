---
discovered_date: 2026-01-24
discovered_by: audit
---

# ENH-138: Add sprint name validation to create_sprint command

## Summary

The `/ll:create_sprint` command documents naming conventions but doesn't enforce them. Add explicit validation to catch invalid sprint names early.

## Context

Lines 47-49 of the command document naming requirements:
- Must be non-empty
- Should use lowercase letters, numbers, and hyphens only
- Suggested format: `sprint-N`, `q1-features`, `bug-fixes-week-1`

However, there's no validation step to enforce these rules before creating the sprint file.

## Current Behavior

The command accepts any sprint name and proceeds to file creation. Invalid names (with spaces, special characters, uppercase) will create files that may cause issues with the `ll-sprint` CLI tool.

## Expected Behavior

Validate the sprint name immediately after parsing inputs and provide helpful feedback if invalid.

## Proposed Solution

Add validation logic to Step 1 (Validate and Parse Inputs):

```markdown
**Validate sprint name:**
- Must be non-empty
- Must match pattern: `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (or single char `^[a-z0-9]$`)
- No consecutive hyphens
- No leading/trailing hyphens

If name is invalid, report the specific issue and suggest a corrected version:

Example validations:
| Input | Issue | Suggestion |
|-------|-------|------------|
| `Sprint 1` | Contains space and uppercase | `sprint-1` |
| `--test--` | Leading/trailing/consecutive hyphens | `test` |
| `Q1_bugs` | Uppercase and underscore | `q1-bugs` |
| `` (empty) | Empty name | Ask user to provide name |

Use AskUserQuestion if name needs correction:
```yaml
questions:
  - question: "Sprint name '${name}' contains invalid characters. Use suggested name instead?"
    header: "Fix name"
    multiSelect: false
    options:
      - label: "Use '${suggested_name}' (Recommended)"
        description: "Auto-corrected name"
      - label: "Enter different name"
        description: "Provide your own name"
      - label: "Use original anyway"
        description: "May cause issues with ll-sprint CLI"
```
```

## Impact

- **Priority**: P4 (low - defensive improvement)
- **Effort**: Low
- **Risk**: Low

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_sprint.md | Target file (lines 47-49) |

## Labels

`enhancement`, `create_sprint`, `validation`

---

## Status

**Open** | Created: 2026-01-24 | Priority: P4
