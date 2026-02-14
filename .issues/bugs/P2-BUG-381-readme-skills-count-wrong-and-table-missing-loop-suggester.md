---
discovered_commit: 19510b2
discovered_branch: main
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-381: README skills count wrong (7 vs 8) and table missing loop-suggester

## Summary

README.md claims "7 skills" but there are 8 skill directories. The Skills table also lists only 7, missing the `loop-suggester` skill.

## Location

- **File**: `README.md`
- **Line(s)**: 86, 186-193
- **Section**: "What's Included" and "Skills" table

## Current Behavior

Line 86 states:
```markdown
- **7 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
```

Skills table (lines 186-193) lists 7 skills but omits `loop-suggester`.

## Actual Behavior

The `loop-suggester` skill exists at `skills/loop-suggester/SKILL.md` but is not counted or listed in the README Skills table. Current skills (8 total):

1. `issue-workflow`
2. `issue-size-review`
3. `map-dependencies`
4. `product-analyzer`
5. `workflow-automation-proposer`
6. `analyze-history`
7. `confidence-check`
8. `loop-suggester` (missing from README)

## Steps to Reproduce

1. Count skill directories: `ls -d skills/*/` (returns 8)
2. Read README.md line 86: says "7 skills"
3. Read README.md Skills table (lines 186-193): lists only 7 entries
4. Observe: `loop-suggester` is missing from both the count and the table

## Expected Behavior

Line 86 should state:
```markdown
- **8 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
```

Skills table should include an additional row:
```markdown
| `loop-suggester` | Automation & Loops | Suggest FSM loops from user message history |
```

## Proposed Solution

1. Update line 86: change "7 skills" to "8 skills"
2. Add `loop-suggester` row to the Skills table after the `confidence-check` row (or in alphabetical/group order under "Automation & Loops")

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

**Reopened** | Created: 2026-02-12 | Priority: P2

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

### Remaining Work

- Update Skills table to include all 15 skills (or the subset not already in Commands tables)
- Remove or correct `loop-suggester` entry in Skills table (no skill directory exists)
