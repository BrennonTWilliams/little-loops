---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# ENH-349: Consolidate duplicated file path extraction into shared utility

## Summary

Three separate modules implement nearly identical file path extraction from markdown content using different regex patterns and return types. These should be consolidated into a single shared utility.

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Line(s)**: 1152-1178 (at scan commit: be30013)
- **Anchor**: `_extract_paths_from_issue()`
- **File**: `scripts/little_loops/issue_discovery.py`
- **Line(s)**: 221-242
- **Anchor**: `_extract_file_paths()`
- **File**: `scripts/little_loops/dependency_mapper.py`
- **Line(s)**: 222-253
- **Anchor**: `extract_file_paths()`

## Current Behavior

Three functions with slightly different regex patterns and return types (`list[str]` vs `set[str]`) each extract file paths from markdown content independently.

## Expected Behavior

A single canonical `extract_file_paths()` function in a shared module that all three callers use.

## Motivation

Reduces maintenance burden and ensures consistent path extraction behavior across modules. Bug fixes to path extraction only need to happen in one place.

## Proposed Solution

Use the `dependency_mapper.py` version as the base (it's the most refined with pre-compiled patterns). Extract to a shared module (e.g., `text_utils.py` or add to existing shared code). Have `issue_history.py` and `issue_discovery.py` import and call the shared function.

## Scope Boundaries

- Only consolidate file path extraction, not other text parsing utilities
- Do not change the return type contract for existing callers (add `.list()` wrapper if needed)

## Success Metrics

- Three separate implementations reduced to one shared function
- All existing tests continue to pass

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper.py` (source of canonical implementation)
- `scripts/little_loops/issue_history.py` (replace `_extract_paths_from_issue`)
- `scripts/little_loops/issue_discovery.py` (replace `_extract_file_paths`)

### Tests
- `scripts/tests/test_dependency_mapper.py`
- `scripts/tests/test_issue_history.py`
- `scripts/tests/test_issue_discovery.py`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Create shared function in appropriate module
2. Update all three callers to use it
3. Verify all tests pass

## Impact

- **Priority**: P3 - Code quality improvement, reduces duplication
- **Effort**: Small - Straightforward refactor
- **Risk**: Low - Well-tested functionality
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `captured`

## Blocks

- ENH-352: batch git log calls in files_modified_since_commit (shared issue_discovery.py)

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P3
