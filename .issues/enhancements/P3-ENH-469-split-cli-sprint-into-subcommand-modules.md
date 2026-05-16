---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 100
outcome_confidence: 78
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
4. Create `cli/sprint/show.py` — `_cmd_sprint_show`, `_render_dependency_graph`, `_render_health_summary`
5. Create `cli/sprint/edit.py` — `_cmd_sprint_edit`
6. Create `cli/sprint/run.py` — `_cmd_sprint_run`, signal handling (`_sprint_signal_handler`), module-level flag `_sprint_shutdown_requested: bool = False` (`sprint.py:37`), state helpers (`_get_sprint_state_file`, `_load_sprint_state`, `_save_sprint_state`, `_cleanup_sprint_state`)
7. Create `cli/sprint/manage.py` — `_cmd_sprint_list`, `_cmd_sprint_delete`, `_cmd_sprint_analyze`
8. Create `cli/sprint/_helpers.py` — `_build_issue_contents`, `_render_dependency_analysis`, `_render_execution_plan` (shared by `show.py`, `manage.py`; follows `cli/loop/_helpers.py` naming convention)
9. Update `cli/__init__.py:23-28` to import `_render_*` functions from their new submodule locations; re-export them from `cli/sprint/__init__.py` so `from little_loops.cli.sprint import _render_*` still resolves

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Function locations in `scripts/little_loops/cli/sprint.py`:**
| Function | Lines | Target Module |
|---|---|---|
| `_sprint_signal_handler` | 40–52 | `run.py` |
| `main_sprint` | 55–207 | `__init__.py` |
| `_cmd_sprint_create` | 210–263 | `create.py` |
| `_render_execution_plan` | 266–387 | `_helpers.py` (shared by show.py + manage.py) |
| `_render_dependency_graph` | 390–458 | `show.py` |
| `_render_health_summary` | 461–515 | `show.py` |
| `_cmd_sprint_show` | 518–616 | `show.py` |
| `_cmd_sprint_edit` | 619–734 | `edit.py` |
| `_cmd_sprint_list` | 737–757 | `manage.py` |
| `_cmd_sprint_delete` | 760–768 | `manage.py` |
| `_cmd_sprint_analyze` | 771–917 | `manage.py` |
| `_get_sprint_state_file` | 920–922 | `run.py` |
| `_load_sprint_state` | 925–939 | `run.py` |
| `_save_sprint_state` | 942–950 | `run.py` |
| `_cleanup_sprint_state` | 953–958 | `run.py` |
| `_build_issue_contents` | 961–963 | `_helpers.py` |
| `_render_dependency_analysis` | 966–1042 | `_helpers.py` |
| `_cmd_sprint_run` | 1045–1371 | `run.py` |

**Module-level mutable state** (`sprint.py:37`): `_sprint_shutdown_requested: bool = False` — must move with `run.py`; read/reset by `_cmd_sprint_run` at lines 1056–1057, 1209, 1248, 1338.

**Key implementation rule from `cli/loop/` pattern**: Deferred submodule imports inside `main_sprint()` body (not at module top-level in `__init__.py`). See `cli/loop/__init__.py:19-23`.

**Critical test update required**: `test_sprint_integration.py` uses 9 `monkeypatch("little_loops.cli.sprint.ParallelOrchestrator", ...)` calls (lines 316, 393, 458, 573, 775, 834, 897, 962, 1232). After moving `_cmd_sprint_run` to `run.py`, update to `"little_loops.cli.sprint.run.ParallelOrchestrator"`.

**`cli/__init__.py:23-28` re-export update**: After split, `cli/sprint/__init__.py` must re-export `_render_execution_plan` (from `_helpers.py`), `_render_dependency_graph`, `_render_health_summary` (from `show.py`) so that `cli/__init__.py` can continue to import them from `little_loops.cli.sprint`.

