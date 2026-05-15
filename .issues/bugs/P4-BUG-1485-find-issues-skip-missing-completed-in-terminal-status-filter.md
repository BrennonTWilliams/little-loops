---
id: BUG-1485
type: BUG
priority: P4
status: open
title: "find_issues and skip.py missing `completed` in terminal status filter"
captured_at: "2026-05-15T22:28:07Z"
discovered_date: "2026-05-15"
discovered_by: capture-issue
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
- **Anchor**: `find_issues()` at line 856
- **Cause**: `"completed"` was not included when the terminal status filter was written. The same omission is present in `scripts/little_loops/cli/issues/skip.py` at line 40.

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
- `scripts/little_loops/issue_parser.py` — line 856, `find_issues()`
- `scripts/little_loops/cli/issues/skip.py` — line 40

### Dependent Files (Callers/Importers)
- Any caller of `find_issues()` benefits automatically (ll-auto, ll-sprint, ll-parallel, next-issue)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` — add test fixture with `status: completed` and assert it's excluded from `find_issues()` results

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Edit `issue_parser.py:856` — add `"completed"` to the tuple
2. Edit `skip.py:40` — add `"completed"` to the tuple
3. Add a test asserting `status: completed` issues are excluded from `find_issues()` output

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

**Open** | Created: 2026-05-15 | Priority: P4

---

## Session Log
- `/ll:format-issue` - 2026-05-15T22:31:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee7de6e9-997b-4bb6-a6ae-e81063eeaa11.jsonl`
- `/ll:capture-issue` - 2026-05-15T22:28:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c83fb486-18e2-416c-9520-e73ea7fb0cda.jsonl`
