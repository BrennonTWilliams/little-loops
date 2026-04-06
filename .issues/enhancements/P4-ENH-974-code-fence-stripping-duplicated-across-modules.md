---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-974: Code-fence stripping logic duplicated across 3 modules

## Summary

The regex pattern for stripping backtick code fences — `` re.compile(r"```[\s\S]*?```", re.MULTILINE) `` followed by `.sub("", content)` — is copy-pasted identically in both `text_utils.py` and `dependency_mapper/analysis.py`. A third variant exists in `IssueParser._strip_code_fences` (line-splitting approach). Consolidating the two identical regex copies into a shared public function in `text_utils.py` eliminates duplication and makes future pattern adjustments apply universally.

## Location

- **File**: `scripts/little_loops/text_utils.py`
- **Line(s)**: 21, 77 (at scan commit: 96d74cda)
- **Anchor**: `_CODE_FENCE` module-level constant and usage in `extract_file_paths`

- **File**: `scripts/little_loops/dependency_mapper/analysis.py`
- **Line(s)**: 28, 114 (at scan commit: 96d74cda)
- **Anchor**: `_CODE_FENCE` module-level constant and usage in `_extract_semantic_targets`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/text_utils.py#L21)
- **Code**:
```python
# text_utils.py (lines 21, 77) and dependency_mapper/analysis.py (lines 28, 114):
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
content = _CODE_FENCE.sub("", content)
```

## Current Behavior

The pattern is defined and applied twice in two separate modules. Any change to the fence-stripping logic (e.g., to handle indented fences or language tags at the close) must be made in both places.

## Expected Behavior

A single public `strip_code_fences(content: str) -> str` function in `text_utils.py` is imported and used by `dependency_mapper/analysis.py`, eliminating the duplicate definition.

## Motivation

Duplicated regex utilities are a maintenance hazard. If the code-fence pattern ever needs updating (e.g., to handle triple-tilde fences or nested fences), changes made to one copy will silently miss the other.

## Proposed Solution

In `text_utils.py`, expose the existing private pattern as a public function:

```python
def strip_code_fences(content: str) -> str:
    """Remove backtick code fences from content."""
    return _CODE_FENCE.sub("", content)
```

In `dependency_mapper/analysis.py`, replace the local `_CODE_FENCE` definition and `.sub(...)` call:

```python
# Before:
_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
...
content = _CODE_FENCE.sub("", content)

# After:
from ..text_utils import strip_code_fences
...
content = strip_code_fences(content)
```

The `IssueParser._strip_code_fences` (line-splitting approach) serves a different purpose (preserving line count) and can remain as-is.

## Scope Boundaries

- Only consolidate the two regex-based identical copies; do not change `IssueParser._strip_code_fences` which serves a different contract (line-preserving)

## Success Metrics

- `dependency_mapper/analysis.py` imports `strip_code_fences` from `text_utils` and has no local `_CODE_FENCE` definition

## Integration Map

### Files to Modify
- `scripts/little_loops/text_utils.py` — add public `strip_code_fences` function
- `scripts/little_loops/dependency_mapper/analysis.py` — remove `_CODE_FENCE`, use imported function

### Dependent Files (Callers/Importers)
- Any module importing `_CODE_FENCE` from `text_utils` (verify with grep)

### Similar Patterns
- `IssueParser._strip_code_fences` — line-preserving variant, intentionally different

### Tests
- `scripts/tests/test_text_utils.py` — add test for `strip_code_fences`
- `scripts/tests/test_dependency_mapper.py` — existing tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `strip_code_fences(content: str) -> str` to `text_utils.py` wrapping the existing `_CODE_FENCE` pattern
2. Update `dependency_mapper/analysis.py` to import and use `strip_code_fences`
3. Remove the local `_CODE_FENCE` definition from `dependency_mapper/analysis.py`
4. Run existing tests to confirm no regressions

## Impact

- **Priority**: P4 — Code health improvement; eliminates a silent drift risk
- **Effort**: Small — Add one function, update one import, remove one definition
- **Risk**: Low — Identical logic, just relocated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `refactor`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
