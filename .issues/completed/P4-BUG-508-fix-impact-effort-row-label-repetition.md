---
discovered_date: 2026-02-25
discovered_by: manual
focus_area: cli
---

# BUG-508: Fix ll-issues impact-effort matrix row label repetition

## Summary

The `ll-issues impact-effort` command rendered "IMPACT" on every row of the top half of the 2×2 ASCII matrix instead of only the first row.

## Current Behavior

```
High IMPACT │ ★ QUICK WINS  │ ▲ MAJOR PROJECTS  │
     IMPACT │ (none)         │ ENH-498  ...       │
     IMPACT │               │ ENH-481  ...        │
```

"IMPACT" repeated on every non-first row of the top half.

## Root Cause

In `scripts/little_loops/cli/issues/impact_effort.py` (lines 120–122), the format string embedded the literal ` IMPACT ` text unconditionally:

```python
impact_label = "High" if i == 0 else "    "
out.append(f"{impact_label} IMPACT {v} {tl_line} {v} {tr_line} {v}")
```

When `i > 0`, `impact_label` became `"    "` (4 spaces) but ` IMPACT ` was still appended. The bottom half avoided this by using 8 spaces instead of the word, but also lacked the "IMPACT" label entirely on its first row.

## Fix

Replaced the label logic so the full 12-character label string is built once per row, rather than composing a prefix with an always-present literal:

```python
# Top half
row_label = "High IMPACT " if i == 0 else " " * 12

# Bottom half
row_label = "Low  IMPACT " if i == 0 else " " * 12
```

Both labels are 12 characters, preserving column alignment. The bottom half now also correctly shows "Low  IMPACT" on its first row.

## Expected Behavior

```
High IMPACT │ ★ QUICK WINS  │ ▲ MAJOR PROJECTS  │
            │ (none)         │ ENH-498  ...       │
            │               │ ENH-481  ...        │
...
Low  IMPACT │ ⚡ FILL-INS    │ ✗ THANKLESS TASKS  │
```

## Files Changed

- `scripts/little_loops/cli/issues/impact_effort.py` — 4 lines modified (lines 120–122, 124–126)

## Verification

- `python -m pytest scripts/tests/ -k impact` — 20 passed, 0 failures

## Resolution

**Fixed** — Row label construction moved to a single variable per row; literal "IMPACT" removed from format string.

## Session Log

- Manual fix — 2026-02-25

---

## Status

**Completed** | Created: 2026-02-25 | Resolved: 2026-02-25 | Priority: P4
