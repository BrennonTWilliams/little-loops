---
id: ENH-788
type: ENH
priority: P3
status: active
discovered_date: 2026-03-16
discovered_by: capture-issue
title: "ll-auto --only should preserve argument order"
confidence_score: 100
outcome_confidence: 86
---

# ENH-788: ll-auto --only should preserve argument order

## Summary

When `--only` is provided to `ll-auto`, the issues are still sorted by priority (then issue ID alphabetically) rather than processed in the order the caller listed them. Users who pass `--only BUG-010,FEAT-005,ENH-020` expect that exact sequence to be honored, but currently the priority sort overrides it.

## Current Behavior

`find_issues()` in `issue_parser.py` always sorts the result by `(priority_int, issue_id)` regardless of whether `--only` was provided. The order of IDs in the `--only` argument is discarded because `parse_issue_ids()` returns a `set`.

Relevant code: `issue_parser.py:660`
```python
issues.sort(key=lambda x: (x.priority_int, x.issue_id))
```

## Expected Behavior

When `--only` is provided, issues are processed in the exact order the IDs were listed. If `--only BUG-010,FEAT-005,ENH-020` is passed, execution order is `BUG-010 → FEAT-005 → ENH-020`, regardless of priority.

When `--only` is not provided, the existing priority sort is preserved.

## Motivation

`--only` is the natural way to run a specific ordered list of issues ad-hoc (without the overhead of creating a named sprint). Respecting list order makes `--only` a lightweight alternative to `ll-sprint` for one-off sequenced runs. The current behavior is surprising — users who specify an order reasonably expect it to be honored.

## Proposed Solution

1. Change `parse_issue_ids()` (or add a new variant) to return a `list[str]` instead of `set[str]` when order matters, preserving the input sequence.
2. In `find_issues()`, when `only_ids` is provided as an ordered sequence, skip the priority sort and instead return issues in the order they appear in `only_ids`.
3. Update `cli_args.py` and call sites in `cli/auto.py` accordingly.

## Implementation Steps

1. In `cli_args.py`: add `parse_issue_ids_ordered(value: str | None) -> list[str] | None` — same as `parse_issue_ids` but use a list comprehension instead of set comprehension at line 196.
2. In `issue_parser.py:find_issues()` (line 597): change `only_ids: set[str] | None` to `only_ids: list[str] | set[str] | None`. When it's a list, build `order = {id: i for i, id in enumerate(only_ids)}`, sort filtered results by `order[info.issue_id]`, skipping the existing priority sort.
3. In `cli/parallel.py:167`: call `parse_issue_ids_ordered` instead of `parse_issue_ids` for `--only` (the `find_issues()` fix in step 2 handles the sort).
4. In `cli/auto.py:67`: call `parse_issue_ids_ordered` instead of `parse_issue_ids` for `--only`.
5. In `issue_manager.py:_get_next_issue()` (line 773): when `self.only_ids` is a `list`, sort `candidates` by `self.only_ids.index(i.issue_id)` before `candidates[0]` — this fixes ordering for the AutoManager path where `find_issues()` is called without `only_ids`.
6. Leave `find_highest_priority_issue` (`issue_parser.py:664`) typed as `set[str] | None` — order irrelevant.
7. Update tests: add `TestParseIssueIdsOrdered` in `test_cli_args.py`; add `test_find_issues_only_ids_ordered` in `test_issue_parser.py`; update `test_cli.py:1326-1351` to match new list type.

## Success Metrics

- `ll-auto --only BUG-010,FEAT-005,ENH-020` processes in that exact order
- `ll-auto` without `--only` continues to sort by priority — no regression
- Existing tests pass

## Scope Boundaries

