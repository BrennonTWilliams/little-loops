---
type: ENH
id: ENH-454
title: Renumber init wizard rounds to eliminate Round 6.5
priority: P3
status: open
created: 2026-02-22
---

# Renumber init wizard rounds to eliminate Round 6.5

## Summary

The interactive wizard currently uses: Rounds 1, 2, 3, 4, 5, 6, **6.5**, 7, 8, 9. The "6.5" numbering is awkward and signals this was added retroactively. Clean numbering improves maintainability and makes progress tracking easier.

## Proposed Change

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

## Files

- `skills/init/interactive.md` (all round headers, summary table at lines ~640-662)
