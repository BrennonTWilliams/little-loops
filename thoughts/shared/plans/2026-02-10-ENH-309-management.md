# ENH-309: Sprint execution plan shows file contention warnings - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-309-sprint-execution-plan-shows-file-contention-warnings.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `_render_execution_plan()` at `cli.py:1520` builds a tree-format string showing waves, issues, and blockers but has no contention info
- `refine_waves_for_contention()` at `dependency_graph.py:321` computes file hints and conflict graphs internally but discards them after splitting — only the refined waves are returned
- Two rendering paths exist: `_cmd_sprint_show()` calls `_render_execution_plan()`, while `_cmd_sprint_run()` has its own inline logger-based rendering (lines 1922-1926)
- `FileHints.overlaps_with()` at `file_hints.py:61` returns only `bool` — to show which specific files are contended, set intersections are needed (pattern from `OverlapDetector` at `overlap_detector.py:97`)
- The established file-list display pattern truncates to 3 files + "and more" (used in `cli.py:1822` and `dependency_mapper.py:607`)

### Patterns to Follow
- Tree characters `├──`, `└──`, `│` for nesting (cli.py:1556)
- `Logger.warning()` for warning output (logger.py:12)
- `_make_issue_with_content()` mock pattern from `test_dependency_graph.py:611` for tests
- Existing `TestSprintShowDependencyVisualization` test class at `test_cli.py:909`

## Desired End State

The execution plan output annotates waves that were split by ENH-306's contention system, showing:
1. Which sub-wave this is (e.g., "sub-wave 1/3")
2. The specific contended files/directories that caused the split

Example after splitting:
```
Wave 2 (after Wave 1):
  └── FEAT-031: Add priority starring (P2)
  ⚠  File contention — sub-wave 1/3
     Contended: src/app/page.tsx

Wave 3 (after Wave 2):
  └── ENH-032: Add empty state placeholder (P3)
  ⚠  File contention — sub-wave 2/3
     Contended: src/app/page.tsx
```

### How to Verify
- `python -m pytest scripts/tests/ -v` — all tests pass
- `ruff check scripts/` — no lint errors
- `python -m mypy scripts/little_loops/` — no type errors
- New tests cover: contention notes displayed, no contention = no annotations, multiple contention groups, `_cmd_sprint_run` inline display

## What We're NOT Doing

- Not changing wave splitting logic (already handled by ENH-306)
- Not modifying runtime overlap detection (BUG-305)
- Not adding interactive prompts or new CLI flags
- Not refactoring `_render_execution_plan()` beyond adding contention display

## Solution Approach

The core problem: `refine_waves_for_contention()` computes contention data (file hints, conflict graph) in local variables that are discarded on return. The rendering functions have no access to this data.

**Solution**: Modify `refine_waves_for_contention()` to return contention metadata alongside the refined waves, then consume it in both rendering paths.

### Data Structure

Add a simple `WaveContentionNote` dataclass to `dependency_graph.py`:

```python
@dataclass
class WaveContentionNote:
    """Annotation for a wave that was split due to file contention."""
    contended_paths: list[str]
    sub_wave_index: int     # 0-based index within the split group
    total_sub_waves: int    # total sub-waves in the split group
```

### Return Type Change

`refine_waves_for_contention()` returns `tuple[list[list[IssueInfo]], list[WaveContentionNote | None]]` where the second list is parallel to the first (same length, one entry per refined wave).

### Overlapping Path Computation

Add `get_overlapping_paths(other: FileHints) -> set[str]` to `FileHints`, computing the union of:
- `self.files & other.files` (exact file matches)
- Overlapping directories (shorter/parent path)
- Files contained in the other's directories

This follows the pattern from `OverlapDetector.check_overlap()` at `overlap_detector.py:97`.

## Code Reuse & Integration

- **Reuse `extract_file_hints()`** — already used in `refine_waves_for_contention()`, no change needed
- **Reuse `FileHints.overlaps_with()`** — still used for the bool check; `get_overlapping_paths()` adds specific path extraction
- **Reuse truncate-to-3 pattern** — inline in `_render_execution_plan()`, following `cli.py:1822`
- **Reuse `_make_issue_with_content()` pattern** — from `test_dependency_graph.py:611` for new tests
- **New code justification**: `WaveContentionNote` dataclass (new, needed to carry metadata), `get_overlapping_paths()` method (new, `overlaps_with()` only returns bool)

## Implementation Phases

### Phase 1: Add `get_overlapping_paths()` to `FileHints`

#### Overview
Add a method to `FileHints` that returns the specific paths causing an overlap, complementing `overlaps_with()` which only returns bool.

#### Changes Required

**File**: `scripts/little_loops/parallel/file_hints.py`
**Changes**: Add `get_overlapping_paths()` method after `overlaps_with()` (after line 97)

```python
def get_overlapping_paths(self, other: FileHints) -> set[str]:
    """Get specific paths that overlap between two hint sets."""
    if self.is_empty or other.is_empty:
        return set()

    overlapping: set[str] = set()

    # Exact file matches
    overlapping.update(self.files & other.files)

    # Directory overlaps (use shorter/parent path)
    for d1 in self.directories:
        for d2 in other.directories:
            if _directories_overlap(d1, d2):
                overlapping.add(d1 if len(d1) <= len(d2) else d2)

    # File in directory
    for f in self.files:
        for d in other.directories:
            if _file_in_directory(f, d):
                overlapping.add(f)
    for f in other.files:
        for d in self.directories:
            if _file_in_directory(f, d):
                overlapping.add(f)

    return overlapping
```

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_file_hints.py -v` — passes with new tests for `get_overlapping_paths()`
- [ ] `ruff check scripts/little_loops/parallel/file_hints.py`
- [ ] `python -m mypy scripts/little_loops/parallel/file_hints.py`

---

### Phase 2: Add `WaveContentionNote` and modify `refine_waves_for_contention()`

#### Overview
Add a contention note dataclass and modify the wave splitting function to return contention metadata alongside the refined waves.

#### Changes Required

**File**: `scripts/little_loops/dependency_graph.py`
**Changes**:
1. Add `WaveContentionNote` dataclass after the existing imports (before `DependencyGraph`)
2. Modify `refine_waves_for_contention()` return type and implementation

Add dataclass (after line 17, before `DependencyGraph`):
```python
@dataclass
class WaveContentionNote:
    """Annotation for a wave that was split due to file contention."""
    contended_paths: list[str]
    sub_wave_index: int
    total_sub_waves: int
