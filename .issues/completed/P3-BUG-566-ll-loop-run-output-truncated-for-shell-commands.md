---
id: BUG-566
type: BUG
priority: P3
status: completed
title: ll-loop run output truncated for shell command actions
created: 2026-03-04
completed: 2026-03-04
---

# BUG-566: ll-loop run output truncated for shell command actions

## Summary

`ll-loop run issue-refinement` showed only 1 line of output for shell command actions (e.g., `ll-issues refine-status`), and that line was from the "Key:" legend at the bottom — not the table data. BUG-564 fixed prompt actions but left shell commands broken.

## Root Cause

Two compounding issues:

1. **`fsm/executor.py:527`** — `output[-500:]` captured the *last* 500 chars. For `ll-issues refine-status` (6210 chars total), this was the "Key:" legend section, not the issue table.

2. **`cli/loop/_helpers.py:253-257`** — For non-prompt shell commands, only the **last single line** of the preview was displayed. BUG-564 had improved prompts to show 3 lines but left shell commands at 1.

## Symptoms

```
[1/100] evaluate (0s) -> ll-issues refine-status
       (0.1s)
       ...  total        Number of /ll:* skills applied
```

The displayed line was a column key description — completely useless for understanding loop state.

## Fix

**`scripts/little_loops/fsm/executor.py`**
- Changed `output[-500:].strip()` → `output[:2000].strip()` to capture from the start where table/report data appears.

**`scripts/little_loops/cli/loop/_helpers.py`**
- Changed shell command display from 1 last line to last 8 lines (matching the style used for prompt actions at 3 lines, but more generous for tabular output).

## Files Changed

- `scripts/little_loops/fsm/executor.py`
- `scripts/little_loops/cli/loop/_helpers.py`

## Related

- Follows BUG-564 (ll-loop run output too sparse for prompt actions)
