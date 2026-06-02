---
id: BUG-1485
type: BUG
priority: P4
status: done
title: find_issues and skip.py missing `completed` in terminal status filter
captured_at: '2026-05-15T22:28:07Z'
completed_at: 2026-05-16T06:41:54Z
discovered_date: '2026-05-15'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1485: `find_issues` and `skip.py` missing `completed` in terminal status filter

## Summary

`find_issues()` in `issue_parser.py` and the skip command in `cli/issues/skip.py` both filter terminal statuses as `("done", "cancelled", "deferred")` but omit `"completed"`. Issues with `status: completed` in their frontmatter pass through both filters as if they were active issues.

## Current Behavior

`find_issues()` at `issue_parser.py:856`:
```python
if info.status in ("done", "cancelled", "deferred"):
    continue
```

`skip.py` at `cli/issues/skip.py:40`:
```python
if issue_info.status in ("done", "cancelled", "deferred"):
    ...
```

Both omit `"completed"`. An issue with `status: completed` in a type-based directory (`bugs/`, `features/`, `enhancements/`, `epics/`) would be included by `find_issues()` and would be skippable via the `skip` command.

## Expected Behavior

`"completed"` should be treated identically to `"done"` — excluded from active issue results and rejected by the skip command as a terminal issue.

## Motivation

The filter is incomplete. While active type-based directories currently use `status: done` for terminal issues (not `completed`), the `completed` value does appear in issue frontmatter (notably in the legacy `.issues/completed/` directory). If any issue in an active type directory ever receives `status: completed` — via automation, migration, or direct edit — it would silently appear as an actionable issue in `ll-issues next-issue` output and elsewhere.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `find_issues()`, filter site at line 870 (the function header / docstring begin around line 856)
- **Cause**: `"completed"` was not included when the terminal status filter was written. The same omission is present in `scripts/little_loops/cli/issues/skip.py:40` inside `cmd_skip()`. A third site, `scripts/little_loops/cli/issues/search.py:138`, has the *inverse* omission (includes `"completed"` but omits `"deferred"`), confirming the tuples drifted because they were copied independently rather than centralized.

## Steps to Reproduce

1. Add `status: completed` to an issue file in `.issues/features/`
2. Run `ll-issues next-issue`
3. Observe the `completed` issue appears as an actionable candidate

## Proposed Solution

Add `"completed"` to both filter tuples:

```python
# issue_parser.py — find_issues()
if info.status in ("done", "cancelled", "deferred", "completed"):
    continue

# cli/issues/skip.py — skip command handler
if issue_info.status in ("done", "cancelled", "deferred", "completed"):
    ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py:870` — `find_issues()` terminal-status tuple (note: the actual line is 870 in current source; issue header references 856, which is the docstring; the filter site is line 870)
- `scripts/little_loops/cli/issues/skip.py:40` — `cmd_skip()` terminal-status guard

### Dependent Files (Callers/Importers)
- Any caller of `find_issues()` benefits automatically: `ll-auto`, `ll-sprint`, `ll-parallel`, `ll-issues next-issue`

### Similar Patterns
- `scripts/little_loops/cli/issues/search.py:138` — **related but distinct inconsistency**: uses `("done", "cancelled", "completed")` and omits `"deferred"` (the inverse of this bug). Out of scope for this fix, but flagged for follow-up — the codebase has three terminal-status sites with three different tuples, and a future enhancement (see [[P2-ENH-1425-decouple-status-dependency-tools]]) should consolidate them onto a shared constant.
- `.issues/enhancements/P2-ENH-1418-decouple-status-discovery-lifecycle-history.md:183` — open ENH that documents the "canonical inline filter" pattern with the same `("done", "cancelled", "deferred")` tuple. If this bug is fixed first, ENH-1418's canonical-pattern example should be updated to include `"completed"` so future implementers don't re-introduce the omission.

### Tests
- `scripts/tests/test_issue_parser.py:1056` — `test_find_issues_skips_status_done` is the direct template for a new `test_find_issues_skips_status_completed`
- `scripts/tests/test_issue_parser.py:1081` — `test_find_issues_skips_status_deferred` is a second template showing the same pattern for another terminal status
- `scripts/tests/test_issues_cli.py:3328` — `test_skip_done_issue_returns_error` is the template for a new `test_skip_completed_issue_returns_error`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/enhancements/P2-ENH-1418-decouple-status-discovery-lifecycle-history.md:183` — contains a "canonical inline filter" example `("done", "cancelled", "deferred")` that will become stale once this fix is applied; update to include `"completed"` so future implementers don't re-introduce the omission [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Edit `scripts/little_loops/issue_parser.py:870` — change `("done", "cancelled", "deferred")` to `("done", "cancelled", "deferred", "completed")` inside `find_issues()`.
2. Edit `scripts/little_loops/cli/issues/skip.py:40` — apply the same change inside `cmd_skip()`.
3. Add `test_find_issues_skips_status_completed` in `scripts/tests/test_issue_parser.py` next to line 1056, modeled directly on `test_find_issues_skips_status_done` — same fixture shape, just `status: completed` in the frontmatter.
4. Add `test_skip_completed_issue_returns_error` in `scripts/tests/test_issues_cli.py` next to line 3328, modeled on `test_skip_done_issue_returns_error`.
5. Verify: `python -m pytest scripts/tests/test_issue_parser.py scripts/tests/test_issues_cli.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `.issues/enhancements/P2-ENH-1418-decouple-status-discovery-lifecycle-history.md` at the "canonical inline filter" example near line 183 — change the tuple from `("done", "cancelled", "deferred")` to `("done", "cancelled", "deferred", "completed")` so the documented pattern stays in sync with the fix

## Impact

- **Priority**: P4 - Low impact today; active dirs use `status: done`, not `completed`
- **Effort**: Small - two one-line edits plus a test
- **Risk**: Low - additive filter, no behavior change for current issue files
- **Breaking Change**: No

## Related Key Documentation

_No documents linked._

## Labels

`bug`, `issue-parser`, `captured`

## Status

**Done** | Created: 2026-05-15 | Completed: 2026-05-16 | Priority: P4

## Resolution

Added `"completed"` to the terminal-status filter tuples in `find_issues()` (`issue_parser.py:870`) and `cmd_skip()` (`cli/issues/skip.py:40`). Updated ENH-1418's canonical-pattern documentation to match. Added regression tests `test_find_issues_skips_status_completed` and `test_skip_completed_issue_returns_error`. Full `test_issue_parser.py` + `test_issues_cli.py` suites pass (300 tests); ruff clean.

---

## Session Log
- `/ll:manage-issue` - 2026-05-16T06:41:54Z - `0010190c-509e-453e-bb85-c00575d1e590.jsonl`
- `/ll:ready-issue` - 2026-05-16T06:40:06 - `047c7021-1a76-4abe-89a6-612cac74a6af.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `6ad5d116-4ca4-4f05-b0f8-90970d1a318e.jsonl`
- `/ll:wire-issue` - 2026-05-16T06:38:01 - `0fa462fb-8f12-4e50-afe0-f85814c87465.jsonl`
- `/ll:refine-issue` - 2026-05-16T06:32:32 - `87e1a073-7fe2-4ff0-abef-79768331f556.jsonl`
- `/ll:format-issue` - 2026-05-15T22:31:32 - `ee7de6e9-997b-4bb6-a6ae-e81063eeaa11.jsonl`
- `/ll:capture-issue` - 2026-05-15T22:28:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c83fb486-18e2-416c-9520-e73ea7fb0cda.jsonl`
