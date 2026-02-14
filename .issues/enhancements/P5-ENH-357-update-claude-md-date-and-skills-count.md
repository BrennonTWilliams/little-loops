---
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit-claude-config
---

# ENH-357: Update CLAUDE.md last-updated date and add new skills count

## Summary

CLAUDE.md has `Last updated: 2026-02-06` but skills grew from 6 to 8 (`loop-suggester` and `confidence-check` were added). The date should be updated and optionally a skills listing or count could be added.

## Location

- **File**: `.claude/CLAUDE.md`

## Fix

- Update the `<!-- Last updated: ... -->` comment to the current date
- Optionally add a skills count or listing to the document

## Motivation

This enhancement would:
- Ensure documentation accuracy and freshness — CLAUDE.md date and skills count reflect actual project state
- Business value: Claude and contributors see accurate metadata when reading project instructions
- Technical debt: Stale documentation creates confusion about project state and available capabilities

## Implementation Steps

1. **Update last-updated date**: Change the `<!-- Last updated: 2026-02-06 -->` comment in `.claude/CLAUDE.md` to the current date
2. **Add or update skills count**: Add a skills count or listing reflecting the current 8 skills (including `loop-suggester` and `confidence-check`)
3. **Coordinate with related files**: Consider fixing `README.md` (BUG-381) and `CONTRIBUTING.md` (BUG-382) for consistency across all documentation

## Note

Could be bundled with ENH-356 since both modify the same file.

## Integration Map

### Files to Modify
- `.claude/CLAUDE.md` — update last-updated date and skills count

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- N/A

### Tests
- N/A — documentation-only change

### Documentation
- `.claude/CLAUDE.md` — update last-updated date and skills count (this IS the change)

### Configuration
- N/A

## Impact

Low — documentation freshness improvement.

## Blocked By

_None — ENH-388 closed (won't-fix)._

---

## Audit Update (2026-02-12)

**By**: audit-docs

The skills count discrepancy extends beyond CLAUDE.md:
- **README.md**: Claims "7 skills", table lists 7 (missing `loop-suggester`) — tracked in BUG-381
- **CONTRIBUTING.md**: Says "7 skill definitions", tree shows 6 — tracked in BUG-382

Consider fixing all three files together for consistency.

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- Core issue still valid: CLAUDE.md date is `2026-02-06` (stale)
- **Skills count severely outdated**: Issue says 8 skills, but now **16 skills** exist in `skills/` directory: analyze-history, audit-claude-config, audit-docs, capture-issue, confidence-check, configure, create-loop, format-issue, init, issue-size-review, issue-workflow, loop-suggester, manage-issue, map-dependencies, product-analyzer, workflow-automation-proposer
- **Stale references**: BUG-381, BUG-382, and ENH-356 are all now **completed** — the "Audit Update" note about fixing "all three files together" and "bundled with ENH-356" is outdated
- Only the CLAUDE.md date/skills count updates remain; README and CONTRIBUTING are already fixed

## Session Log
- `/ll:format-issue --all --auto` - 2026-02-13
