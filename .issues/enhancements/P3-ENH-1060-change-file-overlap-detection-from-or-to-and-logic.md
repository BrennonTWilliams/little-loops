---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
---

# ENH-1060: Change sprint file-overlap detection from OR to AND logic

## Summary

`FileHints.overlaps_with()` in `file_hints.py:126` uses an OR condition to trigger serialization: if two issues share `>= min_files` files **or** share `>= ratio_threshold` of the smaller set, they are serialized into separate steps. This means a single shared hub file (e.g., `App.jsx`) out of 4 total files hits the 25% ratio threshold alone (`1/4 = 0.25`) and forces serialization — even when the changes to that file are to completely different sections. In focused single-component sprints, this creates large cliques where every issue conflicts with every other, collapsing the wave into fully sequential steps.

## Location

- **File**: `scripts/little_loops/parallel/file_hints.py`
- **Line(s)**: 120–127 (`overlaps_with()` file count + ratio check)
- **Anchor**: `in method overlaps_with`
- **Code**:
```python
shared_files = self_files & other_files
if shared_files:
    smaller_set = min(len(self_files), len(other_files))
    if smaller_set > 0:
        ratio = len(shared_files) / smaller_set
        if len(shared_files) >= min_files or ratio >= ratio_threshold:  # ← OR
            return True
```

## Current Behavior

One shared file out of four is enough to trigger serialization (25% ratio). In a sprint where all issues touch a common hub file like `App.jsx` or `index.ts`, this creates a complete conflict graph (K-N), forcing all N issues into N sequential steps regardless of actual code-section overlap.

## Expected Behavior

Both conditions must be satisfied simultaneously:

```python
if len(shared_files) >= min_files and ratio >= ratio_threshold:  # AND
    return True
```

A single shared hub file no longer triggers serialization unless it represents ≥25% of the smaller set **and** there are at least 2 shared files total. Issues with only trivial file overlap remain in parallel.

## Motivation

The OR condition was conservative — it preferred false positives (unnecessary serialization) over false negatives (merge conflicts). But in focused sprints this over-fires aggressively: 10/11 issues serialized for a single-component viewer sprint, eliminating all meaningful parallelism. The AND condition still catches real conflicts (≥2 files, ≥25%) while allowing single-hub-file pairs to run in parallel where the actual changes won't overlap.

## Proposed Solution

Change line 126 in `file_hints.py` from `or` to `and`:

```python
if len(shared_files) >= min_files and ratio >= ratio_threshold:
```

Update `get_overlapping_paths()` (line 201, same file) identically — it duplicates the same condition for returning the overlapping path set.

## Scope Boundaries

- Only change the boolean operator; do not change default threshold values or other detection paths (directory overlap, file-in-directory)
- `contends_with()` (used for worktree isolation, not sprint scheduling) is unaffected

## Success Metrics

- Two issues sharing only 1 file (below `min_files=2`) no longer trigger serialization
- Two issues sharing 3+ files still serialize
- Existing tests pass or are updated to reflect the new logic

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — `overlaps_with()` line 126, `get_overlapping_paths()` line 201

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention()` calls `overlaps_with()` / `get_overlapping_paths()`

### Tests
- `scripts/tests/test_file_hints.py` — overlap detection unit tests; update threshold boundary cases
- `scripts/tests/test_dependency_graph.py` — wave contention tests

### Configuration
- `config-schema.json` — `dependency_mapping.overlap_min_files`, `dependency_mapping.overlap_min_ratio` (unchanged; AND makes defaults less aggressive without changing their values)

## Implementation Steps

1. In `file_hints.py:126`, change `or` to `and` in the shared-file condition
2. Apply the same change in `get_overlapping_paths()` at line 201
3. Update unit tests for the boundary case: 1 shared file of 4 no longer triggers overlap
4. Run full test suite

## Impact

- **Priority**: P3 — Directly reduces over-serialization in single-component sprints; restores intended parallelism
- **Effort**: Tiny — Two-character change (`or` → `and`) in two lines; test updates required
- **Risk**: Low — Makes detection less conservative; real conflicts (≥2 shared files) still serialize correctly
- **Breaking Change**: No

## Labels

`enhancement`, `sprint`, `parallelism`, `file-hints`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`

## Status

**Open** | Created: 2026-04-12 | Priority: P3
