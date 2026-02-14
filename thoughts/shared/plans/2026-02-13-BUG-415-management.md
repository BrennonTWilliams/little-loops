# BUG-415: Dependency graph misses edges after contention wave splitting - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-415-dependency-graph-misses-edges-after-contention-split.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

`_render_dependency_graph()` at `scripts/little_loops/cli/sprint.py:357-433` uses positional root detection (`waves[:1]`) to find dependency chain roots. After `refine_waves_for_contention()` splits Wave 0 into sub-waves, roots like ENH-377 end up in later sub-waves and are never passed to `build_chain()`. The isolated-node fallback at line 426 prints bare IDs without edges.

### Key Discoveries
- `sprint.py:414`: `waves[:1]` only captures sub-wave 0 after contention splitting
- `sprint.py:426-427`: Isolated fallback appends bare IDs, never calls `build_chain()`
- `dependency_mapper.py:759-763`: `format_text_graph()` already uses correct structural root detection pattern
- `sprint.py:375-377`: Edge existence check already computes `all_ids` structurally — same approach should be used for roots

## Desired End State

`_render_dependency_graph()` correctly renders all dependency edges regardless of contention wave splitting. Issues without dependency edges are omitted from the graph.

### How to Verify
- Existing tests still pass
- New test: contention-split waves with dependency edges renders the edge
- New test: only issues with edges appear in the graph (isolated issues omitted)

## What We're NOT Doing
- Not changing `refine_waves_for_contention()` — the splitting is correct
- Not changing `build_chain()` — the chain builder is correct
- Not changing `_render_execution_plan()` — only the graph renderer is affected

## Problem Analysis

Two compounding bugs in `_render_dependency_graph()`:

1. **Root detection is positional** (line 414): `waves[:1]` assumes roots are in the first wave element. After contention splitting, the first wave element is a sub-wave that may only contain a subset of roots.

2. **Isolated fallback skips edges** (line 426-427): Issues not reached by `build_chain()` are printed as bare IDs without discovering their edges.

## Solution Approach

Follow the structural root detection pattern from `dependency_mapper.py:759-763`. Replace positional root detection with graph-structural detection using `dep_graph.blocked_by`. Remove the isolated-node fallback entirely — issues with no edges provide no graph value.

## Code Reuse & Integration

- **Pattern to follow**: `dependency_mapper.py:759-763` — structural root detection
- **Reuse as-is**: `dep_graph.blocked_by` map already provides the data needed
- **Test helper to reuse**: `_make_issue()` staticmethod in `test_cli.py:912`

## Implementation

### Phase 1: Fix root detection and remove isolated fallback

#### Changes Required

**File**: `scripts/little_loops/cli/sprint.py`

Replace lines 412-427 (root detection + isolated fallback):

```python
# BEFORE (lines 412-427):
# Find root issues (no blockers in this graph)
roots: list[str] = []
for wave in waves[:1]:  # First wave has roots
    for issue in wave:
        roots.append(issue.issue_id)

for root in roots:
    if root not in visited:
        chain = build_chain(root)
        if chain:
            chains.insert(0, f"  {chain}")

# Handle any isolated issues not in chains
all_ids = {issue.issue_id for wave in waves for issue in wave}
for issue_id in sorted(all_ids - visited):
    chains.append(f"  {issue_id}")
```

With structural root detection (no isolated fallback):

```python
# AFTER:
# Find root issues structurally (not blocked by anything in this graph)
all_ids = {issue.issue_id for wave in waves for issue in wave}
roots = [
    iid for iid in sorted(all_ids)
    if not (dep_graph.blocked_by.get(iid, set()) & all_ids)
]

for root in roots:
    if root not in visited:
        chain = build_chain(root)
        if chain:
            chains.append(f"  {chain}")
```

Note: `all_ids` is already computed at line 375 for the edge check. We can reuse that by moving the variable to function scope (or just recompute — it's cheap).

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli.py -k "TestSprintShowDependencyVisualization" -v`
- [ ] All existing dependency graph tests still pass

### Phase 2: Add test for contention-split waves with dependency edges

#### Changes Required

**File**: `scripts/tests/test_cli.py`

Add test to `TestSprintShowDependencyVisualization` class:

```python
def test_render_dependency_graph_after_contention_split(self) -> None:
    """Dependency edges render correctly when waves are split by contention."""
    from little_loops.cli import _render_dependency_graph
    from little_loops.dependency_graph import DependencyGraph

    # Simulate the scenario from BUG-415:
    # ENH-377 blocks ENH-371, but contention splits wave 0 into sub-waves
    issue_370 = self._make_issue("ENH-370", priority="P1", title="No deps")
    issue_377 = self._make_issue("ENH-377", priority="P1", title="Blocker")
    issue_378 = self._make_issue("ENH-378", priority="P1", title="No deps 2")
    issue_371 = self._make_issue(
        "ENH-371", priority="P1", title="Blocked", blocked_by=["ENH-377"]
    )

    graph = DependencyGraph.from_issues([issue_370, issue_377, issue_378, issue_371])
    # Simulate post-contention waves: wave 0 split into 3 sub-waves + dep wave
    waves = [[issue_370], [issue_377], [issue_378], [issue_371]]

    output = _render_dependency_graph(waves, graph)

    assert "DEPENDENCY GRAPH" in output
    assert "ENH-377 ──→ ENH-371" in output
    # Issues without edges should NOT appear
    assert "ENH-370" not in output
    assert "ENH-378" not in output
```

#### Success Criteria
- [ ] New test passes: `python -m pytest scripts/tests/test_cli.py -k "test_render_dependency_graph_after_contention_split" -v`
- [ ] Full test suite: `python -m pytest scripts/tests/`

## Testing Strategy

### Unit Tests
- New: contention-split waves with edges → edges rendered
- New: only edge-participating issues appear (isolated ones omitted)
- Existing: chain test, single-wave test, multi-wave-no-edges test all still pass

## References

- Original issue: `.issues/bugs/P3-BUG-415-dependency-graph-misses-edges-after-contention-split.md`
- Pattern: `scripts/little_loops/dependency_mapper.py:759-763`
- Bug location: `scripts/little_loops/cli/sprint.py:412-427`
