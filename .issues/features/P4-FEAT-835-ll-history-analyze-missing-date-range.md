---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 100
---

# FEAT-835: `ll-history analyze` missing `--since`/`--until` date range

## Summary

`ll-history analyze` supports `--compare DAYS` for a rolling window relative to today, but has no `--since`/`--until` for absolute date ranges. The `export` subcommand already has `--since`. Users wanting "analyze Q1 2026" must use `--compare` awkwardly rather than specifying an explicit window.

## Location

- **File**: `scripts/little_loops/cli/history.py`
- **Line(s)**: 67-101 (at scan commit: 8c6cf90)
- **Anchor**: `analyze_parser`

## Current Behavior

`ll-history analyze` only supports relative date windows via `--compare DAYS`. No absolute date filtering is available.

## Expected Behavior

`ll-history analyze --since 2026-01-01 --until 2026-03-31` analyzes only issues completed within that window.

## Use Case

A developer preparing a quarterly review wants to analyze issue trends for Q1 2026. They need `--since 2026-01-01 --until 2026-03-31` to scope the analysis to that quarter, rather than computing the correct `--compare` value relative to today.

## Acceptance Criteria

- [x] `--since YYYY-MM-DD` filters completed issues to those after the given date
- [x] `--until YYYY-MM-DD` filters completed issues to those before the given date
- [x] Both can be combined for a range
- [x] `--compare` and `--since`/`--until` are mutually exclusive
- [x] Date format matches the `--since` format already used in `ll-history export`

## Proposed Solution

Add `--since` and `--until` arguments to `analyze_parser`. Pre-filter the completed issues list from `scan_completed_issues` by date before passing to `calculate_analysis`. Add mutual exclusion with `--compare` using an argparse mutually exclusive group.

## Impact

- **Priority**: P4 - Missing CLI feature; workaround is manual `--compare` calculation
- **Effort**: Small - Pre-filter existing issue list by date
- **Risk**: Low - Additive arguments, default behavior unchanged
- **Breaking Change**: No

## Labels

`feature`, `cli`, `history`

## Status

**Completed** | Created: 2026-03-19 | Completed: 2026-03-21 | Priority: P4

## Resolution

**Completed**: 2026-03-21

Added `--since` and `--until` date range arguments to `ll-history analyze`:

- Added `--since DATE` and `--until DATE` to `analyze_parser` in `scripts/little_loops/cli/history.py`
- `--compare` and `--since` are mutually exclusive via argparse group; `--until` can be combined with either (but only makes practical sense with `--since` or alone)
- Issues without a `completed_date` are excluded from filtered results when either flag is set
- Date format (`YYYY-MM-DD`) matches `ll-history export --since` for consistency
- 5 new tests covering filtering, date range, and mutual exclusion (TDD Red→Green)


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/cli/history.py` exists; `analyze_parser` confirmed at lines 66–101 (matches issue)
- `analyze` subcommand has only `--compare DAYS` (line 94–101); no `--since`/`--until` present
- `export` subcommand has `--since` at line 134–140, confirming the asymmetry described
- All claims accurate; feature gap is real and not yet implemented

## Session Log
- `/ll:manage-issue` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-03-21T21:19:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c41effb-ccb4-4986-b94e-1346cad60324.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:12:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
