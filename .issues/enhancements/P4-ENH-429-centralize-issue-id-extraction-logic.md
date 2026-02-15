---
discovered_commit: 71616c711e2fe9f5f1ececcf1c64552bca9d82ec
discovered_branch: main
discovered_date: 2026-02-15T02:29:53Z
discovered_by: scan-codebase
---

# ENH-429: Centralize issue ID extraction logic

## Summary

Issue ID extraction (`re.search(r"(BUG|FEAT|ENH)-(\d+)", filename)`) is duplicated across `sync.py`, `issue_parser.py`, and the orchestrator's worktree inspection. Each uses slightly different regex patterns, risking inconsistency.

## Current Behavior

Multiple modules independently implement issue ID parsing with slightly different regex patterns. Changes to the ID format require updates in multiple places.

## Expected Behavior

A single `parse_issue_id()` function in `issue_parser.py` serves as the source of truth for ID extraction, used by all modules.

## Motivation

Three or more independent implementations of the same regex increases maintenance burden and risks subtle inconsistencies. Centralizing makes format changes safe and reduces duplicated code.

## Scope Boundaries

- **In scope**: Centralizing ID extraction into one function, updating call sites
- **Out of scope**: Changing the ID format itself

## Proposed Solution

Add to `issue_parser.py`:

```python
_ISSUE_ID_PATTERN = re.compile(r"(BUG|FEAT|ENH)-(\d+)")

def parse_issue_id(filename: str) -> str | None:
    """Extract issue ID (e.g., 'BUG-419') from a filename."""
    match = _ISSUE_ID_PATTERN.search(filename)
    return f"{match.group(1)}-{match.group(2)}" if match else None
```

Update `sync.py:_extract_issue_id()` and orchestrator worktree inspection to use this function.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — add centralized function
- `scripts/little_loops/sync.py` — replace `_extract_issue_id()`
- `scripts/little_loops/parallel/orchestrator.py` — replace inline regex

### Dependent Files (Callers/Importers)
- Any future module needing issue ID parsing

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_issue_parser.py` — add tests for `parse_issue_id()`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `parse_issue_id()` function to `issue_parser.py`
2. Update `sync.py` and `orchestrator.py` to use it
3. Add tests for edge cases (no match, partial match, multiple matches)

## Impact

- **Priority**: P4 - Code quality improvement, reduces duplication
- **Effort**: Small - Add one function, update 2-3 call sites
- **Risk**: Low - Pure refactor, behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `refactoring`, `code-quality`

## Session Log
- `/ll:scan-codebase` - 2026-02-15T02:29:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3135ba2c-6ec1-44c9-ae59-0d6a65c71853.jsonl`

---

**Open** | Created: 2026-02-15 | Priority: P4
