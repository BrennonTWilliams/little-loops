---
discovered_date: 2026-02-12T00:00:00Z
discovered_by: audit_claude_config
---

# ENH-357: Update CLAUDE.md last-updated date and add new skills count

## Summary

CLAUDE.md has `Last updated: 2026-02-06` but skills grew from 6 to 8 (`loop-suggester` and `confidence-check` were added). The date should be updated and optionally a skills listing or count could be added.

## Location

- **File**: `.claude/CLAUDE.md`

## Fix

- Update the `<!-- Last updated: ... -->` comment to the current date
- Optionally add a skills count or listing to the document

## Note

Could be bundled with ENH-356 since both modify the same file.

## Impact

Low — documentation freshness improvement.

---

## Audit Update (2026-02-12)

**By**: audit_docs

The skills count discrepancy extends beyond CLAUDE.md:
- **README.md**: Claims "7 skills", table lists 7 (missing `loop-suggester`) — tracked in BUG-381
- **CONTRIBUTING.md**: Says "7 skill definitions", tree shows 6 — tracked in BUG-382

Consider fixing all three files together for consistency.
