---
discovered_commit: 325fd14
discovered_branch: main
discovered_date: 2026-02-26
discovered_by: manual-audit
focus_area: dependency-mapping
---

# BUG-511: FileHints overlap detection too aggressive — directory containment and lack of thresholds

## Summary

`FileHints.overlaps_with()` is a boolean check with no threshold that serializes issues on any single shared file, directory containment, or scope match. This causes `ll-sprint` and `ll-parallel` to heavily prefer sequential execution even when issues touch unrelated parts of the codebase.

## Current Behavior

`overlaps_with()` in `parallel/file_hints.py:61-97` returns `True` if:
- **Any single file** matches exactly between two issues
- **Any directory** contains the other (`_directories_overlap` at line 132 uses prefix matching)
- **Any file** falls under the other issue's directory (`_file_in_directory` at line 139)
- **Any scope** matches exactly

This is consumed by two layers:
1. `refine_waves_for_contention()` in `dependency_graph.py:339-424` — splits parallel waves into sequential sub-waves
2. `OverlapDetector.check_overlap()` in `parallel/overlap_detector.py:97-135` — defers issues at dispatch time

### Specific problems

**Directory containment is absurdly broad**: `_directories_overlap()` at `file_hints.py:132-136` checks if either directory path starts with the other. If issue A mentions `scripts/` and issue B mentions `scripts/little_loops/parallel/orchestrator.py`, they overlap because the file starts with the directory prefix. Any two issues touching the same top-level directory get serialized.

**No minimum overlap ratio**: A single shared file path (e.g., `__init__.py`, `pyproject.toml`) in a 20-file issue is enough to serialize the entire pair. There's no consideration of what fraction of work overlaps.

**Common files cause false positives**: Files like `__init__.py`, `pyproject.toml`, `setup.py`, `CHANGELOG.md` appear in many issues as incidental references, not as modification targets.

## Expected Behavior

Overlap detection should use graduated thresholds rather than binary matching:
- Require a minimum number of overlapping files (e.g., >= 2) or a minimum overlap ratio (e.g., > 25% of the smaller issue's file set)
- Ignore directory containment at broad levels (e.g., don't treat `scripts/` as a conflict signal)
- Maintain a set of common files to exclude from overlap checks (`__init__.py`, `pyproject.toml`, etc.)

## Steps to Reproduce

1. Create a sprint containing ENH-510, ENH-470, and ENH-506 (three issues that reference files under `scripts/little_loops/` but touch completely different concerns)
2. Run `ll-sprint show` to inspect wave assignments
3. Observe that all three issues are serialized into separate sub-waves despite zero actual file conflict

## Actual Behavior

All three issues get serialized into sequential sub-waves because `_directories_overlap()` treats any two issues under `scripts/little_loops/` as conflicting. A single shared file (e.g., `__init__.py`) or broad directory prefix is enough to force sequential execution, even when the issues modify entirely different files.

## Location

- **File**: `scripts/little_loops/parallel/file_hints.py`
- **Line(s)**: 61-97 (`overlaps_with`), 132-142 (`_directories_overlap`, `_file_in_directory`)
- **Also**: `scripts/little_loops/dependency_graph.py:339-424` (`refine_waves_for_contention`)

## Proposed Solution

1. Add an overlap ratio threshold: only report overlap when `len(shared_files) / min(len(a.files), len(b.files)) > OVERLAP_THRESHOLD` (suggest 0.25)
2. Add a minimum file count: require `len(shared_files) >= MIN_OVERLAP_FILES` (suggest 2)
3. Exclude common infrastructure files from overlap checks via a configurable set
4. For directory containment, require the directory to be at least 2 levels deep (e.g., `scripts/little_loops/parallel/` is fine, but `scripts/` alone is too broad)
5. Make thresholds configurable in `ll-config.json`

### Suggested Approach

1. Add threshold constants to `file_hints.py` (or read from config)
2. Modify `overlaps_with()` to compute overlap count and ratio, not just boolean
3. Add `COMMON_FILES_EXCLUDE` set for `__init__.py`, `pyproject.toml`, etc.
4. Add minimum depth check to `_directories_overlap()`
5. Update `refine_waves_for_contention()` if needed
6. Update tests in `test_file_hints.py`

## Scope Boundaries

- **In scope**: Adding thresholds to `overlaps_with()`, directory depth filtering, common file exclusions
- **Out of scope**: Changing the graph coloring algorithm, modifying the DAG-based wave computation

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/file_hints.py` — add thresholds, depth check, exclusion set
- `scripts/little_loops/dependency_graph.py` — may need minor updates to `refine_waves_for_contention` if `overlaps_with` return type changes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_graph.py:379` — calls `overlaps_with()`
- `scripts/little_loops/parallel/overlap_detector.py:116` — calls `overlaps_with()`

### Tests
- `scripts/tests/test_file_hints.py` — update for new threshold behavior
- `scripts/tests/test_dependency_graph.py` — verify wave splitting with thresholds

## Impact

- **Priority**: P2 — directly causes most sprints to run sequentially instead of in parallel, degrading throughput
- **Effort**: Medium — changes isolated to `file_hints.py` with well-scoped tests, but needs careful threshold tuning
- **Risk**: Low — purely tightening detection criteria, not loosening; worst case is slightly more parallelism than before
- **Breaking Change**: No (strictly better parallelism)

## Labels

`bug`, `performance`, `dependency-mapping`

---

## Resolution

**Fixed** in `scripts/little_loops/parallel/file_hints.py`:

1. **Added overlap thresholds**: `MIN_OVERLAP_FILES=2`, `OVERLAP_RATIO_THRESHOLD=0.25` — single shared files in large sets no longer force serialization
2. **Added common file exclusions**: `COMMON_FILES_EXCLUDE` frozenset filters `__init__.py`, `pyproject.toml`, `setup.py`, `setup.cfg`, `CHANGELOG.md`, `README.md`, `conftest.py`
3. **Added directory depth filtering**: `MIN_DIRECTORY_DEPTH=2` — shallow directories like `scripts/` no longer trigger overlap; `scripts/little_loops/` and deeper still work
4. **Updated `get_overlapping_paths()`** to apply same filters for consistency

No changes needed to callers — return type unchanged (`bool`).

### Note on ENH-514

Item 5 from the proposed solution ("Make thresholds configurable in `ll-config.json`") is deferred to ENH-514, which is already tracked as a separate enhancement.

## Status

**Resolved** | Created: 2026-02-26 | Resolved: 2026-02-26 | Priority: P2

## Session Log
- manual audit - 2026-02-26 - Identified during exhaustive dependency mapping system audit
- manage-issue - 2026-02-26 - Fixed: added thresholds, common file exclusions, and directory depth filtering to overlaps_with()