```

Modify `refine_waves_for_contention()`:
- Change return type to `tuple[list[list[IssueInfo]], list[WaveContentionNote | None]]`
- Add `annotations: list[WaveContentionNote | None] = []` alongside `refined`
- For non-split waves: `annotations.append(None)`
- For split waves: collect overlapping paths from pairwise `get_overlapping_paths()`, then annotate each sub-wave
- Return `(refined, annotations)`

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_dependency_graph.py -v` — existing tests pass (updated for tuple return)
- [ ] `ruff check scripts/little_loops/dependency_graph.py`
- [ ] `python -m mypy scripts/little_loops/dependency_graph.py`

---

### Phase 3: Update `_render_execution_plan()` and callers

#### Overview
Add contention note display to the execution plan rendering and update both caller sites.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

1. Update import of `refine_waves_for_contention` to also import `WaveContentionNote`
2. Add optional `contention_notes` parameter to `_render_execution_plan()`:
   ```python
   def _render_execution_plan(
       waves: list[list[Any]],
       dep_graph: DependencyGraph,
       contention_notes: list[WaveContentionNote | None] | None = None,
   ) -> str:
   ```
3. After rendering each wave's issues/blockers, add contention annotation if present:
   ```python
   # After the blocker rendering loop (after line 1570)
   if contention_notes and wave_num <= len(contention_notes):
       note = contention_notes[wave_num - 1]
       if note:
           lines.append(
               f"  ⚠  File contention — sub-wave "
               f"{note.sub_wave_index + 1}/{note.total_sub_waves}"
           )
           paths_str = ", ".join(note.contended_paths[:3])
           if len(note.contended_paths) > 3:
               paths_str += f" +{len(note.contended_paths) - 3} more"
           lines.append(f"     Contended: {paths_str}")
   ```
4. Update `_cmd_sprint_show()` at line 1671:
   ```python
   waves, contention_notes = refine_waves_for_contention(waves)
   # ...
   print(_render_execution_plan(waves, dep_graph, contention_notes))
   ```
5. Update `_cmd_sprint_run()` at line 1919:
   ```python
   waves, contention_notes = refine_waves_for_contention(waves)
   # ...
   # In the inline display loop, add contention info
   for i, wave in enumerate(waves, 1):
       issue_ids = ", ".join(issue.issue_id for issue in wave)
       note = contention_notes[i - 1] if contention_notes else None
       if note:
           logger.info(f"  Wave {i}: {issue_ids} [sub-wave {note.sub_wave_index + 1}/{note.total_sub_waves}]")
       else:
           logger.info(f"  Wave {i}: {issue_ids}")
   ```

#### Success Criteria
- [ ] `python -m pytest scripts/tests/test_cli.py -v` — existing tests pass
- [ ] `ruff check scripts/little_loops/cli.py`
- [ ] `python -m mypy scripts/little_loops/cli.py`

---

### Phase 4: Add tests

#### Overview
Add tests for the new contention display functionality.

#### Changes Required

**File**: `scripts/tests/test_file_hints.py`
- Add tests for `get_overlapping_paths()`: exact file match, directory overlap, file-in-directory, empty hints, no overlap

**File**: `scripts/tests/test_dependency_graph.py`
- Update existing `TestRefineWavesForContention` tests to unpack tuple return
- Add test: contention notes contain correct sub_wave_index and total_sub_waves
- Add test: contention notes contain correct contended_paths
- Add test: non-split waves have None annotations

**File**: `scripts/tests/test_cli.py`
- Add to `TestSprintShowDependencyVisualization`:
  - `test_render_execution_plan_with_contention_notes`: verify ⚠ and contention display
  - `test_render_execution_plan_no_contention_notes`: verify no change when parameter is None
  - `test_render_execution_plan_mixed_contention`: some waves split, some not

#### Success Criteria
- [ ] `python -m pytest scripts/tests/ -v` — all tests pass
- [ ] `ruff check scripts/` — clean
- [ ] `python -m mypy scripts/little_loops/` — clean

## Testing Strategy

### Unit Tests
- `FileHints.get_overlapping_paths()` — exact matches, directory containment, mixed, empty sets
- `refine_waves_for_contention()` — returns correct tuple with annotations
- `_render_execution_plan()` — renders contention notes in output when provided

### Integration Tests
- End-to-end: sprint with contention → plan shows warnings

## References

- Original issue: `.issues/enhancements/P3-ENH-309-sprint-execution-plan-shows-file-contention-warnings.md`
- `_render_execution_plan()`: `scripts/little_loops/cli.py:1520`
- `refine_waves_for_contention()`: `scripts/little_loops/dependency_graph.py:321`
- `FileHints`: `scripts/little_loops/parallel/file_hints.py:36`
- Overlap pattern: `scripts/little_loops/parallel/overlap_detector.py:97`
- File truncation pattern: `scripts/little_loops/cli.py:1822`
- Existing tests: `scripts/tests/test_cli.py:909`, `scripts/tests/test_dependency_graph.py:633`
