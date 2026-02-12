# BUG-339: CLI hardcodes .loops directory path - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P3-BUG-339-cli-hardcodes-loops-directory-path.md
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `.loops` directory path is hardcoded as `Path(".loops")` in:
- `cli/loop.py`: `resolve_loop_path()` (lines 175, 180), `cmd_list()` (line 443), `cmd_install()` (line 495)
- `fsm/concurrency.py`: `LockManager.__init__()` (line 79)
- `fsm/persistence.py`: `StatePersistence.__init__()` (line 129), `PersistentExecutor.__init__()` (line 236), `list_running_loops()` (line 399)

No `loops` section exists in `config-schema.json` or `config.py`.

## Solution Approach

1. Add `LoopsConfig` dataclass following existing patterns (like `SprintsConfig`)
2. Wire into `BRConfig._parse_config()` and add property + convenience method
3. Add schema section to `config-schema.json`
4. Update all hardcoded references to accept `loops_dir` parameter or use config

The FSM modules already accept `loops_dir: Path | None = None` parameters with `or Path(".loops")` fallback — so the fix is primarily about wiring config through `cli/loop.py` and letting the existing parameter plumbing work.

## What We're NOT Doing

- Not changing commands/skills that reference `.loops/` (tracked in ENH-341)
- Not adding `loops` section to ll-config.json (default `.loops` preserves behavior)

## Implementation Phases

### Phase 1: Config infrastructure
- Add `LoopsConfig` dataclass to `config.py`
- Wire into `BRConfig`
- Add to `config-schema.json`
- Add to `to_dict()` and `__all__`

### Phase 2: Wire config through cli/loop.py
- Load `BRConfig` in `main_loop()`
- Pass `loops_dir` to all functions that need it
- Replace all `Path(".loops")` with config-derived value

### Phase 3: Verify
- Run tests, lint, type check
