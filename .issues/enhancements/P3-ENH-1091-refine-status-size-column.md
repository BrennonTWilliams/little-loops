---
id: ENH-1091
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: issue-size-review
parent_issue: ENH-1089
---

# ENH-1091: ll-issues refine-status shows Size column

## Summary

`ll-issues refine-status` should display a `Size` column in its tabular CLI output by reading the `size` frontmatter field written by `/ll:issue-size-review`. When the field is absent (not yet reviewed), the column shows `—`.

## Parent Issue

Decomposed from ENH-1089: issue-size-review writes size frontmatter, show in refine-status

## Current Behavior

`ll-issues refine-status` renders a table of issues with refinement status columns, but has no `Size` column. Size data from `/ll:issue-size-review` is invisible in CLI workflows.

## Expected Behavior

After `/ll:issue-size-review` (ENH-1090) writes `size` to frontmatter, `refine-status` reads it and renders a `Size` column:

```
 ID       | Priority | Size   | Confidence | Status
----------+----------+--------+------------+--------
 ENH-1089 | P3       | Large  | -          | active
 BUG-1079 | P3       | Small  | high       | active
 ENH-1090 | P3       | —      | -          | active
```

The `size` field is populated from parsed frontmatter by `IssueParser`. The column appears after `priority` and before `title` in the default column order. It is low priority in the elide order (drops before `confidence`).

## Proposed Solution

### Part A — `IssueParser` / `IssueInfo`

Add `size: str | None = None` field to the `IssueInfo` dataclass and wire it through the parser:

- `scripts/little_loops/issue_parser.py:236` — add `size: str | None = None` field to `IssueInfo` (after `outcome_confidence`)
- `scripts/little_loops/issue_parser.py:264-265` — add `"size": self.size` in `to_dict`
- `scripts/little_loops/issue_parser.py:286-287` — add `size=data.get("size")` in `from_dict`
- `scripts/little_loops/issue_parser.py:336-352` — add `size = frontmatter.get("size")` in `IssueParser.parse_file`; pass `size=size` to `IssueInfo(...)`. Follow same pattern as `discovered_by = frontmatter.get("discovered_by")` at line 337.

### Part B — `refine_status.py` column

- `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 6` constant alongside `_SCORE_WIDTH`, `_CONF_WIDTH`, `_TOTAL_WIDTH` (6 chars fits "Large " with padding)
- `scripts/little_loops/cli/issues/refine_status.py:60-72` — add `"size": (_SIZE_WIDTH, "size", False)` entry in `_STATIC_COLUMN_SPECS`
- `scripts/little_loops/cli/issues/refine_status.py:75-85` — insert `"size"` in `_DEFAULT_STATIC_COLUMNS` after `"priority"`, before `"title"`
- `scripts/little_loops/cli/issues/refine_status.py:88` — do NOT add `"size"` to `_POST_CMD_STATIC`
- `scripts/little_loops/cli/issues/refine_status.py:96` — add `"size"` to `_DEFAULT_ELIDE_ORDER` (low priority, drops before `confidence`)
- `scripts/little_loops/cli/issues/refine_status.py:288-323` — add `"size": issue.size` to JSON output records in both `--json` array and `--format json` NDJSON paths
- `scripts/little_loops/cli/issues/refine_status.py:388-409` — add `if col == "size": return issue.size if issue.size else "—"` branch in `_cell_value` (follow existing `"confidence"` branch pattern at line 404)

### Part C — Config schema + docs

