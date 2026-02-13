---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# BUG-403: Dependency graph renders empty isolated nodes when no edges exist

## Summary

`_render_dependency_graph()` in `scripts/little_loops/cli/sprint.py` renders a full DEPENDENCY GRAPH section even when there are zero dependency edges between sprint issues. The output lists every issue as an isolated node with no arrows, which looks broken and provides no useful information.

## Current Behavior

When running `ll-sprint show bug-fixes` on a sprint where no issues depend on each other, the output includes:

```
======================================================================
DEPENDENCY GRAPH
======================================================================

  BUG-365
  BUG-364
  BUG-363
  BUG-347
  BUG-372
  BUG-359

Legend: ──→ blocks (must complete before)
```

This section is pure noise — it shows no relationships and looks like something is broken.

## Expected Behavior

When there are no intra-sprint dependency edges, the DEPENDENCY GRAPH section should be suppressed entirely. The function already has a guard `if not waves or len(waves) <= 1: return ""` but this doesn't cover the case where waves exist due to file contention refinement (not actual dependencies).

## Steps to Reproduce

1. Create a sprint with issues that have no `Blocked By` references to each other
2. Run `ll-sprint show <sprint-name>`
3. Observe: DEPENDENCY GRAPH section shows isolated nodes with no arrows

## Actual Behavior

Full DEPENDENCY GRAPH header, isolated node list, and legend are rendered despite zero edges existing.

## Root Cause

- **File**: `scripts/little_loops/cli/sprint.py`
- **Anchor**: `in function _render_dependency_graph()`
- **Cause**: The function checks `if not waves or len(waves) <= 1` but waves can be > 1 due to `refine_waves_for_contention()` splitting, not actual dependency edges. It should check whether the `dep_graph` has any actual `blocks` or `blocked_by` entries among sprint issues, not just wave count.

## Proposed Solution

Add an edge check before rendering. If `dep_graph.blocks` has no entries for any issue in the sprint, return empty string:

```python
def _render_dependency_graph(waves, dep_graph):
    if not waves or len(waves) <= 1:
        return ""

    # Check if any actual dependency edges exist
    all_ids = {issue.issue_id for wave in waves for issue in wave}
    has_edges = any(
        dep_graph.blocks.get(iid, set()) & all_ids
        for iid in all_ids
    )
    if not has_edges:
        return ""
    # ... rest of function
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — `_render_dependency_graph()`

### Dependent Files (Callers/Importers)
- `_cmd_sprint_show()` calls `_render_dependency_graph()` — no change needed

### Tests
- `scripts/tests/test_sprint.py` — add test for empty graph suppression
- `scripts/tests/test_sprint_integration.py` — verify with real sprint data

### Documentation
- N/A

### Configuration
- N/A

## Motivation

This bug would:
- Eliminate confusing output that makes the sprint tool look broken when there are no intra-sprint dependencies
- Business value: Improves user confidence in the sprint management tool by suppressing meaningless output
- Technical debt: Fixes an incomplete guard condition that fails to account for waves created by file contention refinement

## Implementation Steps

1. Add edge-existence check to `_render_dependency_graph()` after the existing wave count guard
2. Add unit test with a mock `DependencyGraph` that has waves but no edges
3. Verify existing tests still pass

## Impact

- **Priority**: P3 - Cosmetic but confusing output that makes the tool look broken
- **Effort**: Small - Single function guard condition
- **Risk**: Low - Only affects display output, no execution logic
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system architecture |

## Blocked By

- ENH-308: sprint sequential retry for merge-failed issues (shared sprint.py, test_sprint_integration.py)

## Blocks

- ENH-388: standardize issue priority range to P0-P8 (shared ARCHITECTURE.md)
- ENH-386: add command cross-reference validation to audit_claude_config (shared ARCHITECTURE.md)
- ENH-387: add --type flag to CLI processing tools (shared sprint.py)
- FEAT-324: SQLite history database for issues and sessions (shared ARCHITECTURE.md)

## Labels

`bug`, `cli`, `sprint`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab030831-19f7-4fb7-8753-c1c282a30c99.jsonl`
- `/ll:format_issue --all --auto` - 2026-02-13

---

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: VALID
- Commit `3d7713c` attempted a fix at `sprint.py:324-331` but did not resolve the bug
- The bug remains: empty dependency graphs with isolated nodes still render when no intra-sprint edges exist

## Status

**Open** | Created: 2026-02-12 | Priority: P3


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-02-13
- **Reason**: already_fixed
- **Closure**: Automated (ready_issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
