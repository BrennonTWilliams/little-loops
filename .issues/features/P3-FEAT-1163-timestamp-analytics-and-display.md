---
id: FEAT-1163
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
confidence_score: 98
outcome_confidence: 57
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 10
size: Very Large
completed_at: 2026-04-18T00:00:00Z
---

# FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Summary

Update `ll-issues show`, `ll-issues search/list`, and `ll-history` to read and use `captured_at` and `completed_at` frontmatter fields when present, enabling sub-day resolution in display and analytics.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Once FEAT-1161 and FEAT-1162 populate these fields, the display and analytics layer must consume them. This issue is intentionally downstream — implement after FEAT-1161 and FEAT-1162 are merged.

### Upstream Status (verified 2026-04-18)

Both upstream parents are **merged** — this issue is unblocked.

- `captured_at` writers: `skills/capture-issue/SKILL.md:235` and `skills/capture-issue/templates.md:136` (LLM-driven, no Python writer).
- `completed_at` writers: `scripts/little_loops/issue_lifecycle.py:622` and `:698` (FSM completion paths); `scripts/little_loops/parallel/orchestrator.py:1186` (parallel orchestrator).
- Current readers: **none** in `scripts/little_loops/` — this issue fills that gap.

### Coercion Caveat

`parse_frontmatter(content, coerce_types=True)` in `scripts/little_loops/frontmatter.py:18-80` only coerces digit-only strings to `int` (see branch at line 73). ISO 8601 datetime strings like `"2026-04-18T10:30:00Z"` are returned as plain `str`. Readers must call `datetime.fromisoformat(...)` manually (strip trailing `Z` if not using Python 3.11+ tolerant parser). This mirrors the existing `_parse_discovered_date` pattern at `parsing.py:291-306` which manually calls `date.fromisoformat(value)`.

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
- `scripts/little_loops/issue_history/summary.py:47,104,109-110` — groups by `issue.completed_date` (line 110 is the grouping assignment inside a loop that begins at 109)
- `scripts/little_loops/cli/history.py:219-228` — full `--since/--until` filter block (line parses `since_date`/`until_date` at 219-220, comprehension body at 225-227)

**Recommended approach**: keep `CompletedIssue.discovered_date` / `completed_date` as `date` (no promotion) to avoid the fan-out above. Add separate `captured_at: datetime | None = None` and `completed_at: datetime | None = None` fields; analytics code prefers the sub-day timestamps when present and falls back to the existing date fields otherwise.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/API.md:1560-1568` — add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` to the `CompletedIssue` dataclass code block
7. Update `docs/reference/CLI.md:426-434` — add timestamp fields to `ll-issues show` card contents description; update `:456-462` to note `captured_at` is checked before `discovered_date` when resolving `--date-field discovered`
8. Update `docs/reference/OUTPUT_STYLING.md:110-134` — add `Captured at` / `Completed at` rows to the `_render_card` ASCII layout diagram and Detail fields table
9. Rewrite `scripts/tests/test_issue_parser.py:521-541` — `test_parse_file_ignores_captured_at` must become a positive assertion that `captured_at` is read; the fixture at `scripts/tests/fixtures/issues/bug-with-frontmatter.md` already provides the input
10. Add `TestParseDiscoveredDate` class to `scripts/tests/test_issue_history_parsing.py` — no test coverage exists for `_parse_discovered_date(fm)`; mirror the `TestParseCompletionDate` structure starting at line 105
11. Update `scripts/tests/test_issue_history_summary.py:27-57` — `TestCompletedIssue.test_to_dict` must assert new `captured_at`/`completed_at` keys once `to_dict()` is extended

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/list_cmd.py:28` — imports `_parse_discovered_date` directly from `search.py`; silently inherits the `captured_at`-first behavior change without code modification — `ll-issues list --sort created` output will also change
- `scripts/little_loops/issue_history/__init__.py:134` — re-exports `CompletedIssue` in `__all__`; adding fields to `to_dict()` changes the public JSON API shape for callers using the package's public interface

## Tests

- `scripts/tests/test_issue_history_parsing.py` — add fixture with `completed_at` in frontmatter; assert it takes priority over body regex (`TestParseCompletionDate` at lines 105-165); add tests for `_parse_discovered_date` preferring `captured_at`
  - **Replace**: `test_parse_ignores_captured_at` at lines 93-102 currently asserts `captured_at` is ignored. This test will break once readers consume the field — rewrite it to assert `captured_at` is read and populates the new dataclass field.
- `scripts/tests/test_issues_cli.py` — add `ll-issues show` test cases for `captured_at`/`completed_at` in `TestIssuesCLIShow` (starting line 1051); add JSON output test following pattern of `test_show_json_includes_dim_scores` (line 1735); update `test_show_new_fields_absent_gracefully` (line 1493)
- `scripts/tests/test_issues_search.py` — add test case asserting `captured_at` is surfaced when present
- `scripts/tests/test_issue_history_advanced_analytics.py` — ~30+ `CompletedIssue` construction sites; only break if new fields are non-optional; safe with `None` defaults
- `scripts/tests/test_issue_history_summary.py` — ~7 `CompletedIssue` construction sites; same concern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:521-541` — **WILL BREAK**: `test_parse_file_ignores_captured_at` asserts `captured_at` is ignored; rewrite to assert new `captured_at` field is parsed into `IssueParser.parse_file()` result (fixture `scripts/tests/fixtures/issues/bug-with-frontmatter.md:2` already has `captured_at: 2026-01-20T10:30:00Z`)
- `scripts/tests/test_issue_history_summary.py:27-57` — **WILL BREAK**: `TestCompletedIssue.test_to_dict` asserts exact `to_dict()` key set; must be updated when `captured_at`/`completed_at` keys are added to `to_dict()`
- `scripts/tests/test_issue_history_analysis.py` — `CompletedIssue` constructions at lines 69, 76, 94, 119; all keyword-arg form without new fields — safe with `None` defaults, no code change needed but worth noting
- `scripts/tests/test_doc_synthesis.py:97` — `CompletedIssue` construction in `_make_issue()` helper; safe with `None` defaults, no code change needed
- `scripts/tests/test_issue_history_parsing.py` — **GAP**: no `TestParseDiscoveredDate` class exists anywhere; add test class mirroring `TestParseCompletionDate` (line 105) to cover `_parse_discovered_date(fm)` with `captured_at` preference logic

