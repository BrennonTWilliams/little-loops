---
id: BUG-2382
title: "ll-issues list --group-by epic drops issues whose chain passes through a completed parent"
status: open
priority: P2
captured_at: "2026-06-28T19:07:09Z"
discovered_date: "2026-06-28"
discovered_by: capture-issue
relates_to: [EPIC-2149]
---

# BUG-2382: ll-issues list --group-by epic drops issues whose chain passes through a completed parent

## Summary

`ll-issues list --group-by epic` builds its parent-chain lookup (`_parent_map`)
from the *status-filtered* issue set (`raw`), not from all issues. With the
default `--status open` filter, any multi-level chain that routes through a
`done`/`cancelled`/`deferred` intermediate parent breaks at that parent: the
walk in `_find_epic_ancestor` cannot find the next edge, returns `None`, and
the issue is misfiled under **Unparented** instead of grouped under its EPIC.

## Current Behavior

In `scripts/little_loops/cli/issues/list_cmd.py`, the `group_by == "epic"`
branch:

- `raw = _load_issues_with_status(...)` honours the `--status` filter
  (default `open` → open/in_progress/blocked only), at `cmd_list` lines 40-45.
- `_parent_map` is built from `raw` (`{i.issue_id: i.parent for i, _ in raw if i.parent}`)
  — so it only contains edges for issues present under the current filter.
- `parent_titles` is built from `raw` the same way.

For a chain `BUG-2380 (open) → FEAT-2200 (done) → EPIC-2149 (open)`:
`_parent_map` has `BUG-2380 → FEAT-2200` but **no** `FEAT-2200 → EPIC-2149`
edge (FEAT-2200 is `done`, excluded from `raw`). `_find_epic_ancestor("BUG-2380")`
walks to `FEAT-2200`, finds no further edge, and returns `None`. BUG-2380 is
bucketed under **Unparented**.

A secondary symptom: when the resolved EPIC ancestor itself is not in `raw`,
`parent_titles.get(key)` misses and the group header renders the bare EPIC id
with no title.

## Expected Behavior

Issues group under their EPIC ancestor regardless of the status of intermediate
parents in the chain. The parent-chain lookup and the title lookup must reflect
the full issue graph, not the status-filtered display set.

## Root Cause

`list_cmd.py`, `cmd_list`, `group_by == "epic"` branch: `_parent_map` (line ~159)
and `parent_titles` (line ~156) are derived from `raw`, which is constrained by
the `--status` filter. Chain traversal requires the complete edge set; filtering
the edge set by display status severs chains at filtered-out nodes.

## Proposed Solution

Hoist a single all-status load to the top of the `group_by == "epic"` branch and
feed all three consumers from it:

1. Build `_parent_map` and `parent_titles` from the all-status set (not `raw`).
2. Reuse the same set for `all_issues_for_progress` (currently loaded separately
   at line ~197 behind the `named_keys` guard), eliminating the redundant scan.

```python
from little_loops.issue_parser import find_issues as _find_issues_all
_ALL_STATUSES = {"open", "in_progress", "blocked", "done", "cancelled", "deferred"}
all_issues = _find_issues_all(config, status_filter=_ALL_STATUSES)

_parent_map = {i.issue_id: i.parent for i in all_issues if i.parent}
parent_titles = {i.issue_id: i.title for i in all_issues if i.title}
# ... later, reuse `all_issues` for compute_epic_progress instead of re-loading
```

Note: `_find_issues_all` returns issues (not `(issue, status)` tuples like
`raw`); adjust the comprehensions accordingly.

## Impact

- **Cost**: one extra full `.issues/` scan when `--group-by epic` runs with a
  non-`all` status filter. Free for `--status all` (already loads everything).
  Epic grouping is an interactive, non-hot path — acceptable.
- **Scope**: display-only command; no data is mutated. Fix corrects grouping
  accuracy and header titles.

## Implementation Steps

1. Add an all-status `find_issues` load at the start of the `group_by == "epic"`
   branch.
2. Rebuild `_parent_map` and `parent_titles` from it.
3. Remove the redundant `all_issues_for_progress` load (~line 197) and reuse the
   hoisted set for `compute_epic_progress`.
4. Add a regression test: a chain `BUG → FEAT(done) → EPIC(open)` asserts the BUG
   groups under the EPIC, not Unparented. This boundary (completed intermediate
   parent) is currently untested.

## Session Log
- `/ll:capture-issue` - 2026-06-28T19:07:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b88673d-6bf0-48cb-a5d7-7d07fc889091.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
