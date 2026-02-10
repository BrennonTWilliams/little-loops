---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-317: README command tables missing 4 of 34 commands

## Summary

Documentation issue found by `/ll:audit_docs`. The README "Commands" section lists 30 commands in its categorized tables but claims 34 slash commands. Four commands are missing from the tables while correctly listed in `docs/COMMANDS.md`.

## Location

- **File**: `README.md`
- **Lines**: 366-432
- **Section**: Commands

## Missing Commands

| Command | Category | In COMMANDS.md |
|---------|----------|---------------|
| `/ll:open_pr` | Git & Workflow | Yes |
| `/ll:manage_release` | Git & Workflow | Yes |
| `/ll:loop-suggester` | Automation Loops | Yes |
| `/ll:tradeoff_review_issues` | Issue Management | Yes |

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

**Open** | Created: 2026-02-10 | Priority: P2
