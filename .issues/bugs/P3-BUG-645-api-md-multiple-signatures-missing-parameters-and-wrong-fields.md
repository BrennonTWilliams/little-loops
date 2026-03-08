---
id: BUG-645
type: BUG
priority: P3
status: active
title: "API.md multiple API signatures missing parameters and wrong field documentation"
created: 2026-03-07
---

# BUG-645: API.md multiple API signatures missing parameters and wrong field documentation

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
