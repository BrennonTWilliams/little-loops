---
id: BUG-645
type: BUG
priority: P3
status: active
title: "API.md multiple API signatures missing parameters and wrong field documentation"
created: 2026-03-07
---

# BUG-645: API.md multiple API signatures missing parameters and wrong field documentation

## Summary

`docs/reference/API.md` documents twelve API signatures and data class schemas with missing parameters or incorrect methods, causing callers to be unaware of available functionality.

## Current Behavior

Twelve API entries in `docs/reference/API.md` are incomplete or incorrect:
- `IssueInfo` dataclass documents 5 of 16 fields
- `find_issues()` and `find_highest_priority_issue()` omit `only_ids` and `type_prefixes` parameters
- `DependencyGraph.from_issues()` omits `all_known_ids` parameter
- `AutoManager.__init__()` omits `only_ids`, `skip_ids`, `type_prefixes`, `verbose` parameters
- `close_issue()` omits `fix_commit` and `files_changed` parameters
- `ActionRunner.run()` omits `on_output_line` parameter
- `WorkerResult` omits `corrections`, `was_blocked`, `interrupted` fields
- `ParallelConfig` omits 8 fields
- `BRConfig.create_parallel_config()` omits 9 parameters
- `IssuesConfig` omits `capture_template` field
- `AutomationConfig` omits `idle_timeout_seconds` field
- `IssuePriorityQueue` documents nonexistent `p0_count()` and `parallel_count()` methods

## Expected Behavior

All API signatures in `docs/reference/API.md` accurately reflect the actual function/method/class definitions in source, including all parameters and their defaults. Nonexistent methods are removed.

## Steps to Reproduce

1. Open `docs/reference/API.md` and read the `IssueInfo` dataclass documentation (~line 370)
2. Open `scripts/little_loops/issue_parser.py` and read the `IssueInfo` class (~line 201)
3. Observe: API.md shows 5 fields, source has 16

## Problem

Twelve separate API signatures or data class schemas in `docs/reference/API.md` are incomplete or incorrect — missing parameters that exist in the actual code. This causes callers to miss available functionality.

## Findings

### Missing parameters in function/method signatures

**`IssueInfo` dataclass** (~line 370): Documents 5 of 16 actual fields. Missing: `blocked_by`, `blocks`, `discovered_by`, `product_impact`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `session_commands`, `session_command_counts`.

**`find_issues()`** (~line 444): Missing `only_ids=None` and `type_prefixes=None` parameters.

**`find_highest_priority_issue()`** (~line 472): Same — missing `only_ids` and `type_prefixes` parameters.

**`DependencyGraph.from_issues()`** (~line 548): Missing `all_known_ids=None` parameter.

**`AutoManager.__init__()`** (~line 1503): Missing `only_ids=None`, `skip_ids=None`, `type_prefixes=None`, `verbose=True` parameters.

**`close_issue()`** (~line 1578): Missing `fix_commit: str | None = None` and `files_changed: list[str] | None = None` parameters.

**`ActionRunner.run()` protocol** (~line 3272): Missing `on_output_line: Callable[[str], None] | None = None` parameter.

### Missing fields in data classes

**`WorkerResult`** (~line 2170): Missing `corrections: list[str]`, `was_blocked: bool`, `interrupted: bool`.

**`ParallelConfig`** (~line 2110): Missing `type_prefixes`, `idle_timeout_per_issue`, `merge_pending`, `clean_start`, `ignore_pending`, `overlap_detection`, `serialize_overlapping`, `base_branch`.

**`BRConfig.create_parallel_config()`** (~line 207): Missing `idle_timeout_per_issue`, `only_ids`, `skip_ids`, `type_prefixes`, `merge_pending`, `clean_start`, `ignore_pending`, `overlap_detection`, `serialize_overlapping`, `base_branch`.

**`IssuesConfig`** (~line 292): Missing `capture_template: str = "full"` field.

**`AutomationConfig`** (~line 319): Missing `idle_timeout_seconds: int = 0` field.

### Nonexistent methods documented

**`IssuePriorityQueue`** (~line 2211): Documents `p0_count() -> int` and `parallel_count() -> int`. Neither exists. Actual methods: `qsize()`, `in_progress_count()`, `completed_count()`, `failed_count()`.

## Files

- `docs/reference/API.md` — many sections
- `scripts/little_loops/issue_parser.py`
- `scripts/little_loops/dependency_graph.py`
- `scripts/little_loops/issue_manager.py`
- `scripts/little_loops/issue_lifecycle.py`
- `scripts/little_loops/parallel/types.py`
- `scripts/little_loops/config.py`

## Fix

For each finding, update the corresponding API.md section to add the missing parameters/fields and remove nonexistent methods. Verify each against the actual source file before editing.

## Impact

- **Priority**: P3 - Docs inaccuracy that misleads callers; no runtime breakage
- **Effort**: Small - Mechanical docs updates verified against source
- **Risk**: Low - Documentation only, no code changes
- **Breaking Change**: No

## Labels

`documentation`, `api-docs`, `accuracy`

## Status

**Resolved** | Created: 2026-03-07 | Priority: P3

## Resolution

- **Status**: Completed - Fixed
- **Date**: 2026-03-07
- **Fix**: Updated `docs/reference/API.md` to correct all 13 identified inaccuracies:
  - Added 11 missing fields to `IssueInfo` dataclass (`blocked_by`, `blocks`, `discovered_by`, `product_impact`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `session_commands`, `session_command_counts`)
  - Added `only_ids` and `type_prefixes` to `find_issues()` and `find_highest_priority_issue()`
  - Added `all_known_ids` to `DependencyGraph.from_issues()`
  - Added `only_ids`, `skip_ids`, `type_prefixes`, `verbose` to `AutoManager.__init__()`
  - Added `fix_commit` and `files_changed` to `close_issue()`
  - Added `on_output_line` to `ActionRunner.run()` protocol
  - Added `corrections`, `was_blocked`, `interrupted` to `WorkerResult`
  - Added 8 missing fields to `ParallelConfig` (`type_prefixes`, `idle_timeout_per_issue`, `merge_pending`, `clean_start`, `ignore_pending`, `overlap_detection`, `serialize_overlapping`, `base_branch`)
  - Added 9 missing parameters to `BRConfig.create_parallel_config()`
  - Added `capture_template` to `IssuesConfig`
  - Added `idle_timeout_seconds` to `AutomationConfig`
  - Replaced nonexistent `p0_count()` and `parallel_count()` on `IssuePriorityQueue` with actual methods (`qsize()`, `in_progress_count()`, `completed_count()`, `failed_count()`)

## Session Log
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/692cf40c-219e-4c8f-a2bc-55008c9daf35.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/692cf40c-219e-4c8f-a2bc-55008c9daf35.jsonl`