### Implementation Pattern References

- **Rendering optional fields**: see `show.py:283-297` (meta line conditional append) and `show.py:333-341` (detail mid-border section). Add `captured_at`/`completed_at` to `detail_mid_parts` or a new detail row, guarded by `if fields.get(...)`.
- **Reading date from frontmatter**: mirror `_parse_discovered_date` at `parsing.py:291-306` — `fm.get("captured_at")`, manual `datetime.fromisoformat(...)` inside `try/except ValueError`, return `None` on failure.
- **`to_dict` serialization**: follow existing pattern at `models.py:33-34` — `value.isoformat() if value else None`.
- **JSON output**: `_parse_card_fields` returns `str | None` for all values; `print_json(fields)` at `show.py:446-447` emits them verbatim. Test assertions use string values, not coerced types — see `test_show_json_includes_dim_scores:1735-1774`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1560-1568` — `CompletedIssue` dataclass field list in Python code block; add `captured_at` and `completed_at` field entries
- `docs/reference/CLI.md:426-434` — prose description of `ll-issues show` card output ("ID, title, priority, ..."); add timestamp fields to the enumeration
- `docs/reference/CLI.md:456-462` — `--date-field discovered` flag description; note that `captured_at` is checked first as a higher-resolution alternative before falling back to `discovered_date`
- `docs/reference/OUTPUT_STYLING.md:110-134` — `_render_card` ASCII layout diagram and Detail fields table; add `Captured at` / `Completed at` rows (rendered conditionally when present)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-18_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 57/100 → LOW

### Outcome Risk Factors
- **12 files, 4 subsystems** — despite shallow/additive changes, volume elevates execution risk; run `python -m pytest scripts/tests/ -x` after each subsystem to catch regressions early
- **Two explicitly flagged WILL-BREAK tests**: `test_parse_file_ignores_captured_at` (test_issue_parser.py:521) and `TestCompletedIssue.test_to_dict` (test_issue_history_summary.py:27) must be rewritten before CI passes — handle these first to establish a green baseline
- **CompletedIssue: 56 importing files** — additive None-defaulted fields are safe, but `to_dict()` output shape changes; any test asserting exact key sets will need updating (issue calls out test_issue_history_summary.py:27-57 explicitly)

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-18
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1179: Display `captured_at` / `completed_at` in `ll-issues show`
- FEAT-1180: Prefer `captured_at` in `ll-issues search/list` Date Resolution
- FEAT-1181: `ll-history` Analytics and `CompletedIssue` Timestamp Support

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T21:27:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
- `/ll:wire-issue` - 2026-04-18T21:22:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80e14588-3104-405e-a8e6-c53efd5b4b39.jsonl`
- `/ll:refine-issue` - 2026-04-18T21:15:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83c799cc-9c6b-4537-928d-d6776c2531bf.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23c815a9-0c17-406e-a877-05e00b8d0f7d.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
