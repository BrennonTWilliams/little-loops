---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# BUG-103: ll_create_sprint uses wrong issue filename pattern

## Summary

The `/ll:ll_create_sprint` command documentation shows an incorrect file search pattern for validating issue IDs. The bash example searches for `${issue_id}-*.md` (e.g., `BUG-001-*.md`) but actual issue files are named `P[0-5]-[TYPE]-[NNN]-description.md` (e.g., `P2-BUG-001-login-crash.md`).

## Context

Identified during audit of the `/ll:ll_create_sprint` slash command. The Python implementation in `sprint.py` uses the correct pattern (`*-{issue_id}-*.md`), but the command documentation shows the wrong pattern, which would cause validation failures if Claude follows the documented bash commands.

## Current Behavior

Line 74 of `.claude/commands/ll_create_sprint.md`:
```bash
if ! find {{config.issues.base_dir}} -name "${issue_id}-*.md" | grep -q .;
```

This pattern `BUG-001-*.md` will never match files like `P2-BUG-001-description.md`.

## Expected Behavior

Pattern should be `*-${issue_id}-*.md` to match the priority prefix:
```bash
if ! find {{config.issues.base_dir}} -name "*-${issue_id}-*.md" | grep -q .;
```

Or better, use Claude's Glob tool with pattern `**/*-BUG-001-*.md`.

## Proposed Solution

1. Update line 74-77 to use correct glob pattern: `*-${issue_id}-*.md`
2. Consider replacing bash `find` with Claude's Glob tool for consistency

## Impact

- **Priority**: P2 - Command validation fails silently
- **Effort**: Low - Simple pattern fix
- **Risk**: Low - Documentation change only

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Issue file format specification |

## Labels

`bug`, `commands`, `documentation`

---

**Priority**: P2 | **Created**: 2026-01-22
