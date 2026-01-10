# BUG-010: ll-auto manage_issue uses stale abstract ID - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-010-manage-issue-uses-stale-abstract-id.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `_process_issue` method in `issue_manager.py` has a fallback mechanism when `ready_issue` validates the wrong file. When the fallback succeeds:
1. `info.path` MAY be updated (line 403 for renames)
2. `parsed` is updated to the retry result (line 460)
3. **BUG**: `info.issue_id` is NEVER updated

At line 561, the manage_issue command uses `info.issue_id`, which still contains the original abstract ID (e.g., `BUG-1`) even when the fallback used an explicit path and succeeded.

### Key Discoveries
- `issue_manager.py:420` - `relative_path = _compute_relative_path(info.path)` computes the path for fallback
- `issue_manager.py:424` - Fallback retry uses `/ll:ready_issue {relative_path}`
- `issue_manager.py:458-460` - Fallback success only updates `parsed`, not `info.issue_id`
- `issue_manager.py:561` - `manage_issue` uses stale `info.issue_id`
- The `_compute_relative_path` helper already exists and works correctly

## Desired End State

After a successful fallback with explicit path:
1. The `manage_issue` command should use the same relative path that was used for the fallback retry
2. This ensures consistency between ready_issue and manage_issue

### How to Verify
- Run tests: `python -m pytest scripts/tests/test_issue_manager.py -v`
- Run lint: `ruff check scripts/`
- Run types: `python -m mypy scripts/little_loops/`
- New test should verify manage_issue gets the path after fallback

## What We're NOT Doing

- Not changing `info.issue_id` - we'll pass the path instead when fallback was used
- Not modifying the IssueInfo dataclass
- Not changing how ready_issue works
- Not changing the state manager's issue_id tracking (it already uses both)

## Problem Analysis

The bug occurs in the sequence:
1. `ready_issue BUG-1` → matches wrong file
2. Fallback: `ready_issue .issues/bugs/P1-DOC-001-*.md` → succeeds
3. **BUG**: `manage_issue bug fix BUG-1` → fails because BUG-1 doesn't exist

The fix: track when fallback was used and pass the path to manage_issue instead.

## Solution Approach

Use Option A from the issue proposal: Pass the validated path instead of abstract ID when fallback was used. This is the simplest solution with minimal code changes.

Track a local boolean `validated_via_fallback` that gets set to `True` when the fallback succeeds (line 459). Then at line 561, use the relative path instead of `info.issue_id` when this flag is set.

## Implementation Phases

### Phase 1: Add fallback tracking and fix manage_issue command

#### Overview
Add a boolean to track fallback usage and use relative path for manage_issue when fallback was used.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`
**Changes**:
1. Initialize `validated_via_fallback = False` before the fallback logic
2. Set `validated_via_fallback = True` when fallback succeeds (after line 459)
3. Use relative path for manage_issue when `validated_via_fallback` is True (line 561)

At ~line 365 (before the ready_issue call):
```python
# Track whether we used fallback path resolution
validated_via_fallback = False
```

At line 459-460, after "Fallback succeeded":
```python
# Fallback succeeded - use retry result
self.logger.info("Fallback succeeded: validated correct file")
parsed = retry_parsed
validated_via_fallback = True
```

At line 558-567, modify the manage_issue command construction:
```python
# Build manage_issue command
# Use category name that matches the directory (bugs -> bug, features -> feature)
type_name = info.issue_type.rstrip("s")  # bugs -> bug

# Use relative path if fallback was used, otherwise use issue_id
if validated_via_fallback:
    issue_arg = _compute_relative_path(info.path)
else:
    issue_arg = info.issue_id

