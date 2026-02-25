# ENH-467: Add 7 Missing Skills to Command Tables

**Issue**: P4-ENH-467-add-missing-skills-to-command-tables.md
**Action**: implement
**Date**: 2026-02-23

## Summary

Add 7 missing skills to the command/skill reference tables in README.md, docs/COMMANDS.md, and .claude/CLAUDE.md.

## Changes

### 1. README.md - Commands Section Tables (lines 90-168)

Add skill entries to the appropriate category tables:

| Skill | Category | Entry |
|-------|----------|-------|
| `product-analyzer` | Issue Discovery | `/ll:product-analyzer` - Analyze codebase against product goals for feature gaps |
| `issue-workflow` | Issue Refinement | `/ll:issue-workflow` - Quick reference for issue management workflow |
| `issue-size-review` | Issue Refinement | `/ll:issue-size-review` - Evaluate issue size/complexity and propose decomposition |
| `map-dependencies` | Issue Refinement | `/ll:map-dependencies` - Analyze cross-issue dependencies based on file overlap |
| `confidence-check` | Planning & Implementation | `/ll:confidence-check [id]` - Pre-implementation confidence check for readiness |
| `workflow-automation-proposer` | Automation & Loops | `/ll:workflow-automation-proposer` - Synthesize workflow patterns into automation proposals |
| `analyze-history` | Meta-Analysis | `/ll:analyze-history` - Analyze issue history for project health and trends |

### 2. docs/COMMANDS.md - Quick Reference Table (lines 308-345)

Add 7 rows in thematically appropriate locations within the flat table.

### 3. .claude/CLAUDE.md - Commands & Skills List (lines 51-58)

Append each skill with `^` marker to its category line.

## Success Criteria

- [ ] All 3 files updated
- [ ] Total entry count in each location = 43
- [ ] Existing entries unchanged
- [ ] Format matches existing patterns
