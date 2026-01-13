# BUG-034: Work Verification False Positive - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-034-excluded-files-only-false-positive.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The work verification system in `scripts/little_loops/work_verification.py` determines if meaningful implementation work occurred by checking if any changed files are outside of excluded directories. Currently, when ONLY excluded files are modified, the function returns `False` and logs a warning, but provides no information about WHICH excluded files were modified.

### Key Discoveries
- `work_verification.py:18-24` - Hard-coded `EXCLUDED_DIRECTORIES` tuple containing `.issues/`, `.speckit/`, `thoughts/`, `.worktrees/`, `.auto-manage`
- `work_verification.py:67` - Warning logged but does not include which files were modified
- `worker_pool.py:690` - Returns generic error message "Only excluded files modified (e.g., .issues/, thoughts/)"
- `types.py:274` - `require_code_changes` config exists but is a global toggle for ALL issues

### Root Cause
The false positive occurs because:
1. Documentation-only work (modifying `thoughts/` plans, updating `.issues/` files) is valid work for some issues
2. When this happens, there's no diagnostic information about which files were actually modified
3. Users cannot distinguish between "no work was done" and "documentation work was done but not detected as meaningful"

## Desired End State

1. When work verification fails due to only excluded files being modified, log WHICH excluded files were modified
2. This provides diagnostic information to help users understand what happened
3. The error message should include the actual file list to aid troubleshooting

### How to Verify
- Run tests to confirm new logging behavior
- When only excluded files modified, log output should include file names

## What We're NOT Doing

- **Not adding per-category configuration** - The issue proposes several improvements, but the minimal fix is to add diagnostic logging
- **Not adding issue-type-specific handling** - That's a larger enhancement beyond the scope of this bug fix
- **Not modifying the global `require_code_changes` flag behavior** - That already exists as a workaround
- **Not changing the return value logic** - Still returns `False`, just with better logging
- Deferring configuration-based approaches to separate enhancement issues

## Problem Analysis

From the log evidence:
```
[13:09:19] No meaningful changes detected - only excluded files modified
[13:09:20] ENH-686 failed: Only excluded files modified (e.g., .issues/, thoughts/)
```

The worker spent 16+ minutes processing, but we don't know what files were actually modified. This makes debugging impossible. The fix is to log the actual excluded files that were detected.

## Solution Approach

Add diagnostic logging of the actual excluded files when work verification fails. This is a minimal, targeted fix that:
1. Does not change the verification logic (still returns `False`)
2. Provides actionable diagnostic information
3. Helps users understand false positives vs actual lack of work

## Implementation Phases

### Phase 1: Add Diagnostic Logging to work_verification.py

#### Overview
Modify `verify_work_was_done()` to log which excluded files were modified when verification fails.

#### Changes Required

**File**: `scripts/little_loops/work_verification.py`
**Changes**: Update the warning log message to include the excluded files that were detected

Current code (lines 60-68):
```python
if changed_files is not None:
    meaningful_changes = filter_excluded_files(changed_files)
    if meaningful_changes:
        logger.info(
            f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
        )
        return True
    logger.warning("No meaningful changes detected - only excluded files modified")
    return False
```

New code:
```python
if changed_files is not None:
    meaningful_changes = filter_excluded_files(changed_files)
    if meaningful_changes:
        logger.info(
            f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
        )
        return True
    # Log which excluded files were modified for diagnostic purposes
    excluded_files = [f for f in changed_files if f and f not in meaningful_changes]
    logger.warning(
        f"No meaningful changes detected - only excluded files modified: {excluded_files[:10]}"
    )
    return False
```

Also update git-based detection path (lines 100-103):
```python
logger.warning("No meaningful changes detected - only excluded files modified")
return False
```

New code for git path - need to collect and log the excluded files from both unstaged and staged checks.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_work_verification.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/work_verification.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/work_verification.py`

---

### Phase 2: Update Error Message in worker_pool.py

#### Overview
Enhance the error message returned by `_verify_work_was_done()` to include which excluded files were detected.

#### Changes Required

**File**: `scripts/little_loops/parallel/worker_pool.py`
**Changes**: Pass the changed files to a helper that generates a descriptive error message

Current code (lines 686-690):
```python
# Use shared verification function
if verify_work_was_done(self.logger, changed_files):
    return True, ""

return False, "Only excluded files modified (e.g., .issues/, thoughts/)"
```

New code:
```python
# Use shared verification function
if verify_work_was_done(self.logger, changed_files):
    return True, ""

# Generate descriptive error with actual excluded files
excluded_files = [
    f for f in changed_files
    if f and any(f.startswith(excl) for excl in EXCLUDED_DIRECTORIES)
]
if excluded_files:
    files_preview = ", ".join(excluded_files[:5])
    if len(excluded_files) > 5:
        files_preview += f" (+{len(excluded_files) - 5} more)"
    return False, f"Only excluded files modified: {files_preview}"
return False, "Only excluded files modified (e.g., .issues/, thoughts/)"
```

Also need to import `EXCLUDED_DIRECTORIES` at the top of the file.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_worker_pool.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/worker_pool.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/worker_pool.py`

---

### Phase 3: Add Unit Tests

#### Overview
Add tests to verify the new diagnostic logging behavior.

#### Changes Required

**File**: `scripts/tests/test_work_verification.py`
**Changes**: Add tests that verify excluded files are included in warning message

New test cases:
```python
def test_warning_includes_excluded_files(self, mock_logger: MagicMock) -> None:
    """Warning message includes which excluded files were detected."""
    changed_files = [".issues/bugs/BUG-001.md", "thoughts/notes.md"]
    verify_work_was_done(mock_logger, changed_files)
    mock_logger.warning.assert_called()
    call_args = str(mock_logger.warning.call_args)
    assert ".issues/bugs/BUG-001.md" in call_args or "BUG-001" in call_args
    assert "thoughts/notes.md" in call_args or "notes.md" in call_args

def test_warning_truncates_long_file_list(self, mock_logger: MagicMock) -> None:
    """Warning truncates file list when many excluded files."""
    changed_files = [f".issues/bugs/BUG-{i:03d}.md" for i in range(15)]
    verify_work_was_done(mock_logger, changed_files)
    mock_logger.warning.assert_called()
    # Should only show first 10
    call_args = str(mock_logger.warning.call_args)
    assert "BUG-000" in call_args
    assert "BUG-009" in call_args
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_work_verification.py -v`
- [ ] New tests specifically pass

---

## Testing Strategy

### Unit Tests
- Verify warning message includes excluded file names
- Verify file list is truncated for large lists
- Verify existing behavior unchanged when meaningful files exist

### Integration Tests
- Run `ll-parallel` on test repo with documentation-only changes
- Verify error message now shows which files were modified

## References

- Original issue: `.issues/bugs/P2-BUG-034-excluded-files-only-false-positive.md`
- Work verification module: `scripts/little_loops/work_verification.py`
- Worker pool integration: `scripts/little_loops/parallel/worker_pool.py:663-691`
- Existing tests: `scripts/tests/test_work_verification.py`
