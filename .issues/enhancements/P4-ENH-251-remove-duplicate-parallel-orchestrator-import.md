---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-251: Remove duplicate ParallelOrchestrator import

## Summary

`ParallelOrchestrator` is imported at module level on line 37 from `little_loops.parallel.orchestrator`, and again on line 273 inside `main_parallel()` from `little_loops.parallel`. The second import is unnecessary and uses a different import path.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 37, 273 (at scan commit: a8f4144)
- **Anchor**: `top-level imports and main_parallel function`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L37)

## Current Behavior

Duplicate import using different paths.

## Expected Behavior

Single import at module level; remove the local import on line 273.

## Proposed Solution

Remove line 273 (`from little_loops.parallel import ParallelOrchestrator`).

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P4
