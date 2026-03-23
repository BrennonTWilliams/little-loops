---
id: BUG-865
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-865: context-monitor exits 2 on every tool call after threshold (no rate-limit)

## Summary

After the 80% context threshold is crossed in `context-monitor.sh`, every subsequent tool call fires `exit 2` with a stderr message. There is no rate-limiting — each of the 10+ consecutive Read calls in a busy session each produce a "PostToolUse:Read hook error" in the UI, creating a disruptive flood of error messages.

## Current Behavior

Once `USAGE_PERCENT >= THRESHOLD`, every tool call that reaches the exit-2 path (lines 326-335 of `context-monitor.sh`) emits a reminder and exits 2. With `set -euo pipefail` and no cooldown, 10 consecutive Read operations produce 10 "hook error" entries in the Claude Code UI.

## Expected Behavior

The exit 2 reminder should fire at most once per 60 seconds. Between reminders, the hook should write state and exit 0 silently. The user sees the warning periodically rather than on every single tool call.

## Motivation

The flood of "hook error" messages is disruptive and erodes trust in the hook system. Users are more likely to disable `context_monitor` entirely than tolerate the noise, defeating the purpose of the feature. Rate-limiting the reminder gives the same signal with dramatically less friction.

## Steps to Reproduce

1. Run a session until context usage exceeds 80%
2. Make 10+ consecutive Read/tool calls without running `/ll:handoff`
3. Observe: 10 "PostToolUse:Read hook error" messages in the UI

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: `main()` → exit 2 block at lines 334-335 (after `HANDOFF_COMPLETE` check)
- **Cause**: No `last_reminder_at` tracking. Every call that passes the threshold and fails the `HANDOFF_COMPLETE` check unconditionally reaches `exit 2`. The `HANDOFF_COMPLETE = true` short-circuit (lines 302-306) only fires after `/ll:handoff` is explicitly run.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `context-monitor.sh:302-306` — `HANDOFF_COMPLETE` guard: only exits early if `handoff_complete` state field is `true` (set by the handoff file mtime check at lines 310-323)
- `context-monitor.sh:325-335` — exit 2 block; comment at 325-327 explains `exit 2` is used so stderr reaches Claude in non-interactive mode; the echo+exit path is unconditional once past line 306
- `context-monitor.sh:242-245` — state extraction block; `LAST_REMINDER_AT` extraction goes immediately after line 245, following the identical `$(echo "$STATE" | jq -r '.field // ""')` pattern
- `to_epoch` confirmed in `hooks/scripts/lib/common.sh:90-117`; returns `0` for empty input, which safely short-circuits the cooldown check when `last_reminder_at` is absent
- `last_reminder_at` field does NOT exist in the current state schema — confirmed absent from initial state literal (lines 155-163) and all `NEW_STATE` mutation sites

## Proposed Solution

Add a `last_reminder_at` field to state. Before `exit 2`, check if 60 seconds have elapsed since the last reminder. If not, write state and `exit 0` silently.

```bash
# After line 245 (HANDOFF_COMPLETE extraction), add:
LAST_REMINDER_AT=$(echo "$STATE" | jq -r '.last_reminder_at // ""')

# Before the comment at line 325, add cooldown check:
NOW_EPOCH=$(date +%s)
LAST_EPOCH=$(to_epoch "${LAST_REMINDER_AT:-}")
if [ "$LAST_EPOCH" -gt 0 ] && [ $((NOW_EPOCH - LAST_EPOCH)) -lt 60 ]; then
    write_state "$NEW_STATE"
    release_lock "$STATE_LOCK"
    exit 0
fi
# Before line 334 (the echo), update last_reminder_at:
NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reminder_at = $t')
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The `jq` amendment pattern is identical to `context-monitor.sh:298` (`threshold_crossed_at` assignment):
```bash
NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$THRESHOLD_CROSSED_AT" '.threshold_crossed_at = $t')
```
Replace `$THRESHOLD_CROSSED_AT` with `$(date -u +%Y-%m-%dT%H:%M:%SZ)` inline (same format as all existing timestamp writes at lines 157, 297).

The `write_state` + `release_lock` + `exit 0` sequence mirrors the existing early-exit pattern at lines 303-305.

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — add `last_reminder_at` tracking and cooldown check

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers context-monitor.sh as PostToolUse hook

### Similar Patterns
- `hooks/scripts/precompact-state.sh:82-84` — only other hook using `exit 2`; unconditional, no rate-limiting needed (fires once per compaction event by design)
- **Note**: `user-prompt-check.sh` does NOT use `exit 2` (only `exit 0`) — no similar treatment needed there

### Tests
- No existing shell tests for context-monitor.sh; verify manually per plan verification steps

### Documentation
- `docs/reference/hooks.md` (if exists) — may document hook behavior

### Configuration
- `ll-config.json` `context_monitor` section — no new config keys needed (hardcode 60s or make configurable)

## Implementation Steps

1. In `context-monitor.sh` after line 245, add: `LAST_REMINDER_AT=$(echo "$STATE" | jq -r '.last_reminder_at // ""')`
2. Before the comment at line 325, insert the `NOW_EPOCH`/`LAST_EPOCH` cooldown guard that calls `write_state "$NEW_STATE"` + `release_lock "$STATE_LOCK"` + `exit 0` when within 60s
3. Before line 334 (the `echo` that emits the reminder), add the `NEW_STATE` amendment: `NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reminder_at = $t')`
4. Verify: trigger 10+ Read calls above threshold, confirm only 1 "hook error" appears in a 60s window

## Impact

- **Priority**: P2 — Disruptive UX regression; erodes confidence in hook system; users likely to disable context_monitor
- **Effort**: Small — ~10 lines added to context-monitor.sh; no new dependencies
- **Risk**: Low — cooldown logic is additive; existing behavior preserved outside the rate-limit window
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `context-monitor`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-23T22:39:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/152c2182-2d1d-4797-9a20-b5baad497624.jsonl`
- `/ll:refine-issue` - 2026-03-23T22:33:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19fd35ab-9270-4420-96ba-b9bf29365721.jsonl`
- `/ll:format-issue` - 2026-03-23T22:29:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8e2d522-d473-46a2-8169-228e476ec976.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/520e79f8-0528-4c6d-92c0-e09d2d2aa372.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P2
