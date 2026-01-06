# FEAT-006: Continuation Prompt & Handoff Integration - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-006-continuation-prompt-handoff-integration.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The continuation/handoff mechanism currently exists but is tightly coupled to issue management:

### Key Discoveries
- `PreCompact` hook at `hooks/prompts/pre-compact-state.md:1-131` generates continuation prompts
- Continuation functions in `scripts/little_loops/issue_manager.py:34-216`:
  - `CONTEXT_HANDOFF_PATTERN` (line 35)
  - `CONTINUATION_PROMPT_PATH` (line 36)
  - `detect_context_handoff()` (lines 119-128)
  - `read_continuation_prompt()` (lines 131-143)
  - `run_with_continuation()` (lines 146-216)
- `max_continuations` config exists in Python (`config.py:116`) but not in `config-schema.json`
- Autoprompt feature at `commands/toggle_autoprompt.md` provides the pattern to follow

### Patterns Being Followed
- Command structure: `commands/toggle_autoprompt.md:1-157`
- Hook registration: `hooks/hooks.json:4-13` (SessionStart)
- Config schema: `config-schema.json:328-362` (prompt_optimization)
- Python dataclass: `scripts/little_loops/config.py:107-129` (AutomationConfig)

## Desired End State

A first-class continuation feature with:
1. `/ll:handoff` - Manual continuation prompt generation
2. `/ll:resume` - Resume from continuation prompt
3. SessionStart hook - Auto-detect continuation prompts
4. Configuration section for continuation settings
5. Extended PreCompact hook for general sessions

### How to Verify
- Commands appear in `/ll:help` output
- SessionStart shows notification when continuation prompt exists
- Configuration section validates properly
- General sessions (not just issue management) can generate handoff prompts

## What We're NOT Doing

- Not creating a new `continuation.py` module - keeping functions in `issue_manager.py` for now
- Not creating `docs/CONTINUATION.md` - documentation updates deferred
- Not modifying `README.md` - documentation updates deferred
- Not adding Python CLI flags for continuation - existing CLI infrastructure is sufficient

## Implementation Phases

### Phase 1: New Slash Commands

#### Overview
Create `/ll:handoff` and `/ll:resume` commands following the pattern from `toggle_autoprompt.md`.

#### Changes Required

**File**: `commands/handoff.md` (NEW)

Create a new command for manual continuation prompt generation:

```markdown
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

1. **Todo List**: Get current todo items
2. **Git Status**: Run `git status --short` for changed files
3. **Recent Files**: Check `git diff --name-only HEAD~1` for recent modifications
4. **Plan Files**: Look for active plans in `thoughts/shared/plans/`
5. **Context Description**: Use provided context or derive from current work

### 2. Generate Continuation Prompt

Write to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: [Context or Task Description]

## Context
[2-3 sentence summary from gathered state or user-provided context]

## Completed Work
[From todo list - items marked completed]

## Current State
- Working on: [From in-progress todos]
- Modified files: [From git status]
- Last action: [Inferred from recent activity]

## Key File References
[Plan files, recently modified files with paths]

## Resume
To continue: `/ll:resume` or start new session with this prompt.

## Important Context
[Any active decisions or patterns being followed]
```

### 3. Output Handoff Signal

```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md

Run /ll:resume in a new session, or copy the prompt above.
```
```

**File**: `commands/resume.md` (NEW)

Create a new command to resume from continuation prompt:

```markdown
---
description: Resume from a previous session's continuation prompt
arguments:
  - name: prompt_file
    description: Path to continuation prompt file
    required: false
---

# Session Resume

Resume work from a previous session's continuation prompt.

## Process

### 1. Locate Continuation Prompt

```bash
PROMPT_FILE="${prompt_file:-.claude/ll-continue-prompt.md}"
```

Check for file existence:
- If `prompt_file` provided, use that path
- Otherwise, check `.claude/ll-continue-prompt.md`
- If not found, check `.claude/ll-session-state.json`

### 2. Validate Prompt

