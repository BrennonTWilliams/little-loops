# BUG-003: Invalid FEAT-* IDs Generated in Issue Queue - Management Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-003-invalid-feature-ids-in-queue.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Problem Analysis

The issue stems from `_generate_id_from_filename()` in `issue_parser.py:208-223`. When an issue file doesn't contain an explicit ID pattern like `BUG-123` or `FEAT-001`, the function falls back to generating an ID using:

```python
return f"{prefix}-{abs(hash(filename)) % 10000:04d}"
```

This produces pseudo-random 4-digit IDs like `FEAT-1636`, `FEAT-6178`, etc. These IDs:
1. Don't correspond to any actual issue files
2. Are inconsistent (Python's `hash()` varies between runs)
3. Create confusion when processing the issue queue

### Root Cause

The hash-based fallback was designed for edge cases where files don't follow naming conventions, but it creates more problems than it solves:
- Generated IDs appear valid but point to non-existent files
- IDs are non-deterministic across Python sessions
- No validation that the generated ID actually corresponds to a file

## Solution Approach

Replace the hash-based fallback with sequential ID generation using the existing `get_next_issue_number()` function. This ensures:
1. IDs are deterministic and sequential
2. IDs don't collide with existing issues
3. IDs follow the project's established numbering convention

## Implementation Phases

### Phase 1: Fix ID Generation in issue_parser.py

**Files**: `scripts/little_loops/issue_parser.py`

**Changes**:
1. Modify `_generate_id_from_filename()` to use `get_next_issue_number()` instead of hash
2. Add `_get_category_for_prefix()` helper method to map prefix back to category
3. The method already has access to `self.config` which is needed for `get_next_issue_number()`

**Implementation**:
```python
def _get_category_for_prefix(self, prefix: str) -> str:
    """Get category name from prefix."""
    return self._prefix_to_category.get(prefix, "bugs")

def _generate_id_from_filename(self, filename: str, prefix: str) -> str:
    """Generate an issue ID from filename when not explicitly present."""
    # Try to extract a number from the filename
    numbers = re.findall(r"\d+", filename)
    if numbers:
        return f"{prefix}-{numbers[0]}"
    # Use next sequential number instead of hash
    category = self._get_category_for_prefix(prefix)
    next_num = get_next_issue_number(self.config, category)
    return f"{prefix}-{next_num:03d}"
```

### Phase 2: Add Unit Tests

**Files**: `scripts/tests/test_issue_parser.py`

**Changes**:
1. Add test for `_get_category_for_prefix()` helper
2. Add test verifying sequential ID generation (no hash-based IDs)
3. Add test for edge case of filename without numbers

## Verification Plan

1. Run existing test suite to ensure no regressions
2. Verify new tests pass
3. Run linting and type checking
4. Manual verification: create a test file without numeric ID and verify sequential ID is assigned

## Notes

- The fix is minimal and focused - only changing the fallback behavior
- Existing files with proper naming (like `P2-BUG-003-...`) are unaffected
- The `get_next_issue_number()` function already exists and scans both active and completed directories
