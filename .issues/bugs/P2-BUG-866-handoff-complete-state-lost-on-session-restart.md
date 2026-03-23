---
id: BUG-866
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-866: handoff_complete state lost on session restart

## Summary

`session-start.sh` unconditionally deletes `ll-context-state.json` on every new session. The `read_state()` function in `context-monitor.sh` always initializes `handoff_complete: false` for fresh state. When a new session starts with a transcript baseline already showing high token usage, the hook immediately re-crosses the threshold and resumes spamming `exit 2` — even if `/ll:handoff` was run in the prior session and `ll-continue-prompt.md` exists.

## Current Behavior

1. `/ll:handoff` is run; `ll-continue-prompt.md` is written; `handoff_complete: true` is stored in state.
2. User starts a new session.
3. `session-start.sh:13` deletes `ll-context-state.json`.
4. `read_state()` initializes fresh state with `handoff_complete: false` and `threshold_crossed_at: null`.
5. On the first tool call, the hook re-reads the JSONL transcript, sees high token usage, crosses threshold, finds `handoff_complete: false`, and emits `exit 2` again.

## Expected Behavior

In a new session where `ll-continue-prompt.md` already exists, `handoff_complete` should be initialized to `true`. The hook should not re-fire reminders for a handoff that was already completed in the prior session.

## Motivation

The handoff workflow's core promise is "run `/ll:handoff` once and the pressure is off." Having the reminder immediately return after a session restart breaks this promise and makes the feature feel unreliable. It also compounds BUG-865 — a user who already did the handoff still gets the flood.

## Steps to Reproduce

1. Run a session until context usage exceeds 80%
2. Run `/ll:handoff` — observe `ll-continue-prompt.md` created, reminder stops
3. Start a new Claude Code session on the same project
4. Make any tool call (e.g., Read a file)
5. Observe: "PostToolUse hook error" reappears despite handoff already completed

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: `read_state()` function
- **Cause**: When the state file doesn't exist, `read_state()` always emits `handoff_complete: false` (line 161). It never checks whether `ll-continue-prompt.md` exists. Additionally, the new state's `threshold_crossed_at: null` means the mtime comparison (`PROMPT_MTIME > THRESHOLD_EPOCH`) can never pass for a pre-existing handoff file.

- **Secondary file**: `hooks/scripts/session-start.sh`
- **Anchor**: line 13 (`rm -f .claude/ll-context-state.json`)
- **Cause**: Intentional cleanup that discards handoff completion status

## Proposed Solution

In `read_state()`, when creating fresh state (state file absent), check if `ll-continue-prompt.md` exists. If it does, initialize `handoff_complete: true`. No change needed to `session-start.sh`.

```bash
read_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
        local handoff_complete="false"
        local handoff_file=".claude/ll-continue-prompt.md"
        if [ -f "$handoff_file" ]; then
            handoff_complete="true"
        fi
        cat <<EOF
{
    "session_start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "estimated_tokens": 0,
    "tool_calls": 0,
    "threshold_crossed_at": null,
    "handoff_complete": ${handoff_complete},
    "breakdown": {}
}
EOF
    fi
}
```

This ensures a new session with an existing handoff file starts with `handoff_complete: true` and never emits the reminder — the reminder only fires on the **first genuine context overrun** in the new session.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — update `read_state()` to check for handoff file

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers context-monitor.sh
- `hooks/scripts/session-start.sh` — deletes state file (no change needed)

### Similar Patterns
- `hooks/scripts/precompact-state.sh` — may interact with state file; verify no interference

### Tests
- No existing shell tests for context-monitor.sh; verify manually per plan verification steps

### Documentation
- N/A

### Configuration
- N/A — handoff file path is already hardcoded as `.claude/ll-continue-prompt.md` in the handoff skill

## Implementation Steps

1. In `read_state()`, add handoff file existence check before emitting fresh state
2. Set `handoff_complete` to `"true"` if `.claude/ll-continue-prompt.md` exists
3. Verify: run `/ll:handoff`, start new session, confirm no hook error on first tool call
4. Verify: fresh session with no handoff file still correctly fires reminder when threshold crossed

## Impact

- **Priority**: P2 — Breaks the core promise of the handoff workflow; compounds BUG-865
- **Effort**: Small — 4-line change inside `read_state()` in context-monitor.sh
- **Risk**: Low — only affects fresh state initialization; existing sessions unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `context-monitor`, `handoff`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/520e79f8-0528-4c6d-92c0-e09d2d2aa372.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P2
