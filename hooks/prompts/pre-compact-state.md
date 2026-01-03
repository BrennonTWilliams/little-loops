---
event: PreCompact
---

# Pre-Compact State Persistence

Before context compaction, preserve session state to enable resumption.

## State Preservation Actions

### 1. TodoList State

If there are active todo items being tracked:
- Save the current todo state to `.claude/ll-session-state.json`
- Include all pending and in-progress items
- Note the current working context

### 2. Active Issue Tracking

If actively processing an issue via `/ll:manage_issue`:
- Record the issue ID (e.g., `BUG-004`, `FEAT-001`)
- Note the current phase:
  - `planning` - Creating implementation plan
  - `implementing` - Writing code changes
  - `testing` - Running verification
  - `committing` - Preparing commits
  - `completing` - Moving to completed/

### 3. Plan File Reference

If working on a plan in `thoughts/shared/plans/`:
- Note the plan filename
- Ensure plan content is saved before compaction

## State File Format

Write to `.claude/ll-session-state.json`:

```json
{
  "timestamp": "<ISO 8601 timestamp>",
  "active_issue": "<issue ID or null>",
  "phase": "<current phase or null>",
  "plan_file": "<path to active plan or null>",
  "todos": [
    {
      "content": "<todo description>",
      "status": "<pending|in_progress|completed>"
    }
  ],
  "context": "<brief description of current work>"
}
```

## Resumption Hint

After compaction, check `.claude/ll-session-state.json` to resume work:
- Continue with the active issue if one was in progress
- Restore todo tracking from saved state
- Reference the plan file if applicable

## Notes

- This hook ensures long sessions can resume after context limits
- State file is human-readable JSON for manual inspection
- Complements `.auto-manage-state.json` used by automation tools
