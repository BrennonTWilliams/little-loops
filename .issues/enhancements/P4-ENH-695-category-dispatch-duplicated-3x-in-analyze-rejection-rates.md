---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# ENH-695: Category dispatch logic duplicated 3x in `analyze_rejection_rates`

## Summary

In `analyze_rejection_rates`, the same 5-branch `if/elif` chain (completed/rejected/invalid/duplicate/deferred) appears three times — once each for `overall`, `type_metrics`, and `month_metrics` `RejectionMetrics` instances.

## Motivation

Three identical dispatch blocks (15 lines each) in the same function make it easy to update two copies and miss the third. Extracting a helper enforces a single source of truth for the category-to-field mapping and makes each call site intent clear. The three copies are structurally identical, differing only in the target object.

## Location

- **File**: `scripts/little_loops/issue_history/quality.py`
- **Line(s)**: 155-199 (at scan commit: 3e9beea)
- **Anchor**: `in function analyze_rejection_rates()`

## Current Behavior

Three identical `if/elif` dispatch chains, each updating a different `RejectionMetrics` instance with the same category-to-field mapping.

## Expected Behavior

A single helper function `_update_rejection_metrics(metrics: RejectionMetrics, category: str)` encapsulates the dispatch, and each of the three sites calls it.

## Implementation Steps

1. In `quality.py`, add `_update_rejection_metrics(metrics: RejectionMetrics, category: str) -> None` before `analyze_rejection_rates`
2. Move the 5-branch `if/elif` dispatch into the new helper
3. Replace each of the three dispatch blocks in `analyze_rejection_rates` with a call to the helper
4. Run `python -m pytest` to verify identical output

## Integration Map

- **Modified**: `scripts/little_loops/issue_history/quality.py` — `analyze_rejection_rates()` (lines 155-199)
- **New helper**: `_update_rejection_metrics()` (private, same file)

## Scope Boundaries

- Extract helper only; no change to `RejectionMetrics` dataclass
- Do not change the public interface of `analyze_rejection_rates`

## Impact

- **Priority**: P4 - Code cleanliness, reduces maintenance burden
- **Effort**: Small - Extract helper, replace 3 dispatch blocks
- **Risk**: Low - Pure refactoring
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `issue-history`

## Session Log
- `/ll:verify-issues` - 2026-03-23T00:58:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a5c131f-cda7-4559-9788-d72a050aa303.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/quality.py` `analyze_rejection_rates` (lines 150-205) confirms three identical `if/elif` dispatch chains updating `overall`, `type_metrics`, and `month_metrics` respectively, each handling the same 5 categories (completed/rejected/invalid/duplicate/deferred). No `_update_rejection_metrics` helper exists. Enhancement not yet applied.
- **Date**: 2026-03-22
- **Verdict**: VALID
- Three dispatch chains confirmed at lines 157-166 (overall), 173-182 (type_metrics), 191-200 (month_metrics). Function definition at line 126. No `_update_rejection_metrics` helper exists. Lines have shifted slightly from 155-199 to ~157-200; enhancement not applied.
