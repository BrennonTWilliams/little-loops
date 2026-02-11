# ENH-344: Split cli.py into cli/ package - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-344-split-cli-module-into-package.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

`scripts/little_loops/cli.py` is a 2,614-line module with 9 CLI entry points and 17+ helper functions. The codebase already has two well-established package-split patterns to follow: `fsm/` (11 modules) and `parallel/` (8 modules).

### Key Discoveries
- Entry points defined in `scripts/pyproject.toml:47-58` as `little_loops.cli:main_*`
- No changes needed to pyproject.toml if `__init__.py` re-exports all entry points
- `main_loop()` (lines 496-1377) uses **nested** `cmd_*` functions, not module-level helpers
- Sprint uses module-level global `_sprint_shutdown_requested` and `_sprint_signal_handler`
- `cli_args.py` already provides shared arg utilities
- ~130 import sites across 13+ test files
- Tests use both `from little_loops.cli import main_auto` and `from little_loops import cli` patterns

## Desired End State

`cli.py` replaced by `cli/` package with one module per CLI command, public API unchanged.

### How to Verify
- All tests pass: `python -m pytest scripts/tests/`
- All entry points work: `ll-auto --help`, `ll-parallel --help`, etc.
- Lint/type checks pass

## What We're NOT Doing
- Not changing CLI interfaces or behavior
- Not refactoring internal logic within commands
- Not splitting test files (separate concern)
- Not updating docs/API.md (can be done separately)

## Code Reuse & Integration
- **Follow**: `fsm/__init__.py` and `parallel/__init__.py` re-export patterns
- **Reuse**: `cli_args.py` shared utilities (already separate)
- **Absolute imports** between submodules (project convention)

## Implementation Phases

### Phase 1: Create cli/ package structure and extract all modules

1. Read full cli.py content
2. Create `scripts/little_loops/cli/` directory
3. Extract each command to its own module with its imports and helpers:

| Module | Functions | Lines |
|--------|-----------|-------|
| `auto.py` | `main_auto` | ~58 |
| `parallel.py` | `main_parallel` | ~167 |
| `messages.py` | `main_messages`, `_save_combined` | ~203 |
| `loop.py` | `main_loop` (with nested cmd_*) | ~883 |
| `sprint.py` | `main_sprint`, `_sprint_signal_handler`, `_sprint_shutdown_requested`, 12 helpers | ~768 |
| `history.py` | `main_history` | ~133 |
| `sync.py` | `main_sync`, `_print_sync_status`, `_print_sync_result` | ~156 |
| `docs.py` | `main_verify_docs`, `main_check_links` | ~200 |

4. Each module gets only the imports it needs (both top-level and lazy)
5. Create `__init__.py` with re-exports and `__all__`
6. Delete original `cli.py`

#### Import distribution per module:

**auto.py**: `argparse`, `Path`, `BRConfig`, `AutoManager`, `add_common_auto_args`, `parse_issue_ids`
**parallel.py**: `argparse`, `sys`, `Path`, `BRConfig`, `Logger`, `ParallelOrchestrator`, cli_args functions, `parse_issue_ids` + lazy: `WorkerPool`
**messages.py**: `argparse`, `Path`, `Logger` + lazy: `json`, `datetime`, `user_messages`
**loop.py**: `argparse`, `sys`, `Path` + lazy: `yaml`, fsm modules
**sprint.py**: `argparse`, `signal`, `sys`, `Path`, `FrameType`, `Logger`, `SprintManager`, `SprintOptions`, `SprintState`, `DependencyGraph`, `WaveContentionNote`, `refine_waves_for_contention` + lazy: `dependency_mapper`, `process_issue_inplace`
**history.py**: `argparse`, `Path`, `BRConfig` + lazy: `issue_history`
**sync.py**: `argparse`, `Path`, `Any`, `BRConfig`, `Logger`, `GitHubSyncManager`, `SyncResult`, `SyncStatus`
**docs.py**: `argparse`, `Path` + lazy: `doc_counts`, `link_checker`

#### `__init__.py`:
```python
"""CLI entry points for little-loops tools."""

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
    "main_check_links",
    "main_history",
    "main_loop",
    "main_messages",
    "main_parallel",
    "main_sprint",
    "main_sync",
    "main_verify_docs",
]
```

### Phase 2: Update test imports

Tests that use `from little_loops.cli import main_*` should work via `__init__.py` re-exports.

Tests that use `from little_loops import cli` then `cli._helper()` need attention:
- `test_sprint.py` and `test_sprint_integration.py` access `cli._sprint_shutdown_requested`, `cli._cmd_sprint_run`, etc.
- These need to change to `from little_loops.cli import sprint` then `sprint._sprint_shutdown_requested`
- Or keep working if they use `from little_loops.cli import _sprint_shutdown_requested` etc.

Update `mock.patch()` paths from `little_loops.cli.something` to `little_loops.cli.module.something`.

### Phase 3: Verify

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Entry points work: `ll-auto --help` returns 0

## Testing Strategy

- All existing tests should pass without modification to test logic (only import paths change)
- Entry points remain stable via `__init__.py` re-exports
- No new tests needed (pure refactoring)
