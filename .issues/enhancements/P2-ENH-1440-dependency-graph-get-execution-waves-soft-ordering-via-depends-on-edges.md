---
id: ENH-1440
type: ENH
priority: P2
parent: ENH-1436
depends_on:
- ENH-1439
status: completed
completed_at: 2026-05-11
---

# ENH-1440: Update `get_execution_waves()` for soft ordering via `depends_on_edges`

## Summary

Update the BFS loop in `get_execution_waves()` to respect `depends_on_edges` for soft ordering: after each wave is collected, nudge `depends_on` targets to the earliest possible wave without hard-blocking the dependent. Depends on ENH-1439 (`depends_on_edges` field must exist). Includes soft-ordering and non-blocking test cases.

## Current Behavior

`get_execution_waves()` in `dependency_graph.py` builds BFS waves respecting only hard-block constraints (`blocks`/`blocked_by` edges). It does not inspect `depends_on_edges`, so issues whose `depends_on` targets could be scheduled earlier remain in their naturally later BFS position.

## Expected Behavior

After updating, `get_execution_waves()` inspects `depends_on_edges` after each BFS wave and nudges `depends_on` targets to the earliest possible wave — without treating them as hard blockers. The dependent issue always enters a wave regardless; only its preferred ordering is applied.

## Motivation

This enhancement:
- Enables soft scheduling hints: issues express preferred ordering without blocking each other
- Improves sprint execution efficiency by surfacing `depends_on` targets earlier in the plan
- Completes step 2 of ENH-1436's soft-ordering feature (ENH-1439 adds the field; this step uses it)

## Parent Issue

Decomposed from ENH-1436: DependencyGraph soft-ordering via `depends_on`

## Scope Boundaries

Step 2 from ENH-1436 plus the soft-ordering and non-blocking test cases. Does **not** include the field addition or `from_issues()` population (those are ENH-1439).

## Proposed Solution

### Step 2 — Update `get_execution_waves()` (`dependency_graph.py:154`)

After each wave is collected in the BFS loop (lines 154–201), check whether any `depends_on` targets of remaining issues are not yet in `processed`. If so, reorder those targets to the earliest possible wave without introducing hard blocks.

Key constraint: `depends_on` **never prevents** an issue from entering a wave — it only nudges targets earlier. This is purely a reordering suggestion, not a hard blocker.

The insertion point is the BFS loop at lines 154–201. The algorithm must:
1. After collecting a wave, inspect `depends_on_edges` of issues in that wave
2. For each `depends_on` target not yet `processed`, attempt to move it to the current or earlier wave if no hard block prevents it
3. Never delay the dependent — if the target can't move earlier without violating hard-block constraints, leave it where it would naturally fall

### Algorithm Note

The acceptance criteria test observable output only (set membership in waves). Choose the simplest correct approach; document the mechanism briefly in a code comment if the ordering logic is non-obvious. At minimum cover: single-hop `depends_on`, `depends_on` target already processed, `depends_on` target in a later wave moves earlier.

## Implementation Steps

1. Update the BFS loop in `get_execution_waves()` to inspect `depends_on_edges` after each wave is collected
2. Implement nudge algorithm: for each `depends_on` target not yet processed, move it to the current or earlier wave if no hard block prevents it
3. Add `test_depends_on_soft_ordering()` — assert target is in wave 0 not wave 1 after nudge
4. Add `test_depends_on_does_not_hard_block()` — assert dependent still enters a wave even when target is absent or in the same wave
5. Run all existing wave-generation and sprint integration tests to verify no regressions

## Files to Modify

- `scripts/little_loops/dependency_graph.py` — `get_execution_waves()` (lines 154–201)
- `scripts/tests/test_dependency_graph.py` — 2 new test cases

## Tests

Requires ENH-1439's extended `make_issue()` helper (with `depends_on` kwarg) to be in place.

1. **`test_depends_on_soft_ordering()`**: assert that an issue whose `depends_on` target would naturally fall in wave 2 is instead nudged to wave 1. Use set-membership assertions: `assert "TARGET" in {i.issue_id for i in waves[0]}` (model: lines 596–603).
2. **`test_depends_on_does_not_hard_block()`**: confirm the dependent issue still enters a wave even when its `depends_on` target is absent or in the same wave — soft-ordering does not hard-block.

## Acceptance Criteria

- `get_execution_waves()` respects `depends_on_edges` for soft ordering (target nudged to earlier wave, not required)
- `depends_on` never prevents a dependent from entering a wave
- `test_depends_on_soft_ordering()` passes
- `test_depends_on_does_not_hard_block()` passes
- All existing wave-generation tests still pass
- `test_sprint_integration.py` shows no regressions

## Wiring (Callers — verify no regressions, no changes needed)

- `scripts/little_loops/issue_manager.py:1003` — calls `DependencyGraph.from_issues()`
- `scripts/little_loops/sprint.py` — consumes execution waves
- `scripts/little_loops/cli/sprint/run.py` — executes sprints using waves
- `scripts/little_loops/cli/sprint/show.py` — `_render_dependency_graph()` reads `dep_graph.blocks` and `dep_graph.blocked_by` only; safe
- `scripts/little_loops/cli/sprint/_helpers.py` — `_render_execution_plan()` reads `.blocked_by.get(...)` at two points; wave display will not annotate `depends_on`-nudged placement (acceptable)
- `scripts/little_loops/cli/issues/sequence.py` — sequences by dependency order
- `scripts/little_loops/cli/issues/clusters.py` — visualizes clusters

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — `get_execution_waves()` BFS loop

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — calls `DependencyGraph.from_issues()`
- `scripts/little_loops/sprint.py` — consumes execution waves
- `scripts/little_loops/cli/sprint/run.py` — executes sprints using waves
- `scripts/little_loops/cli/sprint/show.py` — reads `blocks`/`blocked_by` only; safe
- `scripts/little_loops/cli/sprint/_helpers.py` — reads `.blocked_by.get(...)` at two points; wave display will not annotate nudged placement
- `scripts/little_loops/cli/issues/sequence.py` — sequences by dependency order
- `scripts/little_loops/cli/issues/clusters.py` — visualizes clusters

### Similar Patterns
- TBD — `grep -r "get_execution_waves" scripts/`

### Tests
- `scripts/tests/test_dependency_graph.py` — 2 new test cases + existing wave tests
- `scripts/tests/test_sprint_integration.py` — regression check (no changes expected)

### Documentation
- N/A — internal algorithm change, no public API or user-facing docs affected

### Configuration
- N/A

## Impact

- **Priority**: P2 — Completes soft-ordering semantics for `depends_on`; needed for sprint execution to respect ordering hints
- **Effort**: Small — Single BFS loop modification + 2 new test cases; algorithm is well-scoped
- **Risk**: Low — Soft ordering only nudges scheduling; hard-block constraints unaffected; all existing tests must pass
- **Breaking Change**: No

## Labels

`enhancement`, `dependency-graph`, `sprint`

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-11T04:00:00 - implementation complete; 70/70 tests pass; 26/26 sprint integration tests pass
- `/ll:format-issue` - 2026-05-11T03:08:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb251496-34dc-4e1c-8e97-be3d12f1a4a5.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
