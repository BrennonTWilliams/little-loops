---
discovered_commit: 19510b2
discovered_branch: main
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-381: README skills count wrong (7 vs 8) and table missing loop-suggester

## Summary

README.md Skills table lists only 8 entries (including phantom `loop-suggester` which has no skill directory) but there are 15 actual skill directories. Eight skills are missing from the table and one invalid entry needs removal.

## Location

- **File**: `README.md`
- **Line(s)**: 86, 185-196
- **Section**: "What's Included" and "Skills" table

## Current Behavior

Line 86 correctly states "15 skills" (already auto-fixed). However, the Skills table (lines 185-196) lists only 8 entries, including `loop-suggester` which has no skill directory (it's a command only). Eight actual skills are missing from the table.

## Actual Behavior

There are 15 skill directories under `skills/`. The Skills table lists only 8 entries and includes `loop-suggester` which no longer has a skill directory.

Missing from table (8 skills with valid `skills/*/SKILL.md`):
1. `audit-claude-config`
2. `audit-docs`
3. `capture-issue`
4. `configure`
5. `create-loop`
6. `format-issue`
7. `init`
8. `manage-issue`

Should be removed from table (no skill directory):
- `loop-suggester` (exists as command only at `commands/loop-suggester.md`)

## Steps to Reproduce

1. Count skill directories: `ls -d skills/*/` (returns 15)
2. Read README.md line 86: says "15 skills" (correct)
3. Read README.md Skills table (lines 185-196): lists only 8 entries
4. Observe: 8 skills missing from table, and `loop-suggester` listed without a skill directory

## Expected Behavior

Skills table should list all 15 skills with valid `skills/*/SKILL.md` directories. The `loop-suggester` entry should be removed (it's a command, not a skill).

## Proposed Solution

1. Remove `loop-suggester` row from the Skills table (no skill directory exists)
2. Add rows for the 8 missing skills: `audit-claude-config`, `audit-docs`, `capture-issue`, `configure`, `create-loop`, `format-issue`, `init`, `manage-issue`
3. Verify final table has 15 entries matching the count on line 86

## Impact

- **Severity**: Medium (documentation inaccuracy visible to users)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `README.md`: Changed "7 skills" to "8 skills" on line 86
- `README.md`: Added `loop-suggester` row to Skills table

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Priority: P2

---

## Reopened

- **Date**: 2026-02-14
- **By**: audit-docs
- **Reason**: Documentation issue recurred

### New Findings

Skills count drifted again after 7 new skills were added since the original fix:
- README.md line 86: was "8 skills", now corrected to "15 skills" (auto-fixed)
- Skills table (lines 186-196) still only lists 8 of 15 skills
- Missing from table: `capture-issue`, `audit-claude-config`, `audit-docs`, `configure`, `format-issue`, `init`, `manage-issue`, `create-loop`
- `loop-suggester` is listed in the Skills table but no longer has a `skills/loop-suggester/SKILL.md` file (it's a command only)

---

## Resolution (Reopen Fix)

- **Action**: fix
- **Completed**: 2026-02-14
- **Status**: Completed

### Changes Made
- `README.md`: Removed `loop-suggester` from Skills table (no skill directory exists)
- `README.md`: Added 8 missing skills to table: `audit-claude-config`, `audit-docs`, `capture-issue`, `configure`, `create-loop`, `format-issue`, `init`, `manage-issue`
- Skills table now has 15 entries matching the "15 skills" count on line 86

### Verification Results
- Tests: PASS (2834 passed)
- Lint: PASS (pre-existing unrelated error)
- Types: PASS
- ll-verify-docs: README skills count matches (15=15)
