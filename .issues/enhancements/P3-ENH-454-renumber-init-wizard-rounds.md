---
type: ENH
id: ENH-454
title: Renumber init wizard rounds to eliminate Round 6.5
priority: P3
status: completed
created: 2026-02-22
confidence_score: 95
---

# Renumber init wizard rounds to eliminate Round 6.5

## Summary

The interactive wizard currently uses: Rounds 1, 2, 3, 4, 5, 6, **6.5**, 7, 8, 9. The "6.5" numbering is awkward and signals this was added retroactively. Clean numbering improves maintainability and makes progress tracking easier.

## Current Behavior

The interactive wizard uses an inconsistent round numbering scheme: Rounds 1–6, then 6.5, then 7–9. The "6.5" designation signals a retroactively-added round and makes progress tracking awkward (e.g., "Step 6.5 of 10" is not meaningful).

## Expected Behavior

The wizard uses clean sequential numbering: Rounds 1–10, with "Round 7" replacing "Round 6.5" (Extended Configuration Gate) and subsequent rounds shifted accordingly.

## Motivation

Clean sequential round numbering enables correct progress indicators (ENH-452) and improves long-term maintainability. Non-integer round numbers signal technical debt and complicate any refactoring that references round numbers.

## Proposed Solution

Renumber to a clean sequence:

| Current | Proposed | Content |
|---------|----------|---------|
| Round 1 | Round 1 | Core Project Settings |
| Round 2 | Round 2 | Additional Configuration |
| Round 3 | Round 3 | Features Selection |
| Round 4 | Round 4 | Product Analysis |
| Round 5 | Round 5 | Advanced Settings (Dynamic) |
| Round 6 | Round 6 | Document Tracking |
| Round 6.5 | Round 7 | Extended Configuration Gate |
| Round 7 | Round 8 | Project Advanced (Optional) |
| Round 8 | Round 9 | Continuation Behavior (Optional) |
| Round 9 | Round 10 | Prompt Optimization (Optional) |

Update the summary table at the bottom of `interactive.md` accordingly.

## Scope Boundaries

- **In scope**: Renaming round headers and updating the summary table in `interactive.md`
- **Out of scope**: Changes to round logic, question content, or the order of rounds; this is a pure renaming exercise

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — All round headers (rename Round 6.5 → Round 7, shift Rounds 7-9 → 8-10); update summary table (lines ~782-799)

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md` — Check for any hardcoded references to "Round 6.5" or old round numbers

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Rename "## Round 6.5" header to "## Round 7" in `interactive.md`
2. Rename "## Round 7" → "## Round 8", "## Round 8" → "## Round 9", "## Round 9" → "## Round 10"
3. Update the summary table at the bottom of `interactive.md` with the new numbering
4. Search `skills/init/SKILL.md` for any references to old round numbers and update

## Impact

- **Priority**: P3 — Cosmetic/maintainability improvement; no user-visible impact beyond round numbers
- **Effort**: Small — Pure text search-and-replace across one file
- **Risk**: Low — No behavioral changes; documentation-only
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `interactive-wizard`, `maintainability`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- BUG-449
- ENH-451
- ENH-452

## Blocks

- ENH-456

---

## Resolution

**Completed** | 2026-02-23

Renumbered all init wizard rounds in `skills/init/interactive.md`:
- Round 6.5 → Round 7 (Extended Configuration Gate)
- Round 7 → Round 8 (Project Advanced)
- Round 8 → Round 9 (Continuation Behavior)
- Round 9 → Round 10 (Prompt Optimization)

Updated all internal references: progress tracking comments, transition directives, TOTAL recalculation comments, and summary table. Also corrected summary table total from "7-11" to "7-12" (matching SKILL.md).

No changes needed to `skills/init/SKILL.md` — already correct at "7-12 rounds".

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-23 | Priority: P3
