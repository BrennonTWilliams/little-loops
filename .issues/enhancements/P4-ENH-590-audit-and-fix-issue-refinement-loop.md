---
discovered_date: 2026-03-05
discovered_by: manual-audit
confidence_score: 95
outcome_confidence: 95
---

# ENH-590: Audit and Fix `issue-refinement` Loop Configuration

## Summary

Audited `.loops/issue-refinement.yaml` for correctness, logic, and efficiency. Found and fixed four issues: a silently-ignored `description` field, a column name mismatch in the LLM evaluation prompt, a suboptimal `on_partial` routing that caused spurious fix invocations, and a missing loop-level timeout safety net.

## Current Behavior

`.loops/issue-refinement.yaml` had the following problems:

1. **`description` field silently ignored** — `FSMLoop.from_dict()` does not parse a `description` key; the field was dropped with no warning.
2. **LLM evaluator prompt said "format" but table column is "fmt"** — `refine_status.py` renders `/ll:format-issue` as a static column named `fmt`. The prompt told the evaluator to check a column named "format", introducing unnecessary ambiguity.
3. **`on_partial: fix` triggered fix on truncated-but-complete backlogs** — If `ll-issues refine-status` output was ambiguous or truncated (e.g. narrow terminal), the loop dispatched a 1200s Claude fix session even when all issues were already refined. Re-evaluating is the correct response to truncation.
4. **No loop-level timeout** — With `timeout: 1200` per fix iteration and up to 100 iterations, a stuck loop could theoretically run for hours with no hard ceiling.

## Resolution

All four issues fixed in a single session:

1. Replaced `description:` YAML field with inline `#` comments.
2. Changed `"format"` → `"fmt"` in both LLM prompt references (lines 20 and 25).
3. Changed `on_partial: fix` → `on_partial: evaluate` to re-check status on ambiguous output.
4. Added `timeout: 14400` (4-hour hard ceiling) at the loop level.

## Files Changed

- `.loops/issue-refinement.yaml` — all four fixes applied

## Impact

- **Priority**: P4 — Minor maintenance; loop was functional but had edge-case reliability issues
- **Effort**: Minimal — configuration-only changes
- **Risk**: None — changes are strictly safer/more correct; no behavioral regression possible
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fsm`, `maintenance`, `configuration`

## Session Log
- Manual audit + fix - 2026-03-05

---

## Status

**Completed** | Created: 2026-03-05 | Priority: P4

---

## Resolution

- **Status**: Completed
- **Completed**: 2026-03-05
- **Reason**: All identified issues fixed; loop configuration verified correct against FSM schema and executor logic.

### Changes Made
| Issue | Fix |
|---|---|
| `description` field silently ignored | Converted to YAML comments |
| `"format"` vs `"fmt"` in LLM prompt | Updated to `"fmt"` in both occurrences |
| `on_partial: fix` wastes fix slot on truncation | Changed to `on_partial: evaluate` |
| No loop-level timeout | Added `timeout: 14400` (4 hours) |
