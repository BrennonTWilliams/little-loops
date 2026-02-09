# ENH-306: File-Contention-Aware Wave Splitting - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-306-file-contention-aware-wave-splitting.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

`DependencyGraph.get_execution_waves()` at `dependency_graph.py:119-166` computes waves purely from `blocked_by` relationships. Issues with no dependency relationship but touching the same files are grouped in the same wave, causing merge conflicts during parallel dispatch.

### Key Discoveries
- `get_execution_waves()` returns `list[list[IssueInfo]]` — each `IssueInfo` has a `.path: Path` field for reading issue content
- `extract_file_hints(content, issue_id)` at `file_hints.py:113-142` extracts file/dir/scope hints from markdown
- `FileHints.overlaps_with()` at `file_hints.py:61-97` does pairwise overlap checking (empty hints → no overlap)
- `OverlapDetector.register_issue()` at `overlap_detector.py:67-84` shows the canonical pattern: `content = issue.path.read_text() if issue.path.exists() else ""`
- Wiring points: `cli.py:1836` (sprint run) and `cli.py:1667` (sprint show)
- Both consumers iterate `list[list[IssueInfo]]` generically — sub-waves slot in transparently
- Resume logic at `cli.py:1861-1866` uses per-issue ID matching, not wave indices — safe with sub-waves

## Desired End State

A new function `refine_waves_for_contention()` in `dependency_graph.py` that:
1. Takes the output of `get_execution_waves()` (`list[list[IssueInfo]]`)
2. For each wave with >1 issue, extracts `FileHints` and checks pairwise overlaps
3. Splits overlapping waves into sub-waves using greedy graph coloring
4. Returns a refined `list[list[IssueInfo]]` with no file contention within any single wave

### How to Verify
- Unit tests confirm wave splitting behavior for various overlap scenarios
- Existing `get_execution_waves` tests still pass (function is additive, not modifying)
- Sprint run and sprint show both display refined waves
- Runtime `OverlapDetector` remains as defense-in-depth (unchanged)

## What We're NOT Doing

- Not modifying `get_execution_waves()` itself — refinement is a separate post-processing step
- Not integrating the full dependency mapper (ENH-301) — out of scope
- Not changing `OverlapDetector` runtime behavior — that remains as a safety net
- Not handling cross-wave file contention — only intra-wave overlaps
- Not modifying `_render_execution_plan()` — sub-waves appear as additional waves automatically

## Solution Approach

Add a standalone function `refine_waves_for_contention(waves)` to `dependency_graph.py`. For each multi-issue wave, build a conflict graph (edges between overlapping issues) and apply greedy graph coloring to partition into conflict-free sub-waves. Wire it into both `_cmd_sprint_run()` and `_cmd_sprint_show()` after `get_execution_waves()`.

## Code Reuse & Integration

- **Reuse as-is**: `extract_file_hints()` from `parallel/file_hints.py:113`
- **Reuse as-is**: `FileHints.overlaps_with()` from `parallel/file_hints.py:61`
- **Reuse as-is**: `IssueInfo.path` pattern from `overlap_detector.py:70-71`
- **New code**: Greedy graph coloring algorithm (no existing equivalent in codebase)
- **New code**: `refine_waves_for_contention()` function in `dependency_graph.py`

## Implementation Phases

### Phase 1: Add `refine_waves_for_contention()` to `dependency_graph.py`

#### Overview
Add the core function that takes waves, extracts file hints, detects overlaps, and splits waves.

#### Changes Required

**File**: `scripts/little_loops/dependency_graph.py`
**Changes**: Add imports for `FileHints`, `extract_file_hints`, and `Path`. Add `refine_waves_for_contention()` function after the `DependencyGraph` class.

