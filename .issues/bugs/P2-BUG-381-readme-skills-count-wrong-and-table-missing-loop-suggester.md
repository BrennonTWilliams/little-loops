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

## Current Content

Line 86:
```markdown
- **7 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
```

Skills table (lines 186-193) lists 7 skills but omits `loop-suggester`.

## Problem

The `loop-suggester` skill exists at `skills/loop-suggester/SKILL.md` but is not counted or listed in the README Skills table. Current skills (8 total):

1. `issue-workflow`
2. `issue-size-review`
3. `map-dependencies`
4. `product-analyzer`
5. `workflow-automation-proposer`
6. `analyze-history`
7. `confidence-check`
8. `loop-suggester` (missing)

## Expected Content

Line 86:
```markdown
- **8 skills** for history analysis, dependency mapping, product analysis, confidence checks, and more
```

Add to Skills table:
```markdown
| `loop-suggester` | Automation & Loops | Suggest FSM loops from user message history |
```

## Impact

- **Severity**: Medium (documentation inaccuracy visible to users)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P2
