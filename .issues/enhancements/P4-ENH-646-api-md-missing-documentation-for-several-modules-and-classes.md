---
id: ENH-646
type: ENH
priority: P4
status: active
title: "API.md missing documentation sections for work_verification, session_log, FSM submodules, and other public APIs"
created: 2026-03-07
---

# ENH-646: API.md missing documentation sections for several modules and public APIs

## Problem

Multiple public modules and classes are listed in the module table of `docs/reference/API.md` but have no corresponding documentation sections, or are entirely absent from the reference. The most impactful gaps are listed below.

## Missing Documentation

### Entire modules with no section

**`work_verification`** — Listed in module table but has no section. The two public functions (`filter_excluded_files`, `verify_work_was_done`) were incorrectly attributed to `git_operations` (now partially fixed via direct edit). A proper section with signatures, parameters, and examples is needed.

**`session_log`** — Listed in module table but has no section. Four public functions: `parse_session_log`, `count_session_commands`, `get_current_session_jsonl`, `append_session_log_entry`.

### Missing classes and functions in existing sections

**`issue_parser.ProductImpact`** — A dataclass (`severity`, `user_impact`, `scope`, `to_dict()`, `from_dict()`) used as `IssueInfo.product_impact` but never documented.

**`issue_parser.is_normalized` / `is_formatted`** — Two public module-level functions with no documentation.

**`issue_lifecycle.defer_issue` / `undefer_issue`** — Two public functions not documented anywhere.

**`sprint.SprintState`** — Public dataclass with 7 fields and `to_dict()`/`from_dict()` exported from `sprint.py` but not documented.

**`StateManager.record_corrections()`** — A public method present in `StateManager` but not listed in the method table.

### Undocumented config classes

Seven config dataclasses are undocumented despite being part of the `BRConfig` property tree:
- `SprintsConfig`
- `LoopsConfig`
- `SyncConfig`
- `GitHubSyncConfig`
- `ScoringWeightsConfig`
- `DependencyMappingConfig`
- `RefineStatusConfig`

### Undocumented FSM submodules

Three FSM submodules have no documentation:
- `handoff_handler` — `HandoffHandler`, `HandoffBehavior`, `HandoffResult`, `handle()` method
- `concurrency` — `ScopeLock`, `LockManager` and methods
- `signal_detector` — `SignalDetector`, `DetectedSignal`, `SignalPattern`, `detect()`/`detect_first()`

### Other undocumented parallel types

- `parallel.overlap_detector` — `OverlapDetector`, `OverlapResult`
- `parallel.types.WorkerStage` and `PendingWorktreeInfo`

### CLI entry points (partially missing)

Six CLI entry points documented in code but absent from the CLI section:
- `main_sprint` (`ll-sprint`)
- `main_parallel` (`ll-parallel`)
- `main_sync` (`ll-sync`)
- `main_deps` (`ll-deps`)
- `main_verify_docs` (`ll-verify-docs`)
- `main_check_links` (`ll-check-links`)

### Undocumented issue_history data classes

17+ real `issue_history` data classes have no individual documentation entries (partly addressed by BUG-643 but completeness remains an issue after inaccuracies are fixed).

## Files

- `docs/reference/API.md` — needs new sections and entries
- `scripts/little_loops/work_verification.py`
- `scripts/little_loops/session_log.py`
- `scripts/little_loops/issue_parser.py`
- `scripts/little_loops/issue_lifecycle.py`
- `scripts/little_loops/sprint.py`
- `scripts/little_loops/state.py`
- `scripts/little_loops/config.py`
- `scripts/little_loops/fsm/`
- `scripts/little_loops/parallel/`

## Fix

Add missing sections to API.md. Prioritize: `work_verification` (high — functions misattributed), `session_log`, lifecycle functions, then config classes and FSM submodules.
