---
discovered_commit: 925b8ce
discovered_branch: main
discovered_date: 2026-02-13T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-404: `/ll:review_sprint` missing from README command tables and COMMANDS.md

## Summary

The `review_sprint` command exists in `commands/review_sprint.md` but is not documented in the README command tables or `docs/COMMANDS.md` (neither the detailed sections nor the Quick Reference table).

## Location

- **Files**: `README.md`, `docs/COMMANDS.md`
- **Sections**: README "Commands" tables, COMMANDS.md detailed sections and Quick Reference

## Current Behavior

- README lists 8 command categories with all commands except `review_sprint`
- `docs/COMMANDS.md` has no entry for `review_sprint` in any section
- The command was added via ENH-394 (completed) but docs were not updated

## Expected Behavior

- README should list `review_sprint` in the "Planning & Implementation" table (or a new "Sprint Management" row)
- `docs/COMMANDS.md` should have a detailed section for `/ll:review_sprint` under Sprint Management and include it in the Quick Reference table

## Proposed Solution

1. Add `review_sprint` to README.md command tables (under Planning & Implementation alongside `create_sprint`)
2. Add detailed `/ll:review_sprint` section to `docs/COMMANDS.md` under Sprint Management
3. Add `review_sprint` to the Quick Reference table in `docs/COMMANDS.md`

## Impact

- **Severity**: Medium (command undiscoverable via documentation)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-13 | Priority: P2
