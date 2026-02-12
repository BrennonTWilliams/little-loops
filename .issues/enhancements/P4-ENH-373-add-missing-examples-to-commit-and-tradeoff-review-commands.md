---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-373: Add missing Examples sections to commit and tradeoff_review_issues commands

## Summary

Two commands are missing `## Examples` sections:

1. **`commit.md`**: No examples section. As a frequently used command, examples showing single-commit vs multi-commit workflows and conventional commit format would be valuable.
2. **`tradeoff_review_issues.md`**: Missing both `arguments` in frontmatter and `## Examples` section.

## Location

- **Files**: `commands/commit.md`, `commands/tradeoff_review_issues.md`

## Expected Behavior

Add `## Examples` sections to both commands, consistent with the 32 other commands that have them.

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: None

## Labels

`enhancement`, `commands`, `documentation`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
