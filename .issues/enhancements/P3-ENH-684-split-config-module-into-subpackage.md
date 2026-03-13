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

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low (re-exports maintain compatibility)
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
