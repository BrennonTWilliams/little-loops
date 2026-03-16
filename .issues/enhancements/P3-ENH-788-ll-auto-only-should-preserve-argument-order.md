---
id: ENH-788
type: ENH
priority: P3
status: active
discovered_date: 2026-03-16
discovered_by: capture-issue
title: "ll-auto --only should preserve argument order"
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

1. In `cli_args.py`: add `parse_issue_ids_ordered(value) -> list[str] | None` that splits on commas and preserves order (no set conversion).
2. In `issue_parser.py:find_issues()`: accept `only_ids` as `list[str] | set[str] | None`. When it's a list, build a dict keyed by `issue_id`, then reorder results to match the list after filtering, skipping the sort.
3. In `cli/auto.py`: call `parse_issue_ids_ordered` instead of `parse_issue_ids` for `--only`.
4. Update `find_highest_priority_issue` if it also threads `only_ids` through (it does — but order doesn't apply there, so leave as set).
5. Add/update tests covering ordered execution via `--only`.

## Success Metrics

- `ll-auto --only BUG-010,FEAT-005,ENH-020` processes in that exact order
- `ll-auto` without `--only` continues to sort by priority — no regression
- Existing tests pass

## Scope Boundaries

- **In scope**: Preserving `--only` argument order in `ll-auto`; changing `parse_issue_ids` to return an ordered list; reordering results in `find_issues()` when `only_ids` is a list
- **Out of scope**: Changing priority-based sort for non-`--only` invocations; modifying `ll-sprint` or `ll-parallel` ordering behavior; adding new sort modes

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `parse_issue_ids_ordered()` returning `list[str]`
- `scripts/little_loops/issue_parser.py` — update `find_issues()` to accept `list[str] | set[str] | None` for `only_ids`; skip sort and reorder by list when `only_ids` is a list
- `scripts/little_loops/cli/auto.py` — call `parse_issue_ids_ordered` instead of `parse_issue_ids` for `--only`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — primary caller of `find_issues()` and `parse_issue_ids`
- Any other CLI entry points that pass `only_ids` to `find_issues()`

### Similar Patterns
- `find_highest_priority_issue` also threads `only_ids` through — leave as set (order doesn't apply)

### Tests
- `scripts/tests/` — add/update tests for ordered execution via `--only`; verify priority sort still applies without `--only`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Improves `--only` ergonomics; not blocking
- **Effort**: Small — Localized changes to `cli_args.py`, `issue_parser.py`, `cli/auto.py`; no new dependencies
- **Risk**: Low — Priority sort path unchanged; list-vs-set distinction isolates the behavior change
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `ll-auto`, `argument-order`

## Status

**Open** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-03-16T23:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03ef4a48-cdf1-402c-a6f3-262d76f4c071.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
