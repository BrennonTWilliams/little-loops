---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 71
---

# ENH-692: "Contents dict or read" guard pattern duplicated 10+ times across issue_history

## Summary

The 4-line pattern `if contents is not None and issue.path in contents: content = contents[issue.path] else: try: content = issue.path.read_text(...) except: continue` appears identically in at least 10 locations across `issue_history/` sub-modules.

## Motivation

10+ identical code blocks across 5 files creates significant maintenance burden: any bug fix or behavioral change must be applied to each copy. A single extracted helper reduces this to one authoritative location and makes the intent clearer at each call site. There is no shared helper for this lookup-or-read operation.

## Location

- **File**: `scripts/little_loops/issue_history/hotspots.py` (lines 33-40)
- **File**: `scripts/little_loops/issue_history/coupling.py` (lines 35-42)
- **File**: `scripts/little_loops/issue_history/regressions.py` (lines 42-53, uses `bug.path` variable name)
- **File**: `scripts/little_loops/issue_history/debt.py` (lines 82-89, 170-177, 286-293)
- **File**: `scripts/little_loops/issue_history/quality.py` (lines 144-150, 312-318)
- **File**: `scripts/little_loops/issue_history/summary.py` (lines 226-232)
- **Anchor**: Multiple functions: `analyze_hotspots`, `analyze_coupling`, `analyze_regression_clustering`, etc.

## Current Behavior

Every analysis function that accepts the optional `contents` cache dict re-implements the same fallback logic inline — check cache, read file, or skip on error.

## Expected Behavior

A single utility function encapsulates the pattern, e.g.:

```python
def get_issue_content(
    issue: CompletedIssue, contents: dict[Path, str] | None
) -> str | None:
    if contents is not None and issue.path in contents:
        return contents[issue.path]
    try:
        return issue.path.read_text(encoding="utf-8")
    except Exception:
        return None
```

Callers replace the 4-line block with `content = get_issue_content(issue, contents); if content is None: continue`.

## Implementation Steps

1. Add `get_issue_content(issue: CompletedIssue, contents: dict[Path, str] | None) -> str | None` to a shared utility module in `issue_history/` (e.g., `_utils.py`)
2. Replace the 4-line inline block at each of the 10+ call sites with `content = get_issue_content(issue, contents); if content is None: continue`
3. Run `python -m pytest` to verify no behavioral changes

## Integration Map

- **New helper**: `scripts/little_loops/issue_history/_utils.py` — `get_issue_content()`
- **Modified (10+ call sites)**: `hotspots.py` (lines 33-40), `coupling.py` (lines 35-42), `regressions.py` (lines 42-53), `debt.py` (lines 82-89, 170-177, 286-293), `quality.py` (lines 144-150, 312-318), `summary.py` (lines 226-232)

## Scope Boundaries

- Extract helper only; no behavior change
- Does not change the `contents` parameter interface on any public function

## Impact

- **Priority**: P3 - Reduces maintenance burden across 10+ call sites
- **Effort**: Medium - Extract helper, update all 10+ call sites, verify tests pass
- **Risk**: Low - Pure refactoring with identical behavior
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `issue-history`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- Confirmed: `issue_history/hotspots.py` has the `if contents is not None and issue.path in contents:` pattern at lines 33-34. `coupling.py` also confirmed. All referenced files (`hotspots.py`, `coupling.py`, `regressions.py`, `debt.py`, `quality.py`, `summary.py`) exist in `scripts/little_loops/issue_history/`. No `_utils.py` helper exists yet.

## Session Log
- `/ll:ready-issue` - 2026-03-15T00:08:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e413ad25-7f0a-43dd-be63-082cfcddd03e.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

## Resolution

- **Action**: completed
- **Date**: 2026-03-14
- **Summary**: Extracted `get_issue_content()` helper to `issue_history/_utils.py` and replaced all 10 inline duplicates across 6 files with a single call.

### Changes Made
- Created `scripts/little_loops/issue_history/_utils.py` with `get_issue_content(issue, contents) -> str | None`
- Updated `hotspots.py` (1 site), `coupling.py` (1 site), `regressions.py` (1 site), `debt.py` (3 sites), `quality.py` (2 sites), `summary.py` (1 site)
- All 221 issue_history tests pass

---

**Completed** | Created: 2026-03-13 | Priority: P3
