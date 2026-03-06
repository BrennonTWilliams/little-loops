---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# BUG-605: Signal-shutdown exit code `1` indistinguishable from genuine failure

## Summary

`run_foreground` and `cmd_resume` return exit code `0` only for `terminated_by == "terminal"` and `1` for everything else — including `"signal"` (graceful user-initiated Ctrl-C). Scripts and CI pipelines cannot distinguish between a user-interrupted loop and a genuine failure.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 350 (at scan commit: c010880)
- **Anchor**: `in function run_foreground()`, final return
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/_helpers.py#L350)
- **Code**:
```python
return 0 if result.terminated_by == "terminal" else 1
```

Same pattern at `lifecycle.py:188` in `cmd_resume`.

## Current Behavior

Graceful signal shutdown returns exit code `1`, same as timeout or max_iterations exceeded.

## Expected Behavior

Different termination reasons should map to distinct exit codes (e.g., `0` for terminal, `0` for signal, `1` for max_iterations/timeout, `2` for error).

## Proposed Solution

Map `terminated_by` values to meaningful exit codes:
```python
EXIT_CODES = {"terminal": 0, "signal": 0, "max_iterations": 1, "timeout": 1, "handoff": 0}
return EXIT_CODES.get(result.terminated_by, 1)
```

## Impact

- **Priority**: P4 - Affects CI/scripting use cases, not interactive users
- **Effort**: Small - Mapping change in 2 locations
- **Risk**: Low - Only changes exit codes for non-terminal cases
- **Breaking Change**: No (scripts depending on exit code `1` for signal would see `0`)

## Labels

`bug`, `ll-loop`, `cli`

---

**Open** | Created: 2026-03-06 | Priority: P4
