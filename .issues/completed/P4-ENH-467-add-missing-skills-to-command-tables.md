---
type: enhancement
title: Add 7 missing skills to README and COMMANDS.md command tables
priority: P4
status: completed
created: 2026-02-23
found_by: audit-docs
---

# Add 7 Missing Skills to README and COMMANDS.md Command Tables

## Summary

The README.md "What's Included" section claims 43 slash commands, but the Commands section tables only list 36 entries. Seven skills are documented in the Skills table but missing from the workflow-organized Commands tables. The same 7 skills are also missing from the COMMANDS.md Quick Reference table and the CLAUDE.md Commands & Skills list.

## Current Behavior

README.md claims 43 slash commands (line 84) but the Commands section tables (lines 90-168) only contain 36 entries. The COMMANDS.md Quick Reference table (lines 306-346) also lists only 36 entries. The CLAUDE.md Commands & Skills list similarly lists 36 entries. Seven skills that exist in `skills/` and are listed in the README Skills table are absent from all three command reference locations.

## Expected Behavior

All 43 commands/skills should be listed in the README Commands tables, COMMANDS.md Quick Reference table, and CLAUDE.md Commands & Skills list, matching the stated count and the actual command+skill files.

## Affected Files

- `README.md` (lines 90-168, Commands section tables)
- `docs/COMMANDS.md` (lines 306-346, Quick Reference table)
- `.claude/CLAUDE.md` (Commands & Skills list, lines 51-58)

## Missing Skills and Suggested Categories

| Skill | Suggested Category | Description |
|-------|-------------------|-------------|
| `issue-workflow` | Issue Refinement | Quick reference for issue management workflow |
| `issue-size-review` | Issue Refinement | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies` | Issue Refinement | Analyze cross-issue dependencies based on file overlap |
| `product-analyzer` | Issue Discovery | Analyze codebase against product goals for feature gaps |
| `confidence-check` | Planning & Implementation | Pre-implementation confidence check for readiness |
| `workflow-automation-proposer` | Automation & Loops | Synthesize workflow patterns into automation proposals |
| `analyze-history` | Meta-Analysis | Analyze issue history for project health and trends |

## Proposed Solution

Add the 7 missing skills to the appropriate tables in each file:

1. **README.md Commands tables**: Insert each skill as a new row in its suggested category table (see table above), using `^` suffix convention for skills
2. **COMMANDS.md Quick Reference**: Add all 7 skills as rows in the Quick Reference table
3. **CLAUDE.md Commands & Skills**: Append each skill with `^` marker to its category line

## Implementation Steps

1. Add each skill as a new row in the appropriate README Commands table
2. Add each skill to the COMMANDS.md Quick Reference table
3. Update CLAUDE.md Commands & Skills list to include the 7 skills with `^` markers
4. Verify the total count of entries matches 43 in all locations

## Scope Boundaries

- Only adds entries to existing tables; does not restructure table layout or categories
- Does not modify skill definitions or SKILL.md files
- Does not update any counts beyond what matches the actual total (43)

## Impact

- **Priority**: P4 - Documentation accuracy; does not block functionality
- **Effort**: Small - Adding rows to existing tables in 3 files
- **Risk**: Low - Documentation-only change with no code impact
- **Breaking Change**: No

## Verification

- Count entries in each README Commands table — total should be 43
- Count entries in COMMANDS.md Quick Reference — should be 43
- Count entries in CLAUDE.md Commands & Skills list — should be 43

## Labels

`enhancement`, `documentation`, `audit-docs`

## Status

**Completed** | Created: 2026-02-23 | Completed: 2026-02-23 | Priority: P4

## Resolution

Added 7 missing skills to command tables in 3 files:
- **README.md**: Added `product-analyzer` to Issue Discovery, `issue-workflow`/`issue-size-review`/`map-dependencies` to Issue Refinement, `confidence-check` to Planning & Implementation, `workflow-automation-proposer` to Automation & Loops, `analyze-history` to Meta-Analysis
- **docs/COMMANDS.md**: Added all 7 skills to Quick Reference table in thematically appropriate positions
- **.claude/CLAUDE.md**: Appended all 7 skills with `^` markers to their respective category lines

Verified: All 3 files now contain 43 entries each, matching the stated count.
