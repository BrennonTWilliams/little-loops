---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "Cosmetic polish with minimal user impact. The function works — it just shows '185.3 minutes' instead of '3h 5m'. This is a minor readability improvement for a log message that appears once at the end of a long run. Not worth tracking as a standalone issue."
---

# ENH-250: format_duration handle hours and days

## Summary

The `format_duration()` utility only distinguishes between seconds and minutes. For long-running automation (sprints, parallel processing), this produces awkward output like "185.3 minutes" instead of "3h 5m".

## Location

- **File**: `scripts/little_loops/logger.py`
- **Line(s)**: 92-103 (at scan commit: a8f4144)
- **Anchor**: `in function format_duration`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/logger.py#L92-L103)
- **Code**:
```python
def format_duration(seconds: float) -> str:
    if seconds >= 60:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds:.1f} seconds"
```

## Current Behavior

Only formats as seconds or minutes.

## Expected Behavior

Should handle hours (and optionally days) for readability.

## Proposed Solution

```python
def format_duration(seconds: float) -> str:
    if seconds >= 3600:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if minutes:
            return f"{hours}h {minutes}m"
        return f"{hours}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} minutes"
    return f"{seconds:.1f} seconds"
```

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4
