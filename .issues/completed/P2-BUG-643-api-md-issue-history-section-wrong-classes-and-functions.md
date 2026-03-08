---
id: BUG-643
type: BUG
priority: P2
status: active
title: "API.md issue_history section documents wrong data class schemas and nonexistent functions"
created: 2026-03-07
---

# BUG-643: API.md issue_history section documents wrong data class schemas and nonexistent functions

## Problem

The `issue_history` section in `docs/reference/API.md` contains pervasive inaccuracies: data class field schemas are wrong, 9 documented public functions don't exist, and 2 documented classes don't exist. Any caller using the API reference will get `ImportError` or `AttributeError`.

## Findings

### Wrong data class schemas

**`CompletedIssue`** (API.md ~line 1185): Documents `issue_id, issue_type, priority, title, completed_at, file_path, blockers, blocks, tags`. Actual fields: `path, issue_type, priority, issue_id, discovered_by, discovered_date, completed_date`. Six documented fields are wrong or nonexistent.

**`HistorySummary`** (API.md ~line 1204): Documents `total_count, date_range, velocity, type_distribution, priority_distribution`. Actual fields: `total_count, type_counts, priority_counts, discovery_counts, earliest_date, latest_date`. Field names all wrong; `velocity` doesn't exist.

**`Hotspot`** (API.md ~line 1219): Documents `file_path, issue_count, issue_types, last_issue_date`. Actual: `path, issue_count, issue_ids, issue_types, bug_ratio, churn_indicator`. `file_path` → `path`, `last_issue_date` doesn't exist.

**`CouplingPair`** (API.md ~line 1232): Documents `issue_a, issue_b, correlation_score, shared_files`. Actual: `file_a, file_b, co_occurrence_count, coupling_strength, issue_ids`. The class tracks file coupling, not issue coupling — entirely wrong semantics.

### Nonexistent public functions (API.md ~line 1165-1175)

The "Public Functions (11)" table lists these that **do not exist**:
- `load_completed_issues()` → actual: `scan_completed_issues()`
- `compute_history_summary()` → actual: `calculate_summary()`
- `compute_velocity()` → does not exist
- `analyze_type_distribution()` → does not exist
- `analyze_priority_distribution()` → does not exist
- `cluster_regressions()` → actual: `analyze_regression_clustering()`
- `get_trend_data()` → does not exist
- `generate_velocity_report()` → does not exist
- `compute_failure_classification()` → does not exist

### Nonexistent classes

**`VelocityMetrics`** and **`TrendDataPoint`** (API.md ~lines 1242-1266) are documented in detail with fields and descriptions but don't exist anywhere in the codebase.

### Wrong count

"Data Classes (19)" claim (API.md ~line 1177). Actual count: 26 classes.

### Broken example code

The usage example (~lines 1272-1294) uses all nonexistent names — it will `ImportError` at import time.

## Files

- `docs/reference/API.md` — lines ~1165–1294 (entire `issue_history` module section)
- `scripts/little_loops/issue_history/` — actual source to verify against

## Fix

Rewrite the `issue_history` section of API.md to match the actual module:
1. Correct all four data class schemas to match actual fields
2. Replace the function table with actual exported functions
3. Remove `VelocityMetrics` and `TrendDataPoint` entries
4. Update the data class count
5. Fix the usage example

## Impact

- **Priority**: P2 - API reference misleads callers with nonexistent function names and wrong data class schemas, causing `ImportError`/`AttributeError` at runtime
- **Effort**: Small - rewriting one section of docs against verified source; no code changes required
- **Risk**: Low - documentation-only change, no runtime behavior affected
- **Breaking Change**: No

## Labels

`documentation`, `accuracy`, `api-reference`, `issue_history`

## Status

**Resolved** | Created: 2026-03-07 | Completed: 2026-03-07 | Priority: P2

## Resolution

- Rewrote the `issue_history` section in `docs/reference/API.md` (~lines 1157–1330)
- Fixed `CompletedIssue` schema: corrected fields to `path, issue_type, priority, issue_id, discovered_by, discovered_date, completed_date`
- Fixed `HistorySummary` schema: corrected fields to `total_count, type_counts, priority_counts, discovery_counts, earliest_date, latest_date`
- Fixed `Hotspot` schema: corrected fields to `path, issue_count, issue_ids, issue_types, bug_ratio, churn_indicator`
- Fixed `CouplingPair` schema: corrected fields to `file_a, file_b, co_occurrence_count, coupling_strength, issue_ids`
- Replaced nonexistent function table (11 wrong entries) with actual 25 public functions across 4 categories
- Removed nonexistent `VelocityMetrics` and `TrendDataPoint` class documentation
- Updated data class count from 19 to 26 (actual count); added table of remaining 22 classes
- Fixed usage example to use actual function names (`scan_completed_issues`, `calculate_summary`, `format_summary_text`)

## Session Log
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7223a0-7f18-4556-a998-58c9508af197.jsonl`
- `/ll:manage-issue bug fix BUG-643` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7223a0-7f18-4556-a998-58c9508af197.jsonl`
