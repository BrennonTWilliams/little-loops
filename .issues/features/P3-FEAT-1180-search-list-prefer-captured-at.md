---
id: FEAT-1180
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
completed_at: 2026-04-18T21:56:22Z
discovered_by: issue-size-review
parent: FEAT-1163
size: Small
confidence_score: 100
outcome_confidence: 90
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# FEAT-1180: Prefer `captured_at` in `ll-issues search/list` Date Resolution

## Summary

Update `ll-issues search` and `ll-issues list` to check the `captured_at` frontmatter field before falling back to the existing regex-based `discovered_date` extraction, enabling sub-day resolution when sorting or filtering by creation date.

## Parent Issue

Decomposed from FEAT-1163: Read `captured_at`/`completed_at` Timestamps in Analytics and Display

## Current Behavior

`ll-issues search` and `ll-issues list --sort created` call `_parse_discovered_date` in `search.py`, which reads only the `discovered_date` field via regex and truncates to date granularity (`date.fromisoformat(date_str[:10])`). Two issues captured minutes apart on the same day sort in an arbitrary order, and `captured_at` (ISO datetime, written by `/ll:capture-issue`) is ignored entirely.

## Expected Behavior

When `captured_at` is present in frontmatter, `_parse_discovered_date` returns it as a `datetime`, giving sub-day resolution for `--sort created`. When `captured_at` is absent, existing regex-based `discovered_date` behavior is preserved. JSON output format and `--since`/`--until` date-granular filters remain unchanged.

## Use Case

A user runs `ll-issues search --sort created` (or `ll-issues list --sort created`) after a burst of issue captures. They expect the output to reflect capture order even among issues captured the same day.

## User Story

As a user of `ll-issues search`/`list`, I want creation-date sorting to honor `captured_at` when present, so that issues captured minutes apart appear in a stable, meaningful order.

## Motivation

`ll-issues search` has its own `_parse_discovered_date` implementation (independent of `parsing.py`) that uses a regex. Once `captured_at` is written to frontmatter, this lookup should prefer it. `ll-issues list` imports `_parse_discovered_date` from `search.py` directly and inherits the fix without code changes.

## Implementation Steps

### search.py

- **`scripts/little_loops/cli/issues/search.py:21-34`** — `_parse_discovered_date()`: before the regex fallback, check `captured_at` in the frontmatter dict. Call `parse_frontmatter(content, coerce_types=True)` (already available in the module or importable from `frontmatter.py`), then `fm.get("captured_at")`. If present, return as `datetime` via `datetime.fromisoformat(value.rstrip("Z"))` inside `try/except ValueError`. Fall through to existing regex on failure or absence.

### Coercion note

`parse_frontmatter` returns ISO 8601 strings as `str`. Strip trailing `Z` before `fromisoformat` to support Python <3.11: `value.rstrip("Z")`. Mirror the pattern in `scripts/little_loops/issue_history/parsing.py:291-306` (note: that helper reads `discovered_date`, not `captured_at` — reference is for the `fromisoformat` error-handling shape, not field selection).

### Return type decision

Current signature is `_parse_discovered_date(content: str) -> date | None` (search.py:21) and callers at `search.py:304` + `list_cmd.py:64` assign the result into tuples typed `date | None` (see `search.py:297`). `captured_at` is an ISO datetime (e.g. `2026-04-18T14:32:10Z`), so to realize sub-day resolution the function must return `datetime | None`.

Because `datetime` is a subclass of `date`, existing comparisons against `since_date`/`until_date` (`date` instances at `search.py:275-283`) still work — but Python raises `TypeError` when comparing naive-datetime with date in some orderings, so be explicit: convert the datetime to date when the existing `--since`/`--until` filters are applied (they are day-granular), and keep the datetime only for sort ordering. Concretely:

