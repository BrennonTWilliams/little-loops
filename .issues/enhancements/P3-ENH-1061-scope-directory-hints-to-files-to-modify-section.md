---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
---

# ENH-1061: Scope directory hint extraction to ### Files to Modify section only

## Summary

`extract_file_hints()` in `file_hints.py` applies `DIR_PATH_PATTERN` against the **entire issue body** to populate the `directories` set, while file hints (`files`) are scoped to only the `### Files to Modify` and `### Files Changed` structured sections. A prose reference like "this feature lives in `src/viewer/`" in the description or motivation sections creates a directory hint that triggers conflicts against every other sprint issue referencing that directory — even when their actual changes touch entirely different files within it. This inflates the conflict graph and forces unnecessary serialization.

## Location

- **File**: `scripts/little_loops/parallel/file_hints.py`
- **Line(s)**: 287–340 (`extract_file_hints()`), specifically line 331 (`directories` extraction)
- **Anchor**: `in function extract_file_hints`
- **Code**:
```python
# files — scoped to ### Files to Modify sections:
files = _extract_write_target_files(content, issue_id)

# directories — full body scan (no section scoping):
directories = {
    m.group(0).rstrip("/") + "/"
    for m in DIR_PATH_PATTERN.finditer(content)  # ← entire body
}
```

## Current Behavior

Directory paths mentioned anywhere in the issue markdown (descriptions, motivation, root cause, implementation steps, etc.) contribute to the `directories` set used for conflict detection. In a viewer sprint, issues discussing `src/viewer/` in prose all conflict with each other regardless of which specific files they actually modify.

## Expected Behavior

Directory hints are extracted from the same structured sections as file hints (`### Files to Modify`, `### Files Changed`, `### Files`). Prose mentions of directories do not contribute to conflict detection.

## Motivation

File hints are already section-scoped to prevent false positives from contextual file references in prose. Directory hints should follow the same principle. The asymmetry is a subtle bug: an issue that says "this fix is in `src/viewer/`" in the *Summary* section but only touches `src/viewer/GraphView.jsx` creates a directory hint that conflicts with every other issue touching `src/viewer/` — effectively serializing all viewer work regardless of actual file overlap.

## Proposed Solution

Refactor `_extract_write_target_files()` or create a parallel `_extract_write_target_directories()` that applies `DIR_PATH_PATTERN` only within the structured sections already identified by `_WRITE_TARGET_SECTION_RE`. The implementation can reuse the section-scoping regex already in place for file extraction.

```python
# Proposed: scope directory extraction to structured sections
def _extract_write_target_directories(content: str, issue_id: str) -> set[str]:
    """Extract directory paths from ### Files to Modify / Files Changed sections only."""
    section_content = "\n".join(_extract_write_target_sections(content))
    return {
        m.group(0).rstrip("/") + "/"
        for m in DIR_PATH_PATTERN.finditer(section_content)
    }
```

## Scope Boundaries

- Only changes where `DIR_PATH_PATTERN` is applied; pattern itself is unchanged
- Does not affect `contends_with()` (worktree isolation) — only `overlaps_with()` / `get_overlapping_paths()` paths used by sprint scheduling
- Does not change the `scopes` set extraction

## Success Metrics

- An issue with `src/viewer/` only in its prose Summary no longer produces a directory hint
- An issue with `src/viewer/` in its `### Files to Modify` section still produces the hint
- Sprint for a single-component project with prose directory references shows fewer serialized steps

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — `extract_file_hints()` line 331; add `_extract_write_target_directories()` or reuse existing section-scoping helpers

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py` — `refine_waves_for_contention()` calls `extract_file_hints()`

### Tests
- `scripts/tests/test_file_hints.py` — add test case: directory in prose → not extracted; directory in `### Files to Modify` → extracted
- `scripts/tests/test_dependency_graph.py` — wave contention tests with directory-only prose references

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Identify the section-scoping helper already used by `_extract_write_target_files()` (the regex capturing `### Files to Modify` sections)
2. Extract it into a shared `_extract_write_target_sections(content) -> list[str]` if not already factored out
3. Apply `DIR_PATH_PATTERN` only to the joined section text, not the full body
4. Add unit tests for the boundary behavior (prose vs structured-section directory references)
5. Run sprint contention tests

## Impact

- **Priority**: P3 — Eliminates a class of false-positive conflicts in single-component sprints; complements ENH-1060
- **Effort**: Small — Refactor one extraction call; section-scoping regex already exists
- **Risk**: Low — Reduces false positives; any remaining real directory conflicts still detected via file overlap
- **Breaking Change**: No

## Blocked By

- None (independent of ENH-1060, though both address over-serialization)

## Labels

`enhancement`, `sprint`, `parallelism`, `file-hints`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`

## Status

**Open** | Created: 2026-04-12 | Priority: P3
