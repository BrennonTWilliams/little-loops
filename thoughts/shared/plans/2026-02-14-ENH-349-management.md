# ENH-349: Consolidate Duplicated File Path Extraction

## Research Summary

Three modules implement nearly identical file path extraction:

1. **`dependency_mapper.py:222-253`** — `extract_file_paths()` → `set[str]`
   - Pre-compiled regex patterns, code fence stripping, 19-extension whitelist
   - 1 production caller, 8 tests
   - **Most refined implementation**

2. **`issue_history/parsing.py:262-288`** — `_extract_paths_from_issue()` → `list[str]` (sorted)
   - Inline patterns, line number normalization, 7-extension hardcoded list
   - 5 production callers (all in `analysis.py`), 5 tests
   - All callers can accept `set[str]` (one already converts to set)

3. **`issue_discovery.py:221-242`** — `_extract_file_paths()` → `set[str]`
   - Inline patterns, 5-extension hardcoded list
   - **0 production callers** (dead code), 1 test

## Decision: New Module Location

Create `scripts/little_loops/text_utils.py` following the existing `subprocess_utils.py` naming convention.

## Plan

### Phase 1: Create shared module

1. Create `scripts/little_loops/text_utils.py` with:
   - Move pre-compiled regex patterns from `dependency_mapper.py` (lines 27-30)
   - Move `_SOURCE_EXTENSIONS` frozenset from `dependency_mapper.py` (lines 33-60)
   - Move `extract_file_paths()` function from `dependency_mapper.py` (lines 222-253)
   - Add line number normalization from `parsing.py` (lines 284-285) into the shared function
   - Return type: `set[str]`

### Phase 2: Update callers

2. **`dependency_mapper.py`**: Replace local function + patterns with import from `text_utils`
3. **`issue_history/parsing.py`**: Replace `_extract_paths_from_issue()` with wrapper that calls shared function and returns `sorted(result)` for backward compat
4. **`issue_history/analysis.py`**: No changes needed (imports from `parsing.py`)
5. **`issue_history/__init__.py`**: Keep re-exporting `_extract_paths_from_issue` (wrapper in parsing.py)
6. **`issue_discovery.py`**: Delete `_extract_file_paths()` entirely (dead code)

### Phase 3: Update tests

7. **`test_dependency_mapper.py`**: Update import to use `text_utils.extract_file_paths`
8. **`test_issue_history_advanced_analytics.py`**: No changes (tests `_extract_paths_from_issue` wrapper)
9. **`test_issue_discovery.py`**: Remove `test_extract_file_paths` test and `_extract_file_paths` import

### Phase 4: Verify

10. Run `python -m pytest scripts/tests/`
11. Run `ruff check scripts/`
12. Run `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] Single canonical `extract_file_paths()` in `text_utils.py`
- [ ] `dependency_mapper.py` imports from `text_utils`
- [ ] `parsing.py` wrapper delegates to `text_utils`
- [ ] Dead code removed from `issue_discovery.py`
- [ ] All tests pass
- [ ] Lint and type checks pass
