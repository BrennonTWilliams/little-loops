---
discovered_commit: 3e9beea
discovered_branch: main
discovered_date: 2026-03-12
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-684: Split config.py (1,012 lines) into config subpackage

## Summary

Architectural issue found by `/ll:audit-architecture`.

`config.py` contains 20+ dataclasses totaling 1,012 lines, covering project config, CLI config, scan config, parallel config, sync config, and more.

## Motivation

A 1,012-line file with 20+ unrelated dataclasses is difficult to navigate, creates merge conflict hot spots as multiple features touch config simultaneously, and makes it hard to understand which components own which configuration. Splitting into domain-specific submodules improves discoverability and reduces contention.

## Location

- **File**: `scripts/little_loops/config.py`
- **Line(s)**: 1-1012 (entire file)
- **Module**: `little_loops.config`

## Finding

### Current State

All configuration dataclasses are in a single file:
- `ProjectConfig`, `CategoryConfig` (core)
- `IssuesConfig`, `ScanConfig` (issue management)
- `AutomationConfig`, `ParallelAutomationConfig` (automation)
- `ConfidenceGateConfig`, `CommandsConfig` (commands)
- `SprintsConfig`, `LoopsConfig` (orchestration)
- `GitHubSyncConfig`, `SyncConfig` (sync)
- `ScoringWeightsConfig`, `DependencyMappingConfig` (analysis)
- `CliColorsLoggerConfig`, `CliColorsPriorityConfig`, `CliColorsTypeConfig`, `CliColorsConfig` (CLI styling)
- `RefineStatusConfig`, `CliConfig` (CLI)
- `BRConfig` (root config)

### Impact

- **Development velocity**: Hard to find specific config classes; merge conflicts likely
- **Maintainability**: Single file with many unrelated concerns
- **Risk**: Low runtime risk

## Proposed Solution

Convert `config.py` into a `config/` subpackage with domain-specific modules.

### Suggested Approach

1. Create `scripts/little_loops/config/` package
2. Split into: `core.py` (ProjectConfig, BRConfig), `cli.py` (CliConfig, colors), `features.py` (scan, sync, sprints, loops), `automation.py` (parallel, automation configs)
3. Re-export from `config/__init__.py` with `__all__` for backwards compatibility
4. Run tests to verify nothing breaks

## Scope Boundaries

- Re-export all existing names from `config/__init__.py` for backwards compatibility — no call site changes required
- Do not change any dataclass definitions, field names, or defaults during the split
- Run full test suite after each submodule extraction to catch regressions

## Implementation Steps

1. Create `scripts/little_loops/config/` package directory
2. Split into domain files: `core.py` (ProjectConfig, BRConfig), `cli.py` (CliConfig, CliColors*), `features.py` (IssuesConfig, ScanConfig, SprintsConfig, LoopsConfig, SyncConfig), `automation.py` (AutomationConfig, ParallelAutomationConfig, ConfidenceGateConfig)
3. Add `__init__.py` with `__all__` re-exporting all existing public names
4. Update `scripts/little_loops/config.py` to import from the new package (or replace with the package)
5. Run `python -m pytest` and verify no import errors

## Integration Map

- **Modified**: `scripts/little_loops/config.py` → replaced by `scripts/little_loops/config/`
- **New files**: `scripts/little_loops/config/core.py`, `config/cli.py`, `config/features.py`, `config/automation.py`, `config/__init__.py`
- **All importers unchanged**: re-exports from `config/__init__.py` preserve `from little_loops.config import BRConfig` etc.

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low (re-exports maintain compatibility)
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
