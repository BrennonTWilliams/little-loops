# BUG-280: ll-auto falsely reports verification failure when manage_issue creates plan awaiting approval - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-280-ll-auto-false-verification-failure-plan-approval.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

When `/ll:manage_issue` creates an implementation plan and asks for user approval, it:
1. Returns exit code 0 (success)
2. Creates a plan file in `thoughts/shared/plans/`
3. Makes no code changes (no git diff)
4. Does not move the issue file to `completed/`

ll-auto's Phase 3 verification logic (`scripts/little_loops/issue_manager.py:497-537`) then:
1. Checks if issue was moved to `completed/` → Returns False
2. Sees returncode 0, enters fallback logic (line 508)
3. Calls `verify_work_was_done()` → Returns False (only plan file in excluded `thoughts/`)
4. Logs error "REFUSING to mark [ISSUE] as completed: no code changes detected" (lines 524-533)
5. Marks issue as failed in state manager

### Key Discoveries

**Phase 3 Verification Entry** (`issue_manager.py:497-537`):
- Lines 502-503: Primary check via `verify_issue_completed()`
- Line 508: Fallback trigger when `not verified and result.returncode == 0`
- Line 515: Work detection via `verify_work_was_done(logger)`
- Lines 524-533: Error logging when no work detected

**Work Verification** (`work_verification.py:44-125`):
- Lines 75-120: Checks `git diff --name-only` and `git diff --cached --name-only`
- Lines 18-25: `EXCLUDED_DIRECTORIES` includes `"thoughts/"` (plan files excluded)
- Returns False when only excluded files modified

**Existing Plan Detection Pattern** (`subprocess_utils.py:23-52`):
- Lines 24-25: `CONTEXT_HANDOFF_PATTERN` regex for special signal detection
- Lines 28-37: `detect_context_handoff()` checks output for pattern
- Similar pattern can be used for plan creation detection

**Output Parsing Infrastructure** (`parallel/output_parsing.py:389-465`):
- `parse_manage_issue_output()` already exists but only detects COMPLETED/FAILED/BLOCKED
- Missing detection for PLAN_CREATED or AWAITING_APPROVAL states

### Patterns to Follow

From research findings:

1. **Signal Detection Pattern** (subprocess_utils.py:23-37):
   - Use regex pattern to detect special output signals
   - Simple boolean detection function
   - Example: `CONTEXT_HANDOFF_PATTERN`

2. **Success Outcome Classification** (issue_lifecycle.py:27-118):
   - Use Enum to classify outcomes (similar to `FailureType`)
   - Pattern-based detection on output strings
   - Return classification + context tuple

3. **Result Dataclass Extension** (parallel/types.py:52-133):
   - Follow `should_close` flag pattern
   - Add related fields: `plan_created: bool`, `plan_path: str | None`

## Desired End State

ll-auto should distinguish between three success outcomes:
1. **COMPLETED**: Issue fully implemented, code changes detected, file moved
2. **PLAN_CREATED**: Implementation plan written to `thoughts/shared/plans/`, awaiting approval
3. **INCOMPLETE**: Command succeeded but no progress (actual error case)

For PLAN_CREATED outcome, ll-auto should:
- Detect the plan file creation
- Mark as incomplete (not failed) to allow re-processing after approval
- Log informative message: "Plan created at [path], awaiting approval"
- NOT mark as failed in state manager

### How to Verify

**Automated Verification**:
- Existing tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- Existing tests pass: `python -m pytest scripts/tests/test_work_verification.py -v`
- New tests pass (see Phase 4)

**Manual Verification**:
- Run ll-auto on an issue that triggers plan creation
- Observe that it logs "Plan created, awaiting approval" instead of "REFUSING to mark as completed"
- Verify issue is NOT marked as failed in state file
- Approve the plan and re-run ll-auto
- Verify issue proceeds to implementation

## What We're NOT Doing

- Not modifying `/ll:manage_issue` command behavior
- Not changing `verify_work_was_done()` function (works correctly)
- Not creating a `--auto-approve-plans` flag (out of scope)
- Not backfilling detection for other CLI tools (ll-parallel, ll-sprint) in this fix
- Not adding plan creation to `parse_manage_issue_output()` yet (future enhancement)

## Problem Analysis

**Root Cause**: Phase 3 verification conflates two distinct success states:
- **State A**: "Command succeeded AND made changes" → Should complete lifecycle
- **State B**: "Command succeeded BUT created plan awaiting approval" → Should mark incomplete, not failed

Current logic at `issue_manager.py:508-533` treats State B as a failure case because:
1. No issue file movement detected
2. No code changes detected
3. Assumes this means command didn't work properly

**Missing Logic**: No detection for plan file creation in `thoughts/shared/plans/`

