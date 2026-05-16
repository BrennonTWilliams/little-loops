---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-252: Add --verbose flag to ll-auto

## Summary

`ll-auto` only has `--quiet` for reduced output, but no `--verbose` flag for debug-level output. Other tools like `ll-messages` and `ll-sprint list` have verbose flags. The `Logger` class supports a `verbose` parameter, but `ll-auto` only toggles between default and quiet.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 60-115 (at scan commit: a8f4144)
- **Anchor**: `in function main_auto`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L60-L115)

- **File**: `scripts/little_loops/cli_args.py`
- **Line(s)**: 162-173 (at scan commit: a8f4144)
- **Anchor**: `in function add_common_auto_args`

## Current Behavior

No way to enable debug-level output (detailed phase timings, dependency graphs, command previews).

## Expected Behavior

A `--verbose` flag that enables enhanced debug output.

## Proposed Solution

Add `add_verbose_arg(parser)` to `add_common_auto_args()` and pass `verbose=args.verbose` to the Logger constructor.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (Won't Fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4

**Closure reason**: Low value. Debug output adds maintenance surface. When debugging is truly needed, temporary print statements or a debugger work fine. Can be added on-demand if requested.
