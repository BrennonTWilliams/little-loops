---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: large-files
---

# ENH-344: Split cli.py into cli/ package

## Summary

Architectural issue found by `/ll:audit-architecture`. The cli.py module is a god module containing 2,624 lines with 9 different CLI entry points, violating the Single Responsibility Principle.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Lines**: 1-2624 (entire file)
- **Module**: `little_loops.cli`

## Current Behavior

cli.py contains 9 CLI entry points in a single file:
- `main_auto()` - ll-auto command
- `main_parallel()` - ll-parallel command
- `main_messages()` - ll-messages command
- `main_loop()` - ll-loop command
- `main_sprint()` - ll-sprint command (with many helpers)
- `main_history()` - ll-history command
- `main_sync()` - ll-sync command
- `main_verify_docs()` - documentation verification
- `main_check_links()` - link checking

The module has high coupling (15 internal imports) and is difficult to maintain and test due to its size.

## Expected Behavior

cli.py should be split into a `cli/` package with one module per CLI command, each self-contained with its own imports and helper functions. The public API remains unchanged via `cli/__init__.py` re-exports.

## Proposed Solution

Split cli.py into a cli/ package with separate modules per command:

```
cli/
├── __init__.py (exports all entry points)
├── auto.py (main_auto)
├── parallel.py (main_parallel)
├── messages.py (main_messages)
├── loop.py (main_loop)
├── sprint.py (main_sprint + sprint helper functions)
├── history.py (main_history)
├── sync.py (main_sync)
└── docs.py (main_verify_docs, main_check_links)
```

### Suggested Approach

1. **Create cli/ package directory**
   ```bash
   mkdir scripts/little_loops/cli
   ```

2. **Extract each CLI command to its own module**
   - Move `main_auto` and related args to `cli/auto.py`
   - Move `main_parallel` to `cli/parallel.py`
   - Move `main_messages` and `_save_combined` to `cli/messages.py`
   - Move `main_loop` to `cli/loop.py`
   - Move `main_sprint` and all `_cmd_sprint_*`, `_sprint_*`, `_render_*`, `_build_*` helpers to `cli/sprint.py`
   - Move `main_history` to `cli/history.py`
   - Move `main_sync` and `_print_sync_*` helpers to `cli/sync.py`
   - Move `main_verify_docs` and `main_check_links` to `cli/docs.py`

3. **Create cli/__init__.py with public API**
   ```python
   """CLI entry points for little-loops."""

   from little_loops.cli.auto import main_auto
   from little_loops.cli.docs import main_check_links, main_verify_docs
   from little_loops.cli.history import main_history
   from little_loops.cli.loop import main_loop
   from little_loops.cli.messages import main_messages
   from little_loops.cli.parallel import main_parallel
   from little_loops.cli.sprint import main_sprint
   from little_loops.cli.sync import main_sync

   __all__ = [
       "main_auto",
       "main_parallel",
       "main_messages",
       "main_loop",
       "main_sprint",
       "main_history",
       "main_sync",
       "main_verify_docs",
       "main_check_links",
   ]
   ```

4. **Update setup.py entry points**
   - Change imports from `little_loops.cli:main_*` to `little_loops.cli:main_*` (no change needed if using __init__.py exports)

5. **Update imports in other modules**
   - Search for `from little_loops.cli import` and verify still works

6. **Run tests**
   ```bash
   python -m pytest scripts/tests/test_cli.py -v
   ```

7. **Delete original cli.py**
   ```bash
   git rm scripts/little_loops/cli.py
   ```

## Motivation

This enhancement would:
- Improve maintainability: 2,624-line god module with 9 CLI entry points is difficult to navigate
- Reduce merge conflicts: developers working on different CLI commands frequently conflict
- Enable focused testing: each command can have isolated, smaller test files

## Scope Boundaries

- **In scope**: Splitting cli.py into cli/ package with one module per CLI command
- **Out of scope**: Changing CLI interfaces, adding new commands, refactoring internal logic

## Implementation Steps

1. Create `cli/` package directory with `__init__.py`
2. Extract each CLI entry point to its own module (auto.py, parallel.py, etc.)
3. Wire up `__init__.py` to re-export all entry points
4. Verify `setup.py` entry points still work via `__init__.py` exports
5. Update imports in other modules
6. Run tests to verify no regressions
7. Delete original `cli.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli.py` - Split into package

