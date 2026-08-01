---
id: ENH-2961
title: 'format-check on a single issue ID emits deprecation warnings for every other
  issue in the corpus'
type: ENH
priority: P4
status: open
captured_at: "2026-08-01T04:12:30Z"
discovered_date: 2026-08-01
discovered_by: capture-issue
labels:
- issues
- format-check
- cli
- ergonomics
---

# ENH-2961: Scope format-check's deprecation warnings to the targeted issue

## Summary

`ll-issues format-check <ID>` targets one issue but emits frontmatter-deprecation warnings for the entire corpus. For `ENH-2941` the run produces 22 lines, 21 of which are `deprecated frontmatter key 'parent_issue'` notices about unrelated FEAT-1081/1200-series files. The single line the user asked for scrolls off the top.

## Current Behavior

```
$ ll-issues format-check ENH-2941 2>&1 | wc -l
22
$ ll-issues format-check ENH-2941 2>&1 | grep -c "deprecated frontmatter key 'parent_issue'"
21
$ ll-issues format-check ENH-2941 2>/dev/null | wc -l
1
```

`cmd_format_check()` (`scripts/little_loops/cli/issues/format_check.py`) unconditionally calls `find_issues(config, status_filter=set(_ALL_STATUSES))` to build the `issue_statuses` map, regardless of whether one ID or a full sweep was requested. Parsing each file trips the deprecation logging in `issue_parser.py` (`deprecated frontmatter key 'parent_issue' — rename to 'parent'`, and its `target_branch`/`related` siblings).

Scope note: the warnings go to **stderr**, so stdout stays clean and piped/scripted consumers are unaffected. This is an interactive-ergonomics problem only, which is why it is filed P4 rather than as a bug.

## Expected Behavior

`format-check <ID>` prints its verdict plus any deprecation warnings **for that issue**. Warnings about other files are suppressed, or collapsed to a single summary line:

```
Formatted: ENH-2941 is structurally compliant
(21 other issues have deprecated frontmatter keys — run `ll-issues format-check` to list)
```

The full sweep (`ll-issues format-check` with no ID) keeps reporting everything, since there the warnings are on-topic.

## Motivation

`format-check <ID>` is the loop an author runs repeatedly while fixing one issue's structure — it ran four times in the session that surfaced this. At a 21:1 noise ratio the useful line is easy to miss, and the warnings are unactionable in that moment because they concern files the author is not editing. The deprecated keys are a real backlog item, but a single-ID check is the wrong place to surface them.

## Proposed Solution

The corpus load itself is **legitimate and must stay** — `issue_statuses` is what lets `check_format_gaps()` distinguish `prose_dep_drift` (dependency on an active issue) from `stale_prose_dep` (dependency on a done/cancelled one). Only the warning emission should be scoped. Options, cheapest first:

1. **Suppress during the status-map load** — wrap the `find_issues(...)` call that builds `issue_statuses` in a logging filter that drops the deprecation records, then parse the *targeted* issue normally so its own warnings still surface. Smallest diff; keeps warning text and levels untouched.
2. **Count and summarize** — capture the suppressed records and print a one-line tally as shown in Expected Behavior. Preserves discoverability of the backlog.
3. **Deduplicate globally** — emit each deprecated-key class once per run rather than once per file. Helps the full sweep too (currently 21 near-identical lines), but does not fully solve the single-ID case.

Recommend 1 + 2 together. If the warnings are wanted on demand, gate the full list behind an existing verbosity flag rather than adding a new one — check the current `ll-issues` flag surface before introducing anything.

## Integration Map

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()`; the `find_issues(config, status_filter=set(_ALL_STATUSES))` call and the single-ID branch below it
- `scripts/little_loops/issue_parser.py` — emits the three deprecation warnings (`parent_issue`, `target_branch`, `related`) during frontmatter parse; no change to the warnings themselves
- Full-sweep behavior (no ID) must be preserved apart from any intentional dedup

### Tests

- `scripts/tests/` — add a case asserting a single-ID `format-check` on a corpus containing a deprecated-key file emits no warning for that unrelated file, and still emits one when the *targeted* issue itself carries a deprecated key
- Assert the full sweep still reports deprecated keys

## Implementation Steps

1. Confirm which `find_issues` call is the warning source (the `_ALL_STATUSES` status-map load, not the targeted read).
2. Add scoped log suppression around it for the single-ID path only.
3. Tally suppressed records; print the summary line when the count is non-zero.
4. Tests for both paths; verify the full sweep is unchanged.

## Program Design

### Types

No new types. A `logging.Filter` subclass (or a `contextlib.contextmanager` wrapping one) is sufficient; prefer the contextmanager so the suppression window is explicit and cannot leak past the status-map load.

### Signatures

- `_suppress_frontmatter_deprecations() -> Iterator[list[logging.LogRecord]]`
  - Contextmanager installing a filter on the `issue_parser` logger; yields the list of records it swallowed so the caller can tally them for the summary line.
- `cmd_format_check(config: BRConfig, args: Namespace) -> int`
  - Unchanged signature; wraps only the `_ALL_STATUSES` status-map load in the contextmanager, and only on the single-ID path.

### Call Path

- `cmd_format_check()` -> `find_issues()` -> `check_format_gaps()`

## Scope Boundaries

- In scope: suppressing and tallying frontmatter-deprecation records emitted during the single-ID status-map load, the summary line, and tests for both the single-ID and full-sweep paths.
- Out of scope: the corpus scan itself (required for `prose_dep_drift` vs `stale_prose_dep` resolution), the deprecation warning text/levels in `issue_parser.py`, actually renaming the ~21 offending `parent_issue` keys, adding a new verbosity flag, and the `program_design_nonspecific` false negatives (BUG-2960).

## Impact

- **Priority**: P4 - Ergonomics only; stdout is already clean, so no tooling is broken
- **Effort**: Small - localized to one CLI module, no parser changes
- **Risk**: Low - suppression is scoped to a single code path; the full sweep is the regression to watch

## Status

**Open** | Created: 2026-08-01 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-01T04:14:35 - `955e48a5-4e30-44bc-914f-c2bd87008116.jsonl`
