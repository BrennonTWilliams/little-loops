---
discovered_commit: 8a8dc63bb0bc722f14e83c027d2696c7746dce5a
discovered_branch: main
discovered_date: 2026-03-20
discovered_by: audit-docs
doc_file: docs/guides/LOOPS_GUIDE.md
testable: false
---

# ENH-847: LOOPS_GUIDE Harness FSM Diagram Shows Only 3 of 5 Evaluation Phases

## Summary

The Harness FSM Structure diagram in `LOOPS_GUIDE.md` shows only 3 evaluation phases (`check_concrete` → `check_semantic` → `check_invariants`), omitting `check_mcp` and `check_skill`. The surrounding text states "up to five evaluation phases" but the diagram contradicts it.

## Location

- **File**: `docs/guides/LOOPS_GUIDE.md`
- **Line(s)**: 785–789
- **Section**: Harness Loops → FSM Structure

## Current Behavior

The Harness FSM Structure diagram shows only 3 evaluation phases:

```
discover ──→ execute ──→ check_concrete ──→ check_semantic ──→ check_invariants ──→ advance ──→ discover
               ↑              │ on_no              │ on_no              │ on_no
               └──────────────┴────────────────────┘
no items remaining ──→ done
```

The diagram omits `check_mcp` and `check_skill` from the evaluation chain, even though the guide's own text says "up to five evaluation phases" and the Evaluation Pipeline table directly above it lists all five. A new reader seeing this diagram first would assume harness loops have only 3 evaluation states.

## Expected Behavior

Either:
1. Expand the diagram to show all 5 phases (or a typical 5-phase variant) with a note that `check_mcp` and `check_skill` are optional
2. Add a "(simplified — omits optional check_mcp and check_skill phases)" annotation below the diagram

Option 2 is lower effort and consistent with how the AUTOMATIC_HARNESSING_GUIDE.md handles the same concern.

## Proposed Solution

Add a "(simplified — omits optional `check_mcp` and `check_skill` phases)" annotation directly below the closing code fence of the diagram block (after line 790 in `docs/guides/LOOPS_GUIDE.md`). This is the lowest-effort fix and is consistent with how the same concern is handled in `AUTOMATIC_HARNESSING_GUIDE.md`.

## Scope Boundaries

- Out of scope: Redesigning the full FSM diagram to show all 5 phases inline (valid but higher effort)
- Out of scope: Updating other diagrams in LOOPS_GUIDE.md unrelated to the evaluation chain

## Impact

- **Severity**: Low — misleads readers about the full evaluation pipeline; they must cross-reference AUTOMATIC_HARNESSING_GUIDE.md to get the complete picture
- **Effort**: Small (1–2 line annotation or diagram update)
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

## Resolution

Added `_(simplified — omits optional \`check_mcp\` and \`check_skill\` phases)_` annotation immediately after the closing code fence of the Harness FSM Structure diagram in `docs/guides/LOOPS_GUIDE.md` (after line 790). This resolves the contradiction between the diagram (3 phases) and the surrounding text ("up to five evaluation phases").

## Session Log
- `/ll:ready-issue` - 2026-03-20T22:26:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72f8a333-fc89-4278-9493-be6da775ca6f.jsonl`
- `/ll:verify-issues` - 2026-03-20T22:23:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55186214-ce82-4440-8e14-22b753b56da2.jsonl`
- `/ll:manage-issue` - 2026-03-20T00:00:00 - improve

---

## Status

**Completed** | Created: 2026-03-20 | Resolved: 2026-03-20 | Priority: P4
