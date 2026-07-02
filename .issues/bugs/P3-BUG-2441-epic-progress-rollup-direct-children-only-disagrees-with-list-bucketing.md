---
captured_at: '2026-07-02T04:31:34Z'
completed_at: '2026-07-02T04:31:34Z'
discovered_date: 2026-07-02
discovered_by: external-plan-review
status: done
priority: P3
type: BUG
relates_to: []
labels:
- issues
- epic-progress
---

# BUG-2441: `compute_epic_progress` counts only direct `parent:` children while `ll-issues list --group-by epic` buckets transitively — contradictory badges

## Summary

`ll-issues list --group-by epic` and `ll-issues epic-progress` disagreed on
what "belongs to an EPIC" means. The list view's bucketing walked the full
`parent:` chain transitively up to an EPIC (so a `FEAT` nested under a
*done* intermediate `FEAT` still counted as an EPIC descendant), but the
progress badge shown next to each EPIC heading — and the standalone
`epic-progress` command — only counted issues whose immediate `parent:` was
that EPIC. An EPIC with active grandchildren nested under a completed
intermediate FEAT would show a `(N/N done)` badge implying full completion
while the list underneath it still displayed those active descendants,
e.g. `EPIC-427: … (5) (18/18 done)` with 5 `pending`/active issues listed
below the heading.

## Current Behavior

- `cli/issues/list_cmd.py::_find_epic_ancestor` walked `parent:` transitively
  (cycle-guarded) to bucket every issue under its ancestor EPIC for the list
  view.
- `issue_progress.py::compute_epic_progress` collected children via
  `i.parent == epic_id` only — direct children, one hop.
- Any issue reachable from an EPIC through an intermediate (often-done) FEAT
  was bucketed under that EPIC in the list but excluded from the badge's
  denominator and numerator entirely.

## Expected Behavior

Both code paths should agree on descendant membership: the progress badge
and `epic-progress` totals must reflect the same transitive set of issues
the list view buckets under an EPIC heading.

## Root Cause

- **File**: `scripts/little_loops/issue_progress.py`
- **Anchor**: `compute_epic_progress`'s prior one-hop `child_ids` set built
  from `i.parent == epic_id`
- **Cause**: two independent implementations of "EPIC membership" — one
  transitive (`list_cmd.py`), one direct-only (`issue_progress.py`) — drifted
  apart with no shared helper enforcing the same semantics.

## Proposed Solution (applied)

Added `_issue_descends_to(issue_id, epic_id, parent_map)` to
`issue_progress.py`: a cycle-guarded upward walk of the `parent:` chain,
mirroring `list_cmd.py::_find_epic_ancestor`'s traversal pattern.
`compute_epic_progress` now builds `child_ids` from
`_issue_descends_to(...)` over all loaded issues instead of a direct
`i.parent == epic_id` comparison, so descendants nested under intermediate
(including completed) parents are now included in the rollup — matching
what the list view already buckets.

A companion change proposed alongside this (treating a raw `pending` status
value as open in the rollup) was investigated and dropped: `frontmatter.py`
already defines `STATUS_SYNONYMS = {"pending": "open", ...}`, applied
unconditionally in `parse_frontmatter` before `IssueInfo.status` is ever
set (`issue_parser.py` reads `frontmatter.get("status", "open")` post-
coercion). A literal `"pending"` status can never reach
`compute_epic_progress` in this codebase, so no `_OPEN_STATUSES` change was
needed — the apparent "pending" descendants in the triggering report were
already being counted as `open`; they were simply excluded from the child
set entirely by the direct-parent-only bug above.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_progress.py` - added `_issue_descends_to`
  helper; `compute_epic_progress` now resolves `child_ids` transitively via
  a `parent_map` walk instead of one-hop `i.parent == epic_id`

### Dependent Files (Callers/Importers)
- `cli/issues/list_cmd.py` - calls `compute_epic_progress` to render the
  per-EPIC badge in `--group-by epic` output; no change needed, now
  consistent with its own `_find_epic_ancestor` bucketing by construction
- `cli/issues/epic_progress.py` - `ll-issues epic-progress <ID>` CLI; totals
  now reflect the same transitive set

### Similar Patterns
- `cli/issues/list_cmd.py::_find_epic_ancestor` - traversal pattern this fix
  mirrors (cycle-guarded `seen` set, upward walk via a `parent_map`)

### Tests
- `scripts/tests/test_issue_progress.py::TestComputeEpicProgress` - added
  `test_transitive_chain_includes_grandchildren`,
  `test_cycle_in_parent_chain_does_not_loop`,
  `test_unrelated_sibling_chains_excluded`; all 15 pre-existing tests in the
  class (including direct-parent cases) still pass unchanged, since direct
  children are a strict subset of transitive descendants

### Documentation
- N/A - internal aggregation behavior; no documented contract changed
  (`EpicProgress` dataclass fields/shapes are unchanged)

### Configuration
- N/A

## Steps to Reproduce

1. Create `EPIC-X`, `FEAT-A` with `parent: EPIC-X` and `status: done`, and
   `BUG-B` with `parent: FEAT-A` and `status: open`.
2. Run `ll-issues list --group-by epic` — `BUG-B` is bucketed under
   `EPIC-X` in the printed list (via `_find_epic_ancestor`'s transitive
   walk).
3. The badge next to `EPIC-X` was computed from `compute_epic_progress`,
   which only saw `FEAT-A` (the direct child) — reporting `1/1 done` even
   though `BUG-B` (open) is listed underneath it.

## Actual Behavior (before fix)

Badge denominator/numerator excluded transitively-nested descendants,
producing a "100% done" badge alongside actively-listed open issues.

## Impact

- **Priority**: P3 - Cosmetic/trust issue in `ll-issues list --group-by
  epic` and `ll-issues epic-progress` output; no data loss, but a
  misleading completion signal for any EPIC with multi-level FEAT nesting
  under a completed intermediate node.
- **Effort**: Small - single helper function + child-resolution swap in one
  file, plus three new unit tests.
- **Risk**: Low - `EpicProgress` dataclass contract unchanged; direct-child
  behavior is a strict subset of the new transitive behavior, so all
  pre-existing direct-parent tests pass unmodified.
- **Breaking Change**: No.

## Related Issues

- None - surfaced via an ad hoc implementation-plan review (not a prior
  `.issues/` entry), then verified and implemented directly in the same
  session.

## Resolution

Fixed (2026-07-02). Added `_issue_descends_to` (cycle-guarded transitive
parent-chain walk) to `issue_progress.py` and switched
`compute_epic_progress`'s child resolution to use it, matching
`list_cmd.py::_find_epic_ancestor`'s existing traversal semantics. Verified
the plan's companion "pending" status change was unnecessary given
`STATUS_SYNONYMS` already coerces `pending` → `open` at frontmatter-parse
time, and dropped it rather than adding dead code plus a test that would
assert an unreachable status value.

`scripts/tests/test_issue_progress.py` and `scripts/tests/test_issues_cli.py`
(epic-progress cases): 35 passed.

## Status

**Current Status**: done


## Session Log
- `hook:posttooluse-status-done` - 2026-07-02T04:32:35 - `c12d98cd-c8c9-4ca3-adf4-3dd8a1480ac6.jsonl`
