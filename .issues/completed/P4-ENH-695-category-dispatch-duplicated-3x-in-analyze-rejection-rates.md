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

In `analyze_rejection_rates`, the same 5-branch `if/elif` dispatch chain (completed/rejected/invalid/duplicate/deferred) appears three times — once each for `overall`, `type_metrics`, and `month_metrics` `RejectionMetrics` instances. Note: `total_closed += 1` is a separate counter at each call site and is NOT part of the dispatch; the helper covers category-to-field mapping only.

## Motivation

Three copies of the dispatch block (10 lines each) in the same function make it easy to update two copies and miss the third. The blocks have already drifted: `completed` is the first `elif` branch in `overall` (line 157) but last in `type_metrics` and `month_metrics` (lines 182, 200), proving they evolved independently. Extracting a dispatch-only helper enforces a single source of truth for the category-to-field mapping and makes each call site intent clear. The `total_closed += 1` counter remains at each call site, preserving the existing semantics (including the `by_month` guard at line 185 that correctly excludes undated issues).

## Location

- **File**: `scripts/little_loops/issue_history/quality.py`
- **Line(s)**: 155-199 (at scan commit: 3e9beea)
- **Anchor**: `in function analyze_rejection_rates()`

## Current Behavior

Three copies of the 5-branch `if/elif` dispatch chain (lines 157-166, 173-182, 191-200), each updating a different `RejectionMetrics` instance. The `total_closed += 1` counter is separate and adjacent at each site (lines 154, 172, 190).

## Expected Behavior

A single helper function `_update_rejection_metrics(metrics: RejectionMetrics, category: str) -> None` encapsulates the category-to-field dispatch only. Each of the three dispatch blocks is replaced by a call to the helper. `total_closed += 1` remains at each call site unchanged:

```python
overall.total_closed += 1
_update_rejection_metrics(overall, category)

type_metrics.total_closed += 1
_update_rejection_metrics(type_metrics, category)

if issue.completed_date:
    ...
    month_metrics.total_closed += 1
    _update_rejection_metrics(month_metrics, category)
```

## Implementation Steps

1. In `quality.py`, add `_update_rejection_metrics(metrics: RejectionMetrics, category: str) -> None` before `analyze_rejection_rates` (before line 126). Body: the 5-branch `if/elif` dispatch from lines 157-166, with `metrics` as the target.
2. Replace dispatch block 1 (lines 157-166, `overall`) with `_update_rejection_metrics(overall, category)`. Leave `overall.total_closed += 1` at line 154 untouched.
3. Replace dispatch block 2 (lines 173-182, `type_metrics`) with `_update_rejection_metrics(type_metrics, category)`. Leave `type_metrics.total_closed += 1` at line 172 untouched.
4. Replace dispatch block 3 (lines 191-200, `month_metrics`) with `_update_rejection_metrics(month_metrics, category)`. Leave `month_metrics.total_closed += 1` at line 190 inside the `if issue.completed_date:` guard untouched.
5. Run `python -m pytest` to verify identical output.

## Integration Map

- **Modified**: `scripts/little_loops/issue_history/quality.py` — `analyze_rejection_rates()` (lines 157-200)
- **New helper**: `_update_rejection_metrics()` (private, same file, dispatch-only — does not touch `total_closed`)

## Scope Boundaries

- Extract dispatch-only helper; `total_closed += 1` stays at each call site
- Do not change the public interface of `analyze_rejection_rates`
- Do not change `RejectionMetrics` dataclass

## Impact

- **Priority**: P4 - Code cleanliness, reduces maintenance burden
- **Effort**: Small - Extract helper, replace 3 dispatch blocks
- **Risk**: Low - Pure refactoring
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `issue-history`

## Session Log
- `/ll:ready-issue` - 2026-03-23T01:35:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2281d203-9afd-4a20-9f62-e801643ffa71.jsonl`
- `/ll:verify-issues` - 2026-03-23T00:58:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a5c131f-cda7-4559-9788-d72a050aa303.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:go-no-go` - 2026-03-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32ecea2a-1500-47d2-b541-9fa9644d4549.jsonl`

---

**Completed** | Created: 2026-03-13 | Priority: P4

## Resolution

- **Action**: improve
- **Date**: 2026-03-22
- **Outcome**: Extracted `_update_rejection_metrics(metrics, category)` helper (quality.py:126) and replaced three 5-branch dispatch blocks with single-line calls. `total_closed += 1` left at each call site. All 3841 tests pass.

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/issue_history/quality.py` `analyze_rejection_rates` (lines 150-205) confirms three identical `if/elif` dispatch chains updating `overall`, `type_metrics`, and `month_metrics` respectively, each handling the same 5 categories (completed/rejected/invalid/duplicate/deferred). No `_update_rejection_metrics` helper exists. Enhancement not yet applied.
- **Date**: 2026-03-22
- **Verdict**: VALID
- Three dispatch chains confirmed at lines 157-166 (overall), 173-182 (type_metrics), 191-200 (month_metrics). Function definition at line 126. No `_update_rejection_metrics` helper exists. Lines have shifted slightly from 155-199 to ~157-200; enhancement not applied.
