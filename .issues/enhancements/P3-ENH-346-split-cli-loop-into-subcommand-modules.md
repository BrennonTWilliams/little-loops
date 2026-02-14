---
discovered_commit: be30013
discovered_branch: main
discovered_date: 2026-02-12
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-346: Split cli/loop.py into subcommand modules

## Summary

Architectural issue found by `/ll:audit-architecture`. The `cli/loop.py` file has grown to 1,034 lines, containing all `ll-loop` subcommand handlers in a single file.

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

## Motivation

This enhancement would:
- Improve maintainability by splitting a 1,034-line monolithic file into focused subcommand modules
- Business value: Reduced merge conflict risk and faster navigation when working on individual subcommands
- Technical debt: Prevents the file from growing further as new subcommands are added

## Implementation Steps

1. **Create cli/loop/ package directory**: Convert `scripts/little_loops/cli/loop.py` to `scripts/little_loops/cli/loop/__init__.py`
2. **Extract subcommand handlers**: Move subcommand handlers into separate modules (e.g., `cli/loop/run.py`, `cli/loop/show.py`, `cli/loop/list.py`)
3. **Keep shared logic in __init__.py**: Retain `main_loop` entry point and shared argument parsing in `__init__.py` or a dedicated `cli/loop/args.py`
4. **Update imports**: Ensure all internal and external imports resolve correctly after the restructure
5. **Run tests**: Execute full test suite to verify no regressions from the module split

## Integration Map

- **Files to Modify**: `scripts/little_loops/cli/loop.py` (split into `scripts/little_loops/cli/loop/` package)
- **Dependent Files (Callers/Importers)**: `scripts/little_loops/cli/__init__.py` (registers loop CLI), `pyproject.toml` (entry points)
- **Similar Patterns**: ENH-390 (split issue_history module into package — same restructuring pattern)
- **Tests**: `scripts/tests/test_loop_runner.py` — update imports to resolve against new package structure
- **Documentation**: `docs/ARCHITECTURE.md` — update module structure for cli/loop package
- **Configuration**: N/A

## Impact Assessment

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

## Blocked By

_None_

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue --all --auto` - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- **Line count**: Now 1,036 lines (was 1,034 at discovery — grew by 2 lines). Core issue still valid.
- **12 subcommands confirmed**: `cmd_run`, `cmd_compile`, `cmd_validate`, `cmd_list`, `cmd_install`, `cmd_status`, `cmd_stop`, `cmd_resume`, `cmd_history`, `cmd_test`, `cmd_simulate`, `cmd_show`
- **Spurious dependency**: Blocked By ENH-390 citing "shared `__init__.py`" appears incorrect — `issue_history/` and `cli/loop/` are entirely different packages with no shared `__init__.py`. Recommend removing this blocker.

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
