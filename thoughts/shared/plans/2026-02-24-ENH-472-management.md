# ENH-472: Add __all__ to cli/loop/__init__.py

## Plan

### Research Findings

- **Target file**: `scripts/little_loops/cli/loop/__init__.py`
- **Only external import**: `from little_loops.cli.loop import main_loop` (in `cli/__init__.py`)
- **Internal imports**: All other imports are from submodules (`cli.loop.run`, `cli.loop.info`, etc.)
- **Pattern**: Other `__init__.py` files use module-level `__all__` list after imports

### Implementation

1. [x] Add `__all__ = ["main_loop"]` to `cli/loop/__init__.py` after imports, before function definition
2. [x] Run tests to verify no breakage
3. [x] Run linting/type checks

### Decision Log

- **Public API**: Only `main_loop` — it's the sole name imported externally and the entry point for the `ll-loop` CLI command