```python
def refine_waves_for_contention(
    waves: list[list[IssueInfo]],
) -> list[list[IssueInfo]]:
    """Refine execution waves by splitting on file contention.

    For each wave with multiple issues, extracts file hints from issue
    content and checks for pairwise overlaps. Overlapping issues are
    split into sub-waves using greedy graph coloring so no two issues
    in the same sub-wave modify the same files.

    Args:
        waves: Execution waves from get_execution_waves()

    Returns:
        Refined wave list with contention-free sub-waves.
        Single-issue waves pass through unchanged.
    """
    from little_loops.parallel.file_hints import FileHints, extract_file_hints

    refined: list[list[IssueInfo]] = []

    for wave in waves:
        if len(wave) <= 1:
            refined.append(wave)
            continue

        # Extract file hints for each issue in the wave
        hints: dict[str, FileHints] = {}
        for issue in wave:
            content = issue.path.read_text() if issue.path.exists() else ""
            hints[issue.issue_id] = extract_file_hints(content, issue.issue_id)

        # Build conflict adjacency: issue_id -> set of conflicting issue_ids
        conflicts: dict[str, set[str]] = {issue.issue_id: set() for issue in wave}
        for i, a in enumerate(wave):
            for b in wave[i + 1:]:
                if hints[a.issue_id].overlaps_with(hints[b.issue_id]):
                    conflicts[a.issue_id].add(b.issue_id)
                    conflicts[b.issue_id].add(a.issue_id)

        # If no conflicts, keep wave as-is
        if not any(conflicts.values()):
            refined.append(wave)
            continue

        # Greedy graph coloring — assign each issue the lowest color
        # not used by any conflicting neighbor
        color: dict[str, int] = {}
        for issue in wave:  # iterate in priority order (preserved from get_ready_issues)
            used_colors = {color[c] for c in conflicts[issue.issue_id] if c in color}
            c = 0
            while c in used_colors:
                c += 1
            color[issue.issue_id] = c

        # Group issues by color into sub-waves, preserving priority order
        max_color = max(color.values())
        for c in range(max_color + 1):
            sub_wave = [issue for issue in wave if color[issue.issue_id] == c]
            if sub_wave:
                refined.append(sub_wave)

        logger.info(
            f"  Wave split into {max_color + 1} sub-waves due to file contention"
        )

    return refined
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_graph.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_graph.py`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_graph.py`

---

### Phase 2: Add Tests for `refine_waves_for_contention()`

#### Overview
Add a `TestRefineWavesForContention` test class covering key scenarios.

#### Changes Required

**File**: `scripts/tests/test_dependency_graph.py`
**Changes**: Add imports for `Mock` and `Path`. Add a `make_issue_with_content()` helper using the mock path pattern from `test_overlap_detector.py`. Add test class with these tests:

1. **test_single_issue_wave_unchanged** — single-issue waves pass through
2. **test_no_overlaps_unchanged** — multi-issue wave with no file contention stays as one wave
3. **test_two_issues_same_file_split** — two issues sharing a file split into 2 sub-waves
4. **test_three_issues_two_overlap_one_independent** — 3 issues where A overlaps B but C is independent → 2 sub-waves: [A, C] and [B]
5. **test_all_three_overlap_pairwise** — 3 issues all overlapping each other → 3 sub-waves
6. **test_empty_hints_no_split** — issues with no file hints (empty content) don't trigger splitting
7. **test_mixed_waves_only_multi_refined** — multiple waves where only multi-issue waves get refined
8. **test_preserves_priority_order** — issues within sub-waves maintain priority ordering
9. **test_empty_waves_input** — empty input returns empty output

#### Success Criteria

**Automated Verification**:
- [ ] New tests pass: `python -m pytest scripts/tests/test_dependency_graph.py::TestRefineWavesForContention -v`
- [ ] All existing tests still pass: `python -m pytest scripts/tests/test_dependency_graph.py -v`

---

### Phase 3: Wire into `_cmd_sprint_run()` and `_cmd_sprint_show()`

#### Overview
Insert the `refine_waves_for_contention()` call after `get_execution_waves()` in both sprint run and sprint show.

#### Changes Required

**File**: `scripts/little_loops/cli.py`

**Change 1** (sprint run, after line 1836):
```python
# Current:
waves = dep_graph.get_execution_waves()

# After:
waves = dep_graph.get_execution_waves()
waves = refine_waves_for_contention(waves)
```

**Change 2** (sprint show, after line 1667):
```python
# Current:
waves = dep_graph.get_execution_waves()

# After:
waves = dep_graph.get_execution_waves()
waves = refine_waves_for_contention(waves)
```

**Change 3**: Add import at top of cli.py:
```python
from little_loops.dependency_graph import DependencyGraph, refine_waves_for_contention
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] Existing sprint tests pass: `python -m pytest scripts/tests/test_sprint.py scripts/tests/test_cli.py -v`

---

## Testing Strategy

### Unit Tests
- Core function behavior: single-issue passthrough, no-overlap passthrough, various overlap patterns
- Greedy coloring correctness: 2-way, 3-way, partial overlaps
- Edge cases: empty input, empty file hints, missing files (path.exists() → False)
- Priority ordering preserved within sub-waves

### Integration
- Sprint show displays refined waves correctly (existing render functions handle it)
- Sprint run dispatches refined waves (single-issue sub-waves go in-place, multi-issue use orchestrator)
- Resume logic still works with sub-waves (per-issue ID matching, not wave indices)

## References

- Original issue: `.issues/enhancements/P2-ENH-306-file-contention-aware-wave-splitting.md`
- Wave computation: `dependency_graph.py:119-166`
- File hints: `parallel/file_hints.py:36-142`
- Overlap detector pattern: `parallel/overlap_detector.py:67-84`
- Sprint run wiring: `cli.py:1836`
- Sprint show wiring: `cli.py:1667`
- Existing wave tests: `tests/test_dependency_graph.py:490-607`
