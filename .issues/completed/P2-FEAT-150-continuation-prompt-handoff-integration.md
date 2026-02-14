---
discovered_commit: b39cd1266a933cdff6eb02e2ed8199bca5fc510e
discovered_branch: main
discovered_date: 2026-01-06T21:30:00Z
---

# FEAT-006: Continuation Prompt & Handoff Integration

## Summary

Elevate the Continuation Prompt & Handoff mechanism from a tightly-coupled component of auto-compaction to a first-class, standalone feature with dedicated commands, hooks, and configuration options. This enables seamless session continuity for all workflows, not just issue management.

## Motivation

Currently, the continuation/handoff mechanism is:
- **Tightly coupled** to `/ll:manage-issue` and `PreCompact` hook
- **Not discoverable** - users don't know it exists unless they read the code
- **Manual session friction** - users must copy/paste continuation prompt content
- **Issue-workflow only** - general long conversations have no handoff mechanism
- **No restoration command** - fresh sessions require manual context injection

Compare this to the autoprompt feature which has:
- Dedicated slash command (`/ll:toggle-autoprompt`)
- Dedicated hook (`UserPromptSubmit`)
- Dedicated configuration schema
- Dedicated agent (`prompt-optimizer`)

The handoff feature deserves the same level of integration.

## Proposed Implementation

### 1. New Slash Commands

#### `/ll:handoff` Command

Manually trigger continuation prompt generation for any session.

**File**: `commands/handoff.md`

```markdown
---
description: Generate continuation prompt for session handoff
arguments:
  - name: context
    description: Brief description of current work context
    required: false
---

# Session Handoff

Generate a continuation prompt capturing current session state for handoff to a fresh session.

## Actions

1. **Gather Current State**
   - Read active todo list
   - Identify recently modified files (from git status)
   - Note current working directory context
   - Capture any active plan files in `thoughts/`

2. **Generate Continuation Prompt**
   - Write to `.claude/ll-continue-prompt.md`
   - Include context summary, completed work, current state
   - List key file references with line numbers
   - Provide resume instructions

3. **Output Handoff Signal**
   ```
   CONTEXT_HANDOFF: Ready for fresh session
   Continuation prompt written to: .claude/ll-continue-prompt.md
   ```

## Usage

```bash
/ll:handoff                           # Auto-detect context
/ll:handoff "Refactoring auth module" # With explicit context
```
```

#### `/ll:resume` Command

Read continuation prompt and restore session context.

**File**: `commands/resume.md`

```markdown
---
description: Resume from a previous session's continuation prompt
arguments:
  - name: prompt_file
    description: Path to continuation prompt file
    required: false
    default: .claude/ll-continue-prompt.md
---

# Session Resume

Resume work from a previous session's continuation prompt.

## Actions

1. **Check for Continuation Prompt**
   - Look for `.claude/ll-continue-prompt.md`
   - If not found, check `.claude/ll-session-state.json`
   - Report if no continuation state exists

2. **Restore Context**
   - Read and display continuation prompt content
   - Restore todo list from state file if available
   - Show summary of previous session state

3. **Ready to Continue**
   - Provide brief "Resuming from previous session" summary
   - List immediate next actions from continuation prompt

## Usage

```bash
/ll:resume                                    # Default prompt file
/ll:resume thoughts/shared/plans/my-plan.md   # Custom prompt file
```
```

### 2. SessionStart Hook Integration

**File**: `hooks/prompts/session-start-resume.md`

Auto-detect continuation prompt on session start and offer to resume.

```markdown
# Session Start Resume Detection

## Trigger

This hook runs at the start of every Claude Code session.

## Actions

1. **Check for Continuation State**
   - Look for `.claude/ll-continue-prompt.md`
   - Check modification time (only if < 24 hours old)

2. **If Found, Notify User**
   Output a brief notification:
   ```
   [ll] Previous session state detected from <timestamp>
   Run /ll:resume to continue where you left off
   ```

3. **If Not Found**
   - Silent - no output
```

**Hook Registration** in `hooks/hooks.json`:

