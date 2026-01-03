---
event: PostToolUse
matchTools:
  - SlashCommand
---

# Post-Tool State Tracking for /ll:manage_issue

This hook tracks progress when `/ll:manage_issue` commands complete.

## Trigger Condition

Only process if the SlashCommand was `/ll:manage_issue`.

## State Tracking Logic

IF the command started with "/ll:manage_issue":

1. **Extract Issue ID** from the command arguments or output
   - Format: `BUG-NNN`, `FEAT-NNN`, or `ENH-NNN`

2. **Determine Outcome**:
   - **SUCCESS**: Output mentions "moved to completed" or issue file now in `.issues/completed/`
   - **IN_PROGRESS**: Implementation ongoing, no completion marker
   - **FAILED**: Output contains error, "blocked", or "failed" indicators

3. **Log State Awareness** (read-only observation):
   - Note the issue ID and outcome for session context
   - If `.auto-manage-state.json` exists, its state reflects automation progress
   - Do NOT modify any files - this hook is for observation only

4. **Session Context**:
   - Keep track of which issues were processed this session
   - This helps with resumption and progress reporting

## Notes

- This hook does not modify state files (Python automation handles that)
- It provides visibility into manual `/ll:manage_issue` invocations
- State changes from `ll-auto` or `ll-parallel` are managed by those tools