## Solution Approach

Add plan detection layer to Phase 3 verification, between the returncode check and work verification:

```
if not verified and result.returncode == 0:
    # NEW: Check if plan was created (State B)
    plan_info = detect_plan_creation(result.stdout, info.issue_id)
    if plan_info is not None:
        → Log "Plan created, awaiting approval"
        → Return IssueProcessingResult(success=False, plan_created=True, ...)
        → Do NOT mark as failed

    # EXISTING: Check for work done (State A)
    work_done = verify_work_was_done(logger)
    if work_done:
        → complete_issue_lifecycle()
    else:
        → Log error "REFUSING to mark as completed" (State C: actual failure)
```

## Code Reuse & Integration

**Reusable existing code**:
- `verify_work_was_done()` (work_verification.py:44-125) - Use as-is for code change detection
- `EXCLUDED_DIRECTORIES` constant (work_verification.py:18-25) - Use as-is
- Signal detection pattern (subprocess_utils.py:23-37) - Model new detection function after this

**Patterns to follow**:
- Enum-based classification (issue_lifecycle.py:27-28, FailureType)
- Result dataclass extension (parallel/types.py:52-133, WorkerResult.should_close pattern)
- Regex pattern detection (subprocess_utils.py:24-25)

**New code justification**:
- `detect_plan_creation()` function - No existing function detects plan files, need new
- `plan_created` field in `IssueProcessingResult` - No existing field for this state, need new

## Implementation Phases

### Phase 1: Add Plan Detection Function

#### Overview
Create a detection function that identifies when `/ll:manage_issue` created a plan file without implementing it.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`

**Changes**: Add plan detection function before `process_issue_inplace()`

```python
def detect_plan_creation(output: str, issue_id: str) -> Path | None:
    """Detect if manage_issue created a plan file awaiting approval.

    Checks for plan file creation in thoughts/shared/plans/ matching the issue ID.
    This happens when manage_issue creates a plan but waits for user approval.

    Args:
        output: Command stdout
        issue_id: Issue ID (e.g., "BUG-280")

    Returns:
        Path to plan file if created, None otherwise
    """
    plans_dir = Path("thoughts/shared/plans")
    if not plans_dir.exists():
        return None

    # Find plan files matching this issue ID (format: YYYY-MM-DD-ISSUE-ID-*.md)
    # Use glob pattern with issue_id
    pattern = f"*-{issue_id}-*.md"
    matching_plans = list(plans_dir.glob(pattern))

    if not matching_plans:
        return None

    # Return the most recently modified plan file
    # (in case multiple exist, take the latest)
    latest_plan = max(matching_plans, key=lambda p: p.stat().st_mtime)
    return latest_plan
```

**Why this approach**:
- Uses filesystem check instead of output parsing (more reliable)
- Follows existing pattern of checking actual results vs parsing text
- Matches plan file naming convention from manage_issue.md documentation
- Returns Path for easy logging and verification

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_manager.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`

**Manual Verification**:
- [ ] Function correctly returns None when no plan exists
- [ ] Function correctly returns Path when plan file exists for issue

---

### Phase 2: Extend IssueProcessingResult Dataclass

#### Overview
Add fields to track plan creation state in the result object.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`

**Changes**: Add fields to `IssueProcessingResult` dataclass (around line 197)

```python
@dataclass
class IssueProcessingResult:
    """Result of processing a single issue in-place."""

    success: bool
    duration: float
    issue_id: str
    was_closed: bool = False
    failure_reason: str = ""
    corrections: list[str] = field(default_factory=list)
    plan_created: bool = False  # NEW
    plan_path: str = ""  # NEW
```

**Why these fields**:
- `plan_created` - Boolean flag following `was_closed` pattern
- `plan_path` - String for logging/debugging (empty string default avoids None handling)

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_manager.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`

**Manual Verification**:
- [ ] Dataclass can be instantiated with new fields
- [ ] Default values work correctly (plan_created=False, plan_path="")

---

### Phase 3: Integrate Plan Detection into Phase 3 Verification

