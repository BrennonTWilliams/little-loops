---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# ENH-430: Centralize code fence stripping utility

## Summary

Code fence stripping logic exists in two places: `issue_parser.py` (line-preserving version) and `text_utils.py` (regex-based version). The two implementations have different behavior — one preserves line counts, the other doesn't — creating a risk of using the wrong one.

## Current Behavior

`issue_parser.py:_strip_code_fences()` iterates line-by-line to replace fenced content with empty lines (preserving line count). `text_utils.py` uses `re.compile(r"```[\s\S]*?```")` to strip fences entirely. Different callers get different behavior.

## Expected Behavior

Both implementations should live in `text_utils.py` as named functions (e.g., `strip_code_fences()` and `strip_code_fences_preserve_lines()`) so callers can choose the appropriate variant.

## Motivation

Two independent implementations of similar logic with subtly different behavior is confusing. Centralizing makes it clear which variant to use and prevents future duplication.

## Scope Boundaries

- **In scope**: Moving `_strip_code_fences()` from issue_parser to text_utils, updating imports
- **Out of scope**: Changing the behavior of either implementation

## Proposed Solution

Move the line-preserving version from `issue_parser.py` to `text_utils.py`:

```python
# text_utils.py
def strip_code_fences(content: str) -> str:
    """Remove code fence blocks entirely."""
    return _CODE_FENCE.sub("", content)

def strip_code_fences_preserve_lines(content: str) -> str:
    """Remove code fence blocks, replacing with empty lines to preserve line count."""
    # ... moved from issue_parser.py
```

Update `issue_parser.py` to import from `text_utils`.

## Integration Map

### Files to Modify
- `scripts/little_loops/text_utils.py` — add line-preserving variant
- `scripts/little_loops/issue_parser.py` — replace method with import

### Dependent Files (Callers/Importers)
- Any future module needing code fence handling

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_text_utils.py` — if exists, add tests for both variants

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Move line-preserving strip function to `text_utils.py`
2. Update `issue_parser.py` to import from `text_utils`
3. Add tests for both variants

## Impact

- **Priority**: P4 - Code quality improvement
- **Effort**: Small - Move function between files
- **Risk**: Low - Pure refactor
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `refactoring`, `code-quality`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
