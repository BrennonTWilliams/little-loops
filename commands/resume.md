---
description: Resume from a previous session's continuation prompt
arguments:
  - name: prompt_file
    description: "Path to continuation prompt file (default: .claude/ll-continue-prompt.md)"
    required: false
---

# Session Resume

Resume work from a previous session's continuation prompt.

## Configuration

Read settings from `.claude/ll-config.json` under `continuation`:
- `prompt_expiry_hours`: Hours before prompt is considered stale (default: 24)

## Process

### 1. Locate Continuation Prompt

```bash
PROMPT_FILE="${prompt_file:-.claude/ll-continue-prompt.md}"
```

Check for continuation state in order:
1. Use provided `prompt_file` if specified
2. Check `.claude/ll-continue-prompt.md` (primary location)
3. Check `.claude/ll-session-state.json` (fallback for metadata)

### 2. Validate Prompt

If continuation prompt found:

- **Check file exists**: Read the file content
- **Check freshness**: Compare file modification time to current time
  - Warn if older than `prompt_expiry_hours` (default: 24)
  - Still allow resume, but note staleness

### 3. Display Resume Context

#### If Continuation Prompt Found (Fresh)

```
Resuming from previous session
─────────────────────────────────────────────────────────────────

[Display full continuation prompt content]

─────────────────────────────────────────────────────────────────
```

**Then immediately continue with the work described in the prompt.** Do not ask what to do - execute the next steps specified in the continuation prompt.

#### If Continuation Prompt Found (Stale)

```
Resuming from previous session (stale: <N> hours old)
─────────────────────────────────────────────────────────────────

[Display full continuation prompt content]

─────────────────────────────────────────────────────────────────

Note: This continuation prompt is over <N> hours old.
      Some context may be outdated.
```

**Then immediately continue with the work described in the prompt.** Do not ask what to do - execute the next steps. If context is too stale to be actionable, state what's unclear and proceed with what can be determined.

#### If Only State File Found

```
Previous session state found
────────────────────────────
  Issue:  [active_issue or "None"]
  Phase:  [phase or "Unknown"]
  Todos:  [count] pending items
  Plan:   [plan_file or "None"]

No continuation prompt available.
Consider running /ll:handoff to create one.
```

#### If Nothing Found

```
No continuation state found.

To create a handoff point:
  /ll:handoff              Generate continuation prompt
  /ll:handoff "context"    With explicit context description

Continuation prompts are created by:
  - /ll:handoff command (manual)
  - PreCompact hook (automatic before context compaction)
```

---

## State File Format

The `.claude/ll-session-state.json` file contains:

```json
{
  "timestamp": "ISO 8601 timestamp",
  "active_issue": "ISSUE-ID or null",
  "phase": "planning|implementing|testing|committing|completing or null",
  "plan_file": "path/to/plan.md or null",
  "todos": [
    {"content": "description", "status": "pending|in_progress|completed"}
  ],
  "context": "brief description",
  "handoff_prompt": ".claude/ll-continue-prompt.md"
}
```

---

## Arguments

$ARGUMENTS

- **prompt_file** (optional, default: `.claude/ll-continue-prompt.md`): Path to continuation prompt file
  - If provided, reads from specified path
  - If omitted, checks default location then falls back to state file

---

## Examples

```bash
# Resume from default location
/ll:resume

# Resume from custom prompt file
/ll:resume thoughts/shared/plans/my-handoff.md

# Resume from a specific path
/ll:resume .claude/backup-continue-prompt.md
```

---

## Integration

- Reads prompts created by `/ll:handoff`
- Works with automation state files from `ll-auto` and `ll-parallel`
- Prompts older than `prompt_expiry_hours` are marked as stale but still usable
