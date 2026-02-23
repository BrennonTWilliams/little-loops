---
type: enhancement
title: Add 7 missing skills to README and COMMANDS.md command tables
priority: P4
status: open
created: 2026-02-23
found_by: audit-docs
---

# Add 7 Missing Skills to README and COMMANDS.md Command Tables

## Problem

The README.md "What's Included" section claims 43 slash commands, but the Commands section tables only list 36 entries. Seven skills are documented in the Skills table but missing from the workflow-organized Commands tables. The same 7 skills are also missing from the COMMANDS.md Quick Reference table.

## Affected Files

- `README.md` (lines 90-168, Commands section tables)
- `docs/COMMANDS.md` (lines 306-346, Quick Reference table)
- `.claude/CLAUDE.md` (Commands & Skills list, also shows 36)

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

## Implementation Steps

1. Add each skill as a new row in the appropriate README Commands table
2. Add each skill to the COMMANDS.md Quick Reference table
3. Update CLAUDE.md Commands & Skills list to include the 7 skills with `^` markers
4. Verify the total count of entries matches 43 in all locations

## Verification

- Count entries in each README Commands table — total should be 43
- Count entries in COMMANDS.md Quick Reference — should be 43
- Count entries in CLAUDE.md Commands & Skills list — should be 43
