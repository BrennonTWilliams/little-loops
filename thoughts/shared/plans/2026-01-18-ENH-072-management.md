# ENH-072: capture_issue Incomplete View Flow - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-072-capture-issue-incomplete-view-flow.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

The `commands/capture_issue.md` file has three "View" options in duplicate detection flows:

1. **Line 177-178**: "View Existing" in exact duplicate flow (score >= 0.8)
2. **Line 207-208**: "View Existing" in similar issue flow (score 0.5-0.8)
3. **Line 232-233**: "View Completed" in reopen flow

Line 182 says: "If 'View Existing' selected, read and display the file, then ask again (Skip or Create Anyway)."

But there's no `AskUserQuestion` block specifying what that follow-up question should look like.

### Key Discoveries
- Pattern for follow-up questions after viewing exists in issue spec at `.issues/enhancements/P4-ENH-072-capture-issue-incomplete-view-flow.md:28-50`
- The codebase follows consistent AskUserQuestion YAML format in `commands/init.md:200-247` and elsewhere
- Follow-up questions should NOT include the "View" option (user already viewed)

## Desired End State

After selecting "View Existing" or "View Completed", the command should:
1. Display the file content
2. Present a clear follow-up question with the remaining action options
3. Proceed based on user's selection

### How to Verify
- Review the capture_issue.md file to confirm all three view flows have explicit follow-up AskUserQuestion blocks
- The follow-up questions should not include "View" options (user already viewed)

## What We're NOT Doing

- Not changing the detection scoring logic
- Not adding new view options to other flows
- Not modifying the file display behavior

## Solution Approach

Add explicit AskUserQuestion YAML blocks after lines 182, 209, and 235 to specify the follow-up questions that should be asked after viewing.

## Implementation Phases

### Phase 1: Add Follow-up for Exact Duplicate "View Existing" Flow

#### Overview
Add a follow-up AskUserQuestion block after line 182 for when user selects "View Existing" in the exact duplicate case.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Add follow-up question block after line 182

After line 182 ("If 'View Existing' selected, read and display the file, then ask again (Skip or Create Anyway)."), add:

```yaml
questions:
  - question: "Having reviewed the existing issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Skip"
        description: "Don't create - this is a duplicate"
      - label: "Create Anyway"
        description: "Create new issue despite similarity"
    multiSelect: false
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] File is valid markdown (no syntax errors)

**Manual Verification**:
- [ ] The follow-up question text is clear and actionable

---

### Phase 2: Add Follow-up for Similar Issue "View Existing" Flow

#### Overview
Add a follow-up AskUserQuestion block after line 209 for when user selects "View Existing" in the similar issue case (score 0.5-0.8).

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Add follow-up question block after line 209 (similar issue section)

After the "View Existing" option mention in the similar issue section, add instruction and block:

```yaml
questions:
  - question: "Having reviewed the existing issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Update Existing"
        description: "Add new context to the existing issue"
      - label: "Create New"
        description: "Create a separate issue"
    multiSelect: false
```

Note: This uses "Update Existing" and "Create New" options to match the similar issue flow's original options (not "Skip" and "Create Anyway" like exact duplicate).

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] The follow-up options match the similar issue context

---

### Phase 3: Add Follow-up for "View Completed" Flow

#### Overview
Add a follow-up AskUserQuestion block after line 235 for when user selects "View Completed" in the reopen flow.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Add follow-up question block after line 235

After the AskUserQuestion block for reopen flow, add:

```markdown
If "View Completed" selected, read and display the file, then ask again:

```yaml
questions:
  - question: "Having reviewed the completed issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Reopen"
        description: "Move back to active and add new context"
      - label: "Create New"
        description: "Create a separate issue"
    multiSelect: false
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] The follow-up options match the reopen context

---

## Testing Strategy

### Manual Review
- Read through the complete Phase 3 flow to verify consistency
- Ensure all three view flows now have explicit follow-up instructions

## References

- Original issue: `.issues/enhancements/P4-ENH-072-capture-issue-incomplete-view-flow.md`
- Pattern examples: `commands/init.md:200-247`
- Similar flow: `commands/capture_issue.md:167-182`