- Check file exists and is readable
- Check modification time (warn if > 24 hours old based on `continuation.prompt_expiry_hours`)

### 3. Display Resume Context

If continuation prompt found:

```
Resuming from previous session
─────────────────────────────
[Display continuation prompt content]
─────────────────────────────

Ready to continue. What would you like to do next?
```

If state file found but no prompt:

```
Previous session state found
────────────────────────────
Issue: [active_issue or "None"]
Phase: [phase or "Unknown"]
Todos: [count] items

No continuation prompt available.
```

If nothing found:

```
No continuation state found.

To create a handoff: /ll:handoff
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Command files exist: `commands/handoff.md`, `commands/resume.md`
- [ ] Commands have valid YAML frontmatter

**Manual Verification**:
- [ ] `/ll:handoff` generates `.claude/ll-continue-prompt.md`
- [ ] `/ll:resume` displays prompt content correctly

> **Phase Gate**: Pause for verification after this phase.

---

### Phase 2: SessionStart Hook Integration

#### Overview
Add a SessionStart hook to auto-detect continuation prompts and notify the user.

#### Changes Required

**File**: `hooks/prompts/session-start-resume.md` (NEW)

```markdown
---
event: SessionStart
---

# Session Start Resume Detection

Check for continuation prompt and notify user if found.

## Actions

### 1. Check for Continuation State

Look for `.claude/ll-continue-prompt.md`:
- Check if file exists
- Check modification time

### 2. Evaluate Freshness

Read expiry setting from `.claude/ll-config.json`:
- `continuation.prompt_expiry_hours` (default: 24)
- Compare file mtime to current time

### 3. Notify If Found and Fresh

If continuation prompt exists and is within expiry window:

```
[ll] Previous session state found (from <relative time>)
     Run /ll:resume to continue where you left off
```

### 4. Silent If Not Found

If no continuation prompt or if stale:
- Output nothing
- Let session start normally

## Notes

- This hook should be fast (<2 seconds)
- Only outputs a single notification line
- Does not auto-resume - user must explicitly run /ll:resume
```

**File**: `hooks/hooks.json`
**Changes**: Add SessionStart prompt hook

Add to the existing `SessionStart` hooks array:

```json
{
  "SessionStart": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash -c '...existing config check...'"
        },
        {
          "type": "prompt",
          "prompt": "${CLAUDE_PLUGIN_ROOT}/hooks/prompts/session-start-resume.md",
          "timeout": 2000
        }
      ]
    }
  ]
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Hook file exists: `hooks/prompts/session-start-resume.md`
- [ ] `hooks/hooks.json` is valid JSON

**Manual Verification**:
- [ ] SessionStart shows notification when `.claude/ll-continue-prompt.md` exists
- [ ] SessionStart is silent when no continuation prompt exists

> **Phase Gate**: Pause for verification after this phase.

---

### Phase 3: Configuration Schema Updates

#### Overview
Add `continuation` section to config schema following the `prompt_optimization` pattern.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add continuation section after `prompt_optimization`

Insert after line 362 (before the closing `}`):

```json
,
    "continuation": {
      "type": "object",
      "description": "Session continuation and handoff settings (commands: /ll:handoff, /ll:resume)",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "Enable continuation prompt features",
          "default": true
        },
        "auto_detect_on_session_start": {
          "type": "boolean",
          "description": "Check for continuation prompt when session starts",
          "default": true
        },
        "include_todos": {
          "type": "boolean",
          "description": "Include todo list state in continuation prompt",
          "default": true
        },
        "include_git_status": {
          "type": "boolean",
          "description": "Include git status in continuation prompt",
          "default": true
        },
        "include_recent_files": {
          "type": "boolean",
          "description": "Include recently modified files in continuation prompt",
          "default": true
        },
        "max_continuations": {
          "type": "integer",
          "description": "Maximum automatic session continuations for CLI tools",
          "default": 3,
          "minimum": 1,
          "maximum": 10
        },
        "prompt_expiry_hours": {
          "type": "integer",
          "description": "Hours before continuation prompt is considered stale",
          "default": 24,
          "minimum": 1,
          "maximum": 168
        }
      },
      "additionalProperties": false
    }
```

