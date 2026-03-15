# Implementation Plan: ENH-684 — Split config.py into config subpackage

**Date**: 2026-03-14
**Issue**: P3-ENH-684-split-config-module-into-subpackage.md
**Action**: improve

## Summary

`scripts/little_loops/config.py` (1,012 lines, 21 classes) is split into a `config/` subpackage with domain-specific modules. All existing public names are re-exported from `config/__init__.py` for full backwards compatibility — no call sites change.

## Subpackage Layout

```
scripts/little_loops/config/
  __init__.py      # re-exports all names from __all__; public API unchanged
  features.py      # REQUIRED_CATEGORIES, DEFAULT_CATEGORIES, CategoryConfig,
                   # IssuesConfig, ScanConfig, SprintsConfig, LoopsConfig,
                   # GitHubSyncConfig, SyncConfig
  automation.py    # AutomationConfig, ParallelAutomationConfig,
                   # ConfidenceGateConfig, CommandsConfig,
                   # ScoringWeightsConfig, DependencyMappingConfig
  cli.py           # CliColorsLoggerConfig, CliColorsPriorityConfig,
                   # CliColorsTypeConfig, CliColorsConfig,
                   # RefineStatusConfig, CliConfig
  core.py          # ProjectConfig, BRConfig, CLConfig alias
```

## Class → File Mapping

| Class | Destination |
|-------|-------------|
| `REQUIRED_CATEGORIES`, `DEFAULT_CATEGORIES` | `features.py` |
| `CategoryConfig`, `IssuesConfig` | `features.py` |
| `ScanConfig`, `SprintsConfig`, `LoopsConfig` | `features.py` |
| `GitHubSyncConfig`, `SyncConfig` | `features.py` |
| `AutomationConfig`, `ParallelAutomationConfig` | `automation.py` |
| `ConfidenceGateConfig`, `CommandsConfig` | `automation.py` |
| `ScoringWeightsConfig`, `DependencyMappingConfig` | `automation.py` |
| `CliColorsLoggerConfig`, `CliColorsPriorityConfig` | `cli.py` |
| `CliColorsTypeConfig`, `CliColorsConfig` | `cli.py` |
| `RefineStatusConfig`, `CliConfig` | `cli.py` |
| `ProjectConfig`, `BRConfig`, `CLConfig` | `core.py` |

## Dependency Flow (no circular imports)

```
features.py   (no intra-package imports)
automation.py (no intra-package imports)
cli.py        (no intra-package imports)
core.py       ← imports from features, automation, cli
__init__.py   ← imports from all four modules
```

## Implementation Steps

- [x] Write plan
- [ ] Create config/features.py
- [ ] Create config/automation.py
- [ ] Create config/cli.py
- [ ] Create config/core.py
- [ ] Create config/__init__.py
- [ ] Delete old config.py (git rm)
- [ ] Run tests
- [ ] Complete issue lifecycle

## Rationale for Grouping

- **features.py**: Issue tracking and project feature configs (categories, scanning, sprints, loops, sync)
- **automation.py**: Execution-time configs (parallel, confidence gate, commands, dependency analysis)
- **cli.py**: CLI presentation layer (colors, styling, display options)
- **core.py**: Root aggregator (ProjectConfig + BRConfig that owns all others)
