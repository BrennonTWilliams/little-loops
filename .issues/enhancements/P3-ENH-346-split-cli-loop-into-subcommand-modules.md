---
discovered_commit: be30013
discovered_branch: main
discovered_date: 2026-02-12
discovered_by: audit_architecture
focus_area: large-files
---

# ENH-346: Split cli/loop.py into subcommand modules

## Summary

Architectural issue found by `/ll:audit_architecture`. The `cli/loop.py` file has grown to 1,034 lines, containing all `ll-loop` subcommand handlers in a single file.

## Location

- **File**: `scripts/little_loops/cli/loop.py`
- **Line(s)**: 1-1034 (entire file)
- **Module**: `little_loops.cli.loop`

## Finding

### Current State

`cli/loop.py` contains the CLI entry point and all subcommand handlers (run, show, list, validate, etc.) in one file. As more subcommands are added, this file will continue to grow.

### Impact

- **Development velocity**: Harder to navigate and find specific subcommand logic
- **Maintainability**: Multiple concerns in one file increases merge conflict risk
- **Risk**: Low — functional but growing

## Proposed Solution

Extract subcommand handlers into a `cli/loop/` package with separate modules per subcommand group.

### Suggested Approach

1. Convert `cli/loop.py` to `cli/loop/__init__.py` (keep `main_loop` entry point)
2. Extract subcommand handlers into separate modules (e.g., `cli/loop/run.py`, `cli/loop/show.py`)
3. Keep shared argument parsing in `__init__.py` or a `cli/loop/args.py`

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
