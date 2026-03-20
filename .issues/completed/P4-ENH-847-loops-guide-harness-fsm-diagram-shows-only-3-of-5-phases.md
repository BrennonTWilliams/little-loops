---
discovered_commit: 8a8dc63bb0bc722f14e83c027d2696c7746dce5a
discovered_branch: main
discovered_date: 2026-03-20
discovered_by: audit-docs
doc_file: docs/guides/LOOPS_GUIDE.md
---

# ENH-847: LOOPS_GUIDE Harness FSM Diagram Shows Only 3 of 5 Evaluation Phases

## Summary

The Harness FSM Structure diagram in `LOOPS_GUIDE.md` shows only 3 evaluation phases (`check_concrete` → `check_semantic` → `check_invariants`), omitting `check_mcp` and `check_skill`. The surrounding text states "up to five evaluation phases" but the diagram contradicts it.

## Location

- **File**: `docs/guides/LOOPS_GUIDE.md`
- **Line(s)**: 785–789
- **Section**: Harness Loops → FSM Structure

## Current Content

```
discover ──→ execute ──→ check_concrete ──→ check_semantic ──→ check_invariants ──→ advance ──→ discover
               ↑              │ on_no              │ on_no              │ on_no
               └──────────────┴────────────────────┘
no items remaining ──→ done
```

## Problem

The diagram omits `check_mcp` and `check_skill` from the evaluation chain, even though the guide's own text says "up to five evaluation phases" and the Evaluation Pipeline table directly above it lists all five. A new reader seeing this diagram first would assume harness loops have only 3 evaluation states.

## Expected Content

Either:
1. Expand the diagram to show all 5 phases (or a typical 5-phase variant) with a note that `check_mcp` and `check_skill` are optional
2. Add a "(simplified — omits optional check_mcp and check_skill phases)" annotation below the diagram

Option 2 is lower effort and consistent with how the AUTOMATIC_HARNESSING_GUIDE.md handles the same concern.

## Impact

- **Severity**: Low — misleads readers about the full evaluation pipeline; they must cross-reference AUTOMATIC_HARNESSING_GUIDE.md to get the complete picture
- **Effort**: Small (1–2 line annotation or diagram update)
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-20 | Priority: P4