### Dependent Files (Callers/Importers)
- `setup.py` / `pyproject.toml` - CLI entry point references
- `scripts/tests/test_cli.py` - ~50 imports from `little_loops.cli`
- `scripts/tests/test_ll_loop_execution.py` - ~40 imports of `main_loop`
- `scripts/tests/test_ll_loop_integration.py` - ~20 imports of `main_loop`
- `scripts/tests/test_ll_loop_state.py` - ~10 imports of `main_loop`
- `scripts/tests/test_ll_loop_display.py` - ~6 imports of `main_loop`
- `scripts/tests/test_ll_loop_commands.py` - ~6 imports of `main_loop`
- `scripts/tests/test_ll_loop_errors.py` - ~12 imports of `main_loop`
- `scripts/tests/test_sprint_integration.py` - ~13 imports of `cli`
- `scripts/tests/test_sprint.py` - ~9 imports of `cli`
- `scripts/tests/test_issue_history_cli.py` - ~9 imports of `main_history`
- `scripts/tests/test_create_loop.py` - ~5 imports of `main_loop`
- `scripts/tests/test_builtin_loops.py` - ~8 imports of `main_loop`
- `scripts/tests/test_cli_e2e.py` - ~4 imports

### Similar Patterns
- ENH-390 (issue_history.py split) follows the same god-module-to-package pattern

### Tests
- `scripts/tests/test_cli.py` - update imports if needed

### Documentation
- `docs/API.md` - update module references

### Configuration
- N/A

## Impact

- **Priority**: P2 - Important maintainability improvement but not blocking features
- **Effort**: Medium - Straightforward file splitting, but many test imports to update (~130 import sites)
- **Risk**: Low - Breaking changes contained to internal imports, public API unchanged via __init__.py re-exports
- **Breaking Change**: No

## Benefits

1. **Improved maintainability** - Each command is self-contained
2. **Better testability** - Tests can be organized per command
3. **Reduced coupling** - Each module imports only what it needs
4. **Easier navigation** - Developers can find command logic quickly
5. **Parallel development** - Multiple developers can work on different commands without conflicts

## Blocks

- ENH-308: Sprint sequential retry for merge-failed issues
- ENH-328: ll-auto verify check implementation markers
- BUG-339: CLI hardcodes .loops directory path

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`, `god-module`

---

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-11 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py` → Split into `scripts/little_loops/cli/` package (8 modules + `__init__.py`)
- `scripts/little_loops/cli/__init__.py` - Re-exports all 9 entry points for backward compatibility
- `scripts/little_loops/cli/auto.py` - `main_auto()` (58 lines)
- `scripts/little_loops/cli/parallel.py` - `main_parallel()` (167 lines)
- `scripts/little_loops/cli/messages.py` - `main_messages()` + `_save_combined()` (203 lines)
- `scripts/little_loops/cli/loop.py` - `main_loop()` with nested commands (883 lines)
- `scripts/little_loops/cli/sprint.py` - `main_sprint()` + 13 helpers + signal handler (768 lines)
- `scripts/little_loops/cli/history.py` - `main_history()` (133 lines)
- `scripts/little_loops/cli/sync.py` - `main_sync()` + 2 helpers (156 lines)
- `scripts/little_loops/cli/docs.py` - `main_verify_docs()` + `main_check_links()` (200 lines)
- Updated ~15 patch paths in `test_cli.py`, `test_sprint.py`, `test_sprint_integration.py`

### Verification Results
- Tests: PASS (2691 passed, 4 skipped)
- Lint: PASS
- Types: PASS

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- cli.py is 2,614 lines (matches reported ~2,624 lines)
- cli/ package does not exist yet — refactoring not started
- All 9 CLI entry points remain in single file

### Ready Issue Validation (2026-02-11)

- **ID Collision**: ENH-344 is also used by completed issue `P3-ENH-344-sprint-execution-plan-shows-file-contention-warnings.md`. This issue needs renormalization to a unique ID.
- Auto-corrected: Renamed "Finding > Current State" to "Current Behavior", added "Expected Behavior", renamed "Impact Assessment" to "Impact" with justifications
- ~130 test import sites in 12+ test files reference `from little_loops.cli import` — Integration Map updated
