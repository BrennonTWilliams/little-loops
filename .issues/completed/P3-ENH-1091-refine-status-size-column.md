---
id: ENH-1091
type: ENH
priority: P3
discovered_date: 2026-04-12
discovered_by: issue-size-review
parent_issue: ENH-1089
confidence_score: 100
outcome_confidence: 70
size: Very Large
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

- `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 10` constant alongside `_SCORE_WIDTH`, `_CONF_WIDTH`, `_TOTAL_WIDTH` (10 chars fits "Very Large" without truncation; 6 would silently truncate to "Very L")
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified line numbers and flagged one implementation discrepancy:_

**Confirmed accurate line numbers:**
- `issue_parser.py:236` — `outcome_confidence: int | None = None`; insert `size: str | None = None` after this line (it becomes line 237 post-insertion). `testable` is currently line 237.
- `issue_parser.py:337` — `discovered_by = frontmatter.get("discovered_by")` — exact pattern for string-field frontmatter reads. Follow immediately below with `size = frontmatter.get("size")`.
- `refine_status.py:62` — `_STATIC_COLUMN_SPECS` dict starts at line 62 (issue says 60; correct value is 62).
- `refine_status.py:75–88` — `_DEFAULT_STATIC_COLUMNS` and `_POST_CMD_STATIC` confirmed. `_POST_CMD_STATIC = frozenset(["ready", "confidence", "total"])` contains score columns that render *after* the dynamic command block. `size` is a frontmatter string field, not a post-cmd score — **do not add to `_POST_CMD_STATIC`** (issue instruction at line 88 is correct).
- `refine_status.py:118–132` — `_truncate()` calls `text.ljust(width)[:width]` (left) or `text.rjust(width)[:width]` (right). This is hard truncation at column width.

**Width discrepancy — `_SIZE_WIDTH = 6` truncates "Very Large":**
The valid `size` values documented in the proposed solution are `Small` (5), `Medium` (6), `Large` (5), `Very Large` (10). With `_SIZE_WIDTH = 6`, the value "Very Large" hard-truncates to `"Very L"` via `_truncate()`.

_Recommended fix_: Use `_SIZE_WIDTH = 10` instead of 6. This fits all four values without truncation and keeps column-header "size" (4 chars) well within the width.

**Config schema:** `config-schema.json` `refine_status.columns` uses `"type": "string"` items (no enum constraint) — valid column names are documented in the `description` string only. Adding `"size"` is a description-text update, not a schema-structure change.

**`_cell_value` pattern for string vs. numeric fields:** The `confidence` branch at line 404 uses `if issue.outcome_confidence is not None` (numeric guard). For the string `size` field, use `if issue.size` (truthy guard) to handle both `None` and empty string: `return issue.size if issue.size else "—"`.

**Test JSON output test:** `test_json_output_is_jsonl` spans lines 686–728; the assertion block is at lines 722–728. Add `assert record["size"] is None` (or `== "Large"`) inside that assertion block.

### Tests

