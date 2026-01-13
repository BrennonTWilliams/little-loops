---
description: Generate continuation prompt for session handoff
arguments:
  - name: context
    description: Brief description of current work context (optional)
    required: false
---

# Session Handoff

Generate a continuation prompt capturing current session state for handoff to a fresh session.

## Configuration

Read settings from `.claude/ll-config.json` under `continuation`:
- `include_todos`: Include todo list state (default: true)
- `include_git_status`: Include git status (default: true)
- `include_recent_files`: Include recently modified files (default: true)

## Process

### 1. Gather Current State

Collect information about the current session:

#### Todo List
- Get all todo items (pending, in_progress, completed)
- Note which items are currently in progress

#### Git Status
Run: `git status --short`
- List modified files (M)
- List added files (A)
- List untracked files (?)

#### Recent Modifications
Run: `git diff --name-only HEAD~1 2>/dev/null || git diff --name-only --cached`
- Files changed in recent commits
- Files staged for commit

#### Plan Files
Check `thoughts/shared/plans/` for:
- Any plan files referenced in conversation
- Most recently modified plan file

#### Context
- Use provided context argument if given: `${context}`
- Otherwise, derive from current work (todos, recent activity)

### 2. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: [Context or Task Description]

## Context
[2-3 sentence summary from gathered state or user-provided context]

## Completed Work
[From todo list - items marked completed, with file:line references where applicable]

## Current State
- **Working on**: [From in-progress todos or current activity]
- **Modified files**: [From git status]
- **Last action**: [Inferred from recent activity]

## Key File References
[Plan files, recently modified files with paths]

## Resume
Run `/ll:resume` in a new session, or copy this prompt content.

## Important Context
[Any active decisions, gotchas, or patterns being followed]
```

### 3. Output Handoff Signal

After writing the continuation prompt, output:

```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md

To continue in a new session:
  1. Start a new Claude Code session
  2. Run /ll:resume

Or copy the prompt content above to paste into a new session.
```

---

## Examples

```bash
# Generate handoff with auto-detected context
/ll:handoff

# Generate handoff with explicit context
/ll:handoff "Refactoring authentication module"

# Generate handoff during issue work
/ll:handoff "Working on BUG-042 - user validation fix"
```

---

## Integration

- Complements `/ll:resume` for reading the prompt
- Uses same file format as automation tools (`ll-auto`, `ll-parallel`)
- Outputs `CONTEXT_HANDOFF` signal for automation detection
- Works with PostToolUse context monitor hook for automatic reminders
