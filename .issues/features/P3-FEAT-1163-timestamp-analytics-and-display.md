---
id: FEAT-1163
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
---

# FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Summary

Update `ll-issues show`, `ll-issues search/list`, and `ll-history` to read and use `captured_at` and `completed_at` frontmatter fields when present, enabling sub-day resolution in display and analytics.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Once FEAT-1161 and FEAT-1162 populate these fields, the display and analytics layer must consume them. This issue is intentionally downstream — implement after FEAT-1161 and FEAT-1162 are merged.

## Implementation Steps

### ll-issues show

- **`scripts/little_loops/cli/issues/show.py:101`** — `_parse_card_fields()`: add `captured_at` and `completed_at` extraction from frontmatter (parsed via `parse_frontmatter(content, coerce_types=True)` at line 114).
- **`scripts/little_loops/cli/issues/show.py:259`** — `_render_card()`: render the two fields when present.

### ll-issues search / list

- **`scripts/little_loops/cli/issues/search.py:21-34`** — independent `_parse_discovered_date` regex implementation (not shared with `parsing.py`). Update to check `captured_at` frontmatter before falling back to regex. `list_cmd.py` inherits automatically since it imports from `search.py`.

### ll-history / analytics

- **`scripts/little_loops/issue_history/parsing.py:291-306`** — `_parse_discovered_date(fm)`: update to check `fm.get("captured_at")` as a higher-resolution alternative to `discovered_date`.
- **`scripts/little_loops/issue_history/parsing.py:131-170`** — `_parse_completion_date()`: add first check `fm.get("completed_at")` before the body-regex → git-log fallback chain.

### CompletedIssue dataclass (optional but recommended)

- **`scripts/little_loops/issue_history/models.py:17-37`** — `CompletedIssue`: add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` fields.
- Update `to_dict()` (lines 28-38) to serialize them.
- Use `None` defaults to avoid breaking ~30+ existing construction sites in tests.

### Type alignment (if dataclass fields promoted to datetime)

If `CompletedIssue.completed_date` or related fields are promoted from `date` to `datetime`, add `.date()` coercion at:
- `scripts/little_loops/issue_history/debt.py:255-256,408-413` — `delta = issue.completed_date - issue.discovered_date`
- `scripts/little_loops/issue_history/summary.py:47,104,110` — groups by `issue.completed_date`
- `scripts/little_loops/cli/history.py:225-227` — `--since/--until` filter compares as `date`

## API/Interface

`ll-issues show` renders new fields when present:

```
Captured at:   2026-04-18T14:32:07Z
Completed at:  2026-05-01T09:15:44Z
```

`ll-history` uses sub-day timestamps where available; falls back to `discovered_date` / file mtime when absent.

## Acceptance Criteria

- [ ] `ll-issues show` displays `captured_at` and `completed_at` when present
- [ ] Existing issues without these fields display without errors
- [ ] `ll-history` uses `captured_at` for capture time at sub-day resolution when present
- [ ] `ll-history` uses `completed_at` for completion time at sub-day resolution when present

## Files to Modify

- `scripts/little_loops/cli/issues/show.py` — extract and display both fields in `_parse_card_fields()` (line 101) and `_render_card()` (line 259)
- `scripts/little_loops/cli/issues/search.py` — update `_parse_discovered_date` (lines 21-34) to check `captured_at`
- `scripts/little_loops/issue_history/parsing.py` — update `_parse_discovered_date()` (line 291) and `_parse_completion_date()` (line 131) to prefer frontmatter timestamps
- `scripts/little_loops/issue_history/models.py` — optionally add `captured_at`/`completed_at` fields to `CompletedIssue` with `None` defaults

## Tests

- `scripts/tests/test_issue_history_parsing.py` — add fixture with `completed_at` in frontmatter; assert it takes priority over body regex (`TestParseCompletionDate` at lines 94-165); add tests for `_parse_discovered_date` preferring `captured_at`
- `scripts/tests/test_issues_cli.py` — add `ll-issues show` test cases for `captured_at`/`completed_at` in `TestIssuesCLIShow` (starting line 1051); add JSON output test following pattern of `test_show_json_includes_dim_scores` (line 1735); update `test_show_new_fields_absent_gracefully` (line 1493)
- `scripts/tests/test_issues_search.py` — add test case asserting `captured_at` is surfaced when present
- `scripts/tests/test_issue_history_advanced_analytics.py` — ~30+ `CompletedIssue` construction sites; only break if new fields are non-optional; safe with `None` defaults
- `scripts/tests/test_issue_history_summary.py` — ~7 `CompletedIssue` construction sites; same concern

## Session Log
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
