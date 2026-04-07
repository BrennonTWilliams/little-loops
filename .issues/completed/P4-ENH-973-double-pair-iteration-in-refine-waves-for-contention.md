---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# ENH-973: `refine_waves_for_contention` iterates all pairs twice when conflicts exist

## Summary

`refine_waves_for_contention` performs two separate O(n²) passes over the same set of issue pairs: one to detect conflicts via `overlaps_with`, and a second to collect contended paths via `get_overlapping_paths`. When conflicts exist, every conflicting pair is processed twice. Both checks can be combined into a single pass since `get_overlapping_paths` is a superset of `overlaps_with`.

## Location

- **File**: `scripts/little_loops/dependency_graph.py`
- **Line(s)**: 380–398 (at scan commit: 96d74cda)
- **Anchor**: `in function refine_waves_for_contention`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/dependency_graph.py#L380-L398)
- **Code**:
```python
# First pass — detect conflicts:
for a, b in combinations(wave, 2):
    if hints[a].overlaps_with(hints[b]):
        conflicts.add(a); conflicts.add(b)

# Second pass — collect contended paths (identical pair iteration):
for a, b in combinations(wave, 2):
    paths = hints[a].get_overlapping_paths(hints[b])
    if paths:
        contended |= paths
```

## Current Behavior

When a wave has conflicts, the full `combinations(wave, 2)` set is iterated twice. `overlaps_with` and `get_overlapping_paths` operate on the same underlying data; `get_overlapping_paths` returns the paths when there is overlap (equivalent to `overlaps_with` returning `True`).

## Expected Behavior

A single pass over pairs collects both the conflict adjacency set and the contended paths, halving the pair comparison work.

## Motivation

`refine_waves_for_contention` is called per wave during sprint and parallel planning. For large waves, the quadratic pair count makes double-iteration a meaningful overhead.

## Proposed Solution

```python
for a, b in combinations(wave, 2):
    paths = hints[a].get_overlapping_paths(hints[b])
    if paths:
        conflicts.add(a); conflicts.add(b)
        contended |= paths
# Remove the second loop entirely
```

This works because `get_overlapping_paths` returns a non-empty set exactly when `overlaps_with` would return `True`.

## API/Interface

N/A - No public API changes

## Scope Boundaries

- Only merge the two loops; do not change the conflict/contention threshold logic or return structure

## Success Metrics

- `refine_waves_for_contention` contains a single `combinations` loop for conflict detection

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention` (lines 378–398: the two `enumerate`/slice pair loops)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/run.py:222` — `waves, contention_notes = refine_waves_for_contention(waves, config=config.dependency_mapping)` — sprint execution planning
- `scripts/little_loops/cli/sprint/manage.py:111` — `waves, contention_notes = refine_waves_for_contention(waves, config=dep_config)` — conflict reporting
- `scripts/little_loops/cli/sprint/show.py:187` — `waves, contention_notes = refine_waves_for_contention(waves, config=dep_config)` — wave display
- `scripts/little_loops/parallel/file_hints.py:84,178` — defines `overlaps_with` and `get_overlapping_paths` on `FileHints`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/_helpers.py:11,40` — imports `WaveContentionNote` (TYPE_CHECKING guard); docstring at line 40 names `refine_waves_for_contention` and its output contract — no code change needed, read-only dependency

### Similar Patterns

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/sprint/manage.py:120-132` — calls both `overlaps_with` and `get_overlapping_paths` in a single loop iteration (pair-check plus path collection inline, no double pass). This is the established pattern to follow.
- `scripts/little_loops/dependency_mapper/analysis.py:307-316` — uses raw set intersection checked for non-emptiness directly (no `overlaps_with` guard), with a comment noting it matches `FileHints.overlaps_with` logic.

