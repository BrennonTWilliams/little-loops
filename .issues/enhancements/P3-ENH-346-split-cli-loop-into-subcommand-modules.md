---
discovered_commit: be30013
discovered_branch: main
discovered_date: 2026-02-12
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-346: Split cli/loop.py into subcommand modules

## Summary

Architectural issue found by `/ll:audit-architecture`. The `cli/loop.py` file has grown to 1,036 lines, containing all 12 `ll-loop` subcommand handlers in a single file.

## Current Behavior

`scripts/little_loops/cli/loop.py` (1,036 lines) contains the CLI entry point (`main_loop`) and all 12 subcommand handlers (`cmd_run`, `cmd_compile`, `cmd_validate`, `cmd_list`, `cmd_install`, `cmd_status`, `cmd_stop`, `cmd_resume`, `cmd_history`, `cmd_test`, `cmd_simulate`, `cmd_show`) in a single monolithic file. As more subcommands are added, this file will continue to grow.

## Expected Behavior

Subcommand handlers should be split into a `cli/loop/` package with separate modules per subcommand group, improving navigability and reducing merge conflict risk. The `main_loop` entry point should remain in `__init__.py`.

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
- **Similar Patterns**: ENH-390 (completed — split issue_history module into package; use as reference for same restructuring pattern)
- **Tests**: No dedicated test file for `cli/loop.py` exists; run full test suite to verify no regressions
- **Documentation**: `docs/ARCHITECTURE.md` — update module structure for cli/loop package
- **Configuration**: N/A

## Scope Boundaries

- Only `scripts/little_loops/cli/loop.py` is in scope — no changes to loop execution logic (`loop_runner.py`, `loop_compiler.py`, etc.)
- Entry point signature (`main_loop`) must remain unchanged for `pyproject.toml` compatibility
- No behavioral changes — purely structural refactoring

## Impact

- **Priority**: P3 — Code health improvement, not blocking any features
- **Effort**: Small — Mechanical file moves and import updates; ENH-390 provides a completed reference
- **Risk**: Low — No behavioral changes, just structural reorganization
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

## Resolution

- **Action**: improve
- **Date**: 2026-02-14
- **Result**: Split 1,037-line `cli/loop.py` into 7-module `cli/loop/` package

### Changes Made
- Deleted `scripts/little_loops/cli/loop.py` (1,037 lines)
- Created `scripts/little_loops/cli/loop/__init__.py` — entry point + argparse + dispatch (~170 lines)
- Created `scripts/little_loops/cli/loop/_helpers.py` — shared utilities (~170 lines)
- Created `scripts/little_loops/cli/loop/run.py` — run subcommand (~85 lines)
- Created `scripts/little_loops/cli/loop/config_cmds.py` — compile, validate, install (~130 lines)
- Created `scripts/little_loops/cli/loop/lifecycle.py` — status, stop, resume (~115 lines)
- Created `scripts/little_loops/cli/loop/info.py` — list, history, show (~215 lines)
- Created `scripts/little_loops/cli/loop/testing.py` — test, simulate (~200 lines)
- Updated `docs/ARCHITECTURE.md` — module tree structure

### Verification
- 2744 tests passed (0 failures)
- Linting: All checks passed
- Type checking: No issues found in 7 source files
- No changes to external imports — backward compatible via `__init__.py`

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-14 | Priority: P3