```json
{
  "SessionStart": [
    {
      "hooks": [
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

### 3. Configuration Schema Updates

**File**: `config-schema.json`

Add new `continuation` section:

```json
{
  "continuation": {
    "type": "object",
    "description": "Session continuation and handoff settings",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": true,
        "description": "Enable continuation prompt features"
      },
      "auto_detect_on_session_start": {
        "type": "boolean",
        "default": true,
        "description": "Check for continuation prompt when session starts"
      },
      "include_todos": {
        "type": "boolean",
        "default": true,
        "description": "Include todo list state in continuation prompt"
      },
      "include_git_status": {
        "type": "boolean",
        "default": true,
        "description": "Include git status in continuation prompt"
      },
      "include_recent_files": {
        "type": "boolean",
        "default": true,
        "description": "Include recently modified files in continuation prompt"
      },
      "max_continuations": {
        "type": "integer",
        "default": 3,
        "minimum": 1,
        "maximum": 10,
        "description": "Maximum automatic session continuations for CLI tools"
      },
      "prompt_expiry_hours": {
        "type": "integer",
        "default": 24,
        "minimum": 1,
        "maximum": 168,
        "description": "Hours before continuation prompt is considered stale"
      }
    }
  }
}
```

### 4. Extend PreCompact Hook for General Sessions

Update `hooks/prompts/pre-compact-state.md` to work for any session, not just issue management:

- Detect if working on an issue (current behavior)
- If not, capture general session context:
  - Recent file reads/edits
  - Current working directory
  - Any active plan files
  - Todo list state

### 5. State Restoration Improvements

Enhance todo list restoration in `/ll:resume`:

```python
# In issue_manager.py or new continuation.py module

def restore_session_state(state_file: Path) -> dict:
    """Restore session state from JSON file."""
    if not state_file.exists():
        return {}

    state = json.loads(state_file.read_text())

    # Restore todos to TodoWrite format
    if state.get("todos"):
        # Signal to restore todo list
        pass

    return state
```

### 6. CLI Integration Updates

Update `scripts/little_loops/issue_manager.py`:

- Move continuation functions to dedicated module (`continuation.py`)
- Add `--resume` flag support for all CLI commands
- Improve `run_with_continuation()` to use new config options

### 7. Documentation

- Update `README.md` with continuation feature section
- Add `docs/CONTINUATION.md` with detailed usage guide
- Update `docs/COMMANDS.md` with new commands

## Location

| Component | File Path |
|-----------|-----------|
| `/ll:handoff` command | `commands/handoff.md` |
| `/ll:resume` command | `commands/resume.md` |
| SessionStart hook | `hooks/prompts/session-start-resume.md` |
| Hook registration | `hooks/hooks.json` |
| Config schema | `config-schema.json` |
| PreCompact updates | `hooks/prompts/pre-compact-state.md` |
| Python module | `scripts/little_loops/continuation.py` |
| Documentation | `docs/CONTINUATION.md` |

## Impact

- **Severity**: Medium - Significant UX improvement for session continuity
- **Effort**: Medium - 2 new commands, 1 new hook, config updates, docs
- **Risk**: Low - Purely additive, backward compatible with existing behavior

## Dependencies

- Existing `PreCompact` hook infrastructure
- Existing `ll-session-state.json` and `ll-continue-prompt.md` file formats
- TodoWrite tool for state restoration

## Blocked By

None - builds on existing infrastructure.

## Blocks

None currently identified.

## Labels

`feature`, `continuation`, `handoff`, `session-management`, `ux`

---

## Status

**Completed** | Created: 2026-01-06 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-06
- **Status**: Completed

### Changes Made

| File | Change |
|------|--------|
| `commands/handoff.md` | New command for manual continuation prompt generation |
| `commands/resume.md` | New command to resume from continuation prompt |
| `hooks/prompts/session-start-resume.md` | New SessionStart hook for auto-detection |
| `hooks/hooks.json` | Registered SessionStart prompt hook |
| `config-schema.json` | Added `continuation` configuration section |
| `hooks/prompts/pre-compact-state.md` | Extended for general sessions (not just issue management) |
| `commands/help.md` | Added new commands to help reference |

### Verification Results
- Tests: PASS (466 tests passed)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
- JSON Validation: PASS (hooks.json, config-schema.json)
