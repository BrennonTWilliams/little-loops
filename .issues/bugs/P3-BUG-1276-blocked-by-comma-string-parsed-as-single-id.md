---
id: BUG-1276
type: BUG
priority: P3
title: "blocked_by comma-separated string parsed as single unknown ID"
status: backlog
captured_at: "2026-04-24T21:09:29Z"
discovered_date: "2026-04-24"
discovered_by: capture-issue
---

# BUG-1276: blocked_by comma-separated string parsed as single unknown ID

## Summary

`ll-issues clusters` outputs messages like "Issue X blocked by unknown issues Issue Y and Issue Z" when the `blocked_by` frontmatter field is a comma-separated YAML string (e.g., `blocked_by: "ENH-419, ENH-422, ENH-423"`) rather than a proper YAML list. The dependency checker receives the whole string as a single ID and cannot match it against known issues.

## Current Behavior

`ll-issues clusters` (and any command invoking `build_dependency_graph`) reports "blocked by unknown issues ENH-419, ENH-422, ENH-423" — treating the entire comma-separated string as one opaque ID rather than splitting it into three individual issue IDs.

## Root Cause

**File**: `scripts/little_loops/issue_parser.py:436`

```python
fm_ids = [fm_val] if isinstance(fm_val, str) else list(fm_val)
```

When `blocked_by` is a string (as YAML allows for scalars), the code wraps the entire value in a list — e.g., `["ENH-419, ENH-422, ENH-423"]` — instead of splitting on commas to produce `["ENH-419", "ENH-422", "ENH-423"]`.

## Steps to Reproduce

1. Write an issue with frontmatter `blocked_by: "ENH-419, ENH-422, ENH-423"` (scalar string, not a list).
2. Run `ll-issues clusters` (or any command that invokes `build_dependency_graph`).
3. Observe: "blocked by unknown issues ENH-419, ENH-422, ENH-423" — treated as one opaque ID.

## Expected Behavior

When `blocked_by` is a scalar string, split on commas and strip whitespace to extract individual issue IDs, matching the behavior of a proper YAML list.

## Proposed Solution

```python
if isinstance(fm_val, str):
    fm_ids = [id.strip() for id in fm_val.split(",") if id.strip()]
else:
    fm_ids = list(fm_val)
```

Apply the same fix to the `blocks` field for consistency (same code path handles both).

## Implementation Steps

1. Update `issue_parser.py` — fix comma-string parsing for `blocked_by` and `blocks` fields in `build_dependency_graph`
2. Apply the same split-and-strip fix to the `blocks` field (same code path)
3. Add unit tests covering: scalar comma string, proper YAML list, and mixed-whitespace variants
4. Run test suite to confirm no regressions

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `build_dependency_graph` function, `blocked_by`/`blocks` parsing (line ~436)

### Dependent Files (Callers/Importers)
- TBD — `grep -r "build_dependency_graph" scripts/`

### Similar Patterns
- Check `issue_parser.py` for other `isinstance(fm_val, str)` patterns — apply same split fix for consistency

### Tests
- `scripts/tests/` — add `test_blocked_by_comma_string` and `test_blocks_comma_string` test cases

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [ ] `ll-issues clusters` resolves individual IDs from a comma-separated `blocked_by` string
- [ ] `ll-issues clusters` resolves individual IDs from a comma-separated `blocks` string
- [ ] Proper YAML lists (`blocked_by: [ENH-419, ENH-422]`) continue to work unchanged
- [ ] Unit test: both scalar string and list forms produce identical `IssueInfo.blocked_by`

## Impact

- **Priority**: P3 — Affects dependency graph display; workaround exists (use YAML list syntax)
- **Effort**: Small — Single-line fix applied to two fields; one unit test to add
- **Risk**: Low — Well-isolated parsing change; proper YAML list form is unaffected
- **Breaking Change**: No

## Labels

`bug`, `issue-parser`, `dependency-graph`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

---

## Session Log
- `/ll:format-issue` - 2026-04-24T21:11:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/baf6354e-f895-4724-a14b-8b08bc94c4ee.jsonl`
- `/ll:capture-issue` - 2026-04-24T21:09:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6dacfdc-344c-4b81-a7b8-929038236222.jsonl`
