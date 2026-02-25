---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-469: Split cli/sprint.py into subcommand modules

## Summary

Architectural issue found by `/ll:audit-architecture`. The `cli/sprint.py` module is 1,371 lines with 18 top-level functions handling all sprint CLI subcommands in a single file.

## Current Behavior

The module `scripts/little_loops/cli/sprint.py` (1,371 lines) contains 18 functions implementing all sprint CLI subcommands:
- `main_sprint` (entry point + argparse setup)
- `_cmd_sprint_create`, `_cmd_sprint_show`, `_cmd_sprint_edit`
- `_cmd_sprint_list`, `_cmd_sprint_delete`, `_cmd_sprint_analyze`
- `_cmd_sprint_run`
- `_render_execution_plan`, `_render_dependency_graph`, `_render_health_summary`, `_render_dependency_analysis`
- `_get_sprint_state_file`, `_load_sprint_state`, `_save_sprint_state`, `_cleanup_sprint_state`
- `_build_issue_contents`, `_sprint_signal_handler`

This mirrors the pattern used successfully in `cli/loop/` which splits its subcommands across `run.py`, `info.py`, `lifecycle.py`, `config_cmds.py`, and `testing.py`.

## Expected Behavior

Sprint CLI subcommands are split into focused modules within a `cli/sprint/` package, following the established `cli/loop/` pattern. Each subcommand handler lives in its own module, reducing file size and improving navigability.

## Motivation

This enhancement would:
- Improve development velocity: navigating 1,371 lines to find a specific subcommand handler is slow
- Reduce merge conflicts: changes to one subcommand risk conflicts with unrelated subcommand work
- Follow established patterns: `cli/loop/` already uses this package structure successfully

## Proposed Solution

Follow the existing `cli/loop/` package pattern:

1. Create `cli/sprint/` package directory
2. Create `cli/sprint/__init__.py` with `main_sprint` entry point and argparse setup
3. Create `cli/sprint/create.py` — `_cmd_sprint_create`
4. Create `cli/sprint/show.py` — `_cmd_sprint_show`, `_render_execution_plan`, `_render_dependency_graph`, `_render_health_summary`
5. Create `cli/sprint/edit.py` — `_cmd_sprint_edit`
6. Create `cli/sprint/run.py` — `_cmd_sprint_run`, signal handling (`_sprint_signal_handler`), state helpers (`_get_sprint_state_file`, `_load_sprint_state`, `_save_sprint_state`, `_cleanup_sprint_state`)
7. Create `cli/sprint/manage.py` — `_cmd_sprint_list`, `_cmd_sprint_delete`, `_cmd_sprint_analyze`
8. Create `cli/sprint/helpers.py` — `_build_issue_contents`, `_render_dependency_analysis`
8. Update `cli/__init__.py` imports

## Scope Boundaries

- **In scope**: Splitting `cli/sprint.py` into a `cli/sprint/` package with subcommand modules; updating imports
- **Out of scope**: Refactoring subcommand logic, adding new subcommands, changing CLI interface or argument parsing

## Implementation Steps

1. Create `cli/sprint/` package directory with `__init__.py`
2. Move entry point and argparse setup to `__init__.py`
3. Create subcommand modules and move functions to respective files
4. Update internal imports between modules
5. Update `cli/__init__.py` to import from new package
6. Run tests to verify no breakage

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — split into package

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py` — imports `main_sprint`
- TBD - use grep to find additional references: `grep -r "from.*cli.sprint import\|cli\.sprint\." scripts/`

### Similar Patterns
- `cli/loop/` package — established pattern with `run.py`, `info.py`, `lifecycle.py`, `config_cmds.py`, `testing.py`

### Tests
- `scripts/tests/` — existing sprint CLI tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Moderate maintenance burden from 1,371-line single file
- **Effort**: Medium — Follows established `cli/loop/` pattern
- **Risk**: Low — Internal restructure, entry point unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected line count (1,371); removed non-existent `_cmd_sprint_run_wave`; updated function list to match actual codebase

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
