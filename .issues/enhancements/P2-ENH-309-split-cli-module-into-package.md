---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: large-files
---

# ENH-309: Split cli.py into cli/ package

## Summary

Architectural issue found by `/ll:audit_architecture`. The cli.py module is a god module containing 2,624 lines with 9 different CLI entry points, violating the Single Responsibility Principle.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Lines**: 1-2624 (entire file)
- **Module**: `little_loops.cli`

## Finding

### Current State

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

### Impact

- **Development velocity**: Hard to navigate and modify specific CLI commands
- **Maintainability**: Changes to one command can affect others, risk of merge conflicts
- **Testability**: Large test files mirror the monolithic structure
- **Risk**: High - Single point of failure for all CLI functionality

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

## Impact Assessment

- **Severity**: High - Maintainability issue affecting all CLI development
- **Effort**: Medium - Straightforward file splitting, careful import updates
- **Risk**: Low - Breaking changes contained to internal imports, public API unchanged
- **Breaking Change**: No - Public API preserved via cli/__init__.py

## Benefits

1. **Improved maintainability** - Each command is self-contained
2. **Better testability** - Tests can be organized per command
3. **Reduced coupling** - Each module imports only what it needs
4. **Easier navigation** - Developers can find command logic quickly
5. **Parallel development** - Multiple developers can work on different commands without conflicts

## Blocks

- FEAT-001: Add ABC for CLI commands
- ENH-308: Sprint sequential retry for merge-failed issues
- ENH-328: ll-auto verify check implementation markers

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`, `god-module`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- cli.py is 2,614 lines (matches reported ~2,624 lines)
- cli/ package does not exist yet — refactoring not started
- All 9 CLI entry points remain in single file
