# BUG-511 Management Plan: FileHints overlap detection too aggressive

**Issue**: P2-BUG-511 — `overlaps_with()` is binary with no thresholds, causing excessive serialization
**Action**: fix
**Date**: 2026-02-26

## Summary

The `FileHints.overlaps_with()` method treats any single shared file, broad directory containment, or scope match as a full conflict. This causes `refine_waves_for_contention()` and `OverlapDetector.check_overlap()` to serialize issues that touch unrelated parts of the codebase, degrading parallel throughput.

## Research Findings

### Call Sites (3 total)
1. `dependency_graph.py:379` — `refine_waves_for_contention()` builds conflict adjacency for wave splitting
2. `overlap_detector.py:116` — `check_overlap()` tests against active issues at runtime dispatch
3. `cli/sprint/manage.py:104` — sprint conflict analysis display

All three use `overlaps_with()` as a simple boolean in an `if` condition. The return type does NOT need to change.

### Root Causes
1. **`_directories_overlap()`** (line 132): Prefix matching with no depth requirement — `scripts/` overlaps with `scripts/little_loops/parallel/orchestrator.py`
2. **No minimum overlap count**: A single shared file (e.g., `__init__.py`) forces serialization
3. **No common file exclusions**: Infrastructure files like `__init__.py`, `pyproject.toml` trigger false positives

### Design Decision: Where to apply thresholds

The fix goes into `overlaps_with()` itself rather than callers. This keeps the single-responsibility pattern: `overlaps_with()` answers "do these issues conflict?", callers just consume the boolean. The `get_overlapping_paths()` method needs analogous changes for consistency.

## Implementation Plan

### Phase 1: Add constants and common file exclusions to `file_hints.py`

Add module-level constants following the project's `ALL_CAPS` pattern:

```python
# Overlap detection thresholds
MIN_OVERLAP_FILES = 2          # Minimum overlapping files to trigger overlap
OVERLAP_RATIO_THRESHOLD = 0.25 # Minimum ratio of overlapping files to smaller set
MIN_DIRECTORY_DEPTH = 2        # Minimum path segments for directory overlap

# Common infrastructure files excluded from overlap detection
COMMON_FILES_EXCLUDE = frozenset({
    "__init__.py",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "CHANGELOG.md",
    "README.md",
    "conftest.py",
})
```

### Phase 2: Add `_is_common_file()` helper

```python
def _is_common_file(path: str) -> bool:
    """Check if a file is a common infrastructure file to exclude from overlap."""
    basename = path.rsplit("/", 1)[-1] if "/" in path else path
    return basename in COMMON_FILES_EXCLUDE
```

### Phase 3: Update `_directories_overlap()` to enforce minimum depth

Add depth checking: a directory must have at least `MIN_DIRECTORY_DEPTH` path segments to be a valid overlap signal.

```python
def _directories_overlap(dir1: str, dir2: str) -> bool:
    d1 = dir1.rstrip("/") + "/"
    d2 = dir2.rstrip("/") + "/"
    if not (d1.startswith(d2) or d2.startswith(d1)):
        return False
    # Require minimum depth — broad directories like "scripts/" are too generic
    shorter = d1 if len(d1) <= len(d2) else d2
    depth = shorter.rstrip("/").count("/")
    return depth >= MIN_DIRECTORY_DEPTH
```

Example: `scripts/` has depth 1 (fails), `scripts/little_loops/` has depth 2 (passes).

### Phase 4: Update `_file_in_directory()` to enforce minimum depth

```python
def _file_in_directory(file_path: str, dir_path: str) -> bool:
    dir_normalized = dir_path.rstrip("/") + "/"
    if not file_path.startswith(dir_normalized):
        return False
    depth = dir_normalized.rstrip("/").count("/")
    return depth >= MIN_DIRECTORY_DEPTH
```

### Phase 5: Update `overlaps_with()` with thresholds and exclusions

1. Filter common files before file intersection check
2. Apply minimum count threshold to file matches
3. Apply ratio threshold based on the smaller file set
4. Keep scope matching as-is (scopes are already semantic signals)

```python
def overlaps_with(self, other: FileHints) -> bool:
    if self.is_empty or other.is_empty:
        return False

    # Filter common infrastructure files
    self_files = {f for f in self.files if not _is_common_file(f)}
    other_files = {f for f in other.files if not _is_common_file(f)}

    # Exact file matches with thresholds
    shared_files = self_files & other_files
    if shared_files:
        smaller_set = min(len(self_files), len(other_files))
        if smaller_set > 0:
            ratio = len(shared_files) / smaller_set
            if len(shared_files) >= MIN_OVERLAP_FILES or ratio >= OVERLAP_RATIO_THRESHOLD:
                return True

    # Directory overlaps (with depth check built into _directories_overlap)
    for d1 in self.directories:
        for d2 in other.directories:
            if _directories_overlap(d1, d2):
                return True

    # File in directory (with depth check built into _file_in_directory)
    for f in self_files:
        for d in other.directories:
            if _file_in_directory(f, d):
                return True
    for f in other_files:
        for d in self.directories:
            if _file_in_directory(f, d):
                return True

    # Scope matches (keep as-is — scopes are intentional semantic signals)
    if self.scopes & other.scopes:
        return True

    return False
```

### Phase 6: Update `get_overlapping_paths()` for consistency

Apply the same filtering and depth checks so that the paths returned are consistent with what `overlaps_with()` considers conflicting.

### Phase 7: Update tests

1. **Update existing tests** that rely on single-file or shallow-directory overlap (they need updated expectations or updated fixtures)
2. **Add new tests**:
   - Common file exclusion (single `__init__.py` overlap → `False`)
   - Threshold behavior (1 file in 20-file issue → `False`, 5 files → `True`)
   - Directory depth filtering (`scripts/` vs `scripts/little_loops/parallel/` → `False`)
   - Deep directory overlap still works (`scripts/little_loops/` vs `scripts/little_loops/parallel/` → `True`)
   - Ratio threshold edge cases

### Phase 8: Verify

- Run `python -m pytest scripts/tests/test_file_hints.py -v`
- Run `python -m pytest scripts/tests/test_dependency_graph.py -v`
- Run `python -m pytest scripts/tests/test_overlap_detector.py -v`
- Run `ruff check scripts/little_loops/parallel/file_hints.py`
- Run `python -m mypy scripts/little_loops/parallel/file_hints.py`

## Success Criteria

- [ ] Common infrastructure files are excluded from overlap detection
- [ ] Single shared file no longer triggers overlap (threshold requires >= 2 or >= 25% ratio)
- [ ] Shallow directory containment (depth < 2) no longer triggers overlap
- [ ] Deep directory overlap still works correctly
- [ ] Scope matching is unchanged
- [ ] `get_overlapping_paths()` is consistent with `overlaps_with()`
- [ ] All existing callers work without changes (return type unchanged)
- [ ] All tests pass

## Risk Assessment

- **Low risk**: Changes only tighten detection criteria, never loosen below rational minimums
- **No breaking changes**: Return type stays `bool`, all callers are compatible
- **Rollback**: Simple — revert the single file
