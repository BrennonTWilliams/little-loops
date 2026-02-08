---
discovered_commit: b57c0542e0f94e62f0f00d59ef27afc70a580d82
discovered_date: 2026-02-08
discovered_source: blender-agents-ll-auto-debug.log
discovered_external_repo: /Users/brennon/AIProjects/ai-workspaces/blender-agents/
---

# BUG-280: ll-auto falsely reports verification failure when manage_issue creates plan awaiting approval

## Summary

When `/ll:manage_issue` creates an implementation plan and waits for user approval to proceed, ll-auto's Phase 3 verification incorrectly treats this as a failure. The command returns exit code 0 (success) but makes no code changes because it's waiting for approval. ll-auto detects no changes and marks the issue as failed, even though the behavior is correct.

## Evidence from Log

**Log File**: `blender-agents-ll-auto-debug.log`
**Log Type**: ll-auto
**External Repo**: `/Users/brennon/AIProjects/ai-workspaces/blender-agents/`
**Occurrences**: 1
**Affected External Issues**: ENH-2028

### Sample Log Output

```
[13:13:11] Phase 2: Implementing ENH-2028...
[13:13:11] Running: claude --dangerously-skip-permissions -p '/ll:manage_issue enhancement improve ENH-2028'
  I've created a comprehensive implementation plan for **ENH-2028: Socket timeout reduction causes body_unification phase failure**.
  The plan is complete and ready for implementation. Would you like me to:
  Let me know how you'd like to proceed!
[13:20:31] Phase 2 (implement) completed in 7.3 minutes
[13:20:31] Phase 3: Verifying ENH-2028 completion...
[13:20:31] Warning: ENH-2028 was NOT moved to completed
[13:20:31] Command returned success but issue not moved - checking for evidence of work...
[13:20:31] No meaningful changes detected - no files modified
[13:20:31] REFUSING to mark ENH-2028 as completed: no code changes detected despite returncode 0
[13:20:31] This likely indicates the command was not executed properly. Check command invocation and Claude CLI output.
```

## Current Behavior

ll-auto Phase 3 verification logic:
1. Checks if issue file was moved to `completed/`
2. If not moved, checks for code changes using `verify_work_was_done()`
3. If no changes detected, reports verification failure and marks issue as failed

When `/ll:manage_issue` creates a plan and asks for approval:
- Command exits with code 0 (not an error)
- No files are modified (plan wasn't implemented yet)
- Issue file isn't moved (not complete)
- ll-auto treats this as a failure

## Expected Behavior

ll-auto should distinguish between three outcomes:
1. **Success**: Issue completed, code changes detected, file moved
2. **Plan Created**: Implementation plan written, waiting for approval (should pause or notify, not fail)
3. **Actual Failure**: Command failed, no work done, error logged

For outcome #2, ll-auto should either:
- Option A: Detect that a plan was created (check for "Would you like me to" or similar in output) and mark as "plan ready, awaiting approval"
- Option B: Add a flag to skip verification for issues that require interactive approval
- Option C: Improve `/ll:manage_issue` to detect `--dangerously-skip-permissions` and proceed without asking

## Affected Components

- **Tool**: ll-auto
- **Likely Module**: `scripts/little_loops/issue_manager.py` (Phase 3 verification)
- **Related**: `commands/manage_issue.md` (plan creation behavior)

## Proposed Investigation

1. Review Phase 3 verification logic in `issue_manager.py`
2. Check if command output can be parsed to detect plan creation
3. Consider adding a `--auto-approve-plans` flag to `/ll:manage_issue` for ll-auto context
4. Add detection for "Would you like me to proceed?" patterns in command output

## Steps to Reproduce

1. Run `ll-auto` with `--dangerously-skip-permissions` flag
2. Let it process an issue that triggers `/ll:manage_issue` to create an implementation plan
3. Observe that `/ll:manage_issue` creates a plan and asks "Would you like me to proceed?"
4. Observe that the command exits with code 0 (success) but makes no file changes
5. See ll-auto Phase 3 verification mark the issue as failed

## Actual Behavior

When `/ll:manage_issue` creates a plan and asks for approval:
- Command exits with code 0 (not an error)
- No files are modified (plan wasn't implemented yet)
- Issue file isn't moved to completed/
- ll-auto treats this as a failure and logs "REFUSING to mark [ISSUE] as completed: no code changes detected despite returncode 0"

## Impact

- **Severity**: Medium (P2)
- **Frequency**: 1 occurrence in single run, but likely affects any issue that requires plan approval
- **User Impact**: False negatives cause issues to be skipped in future runs even though they just need approval to proceed
- **Workaround**: Manually run `/ll:manage_issue` with plan approval, or edit issue to bypass planning phase

## Labels

`bug`, `ll-auto`, `automation`, `false-positive`, `verification`

---

## Status
**Open** | Created: 2026-02-08 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-08
- **Status**: Completed

### Changes Made

**scripts/little_loops/issue_manager.py**:
- Added `detect_plan_creation()` function to detect plan files in `thoughts/shared/plans/`
- Extended `IssueProcessingResult` dataclass with `plan_created` and `plan_path` fields
- Modified Phase 3 verification to check for plan creation before work verification
- Updated `AutoManager._process_issue()` to avoid marking issues as failed when plan is created

**scripts/tests/test_issue_manager.py**:
- Added `TestDetectPlanCreation` test class with 4 unit tests
- Updated `TestFallbackVerification` tests to mock `detect_plan_creation()`

### Implementation Details

The fix adds a new detection layer to Phase 3 verification:

1. **Plan Detection** - New `detect_plan_creation()` function checks for plan files matching the issue ID in `thoughts/shared/plans/`
2. **Early Return** - If plan detected, returns immediately with `success=False` but `plan_created=True` (not a failure)
3. **State Management** - AutoManager checks `plan_created` flag and leaves issue in pending state instead of marking as failed
4. **Logging** - Provides clear message: "Plan created at [path], awaiting approval"

This allows ll-auto to distinguish between:
- **Plan Created**: Issue needs manual approval to proceed (remains pending)
- **Work Done**: Issue has code changes, complete via fallback
- **No Work**: Actual failure, mark as failed

### Verification Results

- **Tests**: All 56 tests pass (4 new tests added)
- **Type Check**: No mypy errors
- **Lint**: All ruff checks pass
- **Coverage**: New code at 87% coverage in issue_manager.py

### Impact

This fix resolves the false negative verification failures when `/ll:manage_issue` creates implementation plans. Issues will now correctly remain in pending state for re-processing after user approves the plan, rather than being incorrectly marked as failed.