#### Overview
Modify Phase 3 verification logic to detect plan creation before checking for code changes.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`

**Changes**: Update Phase 3 verification fallback logic (lines 508-533)

Replace existing fallback block with:

```python
        if not verified and result.returncode == 0:
            # Check if a plan was created awaiting approval
            plan_path = detect_plan_creation(result.stdout, info.issue_id)
            if plan_path is not None:
                logger.info(
                    f"Plan created at {plan_path}, awaiting approval - "
                    "issue will remain incomplete until plan is approved and implemented"
                )
                return IssueProcessingResult(
                    success=False,
                    duration=time.time() - start_time,
                    issue_id=info.issue_id,
                    plan_created=True,
                    plan_path=str(plan_path),
                    failure_reason="",  # Not a failure - plan awaiting approval
                )

            logger.info(
                "Command returned success but issue not moved - "
                "checking for evidence of work..."
            )

            # CRITICAL: Verify actual implementation work was done
            work_done = verify_work_was_done(logger)
            if work_done:
                logger.info("Evidence of code changes found - completing lifecycle...")
                verified = complete_issue_lifecycle(info, config, logger)
                if verified:
                    logger.success(f"Fallback completion succeeded for {info.issue_id}")
                else:
                    logger.warning(f"Fallback completion failed for {info.issue_id}")
            else:
                # NO work was done - do NOT mark as completed
                logger.error(
                    f"REFUSING to mark {info.issue_id} as completed: "
                    "no code changes detected despite returncode 0"
                )
                logger.error(
                    "This likely indicates the command was not executed properly. "
                    "Check command invocation and Claude CLI output."
                )
                verified = False
```

**Key changes**:
1. **NEW block** (lines 510-523): Plan detection check before work verification
2. Returns immediately with `success=False` but `plan_created=True` (not a failure)
3. Uses empty string for `failure_reason` (not a failure case)
4. **Existing logic** (lines 525-548): Unchanged, handles code change detection

**Why this order**:
- Check plan creation BEFORE work verification (plan is valid progress)
- Avoids confusing "no work done" error when plan exists
- Returns early to skip unnecessary work verification

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_manager.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_manager.py`

**Manual Verification**:
- [ ] When plan is created, logs "Plan created at [path], awaiting approval"
- [ ] When plan is created, does NOT log "REFUSING to mark as completed"
- [ ] When plan is created, returns `IssueProcessingResult` with `success=False` but `plan_created=True`

---

### Phase 4: Add Tests for Plan Detection

#### Overview
Add test cases to verify plan detection behavior.

#### Changes Required

**File**: `scripts/tests/test_issue_manager.py`

**Changes**: Add test class for `detect_plan_creation()`

```python
class TestDetectPlanCreation:
    """Tests for detect_plan_creation function."""

    def test_no_plan_returns_none(self, tmp_path: Path) -> None:
        """Returns None when no plan file exists."""
        # Setup: Create plans directory but no matching plan
        plans_dir = tmp_path / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)

        # Test
        result = detect_plan_creation("", "BUG-999")

        # Verify
        assert result is None

    def test_matching_plan_returns_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns Path when matching plan file exists."""
        # Setup: Create plan file
        plans_dir = tmp_path / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        plan_file = plans_dir / "2026-02-08-BUG-280-management.md"
        plan_file.write_text("# Plan content")

        # Change to tmp directory
        monkeypatch.chdir(tmp_path)

        # Test
        result = detect_plan_creation("", "BUG-280")

        # Verify
        assert result is not None
        assert result.name == "2026-02-08-BUG-280-management.md"

    def test_multiple_plans_returns_latest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns most recently modified plan when multiple exist."""
        # Setup: Create multiple plan files
        plans_dir = tmp_path / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        old_plan = plans_dir / "2026-02-07-BUG-280-management.md"
        new_plan = plans_dir / "2026-02-08-BUG-280-management.md"
        old_plan.write_text("# Old plan")
        time.sleep(0.01)  # Ensure different mtimes
        new_plan.write_text("# New plan")

        # Change to tmp directory
        monkeypatch.chdir(tmp_path)

        # Test
        result = detect_plan_creation("", "BUG-280")

        # Verify
        assert result is not None
        assert result.name == "2026-02-08-BUG-280-management.md"

    def test_no_plans_dir_returns_none(self) -> None:
        """Returns None when plans directory doesn't exist."""
        # Test (assuming thoughts/shared/plans doesn't exist in test env)
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            result = detect_plan_creation("", "BUG-999")

        # Verify
        assert result is None
```

**File**: `scripts/tests/test_issue_manager.py`

**Changes**: Add integration test for Phase 3 plan detection

