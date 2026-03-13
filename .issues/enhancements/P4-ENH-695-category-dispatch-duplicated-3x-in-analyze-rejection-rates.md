---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-695: Category dispatch logic duplicated 3x in `analyze_rejection_rates`

## Summary

In `analyze_rejection_rates`, the same 5-branch `if/elif` chain (completed/rejected/invalid/duplicate/deferred) appears three times — once each for `overall`, `type_metrics`, and `month_metrics` `RejectionMetrics` instances. The three copies are structurally identical, differing only in the target object.

## Location

- **File**: `scripts/little_loops/issue_history/quality.py`
- **Line(s)**: 155-199 (at scan commit: 3e9beea)
- **Anchor**: `in function analyze_rejection_rates()`

## Current Behavior

Three identical `if/elif` dispatch chains, each updating a different `RejectionMetrics` instance with the same category-to-field mapping.

## Expected Behavior

A single helper function `_update_rejection_metrics(metrics: RejectionMetrics, category: str)` encapsulates the dispatch, and each of the three sites calls it.

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
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
