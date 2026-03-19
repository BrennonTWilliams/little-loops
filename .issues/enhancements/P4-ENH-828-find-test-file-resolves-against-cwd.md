---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 85
---

# ENH-828: `_find_test_file` resolves paths against process CWD

## Summary

`_find_test_file` in `parsing.py` checks file existence using `Path(candidate).exists()`, which resolves relative to the process working directory. When invoked from different directories (e.g., from within a worktree or subprocess), results are inconsistent.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 317-320 (at scan commit: 8c6cf90)
- **Anchor**: `in function _find_test_file`
- **Code**:
```python
for candidate in candidates:
    if Path(candidate).exists():   # relative to CWD, not project root
        return candidate
```

## Current Behavior

File existence checks are resolved against the Python process's CWD, not the project root. Results depend on where the process was started.

## Expected Behavior

Existence checks should be anchored to the project root path for consistent results regardless of invocation context.

## Motivation

`_find_test_file` is called from `analyze_test_gaps` which runs as part of `ll-history analyze`. When invoked from worktrees or automation contexts, the CWD may differ from the project root.

## Proposed Solution

Add an optional `project_root: Path | None = None` parameter to `_find_test_file`. When provided, resolve candidates via `(project_root / candidate).exists()`. Update call sites in `quality.py` to pass the project root from config.

## Scope Boundaries

- Out of scope: Changing how candidate paths are generated
- Out of scope: Making project_root required (preserve backward compatibility)

## Impact

- **Priority**: P4 - Correctness issue in specific invocation contexts
- **Effort**: Small - Add parameter, update two call sites
- **Risk**: Low - Backward compatible with optional parameter
- **Breaking Change**: No

## Labels

`enhancement`, `issue-history`, `correctness`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verdict**: VALID — Issue accurately describes the current state of the codebase.

**Verified**: 2026-03-19

- `scripts/little_loops/issue_history/parsing.py` exists ✓
- `_find_test_file` at line 278 has no `project_root` parameter ✓
- Loop at lines 318-320 uses `Path(candidate).exists()` without anchoring to project root ✓ (issue states 317-320; shifted by 1 line since scan commit `8c6cf90`, but code is identical)
- Call sites in `quality.py` at lines 64 and 108 still pass no project root argument ✓
- Enhancement remains unimplemented

## Session Log
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:40:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
