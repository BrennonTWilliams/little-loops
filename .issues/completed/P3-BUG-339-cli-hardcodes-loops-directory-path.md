---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-339: CLI hardcodes .loops directory path

## Summary

`cli/loop.py` and `fsm/` modules hardcode `.loops` in 15+ places with no corresponding config key in the schema or `ll-config.json`. Users cannot customize the loops directory location.

## Context

Identified during a config consistency audit. The `.loops` directory is the only major directory path without a config schema entry.

## Current Behavior

`cli/loop.py` hardcodes `.loops` in 6+ places and `fsm/concurrency.py` and `fsm/persistence.py` hardcode it in 9+ places. There is no `loops.loops_dir` config key in `config-schema.json` or `ll-config.json`, so users cannot customize the loops directory location.

## Expected Behavior

A `loops` section should exist in the config schema with a `loops_dir` key (default `.loops`), and all hardcoded references in `cli/loop.py` and `fsm/` modules should use the config value.

## Steps to Reproduce

1. Search `scripts/little_loops/cli/loop.py` and `scripts/little_loops/fsm/` for hardcoded `.loops` references
2. Observe: 15+ locations use literal `.loops` path with no config lookup

## Actual Behavior

The `.loops` directory path is hardcoded and cannot be customized via config.

## Root Cause

- **File**: `scripts/little_loops/cli/loop.py`, `scripts/little_loops/fsm/concurrency.py`, `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `Path(".loops")` used in `resolve_loop_path()`, `_run_loop()`, `copy_loop()`, `LoopLockManager.__init__()`, `StatePersistence.__init__()`, `LoopRunner.__init__()`, `list_running_loops()`
- **Cause**: The loops feature was implemented without adding a corresponding config schema entry, unlike other directory paths

## Affected Files

- `scripts/little_loops/cli/loop.py` (lines ~175, 180, 443, 495): hardcoded `.loops` path
- `scripts/little_loops/fsm/concurrency.py` (line ~79): hardcoded `.loops` default
- `scripts/little_loops/fsm/persistence.py` (lines ~129, 236, 399): hardcoded `.loops` default
- `config-schema.json`: missing `loops.loops_dir` config key
- `scripts/little_loops/config.py`: no `LoopsConfig` dataclass

## Proposed Solution

1. Add `loops` section to `config-schema.json`:
   ```json
   "loops": {
     "type": "object",
     "properties": {
       "loops_dir": { "type": "string", "default": ".loops" }
     }
   }
   ```
2. Add `LoopsConfig` dataclass in `config.py` and wire into `BRConfig`
3. Replace all hardcoded `.loops` references in `cli/loop.py` and `fsm/` modules with `config.loops.loops_dir`

## Implementation Steps

1. Add `loops` section with `loops_dir` to `config-schema.json`
2. Add `LoopsConfig` dataclass in `config.py` and wire into `BRConfig`
3. Replace all hardcoded `.loops` in `cli/loop.py`, `fsm/concurrency.py`, and `fsm/persistence.py` with config value
4. Run tests to verify no regressions

## Integration Map

### Files to Modify
- `config-schema.json` - Add `loops` section
- `scripts/little_loops/config.py` - Add `LoopsConfig` dataclass
- `scripts/little_loops/cli/loop.py` - Replace hardcoded `.loops` references
- `scripts/little_loops/fsm/concurrency.py` - Replace hardcoded `.loops` default
- `scripts/little_loops/fsm/persistence.py` - Replace hardcoded `.loops` defaults

### Dependent Files (Callers/Importers)
- Commands/skills that reference `.loops/` (tracked in ENH-341)

### Similar Patterns
- `issues.base_dir`, `parallel.worktree_base` config patterns

### Tests
- `scripts/tests/test_config.py` - Test new `LoopsConfig` dataclass
- `scripts/tests/test_cli.py` - Verify loops directory uses config

### Documentation
- N/A

### Configuration
- `config-schema.json` - New `loops.loops_dir` key
- `.claude/ll-config.json` - Optional override

## Impact

- **Priority**: P3 - Inconsistency with other configurable paths
- **Effort**: Small-Medium - Schema addition + 15+ references across 3 files
- **Risk**: Low - Default value preserves existing behavior
- **Breaking Change**: No

## Blocked By

- ~~ENH-344: Split cli.py into cli/ package~~ (completed)

## Blocks

- ENH-341: Commands and skills use hardcoded paths instead of config refs

## Labels

`bug`, `config`, `cli`, `captured`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Config system design |

---

## Status

**Completed** | Created: 2026-02-11 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `config-schema.json`: Added `loops` section with `loops_dir` property (default: `.loops`)
- `scripts/little_loops/config.py`: Added `LoopsConfig` dataclass, wired into `BRConfig` with property, convenience method `get_loops_dir()`, and `to_dict()` support
- `scripts/little_loops/cli/loop.py`: Loads `BRConfig` and passes `loops_dir` to all functions that previously hardcoded `Path(".loops")`

### Verification Results
- Tests: PASS (2691 passed)
- Lint: PASS
- Types: PASS
