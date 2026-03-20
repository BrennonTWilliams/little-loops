---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# FEAT-831: `--date-field=updated` stub in `ll-issues search`

## Summary

The `--date-field` argument in `ll-issues search` advertises `choices=["discovered", "updated"]`, but the `"updated"` branch silently falls back to `discovered_date`. The comment in code explicitly states: `"updated" not stored; fall back to discovered_date`.

## Location

- **File**: `scripts/little_loops/cli/issues/search.py`
- **Line(s)**: 240-246 (at scan commit: 8c6cf90)
- **Anchor**: `in function _load_issues_with_status`, `cmd_search`
- **Code**:
```python
date_field = getattr(args, "date_field", "discovered")
if date_field == "discovered":
    ref_date = disc_date
else:
    # "updated" not stored; fall back to discovered_date
    ref_date = disc_date
```

## Current Behavior

`--date-field=updated` is accepted by the CLI but behaves identically to `--date-field=discovered`. Users are misled into thinking they're filtering by last update date.

## Expected Behavior

Either implement the `updated` date (e.g., from the last Session Log entry or file mtime) or remove the `"updated"` choice from the CLI until it's implemented.

## Use Case

A developer wants to find issues that were last worked on within the past week. They run `ll-issues search --date-field=updated --since 2026-03-12` expecting to see recently-touched issues, but get results based on discovery date instead.

## Acceptance Criteria

- [ ] `--date-field=updated` uses an actual last-modified date (file mtime or last session log entry)
- [ ] OR: Remove `"updated"` from `choices` and document it as a future feature

## Proposed Solution

Derive the updated date from the last `## Session Log` entry timestamp, or fall back to `os.path.getmtime()` on the issue file. The Session Log approach is more semantically meaningful.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Add `_parse_updated_date(content: str, file_path: Path) -> date | None` to `search.py`, following the `_parse_completion_date` pattern in `issue_history/parsing.py:80-103`:

1. Use `_SESSION_LOG_SECTION_RE` from `session_log.py:16-18` (or inline the equivalent) to isolate the `## Session Log` section
2. Extract all timestamps with a regex like `r"- `[^`]+` - (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"` — take the **last** match as the most-recent activity date
3. Fall back to `date.fromtimestamp(file_path.stat().st_mtime)` (same pattern as `_parse_completion_date` at `issue_history/parsing.py:98-101`)
4. Replace the stub at `search.py:244-246` with `ref_date = _parse_updated_date(content, issue.path)`
5. **Non-obvious side effect**: the `need_content` guard at `search.py:191-197` must also be set True when `date_field == "updated"` — otherwise file content is never read and `_parse_updated_date` gets an empty string

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/search.py` — add `_parse_updated_date()` helper (model after `_parse_discovered_date` at line 17), replace stub at lines 244–246, update `need_content` guard at lines 191–197
- `scripts/little_loops/cli/issues/__init__.py` — no code change needed; `--date-field choices=["discovered", "updated"]` at line 165 already advertises both values correctly

### Reusable Code

- `scripts/little_loops/session_log.py:16-18` — `_SESSION_LOG_SECTION_RE` regex to isolate the `## Session Log` section (import or inline)
- `scripts/little_loops/issue_history/parsing.py:80-103` — `_parse_completion_date()` is the canonical pattern for structured-field-parse + mtime fallback; already imported in `search.py` at line 255
- `scripts/little_loops/issue_history/parsing.py:98-101` — `date.fromtimestamp(file_path.stat().st_mtime)` mtime fallback pattern

### Tests

- `scripts/tests/test_issues_search.py` — add tests in a new class `TestSearchDateFieldUpdated` following the `TestSearchDateFilter` pattern (lines 467–526); fixture files need a `## Session Log` section with dated entries; assert filtering by session log timestamp vs. discovered date

### Documentation

- `docs/reference/CLI.md` — update `--date-field` description to document the `updated` semantics (last Session Log entry, file mtime fallback)

## Implementation Steps

1. **Add `_parse_updated_date()` to `search.py`** — after the existing `_parse_discovered_date` function (line 30), add a new helper that uses `_SESSION_LOG_SECTION_RE` to find the last session log timestamp; fall back to `date.fromtimestamp(issue.path.stat().st_mtime)`
2. **Fix `need_content` guard** at `search.py:191-197` — add `or getattr(args, "date_field", "discovered") == "updated"` so content is read when `--date-field=updated` is passed even without `--since`/`--until`
3. **Replace the stub** at `search.py:244-246` — change `else: ref_date = disc_date` to `else: ref_date = _parse_updated_date(content, issue.path)`
4. **Add tests** to `test_issues_search.py` — create fixture files with a `## Session Log` section containing entries at known timestamps; assert that `--date-field=updated --since <date>` filters by session log date, not discovered date; also assert mtime fallback when no session log is present
5. **Update docs** at `docs/reference/CLI.md` — clarify `updated` choice semantics

## Impact

- **Priority**: P4 - Advertised but non-functional CLI option; misleading behavior
- **Effort**: Small - Parse last session log timestamp or use file mtime
- **Risk**: Low - Fixes existing stub; no new API surface
- **Breaking Change**: No (changes behavior of a currently-broken option)

## Labels

`feature`, `cli`, `issues`

## Status

**Open** | Created: 2026-03-19 | Priority: P4

## Verification Notes

- **Verdict**: VALID
- **Verified**: 2026-03-19
- **File exists**: Yes — `scripts/little_loops/cli/issues/search.py`
- **Line numbers**: Accurate — code block at lines 240–246 matches exactly
- **Code snippet**: Confirmed — `date_field == "discovered"` branch and `else` branch both assign `ref_date = disc_date`, with comment `# "updated" not stored; fall back to discovered_date`
- **CLI choices**: Confirmed — `choices=["discovered", "updated"]` at `scripts/little_loops/cli/issues/__init__.py:167`
- **Minor inaccuracy**: Anchor says `in function _load_issues_with_status` but the code lives in `cmd_search` (line 149). Does not affect validity.

## Session Log
- `/ll:confidence-check` - 2026-03-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2af7f4f8-73af-4315-81b7-60727567c63e.jsonl`
- `/ll:refine-issue` - 2026-03-20T18:19:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4b6ef1b-b89b-45e2-a89f-d803b08bf7d7.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:26:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
