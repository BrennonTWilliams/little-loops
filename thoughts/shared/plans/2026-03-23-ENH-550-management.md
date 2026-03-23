# ENH-550: Cache `_get_message_category` UUID→category index

**Date**: 2026-03-23
**Issue**: ENH-550
**File**: `scripts/little_loops/workflow_sequence/analysis.py`

## Summary

Replace repeated O(C×E) nested scans in `_detect_workflows` with a pre-built O(1) dict lookup.

## Changes

### `scripts/little_loops/workflow_sequence/analysis.py`

1. Add `_build_category_index(patterns)` after `_get_message_category` (line 491):
   ```python
   def _build_category_index(patterns: dict[str, Any]) -> dict[str, str]:
       """Build a flat UUID → category mapping from patterns category_distribution."""
       index: dict[str, str] = {}
       for category_info in patterns.get("category_distribution", []):
           category = category_info.get("category")
           if not isinstance(category, str):
               continue
           for example in category_info.get("example_messages", []):
               uuid = example.get("uuid")
               if uuid:
                   index[uuid] = category
       return index
   ```

2. In `_detect_workflows`, after `boundary_before` is built (line ~509), add:
   ```python
   category_index = _build_category_index(patterns)
   ```

3. Replace line 533: `_get_message_category(msg.get("uuid", ""), patterns)` → `category_index.get(msg.get("uuid", ""))`

4. Replace line 583: `_get_message_category(msg.get("uuid", ""), patterns)` → `category_index.get(msg.get("uuid", ""))`

5. Keep `_get_message_category` — tested directly by `TestGetMessageCategory`.

### `scripts/tests/test_workflow_sequence_analyzer.py`

1. Add `_build_category_index` to import at line 35.
2. Add `TestBuildCategoryIndex` class after `TestGetMessageCategory` (before `TestParseTimestamps`).

## TDD Approach

- **Red**: Add stub `_build_category_index` returning `{}` + tests → `test_builds_flat_index` fails
- **Green**: Full implementation → all tests pass

## Verification

- `python -m pytest scripts/tests/test_workflow_sequence_analyzer.py -v -k "TestBuildCategoryIndex or TestGetMessageCategory"`
- `python -m pytest scripts/tests/`
- `ruff check scripts/`
- `python -m mypy scripts/little_loops/`
