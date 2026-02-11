# BUG-326: manage_issue improve action inconsistent for documentation issues - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-326-manage-issue-improve-action-inconsistent-for-documentation.md`
- **Type**: bug
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `ll:manage_issue` command's `improve` action is defined vaguely in `commands/manage_issue.md:660` as simply "Improve/enhance" without explicit implementation requirements. This ambiguity causes the model to interpret it inconsistently:

- **Code issues** (e.g., ENH-2078): Implements, tests, and commits as expected
- **Documentation issues** (e.g., ENH-2079): Only verifies and asks confirmation question

### Key Discoveries
- **Primary fix location**: `commands/manage_issue.md:660` - vague action definition
- **Skip conditions**: Only `verify` action has explicit skip conditions (lines 93, 503)
- **Default Behavior section** (lines 423-430): Already forbids `AskUserQuestion` without `--gates`
- **Related fixes**: ENH-304 and BUG-302 previously fixed similar ambiguity issues
- **No code changes needed**: This is a prompt clarification only

### Current Action Definition (commands/manage_issue.md:657-662)
```markdown
- **action** (required): Action to perform
  - `fix` - Fix a bug
  - `implement` - Implement a feature
  - `improve` - Improve/enhance  # VAGUE - needs clarification
  - `verify` - Verify issue status only
  - `plan` - Create plan only (equivalent to --plan-only flag)
```

## Desired End State

The `improve` action should:
1. Always go through full implementation phases (Plan → Implement → Verify → Complete)
2. Make actual changes to the files described in the issue
3. Not ask confirmation questions unless --gates flag is provided
4. Behave consistently regardless of issue type (code vs documentation vs tests)

### How to Verify
- Test with a documentation-only enhancement issue
- Run `/ll:manage_issue enhancement improve [ISSUE-ID]` without --gates flag
- Observe that the command implements changes directly, not just verification
- Verify no `AskUserQuestion` prompts appear without --gates flag
- Confirm ll-auto/ll-parallel automation succeeds

## What We're NOT Doing

- Not changing any Python code (issue_manager.py, work_verification.py, config.py)
- Not modifying the get_category_action() function
- Not changing the verify_work_was_done() logic
- Not creating new tests (this is a prompt-only change)
- Not modifying other action definitions (fix, implement, verify, plan)

## Problem Analysis

**Root Cause**: The `improve` action definition is ambiguous ("Improve/enhance") without explicit behavioral requirements. The model interprets this as potentially verification-only for documentation issues because "improve documentation" can be read as "review and suggest improvements" rather than "make improvements."

**Why automation breaks**: When the model skips implementation and only verifies, ll-auto's `verify_work_was_done()` detects no meaningful changes were made and refuses to mark the issue as complete, causing automation to stall.

## Solution Approach

Replace the vague `improve` action definition with explicit implementation requirements, following the pattern used in ENH-304 and BUG-302 for clarifying ambiguous behavior. Use **IMPORTANT** markers and explicit behavioral requirements.

## Code Reuse & Integration

- **Patterns from ENH-304**: Explicit clarification for ambiguous automation mode behavior
- **Patterns from BUG-302**: "explicitly forbid" language with **IMPORTANT** markers
- **Patterns from init.md**: Multi-line action definitions with IMPORTANT notes
- **No new code needed**: This is a prompt clarification only

## Implementation Phases

### Phase 1: Clarify the `improve` Action Definition

#### Overview
Replace the vague `improve - Improve/enhance` definition with explicit implementation requirements.

#### Changes Required

**File**: `commands/manage_issue.md`
**Location**: Line 660
**Changes**: Replace single-line definition with multi-line explicit requirements

**Current (line 660)**:
```markdown
  - `improve` - Improve/enhance
```

**New (replacement)**:
```markdown
  - `improve` - Improve/enhance existing functionality or documentation
    - **IMPORTANT**: Requires full implementation (Plan → Implement → Verify → Complete)
    - For documentation: Must edit/create files, not just verify content
    - For code: Follow same implementation process as fix/implement
    - Behaves identically to fix/implement actions across all issue types
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax is valid markdown
- [ ] No unintended whitespace changes

**Manual Verification**:
- [ ] Read the updated section to verify clarity
- [ ] Confirm the new definition explicitly states implementation is required
- [ ] Verify documentation-specific guidance is included

### Phase 2: Reinforce Implementation Requirements in Phase 3

#### Overview
Add explicit guidance in the Implementation Process section to prevent ambiguity for documentation issues.

#### Changes Required

**File**: `commands/manage_issue.md`
**Location**: After line 338 (end of Implementation Process list)
**Changes**: Add new subsection clarifying documentation improvement behavior

**Insert after line 338**:
```markdown
### Documentation Implementation Guidance

**IMPORTANT**: The `improve` action requires implementation, not just verification:

- For **documentation issues**: Edit or create the documentation files described in the issue
  - "Improve docs.md" means edit the file to add/update content, not review it for correctness
  - Make actual changes to improve clarity, completeness, or accuracy
  - Do not skip to verification without making file changes

- For **code issues**: Follow the same implementation process as `fix` and `implement` actions

- **All issue types**: The `improve` action is NOT a verification-only action (unlike `verify`)
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax is valid markdown

**Manual Verification**:
- [ ] Verify the new section explicitly states documentation issues require file edits
- [ ] Confirm clear distinction from `verify` action behavior

### Phase 3: Strengthen Default Behavior Section

#### Overview
Add explicit reminder that `improve` requires implementation and must not fall back to verification behavior.

#### Changes Required

**File**: `commands/manage_issue.md`
**Location**: After line 430 (end of Default Behavior bullet list)
**Changes**: Add reminder about improve action requiring implementation

**Insert after line 430**:
```markdown
> **Note**: The `improve` action requires full implementation (Plan → Implement → Verify → Complete). Do not interpret `improve` as a verification-only action or skip the Implementation phase. For all issue types including documentation, `improve` means make changes to files, not just review or verify them.
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax is valid markdown

**Manual Verification**:
- [ ] Verify the reminder explicitly forbids falling back to verification behavior
- [ ] Confirm clear statement that `improve` means make changes to files

## Testing Strategy

### Verification Method
Since this is a prompt-only change, testing involves:

1. **Visual inspection** of the updated prompt to ensure clarity
2. **Syntax validation** that markdown formatting is correct
3. **Future behavioral testing** when using ll-auto/ll-parallel on documentation issues

### Expected Behavior After Fix
When running `/ll:manage_issue enhancement improve ENH-2079` (documentation issue):
1. Should go through Plan → Implement → Verify → Complete phases
2. Should edit/create documentation files
3. Should NOT skip to verification only
4. Should NOT ask confirmation questions without --gates flag
5. Should exit with return code 0 AND have made actual file changes

## References

- Original issue: `.issues/bugs/P2-BUG-326-manage-issue-improve-action-inconsistent-for-documentation.md`
- Primary fix location: `commands/manage_issue.md:660`
- Related pattern: ENH-304 (automation mode clarification)
- Related pattern: BUG-302 (AskUserQuestion prohibition without --gates)
- Related code: `scripts/little_loops/config.py:35-39` (REQUIRED_CATEGORIES with actions)
- Related code: `scripts/little_loops/work_verification.py:44-125` (verify_work_was_done)
