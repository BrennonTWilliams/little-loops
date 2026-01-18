---
discovered_commit: 68997ce18a454cb21ec487df508fed6fda5b3b68
discovered_branch: main
discovered_date: 2026-01-17T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-083: Outdated command count in README.md

## Summary

Documentation issue found by `/ll:audit_docs`. The README claims "21 slash commands" but 22 actually exist after the addition of `cleanup_worktrees`.

## Location

- **File**: `README.md`
- **Line(s)**: 13
- **Section**: Overview

## Current Content

```markdown
- **21 slash commands** for development workflows
```

## Problem

The slash command count is outdated. The `cleanup_worktrees` command was added (FEAT-081) but the count was not updated.

## Expected Content

```markdown
- **22 slash commands** for development workflows
```

## Impact

- **Severity**: Low (documentation accuracy)
- **Effort**: Trivial
- **Risk**: None

## Verification

```bash
# Count actual commands
ls commands/*.md | wc -l
# Expected: 22
```

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-17 | Priority: P2
