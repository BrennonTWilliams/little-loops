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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `context-monitor.sh:297-298`: When `THRESHOLD_CROSSED_AT` is empty (fresh state), it is set to **now** before the mtime comparison. This means `THRESHOLD_EPOCH = current time`, which is always newer than the prior-session `PROMPT_MTIME`, so the guard at line 315-316 (`PROMPT_MTIME -gt THRESHOLD_EPOCH`) always fails for pre-existing handoff files — confirming the "can never pass" claim above.
- `context-monitor.sh:178-208`: `check_compaction()` also resets `handoff_complete = false` (via jq at ~line 200) when a compaction event is detected. This is intentional and unrelated to the fix — the bug is only in the session-restart initialization path.

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
- `hooks/hooks.json` — registers context-monitor.sh (PostToolUse, lines 42-53)
- `hooks/scripts/session-start.sh` — deletes state file at line 13 (no change needed)
- `hooks/scripts/lib/common.sh` — provides `get_mtime()` (lines 134-160) and `to_epoch()` (lines 90-117) used in the mtime comparison at context-monitor.sh:310-323; read-only context

### Similar Patterns
- `hooks/scripts/precompact-state.sh` — may interact with state file; verify no interference

### Tests
- `scripts/tests/test_hooks_integration.py:15` — existing test class for context-monitor.sh; no current test covers `handoff_complete` preservation across session restart
- **New test needed**: add a test class in `test_hooks_integration.py` covering: (a) fresh state with existing `ll-continue-prompt.md` initializes `handoff_complete: true`; (b) fresh state without the file initializes `handoff_complete: false`

### Documentation
- N/A

### Configuration
- N/A — handoff file path is already hardcoded as `.claude/ll-continue-prompt.md` in the handoff skill

## Implementation Steps

1. In `read_state()` at `context-monitor.sh:161`, add handoff file existence check before emitting fresh state (see Proposed Solution for exact code)
2. Set `handoff_complete` to `"true"` if `.claude/ll-continue-prompt.md` exists
3. Add tests in `scripts/tests/test_hooks_integration.py` covering both branches (file present → `true`, file absent → `false`)
4. Verify manually: run `/ll:handoff`, start new session, confirm no hook error on first tool call
5. Verify: fresh session with no handoff file still correctly fires reminder when threshold crossed

## Impact

- **Priority**: P2 — Breaks the core promise of the handoff workflow; compounds BUG-865
- **Effort**: Small — 4-line change inside `read_state()` in context-monitor.sh
- **Risk**: Low — only affects fresh state initialization; existing sessions unaffected
- **Breaking Change**: No

## Related Key Documentation

- `docs/guides/SESSION_HANDOFF.md` — user-facing guide; documents the `handoff_complete` field, `auto_handoff_threshold` config, and the full handoff flow
- `docs/development/TROUBLESHOOTING.md` — references `ll-context-state.json` at lines 334, 348, 350, 354, 482, 734, 739, 800; includes a manual workaround for resetting `handoff_complete`

## Labels

`hooks`, `context-monitor`, `handoff`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-23T22:39:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/152c2182-2d1d-4797-9a20-b5baad497624.jsonl`
- `/ll:refine-issue` - 2026-03-23T22:35:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c9326c8-7686-429c-831f-0b844c3f85aa.jsonl`
- `/ll:format-issue` - 2026-03-23T22:29:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8e2d522-d473-46a2-8169-228e476ec976.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/520e79f8-0528-4c6d-92c0-e09d2d2aa372.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P2
