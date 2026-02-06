---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-240: Consolidate duplicated work verification code

## Summary

`EXCLUDED_DIRECTORIES`, `filter_excluded_files()`, and `verify_work_was_done()` are duplicated across `git_operations.py` and `work_verification.py`. The two versions have already diverged (work_verification adds diagnostic logging). If the exclusion list is updated in one file but not the other, `ll-auto` and `ll-parallel` would use different exclusion lists.

## Location

- **File**: `scripts/little_loops/git_operations.py`
- **Line(s)**: 18-25, 202-274 (at scan commit: a8f4144)
- **Anchor**: `EXCLUDED_DIRECTORIES, filter_excluded_files, verify_work_was_done`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/git_operations.py#L18-L25)

- **File**: `scripts/little_loops/work_verification.py`
- **Line(s)**: 18-125 (at scan commit: a8f4144)
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/work_verification.py#L18-L125)

## Current Behavior

Two near-identical implementations with `work_verification.py` being the enhanced version. `issue_manager.py` imports from `git_operations`, `worker_pool.py` imports from `work_verification`.

## Expected Behavior

A single canonical definition in one module, with the other re-exporting for backward compatibility.

## Proposed Solution

Keep `work_verification.py` as the canonical source. In `git_operations.py`, remove duplicated definitions and re-export:
```python
from little_loops.work_verification import (
    EXCLUDED_DIRECTORIES,
    filter_excluded_files,
    verify_work_was_done,
)
```

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p3`

---

## Verification Notes

**Verified: 2026-02-06** — VALID (line numbers updated)

- `git_operations.py` line range corrected from `202-283` to `202-274`
- Divergence has increased since discovery: `work_verification.py` now includes detailed diagnostic logging for excluded files (lines 68-73, 92-93, 113-117) that the `git_operations.py` version completely lacks
- `EXCLUDED_DIRECTORIES` tuples remain identical in both files (lines 18-25)
- Core duplication confirmed and growing worse over time

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P3
