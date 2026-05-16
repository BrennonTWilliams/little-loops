# BUG-003: Invalid FEAT-* IDs Generated in Issue Queue

## Summary

The issue queue/catalog contains FEAT-* IDs with unusual numbering (FEAT-1636, FEAT-1814, FEAT-6178, FEAT-8671, FEAT-9898) that don't correspond to any actual issue files. These appear to be incorrectly generated IDs.

## Current Behavior

When `ll-auto` processes issues, it encounters IDs that don't exist:

```
Processing: FEAT-1636 - Analysis Replay Mode
...
ready_issue verdict: CLOSE
Reason: invalid_ref
Evidence: The issue FEAT-1636 does not exist in any issue directories
```

The project uses formats like:
- `P0-*`, `P1-*` priority prefixes
- `BUG-XX`, `ENH-XX`, `FEAT-XX` with low numbers

But the queue contains IDs like FEAT-1636, FEAT-6178, FEAT-8671, FEAT-9898 which follow a different numbering scheme.

### Evidence from Log

| Invalid ID | Title in Queue | Result |
|------------|---------------|--------|
| FEAT-1636 | Analysis Replay Mode | invalid_ref |
| FEAT-1814 | Test Coverage Analysis | invalid_ref |
| FEAT-6178 | Code Diff Analysis | invalid_ref |
| FEAT-8671 | Interactive TUI Mode | invalid_ref |
| FEAT-9898 | Dead Code Detector | invalid_ref |

## Expected Behavior

Issue IDs in the queue should:
1. Correspond to actual issue files
2. Follow the project's naming convention
3. Be validated before being added to the processing queue

## Root Cause

Potential causes:
1. **ID Generation Bug**: The `_generate_id_from_filename` function in `issue_parser.py:208-223` uses `abs(hash(filename)) % 10000` as fallback, which could generate large arbitrary numbers
2. **Stale Catalog**: The issue catalog may be out of sync with actual issue files
3. **External Source**: IDs may have been imported from an external system with different numbering

In `issue_parser.py:208-223` (function definition at 208, fallback logic at 218-223):
```python
def _generate_id_from_filename(self, filename: str, prefix: str) -> str:
    # Try to extract a number from the filename
    numbers = re.findall(r"\d+", filename)
    if numbers:
        return f"{prefix}-{numbers[0]}"
    # Use hash of filename as fallback  <-- Problematic
    return f"{prefix}-{abs(hash(filename)) % 10000:04d}"
```

## Affected Files

- `scripts/little_loops/issue_parser.py:208-223` - ID generation with hash fallback

## Reproduction Steps

1. Create an issue file without a numeric ID in the filename
2. Run the issue parser
3. Observe that a hash-based ID is generated

## Proposed Fix

1. **Validate IDs exist**: Before adding to queue, verify the issue file exists
2. **Consistent ID generation**: Use sequential numbering instead of hash-based fallback
3. **Catalog validation**: Add a validation step to `scan_codebase` that verifies all catalog entries

```python
def _generate_id_from_filename(self, filename: str, prefix: str) -> str:
    numbers = re.findall(r"\d+", filename)
    if numbers:
        return f"{prefix}-{numbers[0]}"
    # Use next sequential number instead of hash
    next_num = get_next_issue_number(self.config, self._get_category_for_prefix(prefix))
    return f"{prefix}-{next_num}"
```

## Impact

- **Severity**: Medium (P2)
- **Effort**: Medium
- **Risk**: Low
- **Breaking Change**: No

## Labels

`bug`, `medium-priority`, `issue-parser`, `data-quality`

---

## Status

**Completed** | Created: 2026-01-04 | Resolved: 2026-01-05 | Priority: P2

## Related Issues

- [BUG-001](./P0-BUG-001-ready-issue-glob-matching-wrong-files.md) - Related ID matching issues

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-05
- **Status**: Completed

### Changes Made

- `scripts/little_loops/issue_parser.py`: Added `_get_category_for_prefix()` helper method to map prefixes to category names
- `scripts/little_loops/issue_parser.py`: Modified `_generate_id_from_filename()` to use `get_next_issue_number()` instead of hash-based fallback, ensuring sequential and deterministic IDs
- `scripts/tests/test_issue_parser.py`: Added 3 new tests for prefix-to-category mapping and sequential ID generation

### Verification Results

- Tests: PASS (241 passed)
- Lint: PASS (pre-existing issues only, none in modified files)
- Types: PASS (no issues found in 19 source files)
