---
discovered_commit: 68997ce18a454cb21ec487df508fed6fda5b3b68
discovered_branch: main
discovered_date: 2026-01-17T00:00:00Z
discovered_by: audit_docs
doc_file: docs/COMMANDS.md
---

# BUG-084: Missing cleanup_worktrees command in docs/COMMANDS.md

## Summary

Documentation issue found by `/ll:audit_docs`. The `/ll:cleanup_worktrees` command exists at `commands/cleanup_worktrees.md` but is not documented in the COMMANDS.md reference.

## Location

- **File**: `docs/COMMANDS.md`
- **Section**: Quick Reference table and potentially Git & Workflow section

## Problem

The `cleanup_worktrees` command was added but not included in the command reference documentation. Users looking at COMMANDS.md won't find this utility.

## Expected Content

Add to Quick Reference table and Git & Workflow section:

```markdown
### `/ll:cleanup_worktrees`
Clean up stale git worktrees and branches from parallel processing.
```

Quick Reference entry:
```markdown
| `cleanup_worktrees` | Clean up stale worktrees and branches |
```

## Impact

- **Severity**: Low (documentation completeness)
- **Effort**: Trivial
- **Risk**: None

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-17 | Priority: P2
