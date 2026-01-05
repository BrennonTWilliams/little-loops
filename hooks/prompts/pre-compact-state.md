---
event: PreCompact
---

# Pre-Compact State Persistence

Before context compaction, preserve session state AND generate a continuation prompt for optimal handoff.

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
  "context": "<brief description of current work>",
  "handoff_prompt": "<path to continuation prompt>"
}
```

## Continuation Prompt Generation

**CRITICAL**: Also generate a self-contained continuation prompt for fresh-context handoff.

Write to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: [ISSUE-ID or Task Description]

## Context
[2-3 sentence summary of what was being worked on]

## Completed Work
- [x] [Phase/step that was completed]
- [x] [Another completed item with file:line reference]

## Current State
- Working on: [Current phase/step]
- Last action: [What was just done before handoff]
- Next action: [Immediate next step to take]

## Key File References
- Plan: `[path to plan file]`
- Main files: `[key file:line references]`
- Tests: `[test file references]`

## Resume Command
To continue this work, run:
```
/ll:manage_issue [type] [action] [ISSUE-ID] --resume
```

Or continue manually from the plan at `[plan path]`.

## Important Context
[Any critical information that would be lost without this prompt:
- Decisions made during implementation
- Gotchas discovered
- Patterns being followed]
```

### Prompt Generation Guidelines

1. **Be specific** - Include exact file:line references, not vague descriptions
2. **Capture decisions** - Note any implementation choices made during the session
3. **Include gotchas** - Document any surprises or edge cases discovered
4. **Keep it actionable** - The prompt should let a fresh session continue immediately

## Resumption Options

After compaction or in a new session:

### Option A: Use State File (same session, post-compaction)
- Check `.claude/ll-session-state.json`
- Continue with active issue
- Reference plan file

### Option B: Use Continuation Prompt (new session, fresh context)
- Read `.claude/ll-continue-prompt.md`
- Get full context without compaction artifacts
- Execute with fresh 100% context quality

## Automation Integration

For `ll-auto` and `ll-parallel`:
- State file: `.auto-manage-state.json` (existing)
- Continuation prompt: `.claude/ll-continue-prompt.md` (new)
- On context exhaustion, automation can spawn new session with continuation prompt

## Notes

- This hook ensures long sessions can resume after context limits
- State file is human-readable JSON for manual inspection
- Continuation prompt enables clean handoff to fresh sessions
- Complements `.auto-manage-state.json` used by automation tools