#### Success Criteria

**Automated Verification**:
- [ ] `config-schema.json` is valid JSON
- [ ] Schema validation passes

**Manual Verification**:
- [ ] `continuation` section appears in schema documentation

> **Phase Gate**: Pause for verification after this phase.

---

### Phase 4: Extend PreCompact Hook for General Sessions

#### Overview
Update `pre-compact-state.md` to work for any session, not just issue management.

#### Changes Required

**File**: `hooks/prompts/pre-compact-state.md`
**Changes**: Extend to handle general sessions without active issues

Update the hook to:
1. Detect if working on an issue (existing behavior)
2. If not on an issue, capture general session context:
   - Recent file reads/edits from conversation context
   - Current working directory
   - Any active plan files
   - Todo list state

Add section after "Active Issue Tracking" (around line 28):

```markdown
### 2b. General Session Context (No Active Issue)

If NOT actively processing an issue:
- Set `active_issue` to null
- Set `phase` to null
- Still capture:
  - Todo list state
  - Any plan files in `thoughts/shared/plans/` referenced this session
  - Modified files from git status
  - Brief context description of current work

The continuation prompt should be useful for ANY session, not just issue management.
```

Update the continuation prompt template section to be more generic:

```markdown
## Continuation Prompt Generation

**CRITICAL**: Generate a self-contained continuation prompt for fresh-context handoff.

Write to `.claude/ll-continue-prompt.md`:

```markdown
# Session Continuation: [ISSUE-ID if working on issue, otherwise Task/Context Description]

## Context
[2-3 sentence summary - what was being worked on]
[If issue: Issue type and current phase]
[If general: Brief description of task/goal]

## Completed Work
- [x] [Completed item with file:line reference]
[From todos if available, or summarize from conversation]

## Current State
- Working on: [Current task/phase]
- Last action: [What was just done]
- Next action: [Immediate next step]

## Key File References
- Plan: `[path if applicable]`
- Modified: `[file:line references]`
- Tests: `[test file references if applicable]`

## Resume
[If issue]: /ll:manage_issue [type] [action] [ISSUE-ID] --resume
[If general]: /ll:resume or continue manually

## Important Context
[Decisions made, gotchas discovered, patterns being followed]
```
```

#### Success Criteria

**Automated Verification**:
- [ ] `hooks/prompts/pre-compact-state.md` is valid markdown

**Manual Verification**:
- [ ] PreCompact generates prompt for general sessions (not just issue management)

> **Phase Gate**: Pause for verification after this phase.

---

### Phase 5: Update Commands Help

#### Overview
Update `/ll:help` to include new commands.

#### Changes Required

**File**: `commands/help.md`
**Changes**: Add handoff and resume commands to listing

Add to the Session Management or Utilities section:

```markdown
### Session Management

| Command | Description |
|---------|-------------|
| `/ll:handoff [context]` | Generate continuation prompt for session handoff |
| `/ll:resume [file]` | Resume from previous session's continuation prompt |
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/help.md` contains references to handoff and resume

**Manual Verification**:
- [ ] `/ll:help` shows new commands

> **Phase Gate**: Pause for verification after this phase.

---

## Testing Strategy

### Unit Tests
- No new Python code requiring unit tests (commands are markdown-based)
- Config schema validation handled by JSON Schema

### Integration Tests
- Manual testing of `/ll:handoff` generating prompt
- Manual testing of `/ll:resume` reading prompt
- SessionStart hook notification display
- PreCompact hook for general sessions

## References

- Issue: `.issues/features/P2-FEAT-006-continuation-prompt-handoff-integration.md`
- Autoprompt pattern: `commands/toggle_autoprompt.md`
- Existing continuation: `scripts/little_loops/issue_manager.py:34-216`
- PreCompact hook: `hooks/prompts/pre-compact-state.md`
- Hooks registration: `hooks/hooks.json`
- Config schema: `config-schema.json`
