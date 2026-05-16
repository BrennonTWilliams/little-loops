---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 79
---

# ENH-481: Replace hardcoded category lists with config throughout codebase

## Summary

Multiple functions hardcode `["bugs", "features", "enhancements"]` instead of reading from `BRConfig.issue_categories`. This causes silent misses if a project configures custom categories. At least 4 locations have this pattern.

## Current Behavior

The following functions hardcode the category list:
- `sprint.py:322` — `SprintManager.validate_issues`
- `sprint.py:348` — `SprintManager.load_issue_infos`
- `issue_history/parsing.py:336` — `scan_active_issues`
- `dependency_mapper.py:1001` — dependency scanning

`BRConfig` already exposes `issue_categories` (a property returning directory names from configured categories), but these functions bypass it.

## Expected Behavior

All functions that enumerate issue directories use `config.issue_categories` or accept an explicit list of category directories, falling back to the default set when no config is available.

## Motivation

Projects that rename or add custom categories (e.g., "tasks") will have issues in those categories silently ignored by sprint validation, history analysis, and dependency mapping. This is a systemic consistency issue.

## Proposed Solution

1. Update `SprintManager.validate_issues` and `load_issue_infos` to use `self.config.issue_categories`
2. Add `category_dirs: list[str] | None = None` parameter to `scan_active_issues`, defaulting to the hardcoded list for backward compatibility
3. Update `dependency_mapper.py` similarly
4. Extract a `_find_issue_path(issue_id: str) -> Path | None` helper in `sprint.py` to deduplicate the shared loop pattern between `validate_issues` and `load_issue_infos`

## Scope Boundaries

- **In scope**: Replacing hardcoded category lists with config-driven values; deduplicating the issue lookup pattern in sprint.py
- **Out of scope**: Adding new categories, changing config schema, modifying issue file format

## Implementation Steps

1. Audit all hardcoded `["bugs", "features", "enhancements"]` lists in `scripts/`
2. Replace each with `config.issue_categories` or equivalent parameterized approach
3. Extract `_find_issue_path` helper in sprint.py
4. Run tests to verify no breakage

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — `validate_issues`, `load_issue_infos`
- `scripts/little_loops/issue_history/parsing.py` — `scan_active_issues`
- `scripts/little_loops/dependency_mapper.py` — category enumeration

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/analysis.py` — calls `scan_active_issues`
- `scripts/little_loops/cli/sprint/run.py` — calls `validate_issues` and `load_issue_infos`
- `scripts/little_loops/cli/sprint/manage.py` — calls `validate_issues` and `load_issue_infos`
- `scripts/little_loops/cli/sprint/edit.py` — calls `validate_issues` and `load_issue_infos`
- `scripts/little_loops/cli/sprint/show.py` — calls `validate_issues` and `load_issue_infos`
- `scripts/little_loops/cli/sprint/create.py` — calls `validate_issues`

### Similar Patterns
- `issue_parser.py` uses `config.issue_categories` correctly in some paths

### Tests
- `scripts/tests/test_sprint.py` — verify custom categories are recognized
- `scripts/tests/test_issue_history.py` — verify scan_active_issues with custom dirs

### Documentation
- N/A

### Configuration
- N/A — leverages existing `BRConfig.issue_categories`

## Impact

- **Priority**: P3 — Systemic consistency issue affecting custom category support
- **Effort**: Small — Straightforward replacements across 4 locations
- **Risk**: Low — Uses existing config property
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `consistency`, `auto-generated`

## Resolution

**Resolved**: 2026-02-25

All four hardcoded category list sites replaced with config-driven values:

1. `sprint.py` — Added `_find_issue_path` helper using `self.config.issue_categories`; refactored `validate_issues` and `load_issue_infos` to use it.
2. `issue_history/parsing.py` — Added `category_dirs: list[str] | None = None` parameter to `scan_active_issues`; falls back to default list when omitted.
3. `dependency_mapper.py` — Added `config: BRConfig | None = None` parameter to `gather_all_issue_ids`; uses `config.issue_categories + completed_dir` when provided; updated all callers (`issue_manager.py`, `cli/sprint/run.py`, `show.py`, `manage.py`, `edit.py`) to pass config.

Tests added for all three locations covering custom-category behavior. Full suite: 2911 passed, 0 failures.

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:manage-issue enhancement fix ENH-481` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

## Status

**Completed** | Created: 2026-02-24 | Resolved: 2026-02-25 | Priority: P3

## Blocks

- ENH-486

- ENH-506
- FEAT-441
- ENH-484
- FEAT-503