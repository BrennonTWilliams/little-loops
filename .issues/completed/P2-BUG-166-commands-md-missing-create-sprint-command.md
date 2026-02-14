---
discovered_commit: 9bd4454
discovered_branch: main
discovered_date: 2026-01-23T23:00:00Z
discovered_by: audit_docs
doc_file: docs/COMMANDS.md
---

# BUG-110: COMMANDS.md missing create_sprint command

## Summary

Documentation issue found by `/ll:audit-docs`.

The `docs/COMMANDS.md` command reference is missing the `/ll:create-sprint` command which exists at `.claude/commands/create_sprint.md`.

## Location

- **File**: `docs/COMMANDS.md`
- **Section**: Quick Reference table and main listing

## Current Content

The Quick Reference table (line ~177-205) lists 24 commands but is missing:
- `/ll:create-sprint`

## Problem

The `/ll:create-sprint` command exists at `.claude/commands/create_sprint.md` but is not documented in the command reference. This command creates sprint definitions with curated lists of issues.

## Expected Content

Add the following to the Quick Reference table:

```markdown
| `create_sprint` | Create sprint definition with curated issues |
```

And add a section in the appropriate category (likely under "Issue Management" or a new "Sprint Management" section):

```markdown
### `/ll:create-sprint`
Create a sprint definition with a curated list of issues.

**Arguments:**
- `name`: Sprint name identifier
- `description` (optional): Sprint description
- Other sprint-specific parameters
```

## Impact

- **Severity**: Medium (command exists but undocumented)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-23 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `docs/COMMANDS.md`: Added new "Sprint Management" section with `/ll:create-sprint` documentation (lines 101-113)
- `docs/COMMANDS.md`: Added `create_sprint` entry to Quick Reference table (line 221)

### Verification Results
- Documentation is valid markdown
- Section appears in correct location after Issue Management
- Arguments match command definition at `.claude/commands/create_sprint.md`
