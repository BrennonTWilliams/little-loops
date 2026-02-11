---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-338: Hook scripts ignore configured paths

## Summary

Hook shell scripts hardcode directory paths instead of reading from `ll-config.json`, meaning user config overrides for `issues.base_dir` and `parallel.worktree_base` are silently ignored.

## Context

Identified during a config consistency audit of the codebase. These scripts cannot adapt to custom config paths.

## Affected Files

- `hooks/scripts/check-duplicate-issue-id.sh` (line 74): hardcodes `ISSUES_DIR=".issues"` instead of reading `issues.base_dir`
- `hooks/scripts/session-cleanup.sh` (lines 17-20): hardcodes `if [ -d .worktrees ]` instead of reading `parallel.worktree_base`
- `commands/cleanup_worktrees.md` (line 24): hardcodes `WORKTREE_BASE=".worktrees"` despite documenting `{{config.parallel.worktree_base}}` on line 16

## Proposed Fix

Add jq-based config reading with fallback defaults:

```bash
CONFIG_FILE=".claude/ll-config.json"
ISSUES_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")
WORKTREE_BASE=$(jq -r '.parallel.worktree_base // ".worktrees"' "$CONFIG_FILE" 2>/dev/null || echo ".worktrees")
```

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle and config loading |

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
