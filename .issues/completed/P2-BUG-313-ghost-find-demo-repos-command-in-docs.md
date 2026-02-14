---
discovered_commit: 56c0d40
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: docs/COMMANDS.md
---

# BUG-313: Ghost `find_demo_repos` command documented in COMMANDS.md with no command file

## Summary

Documentation issue found by `/ll:audit-docs`. The command `/ll:find_demo_repos` is fully documented in `docs/COMMANDS.md` (lines 169-176) with description, arguments, and defaults, but no corresponding `commands/find_demo_repos.md` file exists. Users cannot run this command.

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

> **Note**: Counts were already corrected from 35→34 in commit `3b78009`. No count updates needed.
>
> - `README.md:25` - Already says "34 slash commands" ✓
> - `ARCHITECTURE.md:65` - Already says "34 slash command templates" ✓
> - `ARCHITECTURE.md:24` - Mermaid diagram already says "34" ✓
>
> After removing the ghost entry from COMMANDS.md (Option A), COMMANDS.md will document 34 commands matching the 34 command files — all counts stay consistent.

## Impact

- **Severity**: Medium (documented command cannot be used)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `docs/COMMANDS.md`: Removed ghost `/ll:find_demo_repos` detailed section (former lines 169-176)
- `docs/COMMANDS.md`: Removed ghost `find_demo_repos` row from Quick Reference table (former line 294)

### Approach
Applied Option A — removed the ghost documentation entry since the command was never implemented (erroneously documented during ENH-275).

### Verification Results
- `find_demo_repos` no longer appears in COMMANDS.md: PASS
- Command count (34) consistent across COMMANDS.md, README.md, ARCHITECTURE.md: PASS

---

## Status

**Completed** | Created: 2026-02-10 | Resolved: 2026-02-10 | Priority: P2