**Module import pattern**: All submodule-to-helper imports use absolute paths, not relative. E.g., `from little_loops.cli.sprint._helpers import _build_issue_contents` — not `from ._helpers import ...`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — split into package

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:23-28` — imports `main_sprint`, `_render_execution_plan`, `_render_dependency_graph`, `_render_health_summary` from `cli.sprint`; re-exports all four in `__all__` (render functions annotated "for backward compatibility (used in tests)")
- `scripts/tests/test_cli.py:935,985,1245` — imports render functions via `from little_loops.cli import _render_*`; stays valid after split if `cli/sprint/__init__.py` re-exports them
- `scripts/tests/test_sprint_integration.py` — **9 monkeypatch locations** using `"little_loops.cli.sprint.ParallelOrchestrator"` (lines 316, 393, 458, 573, 775, 834, 897, 962, 1232); after moving `_cmd_sprint_run` to `run.py`, these must change to `"little_loops.cli.sprint.run.ParallelOrchestrator"`
- `scripts/tests/test_sprint.py` — imports `main_sprint` via `from little_loops.cli import main_sprint`; unchanged after split

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py:1-194` — entry point pattern: all submodule imports deferred inside `main_loop()` body (e.g., `from little_loops.cli.loop.run import cmd_run`), not at module top-level
- `scripts/little_loops/cli/loop/_helpers.py:1-209` — shared utilities module: underscore-prefixed, uses `TYPE_CHECKING` guard for annotations, heavy imports deferred inside function bodies
- `scripts/little_loops/cli/loop/lifecycle.py:8-9` — submodule import pattern: absolute paths (`from little_loops.cli.loop._helpers import load_loop`); no relative imports; no cross-submodule imports
- `scripts/tests/test_cli_loop_lifecycle.py:9` — test file convention: imports directly from submodule (`from little_loops.cli.loop.lifecycle import cmd_status, cmd_stop, cmd_resume`)

### Tests
- `scripts/tests/test_sprint.py` — unit tests for `_sprint_signal_handler`, `_sprint_shutdown_requested`, and `main_sprint` entry point
- `scripts/tests/test_sprint_integration.py` — integration tests; 9 monkeypatch paths need updating to `"little_loops.cli.sprint.run.ParallelOrchestrator"` (see Dependent Files above)
- `scripts/tests/test_cli.py` — `TestSprintArgumentParsing` (~line 743), `TestMainSprintAdditionalCoverage` (~line 2098); imports render functions via `little_loops.cli`

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

## Resolution

**Status**: Completed | **Date**: 2026-02-24

### Changes Made

1. Created `scripts/little_loops/cli/sprint/` package with 6 submodules:
   - `__init__.py` — `main_sprint` entry point + argparse setup; re-exports all public symbols for backward compatibility
   - `_helpers.py` — `_render_execution_plan`, `_build_issue_contents`, `_render_dependency_analysis`
   - `create.py` — `_cmd_sprint_create`
   - `show.py` — `_render_dependency_graph`, `_render_health_summary`, `_cmd_sprint_show`
   - `edit.py` — `_cmd_sprint_edit`
   - `manage.py` — `_cmd_sprint_list`, `_cmd_sprint_delete`, `_cmd_sprint_analyze`
   - `run.py` — `_sprint_shutdown_requested`, `_sprint_signal_handler`, state helpers, `_cmd_sprint_run`

2. Deleted `scripts/little_loops/cli/sprint.py` (1,371 lines)

3. Updated `scripts/tests/test_sprint_integration.py` — 9 monkeypatch paths updated from `"little_loops.cli.sprint.ParallelOrchestrator"` to `"little_loops.cli.sprint.run.ParallelOrchestrator"`

4. Updated `scripts/tests/test_sprint.py` — `TestSprintSignalHandler` and `TestSprintErrorHandling` classes updated to import from `little_loops.cli.sprint.run`

5. Updated `scripts/tests/test_cli.py` — `TestSprintSignalHandler.setup_class` updated to import from `little_loops.cli.sprint.run`

### Verification

- All 2868 tests pass (excluding integration tests marked with `pytest.mark.integration`)
- Lint: clean (`ruff check` passes)
- Types: clean (`mypy` passes)
- `cli/__init__.py` unchanged — imports from `little_loops.cli.sprint` continue to resolve via package `__init__.py`

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Corrected line count (1,371); removed non-existent `_cmd_sprint_run_wave`; updated function list to match actual codebase
- `/ll:refine-issue` - 2026-02-24 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f35ef8a-9e6a-4cf8-a08e-95c55686681b.jsonl`
- `/ll:manage-issue` - 2026-02-24 - Implemented split; all tests green

---

## Status

**Completed** | Created: 2026-02-24 | Priority: P3
