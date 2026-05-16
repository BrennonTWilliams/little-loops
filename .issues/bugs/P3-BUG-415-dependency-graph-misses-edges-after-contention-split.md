---
discovered_date: 2026-02-13
discovered_by: capture_issue
---

# BUG-415: Dependency graph misses edges after contention wave splitting

## Summary

`_render_dependency_graph()` in `sprint.py` fails to render actual dependency edges when Wave 1 has been split into sub-waves by `refine_waves_for_contention()`. The function uses `waves[:1]` to find root nodes for chain traversal, but after contention splitting, dependency roots can be in later sub-waves. These roots fall through to the "isolated issues" loop which prints bare IDs without calling `build_chain()`, so edges are silently dropped.

## Current Behavior

Running `ll-sprint show hooks-config` on a sprint where ENH-377 blocks ENH-371, and Wave 1 is split into 3 contention sub-waves, produces:

```
DEPENDENCY GRAPH

  ENH-370
  ENH-371
  ENH-377
  ENH-378

Legend: ──→ blocks (must complete before)
```

All 4 issues are rendered as isolated nodes. The ENH-377 → ENH-371 edge is missing despite the EXECUTION PLAN correctly showing ENH-371 as blocked by ENH-377.

## Expected Behavior

The dependency graph should render actual edges:

```
DEPENDENCY GRAPH

  ENH-377 ──→ ENH-371

Legend: ──→ blocks (must complete before)
```

Only issues with edges should appear. Issues with no dependency relationships (ENH-370, ENH-378) should be omitted since they carry no graph information.

## Steps to Reproduce

1. Create a sprint with issues where at least one `Blocked By` dependency exists
2. Ensure the non-blocked issues share files (triggering contention wave splitting)
3. Run `ll-sprint show <sprint-name>`
4. Observe: DEPENDENCY GRAPH shows all issues as isolated nodes, edges missing

## Actual Behavior

The dependency edge (ENH-377 → ENH-371) is not rendered. All issues appear as disconnected nodes.

## Root Cause

- **File**: `scripts/little_loops/cli/sprint.py`
- **Anchor**: `in function _render_dependency_graph()`, lines 414-416 and 425-427
- **Cause**: Two compounding issues:
  1. **Root detection is positional, not structural** (line 414): `waves[:1]` assumes dependency roots are in the first wave, but after `refine_waves_for_contention()` splits Wave 1, roots like ENH-377 end up in later sub-waves and are never passed to `build_chain()`.
  2. **Isolated node fallback skips chain traversal** (line 426-427): Issues not visited by `build_chain()` fall to `for issue_id in sorted(all_ids - visited)` which appends bare IDs (`chains.append(f"  {issue_id}")`) without calling `build_chain()` to discover their edges.

## Proposed Solution

Replace positional root detection with structural root detection from the dependency graph:

```python
# Instead of:
roots: list[str] = []
for wave in waves[:1]:  # First wave has roots
    for issue in wave:
        roots.append(issue.issue_id)

# Use:
all_ids = {issue.issue_id for wave in waves for issue in wave}
roots = [
    iid for iid in sorted(all_ids)
    if not (dep_graph.blocked_by.get(iid, set()) & all_ids)
]
```

Additionally, the isolated-node fallback should call `build_chain()` instead of printing bare IDs, or be removed entirely since issues with no edges provide no graph value.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sprint.py` — `_render_dependency_graph()`

### Dependent Files (Callers/Importers)
- `_cmd_sprint_show()` calls `_render_dependency_graph()` — no change needed

### Tests
- `scripts/tests/test_cli.py` — add test for graph rendering after contention splitting
- `scripts/tests/test_dependency_graph.py` — existing tests unaffected (graph data is correct; bug is rendering only)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace `waves[:1]` root detection with structural detection from `dep_graph.blocked_by`
2. Remove or fix the isolated-node fallback to call `build_chain()` instead of bare ID append
3. Add test with contention-split waves that have actual dependency edges
4. Verify existing sprint show tests still pass

## Impact

- **Priority**: P3 - Functional bug in sprint visualization; edges exist in data but aren't rendered
- **Effort**: Small - Two targeted changes in one function
- **Risk**: Low - Display-only change, no execution logic affected
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system and dependency graph design |

## Blocked By

_None_

## Blocks

_None_

## Labels

`bug`, `cli`, `sprint`, `captured`

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/sprint.py`: Replaced positional root detection (`waves[:1]`) with structural detection using `dep_graph.blocked_by`, and removed isolated-node fallback that printed bare IDs without edges
- `scripts/tests/test_cli.py`: Added test for dependency graph rendering after contention wave splitting

### Verification Results
- Tests: PASS (2734 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

## Session Log
- `/ll:capture-issue` - 2026-02-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff26efc-756f-45c9-b95d-159619b176d9.jsonl`
- `/ll:manage-issue` - 2026-02-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b270f60-8f2c-476b-9a02-8a8bbc3c6ef2.jsonl`

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P3
