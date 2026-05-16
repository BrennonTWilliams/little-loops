---
discovered_commit: 68997ce18a454cb21ec487df508fed6fda5b3b68
discovered_branch: main
discovered_date: 2026-01-17T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-083: Outdated command count in README.md

## Summary

Documentation issue found by `/ll:audit-docs`. The README claims "21 slash commands" but there are now **24 commands** after multiple additions since the original fix.

## Location

Multiple files need updates:

- **File**: `README.md`
- **Line(s)**: 13, 520
- **Sections**: Overview, Plugin Structure

- **File**: `docs/ARCHITECTURE.md`
- **Line(s)**: 64
- **Section**: Directory Structure

## Current Content

```markdown
- **21 slash commands** for development workflows
```

## Problem

The slash command count is outdated in multiple documentation files. Commands have been added (including `capture_issue`, `create_loop`, `align_issues`) but counts were not updated.

## Expected Content

```markdown
- **24 slash commands** for development workflows
```

## Files Requiring Updates

1. `README.md:13` - Overview count
2. `README.md:520` - Plugin Structure section
3. `docs/ARCHITECTURE.md:64` - Directory Structure comment

## Impact

- **Severity**: Low (documentation accuracy)
- **Effort**: Trivial
- **Risk**: None

## Verification

```bash
# Count actual commands
ls commands/*.md | wc -l
# Expected: 24
```

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-17 | Completed: 2026-01-20 | Priority: P2

---

## Completed

- **Date**: 2026-01-20
- **Fixed by**: /ll:ready-issue auto-correction
- **Resolution**: Updated command counts from 21 to 24 in all three locations

### Changes Made

1. `README.md:13` - Updated "21 slash commands" → "24 slash commands"
2. `README.md:520` - Updated "(21 commands)" → "(24 commands)"
3. `docs/ARCHITECTURE.md:64` - Updated "21 slash command templates" → "24 slash command templates"

---

## History

### Reopened (2026-01-20)

- **By**: audit_docs
- **Reason**: Documentation issue recurred - count was updated to 22 but has regressed

The command count had again become outdated. Originally fixed when there were 22 commands, but now there are 24:
- `capture_issue.md` was added
- `create_loop.md` was added
- `align_issues.md` was added