```python
class TestProcessIssueInplaceWithPlanCreation:
    """Tests for process_issue_inplace when plan is created."""

    def test_plan_creation_returns_incomplete_not_failed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mock_config: Config,
        mock_logger: logging.Logger,
    ) -> None:
        """When plan created, returns success=False with plan_created=True."""
        # Setup: Create issue file and plan
        bugs_dir = tmp_path / ".issues/bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P2-BUG-280-test.md"
        issue_file.write_text("# BUG-280\nTest issue")

        plans_dir = tmp_path / "thoughts/shared/plans"
        plans_dir.mkdir(parents=True)
        plan_file = plans_dir / "2026-02-08-BUG-280-management.md"
        plan_file.write_text("# Implementation Plan")

        monkeypatch.chdir(tmp_path)

        # Mock run_with_continuation to simulate plan creation
        def mock_run(cmd: list[str], logger: logging.Logger) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="Plan created, awaiting approval",
                stderr="",
            )

        monkeypatch.setattr("little_loops.issue_manager.run_with_continuation", mock_run)

        # Test
        info = IssueInfo(
            issue_id="BUG-280",
            priority="P2",
            path=issue_file,
            issue_type=IssueType.BUG,
        )
        result = process_issue_inplace(info, mock_config, mock_logger, dry_run=False)

        # Verify
        assert result.success is False  # Not successful yet (awaiting approval)
        assert result.plan_created is True  # But plan was created
        assert result.failure_reason == ""  # Not a failure
        assert "2026-02-08-BUG-280-management.md" in result.plan_path
```

**Why these tests**:
- Test unit behavior of `detect_plan_creation()` in isolation
- Test integration behavior of Phase 3 with plan creation
- Cover edge cases: no plan, multiple plans, missing directory
- Follow existing test patterns in the file

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestDetectPlanCreation -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py::TestProcessIssueInplaceWithPlanCreation -v`
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`
- [ ] Type check passes: `python -m mypy scripts/tests/test_issue_manager.py`

**Manual Verification**:
- [ ] Test coverage shows new code is exercised
- [ ] Test output is clear and descriptive

---

### Phase 5: Update AutoManager to Handle Plan Creation

#### Overview
Ensure AutoManager doesn't mark issues as failed when plan_created=True.

#### Changes Required

**File**: `scripts/little_loops/issue_manager.py`

**Changes**: Update `_process_issue()` method (around line 799) to check for plan creation

Find the section that marks issues as failed:

```python
        if not result.success:
            reason = result.failure_reason or "Unknown failure"
            self.state_manager.mark_failed(info.issue_id, reason)
```

Replace with:

```python
        if not result.success:
            # Don't mark as failed if a plan was created (awaiting approval)
            if result.plan_created:
                self.logger.info(
                    f"{info.issue_id} has plan at {result.plan_path} - "
                    "leaving in pending state for manual approval"
                )
                # Issue remains in pending state (not marked as failed)
            else:
                reason = result.failure_reason or "Unknown failure"
                self.state_manager.mark_failed(info.issue_id, reason)
```

**Why this change**:
- Prevents marking as failed when plan is awaiting approval
- Allows re-processing after user approves the plan
- Provides clear logging about the state

#### Success Criteria

**Automated Verification**:
- [ ] Type check passes: `python -m mypy scripts/little_loops/issue_manager.py`
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_manager.py -v`

**Manual Verification**:
- [ ] When plan is created, issue is NOT marked as failed in state file
- [ ] When plan is created, logs "leaving in pending state for manual approval"
- [ ] Issue can be re-processed after approval

---

## Testing Strategy

### Unit Tests

**New test file**: `scripts/tests/test_issue_manager.py` (add to existing)

Tests to add:
1. `test_detect_plan_creation_no_plan_returns_none()` - No plan file exists
2. `test_detect_plan_creation_matching_plan_returns_path()` - Plan file exists
3. `test_detect_plan_creation_multiple_plans_returns_latest()` - Multiple plans, returns newest
4. `test_detect_plan_creation_no_plans_dir_returns_none()` - Directory doesn't exist
5. `test_process_issue_inplace_with_plan_creation()` - Integration test for Phase 3

### Integration Tests

**Manual test scenario**:
1. Create a test issue in `.issues/bugs/`
2. Run `ll-auto --issue BUG-XXX` (or let it auto-select)
3. Let `/ll:manage_issue` create a plan and stop
4. Verify ll-auto logs "Plan created, awaiting approval"
5. Verify issue is NOT in failed state
6. Approve plan and re-run ll-auto
7. Verify implementation proceeds normally

### Edge Cases

1. **Plan file exists but is old** - Should still detect and handle
2. **Multiple plan files for same issue** - Should use most recent
3. **Plan file deleted between command and verification** - Should fall back to work verification
4. **Command creates plan AND makes code changes** - Work verification should catch changes

## References

- Original issue: `.issues/bugs/P2-BUG-280-ll-auto-false-verification-failure-plan-approval.md`
- Phase 3 verification: `scripts/little_loops/issue_manager.py:497-537`
- Work verification: `scripts/little_loops/work_verification.py:44-125`
- manage_issue command: `commands/manage_issue.md:172-174`
- Signal detection pattern: `scripts/little_loops/subprocess_utils.py:23-37`
- Result dataclass: `scripts/little_loops/issue_manager.py:197-207`
