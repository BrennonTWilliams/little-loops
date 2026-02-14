# ENH-350: Cache Issue File Contents in History Analysis Pipeline

## Summary

Add a content cache (`dict[str, str]`) to `calculate_analysis()` that pre-loads all issue file contents once, then passes the cache to each of the 9 analysis functions that currently read files independently. This reduces I/O from ~9N to N file reads.

## Research Findings

### Current State
- `calculate_analysis()` in `analysis.py:1549-1698` orchestrates 9 analysis functions sequentially
- Each of 9 functions independently calls `issue.path.read_text(encoding="utf-8")` in a try/except loop
- 2 functions (`analyze_test_gaps`, `detect_config_gaps`) do NOT read issue files — skip these
- The `detect_cross_cutting_smells` function at line 1038 also calls `read_text()` — total is 9 functions

### Functions That Read Issue Files (9 total)
1. `_analyze_subsystems()` — line 263
2. `analyze_hotspots()` — line 309
3. `analyze_coupling()` — line 423
4. `analyze_regression_clustering()` — line 558
5. `analyze_rejection_rates()` — line 771
6. `detect_manual_patterns()` — line 950
7. `detect_cross_cutting_smells()` — line 1038
8. `analyze_agent_effectiveness()` — line 1272
9. `analyze_complexity_proxy()` — line 1383

### Existing Patterns
- `sprint.py:779-781`: `_build_issue_contents()` — exact same pattern (dict comprehension, `issue_id → content`)
- `dependency_mapper.py:895-898`: Same pattern with explicit type annotation
- All functions use `issue.path` (a `Path` object) and `issue.issue_id` (a `str`)

### Design Decision
- Use `issue.path` as dict key (not `issue_id`) since that's what's used for lookup in each function's loop
- Type: `dict[Path, str]` — maps `issue.path → file content`
- Each function's loop iterates `for issue in issues:` and reads `issue.path.read_text()` — so looking up by `issue.path` is natural
- Wait, actually: using `str(issue.path)` or `issue.path` directly as key. `Path` is hashable, so `dict[Path, str]` works fine.

## Implementation Plan

### Phase 1: Add `_load_issue_contents()` helper

**File**: `analysis.py` (after imports, before first function)

```python
def _load_issue_contents(issues: list[CompletedIssue]) -> dict[Path, str]:
    """Pre-load issue file contents for pipeline efficiency.

    Args:
        issues: List of completed issues to load

    Returns:
        Mapping of issue path to file content (skips unreadable files)
    """
    contents: dict[Path, str] = {}
    for issue in issues:
        try:
            contents[issue.path] = issue.path.read_text(encoding="utf-8")
        except Exception:
            pass  # Skip unreadable files (same as individual functions)
    return contents
```

### Phase 2: Update each analysis function signature

Add `contents: dict[Path, str] | None = None` parameter to each of the 9 functions. Inside each function's loop, replace:

```python
# Before
try:
    content = issue.path.read_text(encoding="utf-8")
except Exception:
    continue
```

With:

```python
# After
if contents is not None and issue.path in contents:
    content = contents[issue.path]
else:
    try:
        content = issue.path.read_text(encoding="utf-8")
    except Exception:
        continue
```

This preserves standalone usage (when `contents` is None, falls back to reading from disk).

Functions to update:
- [ ] `_analyze_subsystems()` — line 245
- [ ] `analyze_hotspots()` — line 295
- [ ] `analyze_coupling()` — line 406
- [ ] `analyze_regression_clustering()` — line 532
- [ ] `analyze_rejection_rates()` — line 751
- [ ] `detect_manual_patterns()` — line 924
- [ ] `detect_cross_cutting_smells()` — line 1002
- [ ] `analyze_agent_effectiveness()` — line 1252
- [ ] `analyze_complexity_proxy()` — line 1339

### Phase 3: Wire through `calculate_analysis()`

In `calculate_analysis()`, after line 1568 (`today = date.today()`):

```python
# Pre-load issue file contents for pipeline efficiency
issue_contents = _load_issue_contents(completed_issues)
```

Then pass `contents=issue_contents` to each of the 9 function calls.

### Phase 4: Verify

- [ ] All existing tests pass (`python -m pytest scripts/tests/`)
- [ ] Type checking passes (`python -m mypy scripts/little_loops/`)
- [ ] Linting passes (`ruff check scripts/`)

## Success Criteria

- [x] `_load_issue_contents()` helper exists
- [ ] 9 analysis functions accept optional `contents` parameter
- [ ] `calculate_analysis()` pre-loads and passes contents
- [ ] File reads reduced from ~9N to N
- [ ] All existing tests pass
- [ ] No public API changes (parameters are optional with `None` defaults)