- **In scope**: Preserving `--only` argument order in `ll-auto`; changing `parse_issue_ids` to return an ordered list; reordering results in `find_issues()` when `only_ids` is a list
- **Out of scope**: Changing priority-based sort for non-`--only` invocations; modifying `ll-sprint` or `ll-parallel` ordering behavior; adding new sort modes

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `parse_issue_ids_ordered()` returning `list[str]`; existing `parse_issue_ids()` returns `set[str] | None` via set comprehension at line 196
- `scripts/little_loops/issue_parser.py` — update `find_issues()` (line 597) to accept `list[str] | set[str] | None` for `only_ids`; skip sort and reorder by list when `only_ids` is a list; the sort at line 660 is `issues.sort(key=lambda x: (x.priority_int, x.issue_id))`
- `scripts/little_loops/issue_manager.py` — **primary fix for `ll-auto`**: `_get_next_issue()` at line 773 builds `candidates = [i for i in ready_issues if i.issue_id in self.only_ids ...]` and returns `candidates[0]`; when `only_ids` is a list, sort candidates by their index in `only_ids` before taking `candidates[0]`; `self.only_ids` stored at line 711 from `AutoManager.__init__` parameter
- `scripts/little_loops/cli/auto.py` — call `parse_issue_ids_ordered` instead of `parse_issue_ids` for `--only`; passes result to `AutoManager` at lines 71-81

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py:67` — `only_ids = parse_issue_ids(args.only)` → passes to `AutoManager.__init__`; AutoManager stores it and uses in `_get_next_issue()`, NOT in `find_issues()` call (line 721 calls `find_issues` without `only_ids`)
- `scripts/little_loops/cli/parallel.py:167` — also calls `parse_issue_ids(args.only)`, passes as `only_ids=` at line 190; this caller DOES pass `only_ids` to `find_issues()`, so the `find_issues()` list-reorder fix applies here
- `scripts/little_loops/cli/sprint/run.py:121` — calls `parse_issue_ids()` but sprint already preserves order via list iteration at line 129; no change needed

### Similar Patterns
- `find_highest_priority_issue` (`issue_parser.py:664`) delegates to `find_issues()` and returns `issues[0]`; leave `only_ids` typed as `set[str] | None` there — order is irrelevant to its semantics

### Tests
- `scripts/tests/test_cli_args.py:29-60` — `TestParseIssueIds` with 4 tests; `test_multiple_issues` at line 43 asserts `== {"BUG-001", "FEAT-002", "ENH-003"}` (set) — add parallel tests for `parse_issue_ids_ordered`
- `scripts/tests/test_cli.py:1326-1351` — currently asserts `only_ids == {"BUG-001", "BUG-002"}` (set equality); update after `parse_issue_ids_ordered` introduced
- `scripts/tests/test_issue_parser.py:803-933` — `TestFindIssues` with 7 tests; no test for `only_ids` currently; add test asserting list-ordered result
- `scripts/tests/test_cli_args.py:357,400` — integration tests covering `--only`

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: Two distinct execution paths for `--only`, requiring different fixes:**

1. **`ll-auto` path** (`AutoManager`): `find_issues()` is called at `issue_manager.py:721` **without** `only_ids`. The `only_ids` filter is applied later in `_get_next_issue()` at line 773. Fix is in `issue_manager.py`, not `find_issues()`.

2. **`ll-parallel` path** (`cli/parallel.py:190`): `find_issues()` IS called with `only_ids`. Fix is in `find_issues()` sort bypass at `issue_parser.py:660`.

**Data flow for `ll-auto`:**
```
parse_issue_ids("BUG-010,FEAT-005") → set (order lost at cli_args.py:196)
AutoManager(only_ids=set) → self.only_ids = set (issue_manager.py:711)
find_issues(config, category)  [no only_ids]  (issue_manager.py:721)
_get_next_issue(): candidates = [i for i in ready_issues if i.issue_id in self.only_ids]
return candidates[0]  ← order determined by dep_graph, not --only arg
```

## Impact

- **Priority**: P3 — Improves `--only` ergonomics; not blocking
- **Effort**: Small — Localized changes to `cli_args.py`, `issue_parser.py`, `cli/auto.py`; no new dependencies
- **Risk**: Low — Priority sort path unchanged; list-vs-set distinction isolates the behavior change
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `ll-auto`, `argument-order`

## Resolution

**Completed** | 2026-03-16

### Changes Made

1. **`scripts/little_loops/cli_args.py`**: Added `parse_issue_ids_ordered()` returning `list[str] | None`, preserving input order via list comprehension instead of set comprehension.
2. **`scripts/little_loops/issue_parser.py`**: Updated `find_issues()` signature to `only_ids: list[str] | set[str] | None`. When `only_ids` is a list, issues are sorted by their position in the list instead of by priority.
3. **`scripts/little_loops/issue_manager.py`**: Updated `AutoManager.__init__` signature and `_get_next_issue()` to sort candidates by list order when `self.only_ids` is a list. Fixed set intersection to work with both list and set types.
4. **`scripts/little_loops/cli/auto.py`**: Changed `parse_issue_ids` → `parse_issue_ids_ordered` for `--only` argument so `ll-auto` preserves argument order.
5. **Tests**: Added `TestParseIssueIdsOrdered` in `test_cli_args.py`; added `test_find_issues_only_ids_ordered` and `test_find_issues_only_ids_set_uses_priority_sort` in `test_issue_parser.py`; updated `test_only_and_skip_parsed_to_sets` in `test_cli.py` to expect list instead of set.

Note: `ll-parallel` was intentionally left using `parse_issue_ids` (set) as parallel ordering behavior is out of scope per issue boundaries. `ll-sprint` unchanged as it already preserves order via list iteration.

## Status

**Completed** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-17T00:09:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bb09ebe-c7cc-4096-90dd-091384e81465.jsonl`
- `/ll:refine-issue` - 2026-03-16T23:24:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f41b047-87a9-4dc6-bd79-b70fcba93e87.jsonl`
- `/ll:format-issue` - 2026-03-16T23:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03ef4a48-cdf1-402c-a6f3-262d76f4c071.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f7bf6f5-8d0a-49aa-a2dc-02169a6d3f97.jsonl`
