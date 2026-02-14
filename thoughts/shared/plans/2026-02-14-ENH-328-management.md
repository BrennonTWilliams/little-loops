# ENH-328: Add Implementation Marker Checking to ll-auto Verify Phase

## Summary

Add issue file content marker checking as an additional fallback signal in the `process_issue_inplace()` verify phase. When the issue file contains implementation markers like "Status: Implemented" or a Resolution section, this provides evidence that the implementation completed even when git evidence is ambiguous.

## Research Findings

### Current Fallback Chain (issue_manager.py:540-597)
1. **Check 1** (line 545): `verify_issue_completed()` - File moved to `completed/`
2. **Check 2** (line 553): `detect_plan_creation()` - Plan file created (awaiting approval)
3. **Check 3** (line 575): `verify_work_was_done()` - Git evidence of code changes
4. **Check 4** (line 578): `complete_issue_lifecycle()` - Auto-complete if work confirmed

### Gap
No check for implementation markers in the issue file content itself. If `manage-issue` updated the issue file with a Resolution section or status markers but the git diff only shows `.issues/` changes (which are excluded by `filter_excluded_files()`), the verify phase reports no work done.

## Implementation Plan

### Phase 1: Add `check_content_markers()` function

**File**: `scripts/little_loops/issue_manager.py`

Add a new function near `detect_plan_creation()` (around line 233):

```python
def check_content_markers(issue_path: Path) -> bool:
    """Check if issue file content contains implementation markers.

    Looks for indicators that an implementation was completed, such as
    Resolution sections or status markers added by manage-issue.

    Args:
        issue_path: Path to the issue file

    Returns:
        True if implementation markers found
    """
    try:
        content = issue_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    markers = [
        "## Resolution",
        "Status: Implemented",
        "Status: Completed",
        "**Completed**:",
    ]
    return any(marker in content for marker in markers)
```

**Rationale**:
- Keep it in `issue_manager.py` alongside `detect_plan_creation()` since both are verify-phase helpers
- Simple string matching (no regex needed) - these are well-defined markers
- Read file content directly (no frontmatter parsing needed)
- Defensive: returns `False` on read errors

### Phase 2: Insert marker check into fallback chain

**File**: `scripts/little_loops/issue_manager.py`, lines 568-574

Insert the content marker check between plan detection and git evidence check. The new check acts as an **additional positive signal** alongside `verify_work_was_done()`, not as a replacement.

```python
# After plan detection returns None (line 567):

# Check issue file content for implementation markers
if check_content_markers(info.path):
    logger.info(
        "Implementation markers found in issue file - completing lifecycle..."
    )
    verified = complete_issue_lifecycle(info, config, logger)
    if verified:
        logger.success(
            f"Content marker completion succeeded for {info.issue_id}"
        )
    else:
        logger.warning(
            f"Content marker completion failed for {info.issue_id}"
        )
else:
    # Existing code: check git evidence
    ...
```

**Design Decision**: The content marker check triggers `complete_issue_lifecycle()` directly (same as the git evidence path). If content markers are found, we skip the git evidence check since the markers are themselves strong evidence.

If content markers are NOT found, fall through to the existing git evidence check unchanged.

### Phase 3: Add tests

**File**: `scripts/tests/test_issue_manager.py`

Add tests in the existing `TestProcessIssueInplace` class:

1. **`test_check_content_markers_resolution_section`** - Returns `True` when `## Resolution` present
2. **`test_check_content_markers_status_implemented`** - Returns `True` when `Status: Implemented` present
3. **`test_check_content_markers_none_found`** - Returns `False` when no markers present
4. **`test_check_content_markers_file_not_found`** - Returns `False` when file doesn't exist
5. **`test_fallback_uses_content_markers`** - Integration test: verify phase uses content markers when file not moved but markers present
6. **`test_fallback_skips_to_git_when_no_markers`** - Integration test: falls through to git evidence when no markers

### Success Criteria

- [ ] `check_content_markers()` function added to `issue_manager.py`
- [ ] Content marker check inserted into verify phase fallback chain
- [ ] Unit tests for `check_content_markers()` pass
- [ ] Integration tests for fallback chain pass
- [ ] Existing tests still pass (no regressions)
- [ ] Type checking passes
- [ ] Linting passes

## Risk Assessment

- **Low risk**: Additive change to existing fallback chain
- **No breaking changes**: Existing behavior preserved when no markers found
- **Conservative**: Only triggers on explicit markers, not heuristic content analysis