### Tests
- `scripts/tests/test_dependency_graph.py:664-837` — `TestRefineWavesForContention` (12 test methods); all tests verify external outputs (sub-wave membership, `WaveContentionNote` fields), not internal iteration count
- `scripts/tests/test_file_hints.py:424-501` — `TestGetOverlappingPaths` confirms `get_overlapping_paths` returns `set()` in all cases `overlaps_with` returns `False`
- `scripts/tests/test_sprint_integration.py:420,484` — integration-level references to `refine_waves_for_contention` behavior

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — ~14 test methods exercise `_render_execution_plan` and `_render_dependency_graph` which consume `WaveContentionNote` objects downstream; safe (output contract unchanged by the loop merge)
- **No mocks of `overlaps_with` or `get_overlapping_paths` exist anywhere in the test suite** — the loop merge (removing the `overlaps_with` call) will not leave any dead mocks and all 12 `TestRefineWavesForContention` tests exercise the real `FileHints` call chain end-to-end via `_make_issue_with_content`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `dependency_graph.py:378-398`, replace the two `for i, a in enumerate(wave): for b in wave[i + 1:]` loops with a single merged loop:
   ```python
   # Single pass — build conflict adjacency and collect contended paths together
   conflicts: dict[str, set[str]] = {issue.issue_id: set() for issue in wave}
   contended: set[str] = set()
   for i, a in enumerate(wave):
       for b in wave[i + 1 :]:
           paths = hints[a.issue_id].get_overlapping_paths(hints[b.issue_id], config=config)
           if paths:
               conflicts[a.issue_id].add(b.issue_id)
               conflicts[b.issue_id].add(a.issue_id)
               contended |= paths
   ```
   Then remove the standalone `contended: set[str] = set()` block that was formerly at lines 392-398, and move `contended_paths = sorted(contended)` to after the single loop (before the early-exit check).
2. Adjust the early-exit block (`if not any(conflicts.values())`) at line 386 — it moves to after the merged loop but must now guard `contended_paths` use too; `contended` will be empty exactly when no conflicts exist.
3. Add a test in `scripts/tests/test_dependency_graph.py` inside `TestRefineWavesForContention` using `mock_path.read_text` (follow `_make_issue_with_content` helper at line 637) to verify `contended_paths` on the `WaveContentionNote` matches the correct overlapping files — this validates semantic equivalence after merge.
4. Run `python -m pytest scripts/tests/test_dependency_graph.py::TestRefineWavesForContention -v` and `scripts/tests/test_sprint_integration.py -v` to confirm no behavior change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Semantics confirmed**: `get_overlapping_paths` (file_hints.py:178) returns a non-empty `set[str]` if and only if `overlaps_with` (file_hints.py:84) returns `True`. Both methods apply identical emptiness guards, threshold resolution, and filtering logic. `overlaps_with` short-circuits on the first match; `get_overlapping_paths` collects all matching paths and returns them — which is why it is safe to replace the bool check with `if paths:`.

**Loop structure note**: The actual production code uses `for i, a in enumerate(wave): for b in wave[i + 1:]` — not `combinations(wave, 2)` as shown in the issue pseudocode. The proposed solution pseudocode is illustrative; use the enumerate/slice pattern to match the existing style.

**Parallel in manage.py**: `cli/sprint/manage.py:120-132` already does `overlaps_with` then `get_overlapping_paths` in one loop body. The merged loop here goes one step further — eliminate the `overlaps_with` call entirely and just test the set.

## Impact

- **Priority**: P4 — Minor optimization for an already fast path; worth doing for correctness of the pattern
- **Effort**: Small — Remove one loop, add two lines to the other
- **Risk**: Low — Pure algorithmic refactor with identical semantics
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-06T21:46:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1edc8d3d-445a-4fa8-b108-e2eb949c2fc1.jsonl`
- `/ll:ready-issue` - 2026-04-06T21:46:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1edc8d3d-445a-4fa8-b108-e2eb949c2fc1.jsonl`
- `/ll:ready-issue` - 2026-04-06T21:46:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1edc8d3d-445a-4fa8-b108-e2eb949c2fc1.jsonl`
- `/ll:ready-issue` - 2026-04-06T21:46:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1edc8d3d-445a-4fa8-b108-e2eb949c2fc1.jsonl`
- `/ll:confidence-check` - 2026-04-06T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1be35860-22ad-4f3a-b0ee-03874711c040.jsonl`
- `/ll:wire-issue` - 2026-04-06T21:41:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef0de39e-b118-4aa2-93da-289cabc4f132.jsonl`
- `/ll:refine-issue` - 2026-04-06T21:37:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7819baad-acc7-4d97-a9d2-cc35365503a9.jsonl`
- `/ll:format-issue` - 2026-04-06T21:34:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d45f0009-410f-4a18-b401-38d77214ff65.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Resolution

Merged the two O(n²) `combinations` loops into a single pass. `get_overlapping_paths` is now called once per pair; its non-empty result drives both conflict adjacency and contended-path collection. Added `test_contended_paths_multi_file_overlap` to verify all overlapping files are collected across multiple pairs. 13/13 unit tests + 25/25 sprint integration tests pass.

## Status

**Completed** | Created: 2026-04-06 | Resolved: 2026-04-06 | Priority: P4
