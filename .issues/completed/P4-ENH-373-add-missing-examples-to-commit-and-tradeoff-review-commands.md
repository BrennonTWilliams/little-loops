---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-373: Add missing Examples sections to commit and tradeoff_review_issues commands

## Summary

Two commands are missing `## Examples` sections:

1. **`commit.md`**: No examples section. As a frequently used command, examples showing single-commit vs multi-commit workflows and conventional commit format would be valuable.
2. **`tradeoff_review_issues.md`**: Missing both `arguments` in frontmatter and `## Examples` section.

## Current Behavior

- `commands/commit.md` (32 of 34 commands have `## Examples`; this is one of two that do not)
- `commands/tradeoff_review_issues.md` is also missing `## Examples` and `arguments` in frontmatter

## Location

- **Files**: `commands/commit.md`, `commands/tradeoff_review_issues.md`

## Expected Behavior

Add `## Examples` sections to both commands, consistent with the 32 other commands that have them.

## Proposed Solution

1. Add a `## Examples` section to `commands/commit.md` showing typical usage (e.g., `/ll:commit`)
2. Add a `## Examples` section to `commands/tradeoff_review_issues.md` showing typical usage (e.g., `/ll:tradeoff-review-issues`)
3. Add `arguments` field to `tradeoff_review_issues.md` frontmatter if applicable

## Scope Boundaries

- Only add `## Examples` sections and missing frontmatter fields
- Do not restructure or rewrite other sections of these command files
- Do not modify any other command files

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: None

## Labels

`enhancement`, `commands`, `documentation`

## Session Log
- `/ll:manage-issue` - 2026-02-12T00:00:00Z - managed via current session

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `commands/commit.md`: Added `## Examples` section with bash code block before `## Integration`
- `commands/tradeoff_review_issues.md`: Added `## Examples` section with bash code block before `## Integration`
- `arguments` frontmatter was not added to either file as neither command accepts arguments (consistent with other no-argument commands)

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Integration: PASS
