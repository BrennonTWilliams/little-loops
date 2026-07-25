---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
---

# FEAT-2786: Cycle-breaking strategy for `ll-deps` dependency auto-fix

## Summary

`fix_dependencies()` (invoked by `ll-deps`) auto-repairs broken refs, stale
completed refs, and missing backlinks, but circular `Blocked By` chains are
only detected, counted (`skipped_cycles` in `FixResult`), and left
unmodified. No cycle-breaking strategy exists.

## Location

- **File**: `scripts/little_loops/dependency_mapper/operations.py`
- **Line(s)**: 189-213 (docstring note at 202, at scan commit: fb567390)
- **Anchor**: `in function fix_dependencies()`; companion field `skipped_cycles` in `dependency_mapper/models.py:112`
- **Code**:
```python
def fix_dependencies(
    issues: list[IssueInfo],
    ...
) -> FixResult:
    """Auto-repair broken dependency references.
    ...
    Cycles are explicitly out of scope and are skipped with a count.
```

## Current Behavior

Cyclic dependencies survive every `ll-deps` fix run; affected issues stay
mutually blocked until a human hand-edits an edge.

## Expected Behavior

`ll-deps` offers a cycle-resolution path — at minimum reporting each cycle's
edges with a suggested edge to drop; optionally an interactive or
`--break-cycles` mode that removes the chosen edge and its backlink.

## Use Case

Autodev/`ll-auto` dequeue skips mutually-blocked issues silently; a curated
cycle-breaking pass restores them to the ready pool without manual file
surgery.

## Acceptance Criteria

- Cycles are enumerated with their member edges in fix output (not just a count)
- A suggested minimal edge-cut is proposed per cycle (e.g. lowest-priority edge)
- Opt-in flag applies the cut, maintaining bidirectional consistency
- `dry_run` shows the plan without writing

## Proposed Solution

Detect cycles via the existing `DependencyGraph`, pick a break edge
heuristically (newest edge or lowest-priority blocker), and route removal
through the same backlink-consistent write path the other three fix
categories use.

## Impact

- **Scope**: Medium

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
