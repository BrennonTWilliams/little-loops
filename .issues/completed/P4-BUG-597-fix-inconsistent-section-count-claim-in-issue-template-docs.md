# BUG: ISSUE_TEMPLATE.md section count claim is internally inconsistent

## Summary

`docs/reference/ISSUE_TEMPLATE.md` states both "21 sections → 20 sections (-5%)" and "removing 8 low-value sections" + "adding 4 high-impact sections" — these cannot both be true (21 - 8 + 4 = 17, not 20).

## Current Behavior

Lines 8-9 of `docs/reference/ISSUE_TEMPLATE.md`:
```
The little-loops issue template has been optimized to maximize value for both AI agents
during implementation and human reviewers. Version 2.0 reduces cognitive overhead by
**removing 8 low-value sections** and **adding 4 high-impact sections** that appear in
best-practice issues.

**Key Changes**:
- 21 sections → 20 sections (-5%)
```

The two claims contradict each other:
- "removing 8 / adding 4" implies net -4 sections: 21 - 4 = **17**
- "21 → 20 (-5%)" implies net -1 section

## Expected Behavior

The section count claim should match the actual math. One of the following must be corrected:
1. The net change description (not "8 removed / 4 added"), OR
2. The resulting section count (not "20")

## Root Cause

- **File**: `docs/reference/ISSUE_TEMPLATE.md`
- **Anchor**: Overview paragraph, `**Key Changes**` block
- **Cause**: Likely an edit updated the summary count without updating the ±section description (or vice versa)

## Proposed Solution

Count actual v2.0 template sections (common + type-specific) to determine the correct number, then update either:
- The "removing N / adding N" description, or
- The "21 → X" summary line

The Quick Reference table lists 11 common sections + type-specific sections (5 BUG, 3 FEAT, 2 ENH). Cross-reference against v1.0 to determine the correct before/after counts.

## Integration Map

### Files to Modify
- `docs/reference/ISSUE_TEMPLATE.md` — Fix the inconsistent section count claim (lines 8-9)

### Dependent Files (Callers/Importers)
- N/A — documentation only

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 - Minor docs inaccuracy, no functional impact
- **Effort**: Small - Count sections, fix one line
- **Risk**: None
- **Breaking Change**: No

## Labels

`bug`, `docs`, `issue-template`

## Status

**Completed** | Created: 2026-03-05 | Completed: 2026-03-05 | Priority: P4

## Resolution

Changed `docs/reference/ISSUE_TEMPLATE.md` line 11 from `21 sections → 20 sections (-5%)` to `21 sections → 17 sections (-19%)`. The math 21 - 8 + 4 = 17 is now consistent with the stated "removing 8 / adding 4" operation.

## Session Log
- `/ll:ready-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f275d2ce-2845-4a08-8893-1f0ad46695b3.jsonl`
- `/ll:manage-issue bug fix BUG-597` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f275d2ce-2845-4a08-8893-1f0ad46695b3.jsonl`
