# ENH-346: Split cli/loop.py into subcommand modules

## Plan Summary

Split the 1,036-line `scripts/little_loops/cli/loop.py` monolith into a `cli/loop/` package with focused submodules, following the ENH-390 pattern (issue_history split).

## Research Findings

- **File**: `scripts/little_loops/cli/loop.py` — 1,037 lines, 12 subcommand handlers all nested inside `main_loop()`
- **Entry point**: `main_loop()` — imports, config, argparse setup, helpers, command handlers, and dispatch all within one function
- **Import path**: `pyproject.toml` → `little_loops.cli:main_loop` → `cli/__init__.py` line 19 → `cli.loop.main_loop`
- **Tests**: 11 test files import `main_loop` via `from little_loops.cli import main_loop` (never directly from `cli.loop`)
- **No test changes needed**: All tests use the `cli/__init__.py` re-export
- **Reference pattern**: ENH-390 split `issue_history.py` (3,824 lines) into `issue_history/` package with zero test failures

### Key Structural Insight

All 12 `cmd_*` handlers are **nested functions** inside `main_loop()`, sharing closure variables (`args`, `logger`, `config`, `loops_dir`, `yaml`, `compile_paradigm`, `load_and_validate`). To extract them into separate modules, they must become top-level functions that receive these dependencies as parameters.

### Module Grouping

| Module | Commands | Lines (approx) | Rationale |
|--------|----------|----------------|-----------|
| `__init__.py` | `main_loop` entry point, argparse, dispatch | ~190 | Core CLI skeleton |
| `_helpers.py` | `get_builtin_loops_dir`, `resolve_loop_path`, `load_loop`, `print_execution_plan`, `run_foreground` | ~140 | Shared utilities used by multiple commands |
| `run.py` | `cmd_run` | ~70 | Execution with locking, queueing, dry-run |
| `config_cmds.py` | `cmd_compile`, `cmd_validate`, `cmd_install` | ~120 | Configuration/setup commands |
| `lifecycle.py` | `cmd_status`, `cmd_stop`, `cmd_resume` | ~80 | Loop state lifecycle |
| `info.py` | `cmd_list`, `cmd_history`, `cmd_show` | ~180 | Read-only information display |
| `testing.py` | `cmd_test`, `cmd_simulate` | ~200 | Testing and simulation |

## Dependency Context

### Shared Dependencies (passed from `main_loop` or imported per-module)

Every command handler currently uses via closure:
- `args` (argparse.Namespace) — module-specific args accessed per command
- `logger` (Logger) — for log output
- `loops_dir` (Path) — resolved from config
- `yaml` — YAML parsing
- `compile_paradigm` — paradigm auto-compilation
- `load_and_validate` — loop validation

**Strategy**: Extract a `_helpers.py` module with a `LoopContext` dataclass that bundles shared state. Each command function accepts what it needs as parameters rather than relying on closures.

The `load_loop` helper will deduplicate the auto-compile pattern repeated 6 times across handlers.

## Implementation Phases

### Phase 1: Create package structure
- [ ] Create `scripts/little_loops/cli/loop/` directory
- [ ] Create `scripts/little_loops/cli/loop/__init__.py` with `main_loop` re-export
- [ ] Create `scripts/little_loops/cli/loop/_helpers.py` with shared utilities
- [ ] Delete original `scripts/little_loops/cli/loop.py`

### Phase 2: Extract subcommand modules
- [ ] Create `scripts/little_loops/cli/loop/run.py` — `cmd_run`
- [ ] Create `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_compile`, `cmd_validate`, `cmd_install`
- [ ] Create `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status`, `cmd_stop`, `cmd_resume`
- [ ] Create `scripts/little_loops/cli/loop/info.py` — `cmd_list`, `cmd_history`, `cmd_show`
- [ ] Create `scripts/little_loops/cli/loop/testing.py` — `cmd_test`, `cmd_simulate`

### Phase 3: Verification
- [ ] Run tests: `python -m pytest scripts/tests/`
- [ ] Run linting: `ruff check scripts/`
- [ ] Run type checking: `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] All 12 subcommands work identically (behavioral parity)
- [ ] `from little_loops.cli.loop import main_loop` still works
- [ ] `from little_loops.cli import main_loop` still works (test path)
- [ ] All existing tests pass without modification
- [ ] Linting passes
- [ ] Type checking passes
- [ ] No module exceeds ~200 lines

## Risk Assessment

- **Risk**: Low — purely structural, no behavioral changes
- **Mitigation**: All tests go through `cli/__init__.py` re-export, so the internal restructure is transparent
- **Rollback**: `git revert` if anything breaks