- `scripts/tests/test_refine_status.py:19-53` — `_make_issue` helper needs `size: str | None = None` kwarg; follow `confidence_score` parameter pattern
- `scripts/tests/test_refine_status.py:248-280` — `test_ready_and_outconf_columns` is the direct test pattern to model the new `size` column test after
- `scripts/tests/test_refine_status.py:722-728` — existing JSON output test asserts specific field names; add `assert record["size"] == ...` once `size` is in JSON output records
- `scripts/tests/test_issue_parser.py` — add test for `size` frontmatter field parsing (present and absent)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_status.py:594-645` — `test_table_row_width_fits_terminal` asserts no row exceeds 120 cols; inserting `_SIZE_WIDTH=10` into default column set may cause overflow — verify/update thresholds after implementation
- `scripts/tests/test_refine_status.py:1228-1272` — `test_json_flag_fields` checks specific JSON field presence; add `assert "size" in record`
- `scripts/tests/test_refine_status.py:1562-1607` — `test_json_mode_unaffected_by_narrow_terminal` asserts a specific set of fields in JSON mode; add `"size"` to that asserted set
- `scripts/tests/test_refine_status.py:~1340-1660` — `TestRefineStatusColumnElision` class: multiple tests assert exact column visibility at specific terminal widths (80/100/120 cols); elision cascade shifts when `_SIZE_WIDTH=10` is inserted — **likely to break**, update width thresholds post-implementation

## Implementation Steps

1. Edit `scripts/little_loops/issue_parser.py:236` — add `size: str | None = None` to `IssueInfo`.
2. Edit `scripts/little_loops/issue_parser.py:264-265` — add `"size": self.size` in `to_dict`.
3. Edit `scripts/little_loops/issue_parser.py:286-287` — add `size=data.get("size")` in `from_dict`.
4. Edit `scripts/little_loops/issue_parser.py:336-352` — add `size = frontmatter.get("size")` in `parse_file`; pass `size=size` to `IssueInfo(...)`.
5. Edit `scripts/little_loops/cli/issues/refine_status.py:18-22` — add `_SIZE_WIDTH = 10` (not 6; see Integration Map research note on truncation).
6. Edit `scripts/little_loops/cli/issues/refine_status.py:60-72` — add `"size"` to `_STATIC_COLUMN_SPECS`.
7. Edit `scripts/little_loops/cli/issues/refine_status.py:75-96` — insert `"size"` in `_DEFAULT_STATIC_COLUMNS` and `_DEFAULT_ELIDE_ORDER`.
8. Edit `scripts/little_loops/cli/issues/refine_status.py:388-409` — add `"size"` branch in `_cell_value`.
9. Edit `scripts/little_loops/cli/issues/refine_status.py:288-323` — add `"size": issue.size` to JSON output dicts.
10. Edit `config-schema.json:674-692` — add `"size"` to column enum.
11. Update `docs/reference/API.md`, `docs/reference/CONFIGURATION.md:489`, `docs/reference/CLI.md:486`, `docs/reference/CLI.md:499`.
12. Update `scripts/tests/test_refine_status.py` — add `size` kwarg to `_make_issue`, add column test, add JSON assertion.
13. Add test to `scripts/tests/test_issue_parser.py` for `size` frontmatter parsing.

### Wiring Phase (added by `/ll:wire-issue`)

_These test touchpoints were identified by wiring analysis and must be included in the implementation:_

14. Update `scripts/tests/test_refine_status.py:~1340-1660` (`TestRefineStatusColumnElision`) — adjust all width-threshold assertions after `_SIZE_WIDTH=10` shifts the elision cascade; run tests after Step 7 to identify exact breakage
15. Update `scripts/tests/test_refine_status.py:594-645` (`test_table_row_width_fits_terminal`) — verify 120-col row budget still holds; adjust expected width or the test's terminal-width fixture if needed
16. Update `scripts/tests/test_refine_status.py:1228-1272` (`test_json_flag_fields`) — add `assert "size" in record`
17. Update `scripts/tests/test_refine_status.py:1562-1607` (`test_json_mode_unaffected_by_narrow_terminal`) — add `"size"` to the asserted field tuple

## Impact

- **Scope**: Small — additive changes to parser + CLI; no behavior changes to existing columns
- **Risk**: Low — missing `size` field gracefully shows `—`
- **Users**: Anyone using `ll-issues refine-status` for issue triage or sprint prep

## Labels

`enhancement`, `ll-issues`, `refine-status`, `frontmatter`, `cli`

## Session Log
- `/ll:ready-issue` - 2026-04-13T04:40:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/185664a0-98da-40d3-8287-f23286360928.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40bdadde-d5c3-4462-9452-ca9d883de748.jsonl`
- `/ll:wire-issue` - 2026-04-13T04:17:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58e79566-1346-4c60-b681-953ad7d4f94b.jsonl`
- `/ll:refine-issue` - 2026-04-13T04:04:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2aef20a-db49-458b-b9d6-4f1a97c648d9.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24bfa590-00d2-4387-9ba6-799d36510a45.jsonl`

- `/ll:manage-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Resolution

**State**: completed
**Resolved**: 2026-04-12

### Changes Made

- `scripts/little_loops/issue_parser.py` — Added `size: str | None = None` to `IssueInfo` dataclass; wired through `to_dict`, `from_dict`, and `parse_file` (reads `frontmatter.get("size")`)
- `scripts/little_loops/cli/issues/refine_status.py` — Added `_SIZE_WIDTH = 10`, `"size"` entry in `_STATIC_COLUMN_SPECS`, inserted `"size"` in `_DEFAULT_STATIC_COLUMNS` (after `priority`, before `title`), added `"size"` to `_DEFAULT_ELIDE_ORDER` (after `fmt`, before `confidence`), added `"size"` branch in `_cell_value` with em-dash fallback, added `"size": issue.size` to both JSON output paths
- `config-schema.json` — Added `size` to `columns` description
- `docs/reference/API.md` — Documented `size: str | None` on `IssueInfo`
- `docs/reference/CONFIGURATION.md` — Added `size` to valid column names and updated default elide_order
- `docs/reference/CLI.md` — Added `size` to refine-status column list and elide sequence description
- `scripts/tests/test_issue_parser.py` — Added `TestIssueInfoSize` class (9 tests)
- `scripts/tests/test_refine_status.py` — Added `size` kwarg to `_make_issue`, added 3 new column tests, updated 3 JSON assertion tests, fixed 2 elision tests

### Verification

- 4720 tests pass, 0 failures
- `ruff check`: all checks passed
- `mypy`: no new errors
