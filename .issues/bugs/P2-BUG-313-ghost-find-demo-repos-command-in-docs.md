---
discovered_commit: 56c0d40
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: docs/COMMANDS.md
---

# BUG-313: Ghost `find_demo_repos` command documented in COMMANDS.md with no command file

## Summary

Documentation issue found by `/ll:audit_docs`. The command `/ll:find_demo_repos` is fully documented in `docs/COMMANDS.md` (lines 169-176) with description, arguments, and defaults, but no corresponding `commands/find_demo_repos.md` file exists. Users cannot run this command.

This also causes a command count mismatch: COMMANDS.md documents 35 commands but only 34 command files exist.

## Location

- **File**: `docs/COMMANDS.md`
- **Lines**: 169-176
- **Section**: Auditing & Analysis

## Current Content

```markdown
### `/ll:find_demo_repos`
Search for and score public GitHub repositories as demo candidates for little-loops.

**Arguments:**
- `query` (optional): GitHub search query
- `limit` (optional): Number of repos to search (default: 5)
- `min_score` (optional): Minimum score to include (default: 35)
```

## Problem

No `commands/find_demo_repos.md` file exists. The command was either:
- Deleted without cleaning up COMMANDS.md, or
- Planned but never implemented

## Expected Fix

**Option A** (if command was removed): Delete lines 169-176 from COMMANDS.md and remove from Quick Reference table (line 294).

**Option B** (if command was planned): Create `commands/find_demo_repos.md` with matching implementation.

## Related Count Fixes

After resolving, update counts in:
- `README.md:25` - "35 slash commands" → update to match actual count
- `ARCHITECTURE.md:65` - "35 slash command templates" → update to match actual count
- `ARCHITECTURE.md:24` - Mermaid diagram already says "34" (correct if Option A)

## Impact

- **Severity**: Medium (documented command cannot be used)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2