- Return `datetime` from `_parse_discovered_date` when `captured_at` is present.
- In the enriched tuple (`search.py:297`), widen the type to `datetime | date | None` or normalize to `datetime` by converting the regex-only `date` result via `datetime.combine(d, datetime.min.time())`.
- Update `_sort_issues` (if it compares these values) to handle mixed types consistently — easiest is to normalize both branches to `datetime` inside `_parse_discovered_date`.

### Dependent caller

- `scripts/little_loops/cli/issues/list_cmd.py:28` — imports `_parse_discovered_date` from `search.py`; silently inherits the `captured_at`-first behavior. No code change needed, but note that `ll-issues list --sort created` output will also change.
- `scripts/little_loops/cli/issues/list_cmd.py:64` — only call-site in list_cmd; assigns to a local variable (no static type annotation beyond inference), so a datetime return is source-compatible.
- `scripts/little_loops/cli/issues/search.py:304` — assigns into the enriched tuple declared at `search.py:297` as `list[tuple[IssueInfo, str, date | None, date | None]]`. If return type widens to `datetime`, update this annotation accordingly.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Fix `_sort_issues` sentinel in `search.py:205` — change `date(9999, 12, 31)` to `datetime(9999, 12, 31, 0, 0, 0)` (or `datetime.max`) to avoid `TypeError` when `sorted()` compares a `datetime` value (from `captured_at`) against the `date` sentinel. This affects both `search` and `list` since `list_cmd.py` imports `_sort_issues`.
- Fix JSON output format in `search.py:391` — `str(d)` on a `datetime` produces `"2026-01-10 00:00:00"`, not `"2026-01-10"`; normalize to `d.isoformat()` (or `d.date().isoformat()` if you want date-only) to avoid a silent format change in `--json` output.
- Fix analogous JSON format in `list_cmd.py:106` — same `str(disc_date)` pattern; normalize output format consistently.
- Update `docs/reference/CLI.md:458` — `--date-field discovered` description names `discovered_date` as the exclusive source; revise to note that `captured_at` is preferred when present.

## API/Interface

No visible interface change — sort and filter results become more precise when `captured_at` is present. Output format unchanged.

## Impact

- **Priority**: P3 — quality-of-life refinement; no active bug. Justified because `captured_at` is already written but unused by search/list.
- **Effort**: Small — single helper function plus two normalization fixes and a docs update.
- **Risk**: Low — narrow blast radius; existing regex path preserved as fallback. Type widening from `date` to `datetime` requires the `_sort_issues` sentinel and JSON-output fixes flagged in the wiring phase.

## Labels

tooling, cli, sorting, refactor

## Acceptance Criteria

- [ ] When `captured_at` is in frontmatter, `ll-issues search` uses it as the creation date
- [ ] When `captured_at` is absent, existing regex behavior is unchanged
- [ ] `ll-issues list --sort created` inherits the improvement with no code changes

## Files to Modify

- `scripts/little_loops/cli/issues/search.py` — update `_parse_discovered_date` (lines 21-34) to check `captured_at` first; also fix `_sort_issues` sentinel at line 205 and JSON output at line 391
- `scripts/little_loops/cli/issues/list_cmd.py` — update JSON output format at line 106 (no logic change, normalization only)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py:2400-2422` — `TestListSorting.test_sort_by_created_default_desc` exercises `list_cmd.py`'s use of `_sort_issues` and `_parse_discovered_date`; existing fixtures cover the fallback path [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:458` — `--date-field discovered` description names `discovered_date` as the sole source field; needs updating to note `captured_at` is preferred when present [Agent 2 finding]

## Tests

