---
id: BUG-2120
title: "Fix capture-ordering ALLOWLIST for loop-composer and loop-composer-adaptive"
status: done
priority: P3
type: BUG
captured_at: "2026-06-13T20:10:14Z"
discovered_date: "2026-06-13"
discovered_by: capture-issue
---

# BUG-2120: Fix capture-ordering ALLOWLIST for loop-composer and loop-composer-adaptive

## Summary

`test_deterministic_warning_categories_do_not_regrow` was failing because the FSM validator newly detects that `validation_result` (captured in `validate_plan`) may not execute on all paths to `decompose_goal`. The first-pass path `discover_loops → decompose_goal` bypasses `validate_plan`, so `${captured.validation_result.output}` references a capture that may not exist yet. Both loops already used `:default=` in the template, making this Bucket B (safe). The ALLOWLIST in the test file was missing the new path entry.

## Root Cause

- **File**: `scripts/tests/test_builtin_loops.py`
- **Function**: `TestValidatorWarningBudget.ALLOWLIST`
- **Explanation**: The FSM validator's capture-ordering check was enhanced to detect reachability gaps. `loop-composer` and `loop-composer-adaptive` both reference `${captured.validation_result.output:default=(none — this is the first attempt)}` in `decompose_goal.action`. The `:default=` makes this safe at runtime (Bucket B), but `states.decompose_goal.action` was not listed in the ratchet ALLOWLIST entries for either loop, causing the test to fail.

## Fix

Added `"states.decompose_goal.action"` to the ALLOWLIST entries for `("loop-composer", "capture-ordering")` and `("loop-composer-adaptive", "capture-ordering")` in `scripts/tests/test_builtin_loops.py` (lines 7051–7058).

## Verification

```
pytest scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget::test_deterministic_warning_categories_do_not_regrow
# 1 passed in 7.98s
```

Full suite: **11328 passed, 7 skipped, 1 failed → 0 failed** after fix.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-13T20:10:39 - `0689c23b-e672-439e-9ad3-4d3ec529ef82.jsonl`
- `/ll:run-tests` + `/ll:capture-issue` - 2026-06-13T20:10:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

done