# Use run_with_continuation to handle context exhaustion
result = run_with_continuation(
    f"/ll:manage_issue {type_name} {action} {issue_arg}",
    self.logger,
    timeout=self.config.automation.timeout_seconds,
    stream_output=self.config.automation.stream_output,
    max_continuations=self.config.automation.max_continuations,
    repo_path=self.config.repo_path,
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add test for fallback path propagation

#### Overview
Add a test that verifies manage_issue receives the path (not stale ID) after fallback.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`
**Changes**: Add a new test in `TestPathMismatchFallback` class

```python
def test_manage_issue_uses_path_after_fallback(self, temp_project_dir: Path) -> None:
    """Test that manage_issue uses relative path after fallback, not stale issue_id."""
    from unittest.mock import MagicMock, patch, call

    from little_loops.config import BRConfig
    from little_loops.issue_manager import AutoManager, _compute_relative_path
    from little_loops.issue_parser import IssueInfo

    # Setup project structure
    issues_dir = temp_project_dir / ".issues" / "bugs"
    issues_dir.mkdir(parents=True)
    (temp_project_dir / ".issues" / "completed").mkdir(parents=True)

    # Create the actual issue file with external repo naming convention
    actual_file = issues_dir / "P1-DOC-001-fix-layer-count.md"
    actual_file.write_text("# DOC-001: Fix Layer Count\n\n## Summary\nTest issue\n")

    # Create a different file that initial ready_issue might match
    wrong_file = issues_dir / "P3-BUG-001-old-issue.md"
    wrong_file.write_text("# BUG-001: Old Issue\n")

    # Create IssueInfo with abstract ID that doesn't match filename
    info = IssueInfo(
        path=actual_file,
        issue_type="bugs",
        priority="P1",
        issue_id="BUG-1",  # Abstract ID from queue
        title="Fix Layer Count",
    )

    # Expected relative path for the fallback
    expected_relative_path = _compute_relative_path(actual_file, temp_project_dir)

    # Mock ready_issue outputs
    first_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{wrong_file}
"""
    retry_output = f"""
## VERDICT
READY

## VALIDATED_FILE
{actual_file}
"""

    # Mock manage_issue output
    manage_output = """
================================================================================
ISSUE MANAGED: DOC-001 - fix
================================================================================

## RESULT
- Status: COMPLETED
"""

    # Track calls to run_claude_command and run_with_continuation
    call_history = []

    def mock_run_claude(command, *args, **kwargs):
        call_history.append(("run_claude_command", command))
        result = MagicMock()
        result.returncode = 0
        if "ready_issue" in command:
            if expected_relative_path in command:
                result.stdout = retry_output
            else:
                result.stdout = first_output
        return result

    def mock_run_with_continuation(command, *args, **kwargs):
        call_history.append(("run_with_continuation", command))
        result = MagicMock()
        result.returncode = 0
        result.stdout = manage_output
        result.stderr = ""
        return result

    # Create mock config
    mock_config = MagicMock(spec=BRConfig)
    mock_config.repo_path = temp_project_dir
    mock_config.automation = MagicMock()
    mock_config.automation.timeout_seconds = 60
    mock_config.automation.stream_output = False
    mock_config.automation.max_continuations = 3
    mock_config.get_category_action.return_value = "fix"
    mock_config.get_state_file.return_value = temp_project_dir / ".auto-state.json"

    with (
        patch("little_loops.issue_manager.run_claude_command", side_effect=mock_run_claude),
        patch("little_loops.issue_manager.run_with_continuation", side_effect=mock_run_with_continuation),
        patch("little_loops.issue_manager.check_git_status", return_value=False),
        patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
    ):
        manager = AutoManager(mock_config, dry_run=False)
        manager._process_issue(info)

    # Verify the sequence of calls
    assert len(call_history) >= 3, f"Expected at least 3 calls, got {len(call_history)}"

    # First call: ready_issue with abstract ID
    assert call_history[0][0] == "run_claude_command"
    assert "/ll:ready_issue BUG-1" in call_history[0][1]

    # Second call: ready_issue fallback with explicit path
    assert call_history[1][0] == "run_claude_command"
    assert expected_relative_path in call_history[1][1]

    # Third call: manage_issue should use the path, NOT the stale BUG-1
    assert call_history[2][0] == "run_with_continuation"
    manage_cmd = call_history[2][1]
    assert "manage_issue" in manage_cmd
    # The key assertion: must use path, not stale ID
    assert expected_relative_path in manage_cmd, \
        f"Expected manage_issue to use '{expected_relative_path}', got: {manage_cmd}"
    assert "BUG-1" not in manage_cmd, \
        f"manage_issue should NOT use stale ID 'BUG-1', got: {manage_cmd}"
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_issue_manager.py::TestPathMismatchFallback::test_manage_issue_uses_path_after_fallback -v`
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/`

---

## Testing Strategy

### Unit Tests
- Test that `validated_via_fallback` is set correctly after fallback
- Test that manage_issue receives path instead of stale ID

### Edge Cases
- Normal flow (no fallback): manage_issue uses issue_id
- Fallback flow: manage_issue uses relative path
- Rename flow: manage_issue uses issue_id (path updated but not via fallback)

## References

- Original issue: `.issues/bugs/P2-BUG-010-manage-issue-uses-stale-abstract-id.md`
- Related BUG-002: Added validated path tracking (enabled the fallback mechanism)
- Fallback logic: `issue_manager.py:408-460`
- manage_issue construction: `issue_manager.py:556-567`
