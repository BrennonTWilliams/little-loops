---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-317: README command tables missing 4 of 34 commands

## Summary

Documentation issue found by `/ll:audit-docs`. The README "Commands" section lists 30 commands in its categorized tables but claims 34 slash commands. Four commands are missing from the tables while correctly listed in `docs/COMMANDS.md`.

## Location

- **File**: `README.md`
- **Lines**: 388-456
- **Section**: Commands
- **Anchor**: `## Commands`

## Current Behavior

The README states "34 slash commands" (line 25) and the directory tree shows "34 commands" (line 761), but the command tables only contain 30 entries. Four commands that exist in `commands/` and `docs/COMMANDS.md` are not listed in the README tables.

## Expected Behavior

All 34 commands should be listed in the README command tables, matching the stated count and the actual command files.

## Steps to Reproduce

1. Count commands listed in README tables: `grep -cE '^\| \x60/ll:' README.md` → 30
2. Count actual command files: `ls commands/*.md | wc -l` → 34
3. Observe: 4 commands are missing from README tables

## Actual Behavior

README tables list only 30 of 34 commands. The 4 missing commands are documented in `docs/COMMANDS.md` and have corresponding files in `commands/` but are absent from the README.

## Missing Commands

| Command | Category | In COMMANDS.md |
|---------|----------|---------------|
| `/ll:open-pr` | Git & Workflow | Yes |
| `/ll:manage-release` | Git & Workflow | Yes |
| `/ll:loop-suggester` | Automation Loops | Yes |
| `/ll:tradeoff-review-issues` | Issue Management | Yes |

## Proposed Fix

Add the 4 missing commands to their appropriate tables:
- `open_pr` and `manage_release` to "Git & Workflow"
- `loop-suggester` to a new "Automation Loops" section or under "Git & Workflow"
- `tradeoff_review_issues` to "Issue Management"

## Impact

- **Severity**: Medium (users can't discover these commands from README)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-02-10 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `README.md`: Added 4 missing command rows to command tables
  - `/ll:tradeoff-review-issues` → Issue Management
  - `/ll:open-pr` → Git & Workflow
  - `/ll:manage-release` → Git & Workflow
  - `/ll:loop-suggester` → Git & Workflow

### Verification Results
- Command count: 34 (matches stated count)
- All 4 commands present in correct categories
