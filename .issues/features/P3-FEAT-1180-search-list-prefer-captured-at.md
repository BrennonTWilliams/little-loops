---
id: FEAT-1180
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1163
size: Small
---

# FEAT-1180: Prefer `captured_at` in `ll-issues search/list` Date Resolution

## Summary

Update `ll-issues search` and `ll-issues list` to check the `captured_at` frontmatter field before falling back to the existing regex-based `discovered_date` extraction, enabling sub-day resolution when sorting or filtering by creation date.

## Parent Issue

Decomposed from FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Motivation

`ll-issues search` has its own `_parse_discovered_date` implementation (independent of `parsing.py`) that uses a regex. Once `captured_at` is written to frontmatter, this lookup should prefer it. `ll-issues list` imports `_parse_discovered_date` from `search.py` directly and inherits the fix without code changes.

## Implementation Steps

### search.py

- **`scripts/little_loops/cli/issues/search.py:21-34`** — `_parse_discovered_date()`: before the regex fallback, check `captured_at` in the frontmatter dict. Call `parse_frontmatter(content, coerce_types=True)` (already available in the module or importable from `frontmatter.py`), then `fm.get("captured_at")`. If present, return as `datetime` via `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`. Fall through to existing regex on failure or absence.

### Coercion note

`parse_frontmatter` returns ISO 8601 strings as `str`. Strip trailing `Z` before `fromisoformat` to support Python <3.11: `value.rstrip("Z")`. Mirror the pattern in `parsing.py:291-306`.

### Dependent caller

- `scripts/little_loops/cli/issues/list_cmd.py:28` — imports `_parse_discovered_date` from `search.py`; silently inherits the `captured_at`-first behavior. No code change needed, but note that `ll-issues list --sort created` output will also change.

## API/Interface

No visible interface change — sort and filter results become more precise when `captured_at` is present. Output format unchanged.

## Acceptance Criteria

- [ ] When `captured_at` is in frontmatter, `ll-issues search` uses it as the creation date
- [ ] When `captured_at` is absent, existing regex behavior is unchanged
- [ ] `ll-issues list --sort created` inherits the improvement with no code changes

## Files to Modify

- `scripts/little_loops/cli/issues/search.py` — update `_parse_discovered_date` (lines 21-34) to check `captured_at` first

## Tests

- `scripts/tests/test_issues_search.py` — add test case: fixture with `captured_at` in frontmatter, assert `_parse_discovered_date` returns the `captured_at` datetime, not the regex-extracted `discovered_date`

### Implementation Pattern References

- **Reading date from frontmatter**: mirror `_parse_discovered_date` in `parsing.py:291-306`
- **`fromisoformat` with Z suffix**: `value.rstrip("Z")` for Python <3.11 compatibility

## Session Log
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
