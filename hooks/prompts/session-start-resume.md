---
event: SessionStart
---

# Session Start Resume Detection

Check for continuation prompt on session start and notify user if found.

## Configuration

Read settings from `.claude/ll-config.json` under `continuation`:
- `auto_detect_on_session_start`: Enable detection (default: true)
- `prompt_expiry_hours`: Hours before prompt is stale (default: 24)

## Actions

### 1. Check Configuration

First, check if auto-detection is enabled:
- Read `.claude/ll-config.json`
- Check `continuation.auto_detect_on_session_start`
- If `false`, skip detection entirely (no output)
- If `true` or not set, proceed with detection

### 2. Check for Continuation Prompt

Look for `.claude/ll-continue-prompt.md`:
- Check if file exists
- If exists, get file modification time

### 3. Evaluate Freshness

Compare file modification time to current time:
- Get `prompt_expiry_hours` from config (default: 24)
- Calculate hours since last modification
- Mark as "fresh" if within expiry window, "stale" otherwise

### 4. Notify If Found

#### If Fresh Continuation Prompt Exists

Output a brief notification:

```
[ll] Previous session state detected (<relative time ago>)
     Run /ll:resume to continue where you left off
```

Examples of relative time:
- "2 minutes ago"
- "1 hour ago"
- "3 hours ago"

#### If Stale Continuation Prompt Exists

Output with staleness note:

```
[ll] Stale session state found (<N> hours old)
     Run /ll:resume to view, or /ll:handoff to create fresh
```

### 5. Silent If Not Found

If no continuation prompt exists:
- Output nothing
- Let session start normally

### 6. Reset Context Monitor State

If `context_monitor.enabled` is `true` in config:
- Delete `.claude/ll-context-state.json` if it exists
- This resets context tracking for the fresh session
- Silent operation (no output needed)

## Performance

- This hook must complete quickly (< 2 seconds)
- Only file existence and mtime checks - no heavy processing
- Silent failure if any errors occur (don't block session start)

## Notes

- Does NOT auto-resume - user must explicitly run `/ll:resume`
- Only outputs 1-2 lines to avoid cluttering session start
- Respects `enabled` and `auto_detect_on_session_start` config settings
- Works with prompts from `/ll:handoff` or PreCompact hook
- Context monitor state is reset on every session start (fresh context = fresh tracking)