- `config-schema.json:674-692` — add `"size"` to valid `refine_status.columns` names
- `docs/reference/API.md` — add `size` as a documented frontmatter field with valid values (`Small`, `Medium`, `Large`, `Very Large`)
- `docs/reference/CONFIGURATION.md:489` — valid column names list reads `id, priority, title, source, norm, fmt, ready, confidence, total`; add `size`
- `docs/reference/CLI.md:486` — `refine-status` column list description omits `size`; add it
- `docs/reference/CLI.md:499` — elide sequence description (`source → norm → fmt → confidence → ready → total`) will be stale once `size` is in `_DEFAULT_ELIDE_ORDER`; update

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass, `to_dict`, `from_dict`, `parse_file`
- `scripts/little_loops/cli/issues/refine_status.py` — width constant, column specs, defaults, elide order, `_cell_value`, JSON output
- `config-schema.json` — `refine_status.columns` enum
- `docs/reference/API.md` — frontmatter field docs
- `docs/reference/CONFIGURATION.md` — valid column names list
- `docs/reference/CLI.md` — refine-status column list and elide sequence

### Dependent Files (Read-only)

- `scripts/little_loops/frontmatter.py` — no changes needed; `parse_frontmatter` already returns arbitrary fields

### Similar Patterns

- `scripts/little_loops/issue_parser.py:337` — `discovered_by = frontmatter.get("discovered_by")` is the exact string field read pattern
- `scripts/little_loops/cli/issues/refine_status.py:404` — existing `"confidence"` branch in `_cell_value` shows the em-dash fallback pattern

### Tests

- `scripts/tests/test_refine_status.py:19-53` — `_make_issue` helper needs `size: str | None = None` kwarg; follow `confidence_score` parameter pattern
- `scripts/tests/test_refine_status.py:248-280` — `test_ready_and_outconf_columns` is the direct test pattern to model the new `size` column test after
- `scripts/tests/test_refine_status.py:722-728` — existing JSON output test asserts specific field names; add `assert record["size"] == ...` once `size` is in JSON output records
- `scripts/tests/test_issue_parser.py` — add test for `size` frontmatter field parsing (present and absent)

## Implementation Steps

1. Edit `scripts/little_loops/issue_parser.py:236` — add `size: str | None = None` to `IssueInfo`.
2. Edit `scripts/little_loops/issue_parser.py:264-265` — add `"size": self.size` in `to_dict`.
3. Edit `scripts/little_loops/issue_parser.py:286-287` — add `size=data.get("size")` in `from_dict`.
4. Edit `scripts/little_loops/issue_parser.py:336-352` — add `size = frontmatter.get("size")` in `parse_file`; pass `size=size` to `IssueInfo(...)`.
5. Edit `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 6`.
6. Edit `scripts/little_loops/cli/issues/refine_status.py:60-72` — add `"size"` to `_STATIC_COLUMN_SPECS`.
7. Edit `scripts/little_loops/cli/issues/refine_status.py:75-96` — insert `"size"` in `_DEFAULT_STATIC_COLUMNS` and `_DEFAULT_ELIDE_ORDER`.
8. Edit `scripts/little_loops/cli/issues/refine_status.py:388-409` — add `"size"` branch in `_cell_value`.
9. Edit `scripts/little_loops/cli/issues/refine_status.py:288-323` — add `"size": issue.size` to JSON output dicts.
10. Edit `config-schema.json:674-692` — add `"size"` to column enum.
11. Update `docs/reference/API.md`, `docs/reference/CONFIGURATION.md:489`, `docs/reference/CLI.md:486`, `docs/reference/CLI.md:499`.
12. Update `scripts/tests/test_refine_status.py` — add `size` kwarg to `_make_issue`, add column test, add JSON assertion.
13. Add test to `scripts/tests/test_issue_parser.py` for `size` frontmatter parsing.

## Impact

- **Scope**: Small — additive changes to parser + CLI; no behavior changes to existing columns
- **Risk**: Low — missing `size` field gracefully shows `—`
- **Users**: Anyone using `ll-issues refine-status` for issue triage or sprint prep

## Labels

`enhancement`, `ll-issues`, `refine-status`, `frontmatter`, `cli`

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24bfa590-00d2-4387-9ba6-799d36510a45.jsonl`

---

## Status

**State**: active
