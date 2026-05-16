---
discovered_date: 2026-01-24
discovered_by: audit
---

# ENH-136: Add overwrite handling to create_sprint command

## Summary

The `/ll:create-sprint` command should check if a sprint file already exists and prompt the user before overwriting, similar to how `/ll:create-loop` handles this case.

## Context

During an audit of the create_sprint command, it was noted that the command will silently overwrite existing sprint files without warning. The create_loop command (Step 5.2) implements this check properly.

## Current Behavior

The command writes directly to `.sprints/${SPRINT_NAME}.yaml` without checking if the file exists.

## Expected Behavior

Before writing the sprint file:
1. Check if `.sprints/${SPRINT_NAME}.yaml` exists
2. If exists, use AskUserQuestion to ask:
   - "Overwrite existing sprint?"
   - "Choose a different name"
   - "Cancel"

## Proposed Solution

Add a check step between Step 4 (Create Sprint Directory) and Step 5 (Create Sprint YAML File):

```yaml
### Step 4b: Check for Existing Sprint

Check if a sprint with this name already exists:

Use the Glob tool to check: `.sprints/${SPRINT_NAME}.yaml`

If file exists, use AskUserQuestion:
```yaml
questions:
  - question: "A sprint named '${SPRINT_NAME}' already exists. What would you like to do?"
    header: "Overwrite"
    multiSelect: false
    options:
      - label: "Overwrite"
        description: "Replace the existing sprint configuration"
      - label: "Choose different name"
        description: "Go back and pick a new name"
      - label: "Cancel"
        description: "Abort sprint creation"
```

If "Choose different name": Return to name input
If "Cancel": Exit with message
If "Overwrite": Continue to Step 5
```

## Impact

- **Priority**: P4 (low - edge case improvement)
- **Effort**: Low (add ~15 lines)
- **Risk**: Low

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_loop.md | Reference implementation (Step 5.2) |

## Labels

`enhancement`, `create_sprint`, `ux`

---

## Status

**Open** | Created: 2026-01-24 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made
- `commands/create_sprint.md`: Added Step 4b between Step 4 (Create Sprint Directory) and Step 5 (Create Sprint YAML File) that checks for existing sprint files and prompts the user with three options: Overwrite, Choose different name, or Cancel

### Verification Results
- Tests: N/A (markdown command file, no Python changes)
- Lint: PASS
- Types: PASS
