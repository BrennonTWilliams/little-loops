---
discovered_date: 2025-01-15
discovered_by: manual_review
---

# ENH-072: capture_issue has incomplete "View Existing/Completed" flow specification

## Summary

Phase 3 of `/ll:capture_issue` offers "View Existing" and "View Completed" options but doesn't fully specify the follow-up interaction after displaying the file content.

## Current Behavior

The command says (line 182-183):
> If "View Existing" selected, read and display the file, then ask again (Skip or Create Anyway).

But no `AskUserQuestion` block is provided for this follow-up. The flow is:
1. User selects "View Existing"
2. File content is displayed
3. ??? (How should Claude ask the follow-up question?)

Similar issue for "View Completed" option in the reopen flow.

## Expected Behavior

Add explicit `AskUserQuestion` blocks for the follow-up questions after viewing:

```yaml
# After viewing existing active issue:
questions:
  - question: "Having reviewed the existing issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Skip"
        description: "Don't create - this is a duplicate"
      - label: "Create Anyway"
        description: "Create new issue despite similarity"
    multiSelect: false

# After viewing completed issue:
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

## Files to Modify

- `commands/capture_issue.md` - Add follow-up question blocks after lines 183 and 235

## Impact

- **Priority**: P4
- **Effort**: Low
- **Risk**: Low

## Labels

`enhancement`, `commands`, `documentation`

---

## Status

**Open** | Created: 2025-01-15 | Priority: P4
