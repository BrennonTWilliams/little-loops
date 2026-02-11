---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-339: CLI hardcodes .loops directory path

## Summary

`cli.py` hardcodes `.loops` in 4+ places with no corresponding config key in the schema or `ll-config.json`. Users cannot customize the loops directory location.

## Context

Identified during a config consistency audit. The `.loops` directory is the only major directory path without a config schema entry.

## Current Behavior

`cli.py` hardcodes `.loops` in 4+ places. There is no `loops.loops_dir` config key in `config-schema.json` or `ll-config.json`, so users cannot customize the loops directory location.

## Expected Behavior

A `loops` section should exist in the config schema with a `loops_dir` key (default `.loops`), and all hardcoded references in `cli.py` should use the config value.

## Steps to Reproduce

1. Search `cli.py` for hardcoded `.loops` references
2. Observe: 4+ locations use literal `.loops` path with no config lookup

## Actual Behavior

The `.loops` directory path is hardcoded and cannot be customized via config.

## Root Cause

- **File**: `scripts/little_loops/cli.py`
- **Anchor**: `lines ~659, 664, 927, 979`
- **Cause**: The loops feature was implemented without adding a corresponding config schema entry, unlike other directory paths

## Affected Files

- `scripts/little_loops/cli.py` (lines ~659, 664, 927, 979): hardcoded `.loops` path
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
3. Replace all hardcoded `.loops` references in `cli.py` with `config.loops.loops_dir`

## Implementation Steps

1. Add `loops` section with `loops_dir` to `config-schema.json`
2. Add `LoopsConfig` dataclass in `config.py` and wire into `BRConfig`
3. Replace all hardcoded `.loops` in `cli.py` with `config.loops.loops_dir`
4. Run tests to verify no regressions

## Integration Map

### Files to Modify
- `config-schema.json` - Add `loops` section
- `scripts/little_loops/config.py` - Add `LoopsConfig` dataclass
- `scripts/little_loops/cli.py` - Replace hardcoded `.loops` references

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
- **Effort**: Small - Schema addition + 4 file references
- **Risk**: Low - Default value preserves existing behavior
- **Breaking Change**: No

## Blocked By

- ENH-309: Split cli.py into cli/ package (structural split should precede targeted fixes)

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

**Open** | Created: 2026-02-11 | Priority: P3
