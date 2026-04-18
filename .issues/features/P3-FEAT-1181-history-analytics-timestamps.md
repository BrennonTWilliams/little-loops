---
id: FEAT-1181
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1163
size: Large
---

# FEAT-1181: `ll-history` Analytics and `CompletedIssue` Timestamp Support

## Summary

Update `ll-history` to use `captured_at` / `completed_at` frontmatter timestamps at sub-day resolution, add optional fields to the `CompletedIssue` dataclass, fix two WILL-BREAK tests, add missing test coverage for `_parse_discovered_date`, and update API/CLI docs.

## Parent Issue

Decomposed from FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Motivation

The analytics layer (`ll-history`) currently falls back to regex and git-log for dates. Frontmatter timestamps are more precise and should be preferred when available. This is the highest-risk child — it touches the most files and has two tests that will break on implementation.

## Implementation Steps

### parsing.py

- **`scripts/little_loops/issue_history/parsing.py:291-306`** — `_parse_discovered_date(fm)`: check `fm.get("captured_at")` first. Parse via `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`; return `None` on failure. Fall through to existing `discovered_date` logic on absence.
- **`scripts/little_loops/issue_history/parsing.py:131-170`** — `_parse_completion_date()`: add first check `fm.get("completed_at")` before the body-regex → git-log fallback chain. Same `fromisoformat` pattern.

### models.py

- **`scripts/little_loops/issue_history/models.py:17-37`** — `CompletedIssue`: add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` fields (use `None` defaults to avoid breaking ~56 importing files).
- Update `to_dict()` (lines 28-38): follow existing `value.isoformat() if value else None` pattern at lines 33-34.
- **Do NOT** promote `discovered_date` / `completed_date` from `date` to `datetime` — this avoids a fan-out of `.date()` coercions in debt.py, summary.py, and history.py. Use separate `captured_at`/`completed_at` datetime fields alongside the existing date fields.

### WILL-BREAK tests (fix these first)

- **`scripts/tests/test_issue_parser.py:521-541`** — `test_parse_file_ignores_captured_at`: currently asserts `captured_at` is ignored. Rewrite to assert the new `captured_at` field is parsed and returned. Fixture `scripts/tests/fixtures/issues/bug-with-frontmatter.md:2` already has `captured_at: 2026-01-20T10:30:00Z`.
- **`scripts/tests/test_issue_history_summary.py:27-57`** — `TestCompletedIssue.test_to_dict`: currently asserts exact `to_dict()` key set. Update to include the new `captured_at` and `completed_at` keys.

### Missing test coverage

- **`scripts/tests/test_issue_history_parsing.py`** — add `TestParseDiscoveredDate` class mirroring `TestParseCompletionDate` (line 105): test `_parse_discovered_date(fm)` with `captured_at` present (should return datetime), absent (should fall back to `discovered_date`), and malformed (should return `None`).

### Documentation

- **`docs/reference/API.md:1560-1568`** — add `captured_at: datetime | None = None` and `completed_at: datetime | None = None` to the `CompletedIssue` dataclass code block.
- **`docs/reference/CLI.md:426-434`** — add `captured_at` and `completed_at` to the `ll-issues show` card contents description.
- **`docs/reference/CLI.md:456-462`** — note that `captured_at` is checked first as higher-resolution alternative before `discovered_date` when resolving `--date-field discovered`.

## Coercion note

`parse_frontmatter(content, coerce_types=True)` returns ISO 8601 strings as `str`. Strip trailing `Z` before `fromisoformat` for Python <3.11 compatibility: `value.rstrip("Z")`.

## Acceptance Criteria

- [ ] `ll-history` uses `captured_at` for capture time at sub-day resolution when present
- [ ] `ll-history` uses `completed_at` for completion time at sub-day resolution when present
- [ ] `CompletedIssue` has `captured_at: datetime | None` and `completed_at: datetime | None` fields
- [ ] `to_dict()` serializes new fields as ISO strings or `None`
- [ ] All existing tests pass (including the two rewritten WILL-BREAK tests)
- [ ] `TestParseDiscoveredDate` class added with `captured_at`-preference coverage
- [ ] API.md and CLI.md updated

## Files to Modify

- `scripts/little_loops/issue_history/parsing.py` — `_parse_discovered_date()` (line 291) and `_parse_completion_date()` (line 131)
- `scripts/little_loops/issue_history/models.py` — `CompletedIssue` dataclass (lines 17-37) and `to_dict()` (lines 28-38)
- `scripts/tests/test_issue_parser.py` — rewrite `test_parse_file_ignores_captured_at` (lines 521-541)
- `scripts/tests/test_issue_history_summary.py` — update `TestCompletedIssue.test_to_dict` (lines 27-57)
- `scripts/tests/test_issue_history_parsing.py` — add `TestParseDiscoveredDate` class
- `docs/reference/API.md` — add fields to `CompletedIssue` block (lines 1560-1568)
- `docs/reference/CLI.md` — update show card description (lines 426-434, 456-462)

## Tests

Run `python -m pytest scripts/tests/ -x` after each subsystem to catch regressions early. Fix the two WILL-BREAK tests before any other changes to establish a green baseline.

### Safe callers (no code change needed)

- `scripts/tests/test_issue_history_advanced_analytics.py` — ~30+ `CompletedIssue` constructions; keyword-arg form, safe with `None` defaults
- `scripts/tests/test_issue_history_analysis.py` — constructions at lines 69, 76, 94, 119; keyword-arg form, safe
- `scripts/tests/test_doc_synthesis.py:97` — `CompletedIssue` in `_make_issue()`; safe with `None` defaults

### Implementation Pattern References

- **Reading datetime from frontmatter**: `parsing.py:291-306` — `fm.get("captured_at")`, manual `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`, return `None` on failure
- **`to_dict` serialization**: `models.py:33-34` — `value.isoformat() if value else None`

## Session Log
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