- `scripts/tests/test_issues_search.py` — add unit test case: fixture with both `captured_at` and `discovered_date` in frontmatter, assert `_parse_discovered_date` returns the `captured_at` value (not the `discovered_date` value).
- Existing tests at `scripts/tests/test_issues_search.py:540-615` exercise the helper indirectly via CLI (`_run_search`). Two of these fixtures write `discovered_date: 2026-01-01T00:00:00Z` style frontmatter — when adding `captured_at` support, confirm these fixtures still pass (no `captured_at` key, so regex fallback path exercised).
- Add a second fixture variant: `captured_at` present with sub-day resolution (e.g. `2026-01-01T14:30:00Z`), two issues captured on the same day but different times, assert sort order by `--sort created` is deterministic and reflects the finer resolution.
- Consider adding a direct unit test (no CLI) against `_parse_discovered_date` — no such direct tests exist today (`grep _parse_discovered_date scripts/tests/test_issues_search.py` returns nothing), so this would be a new pattern. Style: module-level `def test_parse_discovered_date_prefers_captured_at(): ...` is consistent with the other module-level helpers if placed outside the `TestUpdatedSince*` class.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py:2400-2422` — `TestListSorting.test_sort_by_created_default_desc` exercises `_sort_issues` via `list_cmd.py`; add a parallel fixture variant with `captured_at` to cover the new preferred path [Agent 3 finding]
- `scripts/tests/test_issues_search.py:469-509` — `TestSearchDateFilter` (`--since`/`--until` tests): verify these still pass after the change; the normalization plan (convert `datetime` to `date` for `since_date`/`until_date` comparisons) must be in place for these not to break [Agent 3 finding]

### Implementation Pattern References

- **Reading date from frontmatter**: the semantically-closest helper is `scripts/little_loops/issue_history/parsing.py:291-306`, though it reads `discovered_date` and returns `date` (not `datetime`). Use its try/except ValueError shape; replace the field name and return type.
- **`parse_frontmatter` usage**: `scripts/little_loops/frontmatter.py:18` — call with `coerce_types=False` (default) since we want ISO strings, not coerced ints. Handles both quoted and unquoted values, so no manual `.strip("\"'")` needed on the returned dict value.
- **`fromisoformat` with Z suffix**: `value.rstrip("Z")` for Python <3.11 compatibility (Python 3.11+ accepts `Z` natively).

## Resolution

**Completed**: 2026-04-18

### Summary of Changes

- `scripts/little_loops/cli/issues/search.py` — `_parse_discovered_date` now prefers `captured_at` via `parse_frontmatter`, returns `datetime` (midnight for regex-only path) for uniform sort comparisons; updated `_sort_issues` sentinels (`datetime.max` for created, `date.max` for completed); normalized `--since`/`--until` to day granularity via `.date()`; JSON output now emits `YYYY-MM-DD` via `d.date().isoformat()`.
- `scripts/little_loops/cli/issues/list_cmd.py` — widened `disc_date` type to `datetime`; JSON output normalized identically.
- `docs/reference/CLI.md` — `--date-field discovered` now documents `captured_at` preference.
- Tests: four direct `_parse_discovered_date` unit tests, a `TestCreatedSortSubDayResolution` CLI class (same-day ordering, `--since`/`--until` compatibility, JSON format), and a `list` parallel test in `TestListSorting`.

### Verification

- `python -m pytest scripts/tests/` — 4990 passed, 5 skipped.
- `ruff check scripts/` — clean on changed files.
- `python -m mypy scripts/little_loops/cli/issues/search.py scripts/little_loops/cli/issues/list_cmd.py` — no issues.

## Session Log
- `/ll:ready-issue` - 2026-04-18T21:51:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3fac7303-44f1-4ca6-8a6d-9e9f3bfae350.jsonl`
- `/ll:confidence-check` - 2026-04-18T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d99e4ff1-a50f-4a21-95bb-0e3a032dd7eb.jsonl`
- `/ll:wire-issue` - 2026-04-18T21:48:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/050f49f9-2994-46ba-b73a-28acb529326d.jsonl`
- `/ll:refine-issue` - 2026-04-18T21:42:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9ba1f24-83c4-49e2-824c-bcfc7c6a231d.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1357a791-c921-47ef-95b7-1d0a7b03979b.jsonl`
- `/ll:manage-issue` - 2026-04-18T21:56:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/815856ca-4c2b-4a38-9909-96967ce1bcbf.jsonl`
