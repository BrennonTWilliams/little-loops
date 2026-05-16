---
discovered_commit: 925b8ce
discovered_branch: main
discovered_date: 2026-02-13T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-404: `/ll:review-sprint` missing from README command tables and COMMANDS.md

## Summary

The `review_sprint` command exists in `commands/review_sprint.md` but is not documented in the README command tables or `docs/COMMANDS.md` (neither the detailed sections nor the Quick Reference table).

## Location

- **Files**: `README.md`, `docs/COMMANDS.md`
- **Sections**: README "Commands" tables, COMMANDS.md detailed sections and Quick Reference

## Steps to Reproduce

1. Open `README.md` and search for `review_sprint`
2. Open `docs/COMMANDS.md` and search for `review_sprint`
3. Observe: neither file contains any reference to the `review_sprint` command

## Current Behavior

- README lists 8 command categories with all commands except `review_sprint`
- `docs/COMMANDS.md` has no entry for `review_sprint` in any section
- The command was added via ENH-394 (completed) but docs were not updated

## Actual Behavior

The `review_sprint` command exists in `commands/review_sprint.md` but is completely absent from both `README.md` and `docs/COMMANDS.md`, making it undiscoverable through documentation.

## Expected Behavior

- README should list `review_sprint` in the "Planning & Implementation" table (or a new "Sprint Management" row)
- `docs/COMMANDS.md` should have a detailed section for `/ll:review-sprint` under Sprint Management and include it in the Quick Reference table

## Proposed Solution

1. Add `review_sprint` to README.md command tables (under Planning & Implementation alongside `create_sprint`)
2. Add detailed `/ll:review-sprint` section to `docs/COMMANDS.md` under Sprint Management
3. Add `review_sprint` to the Quick Reference table in `docs/COMMANDS.md`

## Impact

- **Severity**: Medium (command undiscoverable via documentation)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

## Session Log
- `/ll:manage-issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e133534-9c00-4318-b32b-af5c69e96dad.jsonl`

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `README.md`: Added `review_sprint` to Planning & Implementation table
- `docs/COMMANDS.md`: Added detailed Sprint Management section and Quick Reference entry
- `commands/help.md`: Added to PLANNING & IMPLEMENTATION section and Quick Reference Table
- `.claude/CLAUDE.md`: Added to Planning & Implementation command list

### Verification Results
- Tests: PASS (2728 passed)
- Lint: PASS
- Doc counts: PASS (README.md matches actual command count)

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P2
