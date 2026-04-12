---
discovered_date: 2026-04-12T17:20:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
- `scripts/little_loops/dependency_graph.py:376` — `refine_waves_for_contention()` calls `extract_file_hints()`
- `scripts/little_loops/parallel/overlap_detector.py:87,120` — `OverlapDetector` calls `extract_file_hints()` in two places; `overlaps_with()` and `get_overlapping_paths()` consume `hints.directories`
- `scripts/little_loops/cli/sprint/manage.py:117` — sprint `manage` CLI calls `extract_file_hints()` directly
- `scripts/little_loops/parallel/__init__.py` — re-exports `FileHints` and `extract_file_hints` as public API

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py:116-117,813-814,829,841-942` — instantiates `OverlapDetector` and calls `check_overlap()`, `register_issue()`, `unregister_issue()`; indirect consumer of `hints.directories` via `OverlapDetector` [Agent 1 finding]

### Tests
- `scripts/tests/test_file_hints.py` — add test case: directory in prose → not extracted; directory in `### Files to Modify` → extracted. Model after `TestExtractWriteTargetFiles` (line 143) and `test_files_outside_write_sections_not_extracted` (line 136)
- `scripts/tests/test_dependency_graph.py` — wave contention tests with directory-only prose references
- `scripts/tests/test_overlap_detector.py` — section-aware overlap detection (line 14 references this behavior)
- `scripts/tests/test_sprint_integration.py` — integration tests covering contention/overlap logic end-to-end

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_file_hints.py:54-58` — **WILL BREAK**: `test_extracts_directories` passes prose-only content (`"Changes to scripts/little_loops/ directory"`) with no `### Files to Modify` section and asserts `hints.directories` is non-empty; after this change that assertion fails. Must be updated: wrap content in `### Files to Modify` for the positive case, add a separate test asserting prose directories are NOT extracted [Agent 2+3 finding]
- `scripts/tests/test_sprint.py` — exercises full sprint overlap pipeline via `_setup_overlapping_issues` which writes `### Files to Modify` sections; run to confirm no regressions [Agent 1 finding]
- `scripts/tests/test_orchestrator.py` — tests `ParallelOrchestrator` with `OverlapDetector` mocked; run to confirm mock isolation holds [Agent 1 finding]

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read `_extract_write_target_files()` at `file_hints.py:287–310` to understand the inline section pattern (`re.compile(r"###\s*(?:Files to Modify|Files Changed)\s*\n(.*?)(?=\n###|\n##|\Z)", re.DOTALL)` at lines 301–304) — note: **there is no module-level `_WRITE_TARGET_SECTION_RE` constant**; the regex is defined inline
2. Add `_extract_write_target_directories(content: str) -> set[str]` immediately after `_extract_write_target_files()` using the same inline section pattern; apply `DIR_PATH_PATTERN` only to each captured `section.group(1)` (no need for a shared `_extract_write_target_sections()` helper — mirroring the existing pattern directly is simpler and consistent with codebase style)
3. Replace `DIR_PATH_PATTERN.finditer(content)` loop in `extract_file_hints()` (lines 331–334) with a call to `_extract_write_target_directories(content)`
4. Update `test_file_hints.py`: add tests confirming directory in prose → not in `hints.directories`; directory in `### Files to Modify` → in `hints.directories`; follow the pattern of `TestExtractWriteTargetFiles` (line 143) and `test_files_outside_write_sections_not_extracted` (line 136)
5. Run `python -m pytest scripts/tests/test_file_hints.py scripts/tests/test_overlap_detector.py scripts/tests/test_sprint_integration.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Fix breaking test** in `scripts/tests/test_file_hints.py:54-58` (`test_extracts_directories`) — update the test to wrap the directory reference inside `### Files to Modify\n...\n` for the positive-extraction case; add a companion test that asserts a prose-only directory is NOT in `hints.directories`
7. **Expand test run** to include `test_sprint.py` and `test_orchestrator.py`: `python -m pytest scripts/tests/test_file_hints.py scripts/tests/test_overlap_detector.py scripts/tests/test_sprint_integration.py scripts/tests/test_sprint.py scripts/tests/test_orchestrator.py -v`

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
- `/ll:wire-issue` - 2026-04-12T16:36:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7b427a4-828a-4b73-a1c0-44765d29b11f.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:30:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d9b1de7-b67d-4ec1-ab1a-2d2d2d583651.jsonl`
- `/ll:capture-issue` - 2026-04-12T17:20:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d397308b-e908-423f-9d30-383270c713d4.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46202feb-d001-41be-a52b-687026007370.jsonl`

## Status

**Open** | Created: 2026-04-12 | Priority: P3
