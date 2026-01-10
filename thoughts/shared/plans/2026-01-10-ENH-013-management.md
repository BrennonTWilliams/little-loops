# ENH-013: Persistent Handoff Reminder Until Completion - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-013-persistent-handoff-reminder.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The context-monitor hook at `hooks/scripts/context-monitor.sh` currently:

1. **Lines 116-135**: Initializes state with `handoff_triggered: false`
2. **Line 160**: Reads `HANDOFF_TRIGGERED` from state
3. **Line 183**: Checks `[ "$HANDOFF_TRIGGERED" != "true" ]`
4. **Line 185**: Sets `handoff_triggered = true` after first reminder
5. **Lines 189-196**: Outputs one-time reminder message

### Key Discoveries
- State file schema at `hooks/scripts/context-monitor.sh:123-130` uses boolean `handoff_triggered`
- No connection to `/ll:handoff` output file (`.claude/ll-continue-prompt.md`)
- Single reminder then permanent silence - Claude may ignore it
- Cross-platform date/stat commands needed (macOS vs Linux)

## Desired End State

After implementation:
1. When threshold is crossed, record `threshold_crossed_at` timestamp (not boolean)
2. On EVERY subsequent PostToolUse after threshold:
   - Check if `.claude/ll-continue-prompt.md` exists AND was modified AFTER threshold crossing
   - If NO: output reminder with current usage percentage
   - If YES: mark `handoff_complete: true`, stop reminding
3. Persistent reminders make it impossible for Claude to ignore

### How to Verify
- Enable context_monitor in config
- Trigger threshold with many tool calls
- Verify reminder appears on every tool call after threshold
- Run `/ll:handoff` command
- Verify reminders stop after handoff file is created

## What We're NOT Doing

- Not changing token estimation logic (out of scope)
- Not modifying `/ll:handoff` command itself
- Not adding new configuration options beyond existing schema
- Not changing threshold percentage or context limit defaults

## Problem Analysis

The root cause is the boolean flag design:
- `handoff_triggered: true` blocks ALL future reminders
- No feedback loop to detect if handoff was actually completed
- Claude can ignore a single message and continue until context exhaustion

## Solution Approach

Replace boolean flag with timestamp-based detection:
1. Replace `handoff_triggered: boolean` with `threshold_crossed_at: string | null`
2. Add `handoff_complete: boolean` for explicit completion tracking
3. On every PostToolUse after threshold: check if handoff file exists and was modified after threshold
4. Output reminder on every call until handoff is detected
5. Add cross-platform helper functions for file mtime and date parsing

## Implementation Phases

### Phase 1: Add Cross-Platform Helper Functions

#### Overview
Add two helper functions for cross-platform compatibility with file modification times and ISO date parsing.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Add helper functions after the estimate_tokens function (around line 114)

```bash
# Get file modification time as epoch seconds (cross-platform)
get_mtime() {
    local file="$1"
    # Try macOS syntax first
    if stat -f %m "$file" 2>/dev/null; then
        return 0
    fi
    # Fall back to Linux syntax
    stat -c %Y "$file" 2>/dev/null
}

# Parse ISO 8601 date to epoch seconds (cross-platform)
parse_iso_date() {
    local iso_date="$1"
    # Try macOS syntax first
    if date -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso_date" +%s 2>/dev/null; then
        return 0
    fi
    # Fall back to Linux syntax
    date -d "$iso_date" +%s 2>/dev/null
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Script syntax is valid: `bash -n hooks/scripts/context-monitor.sh`
- [ ] Lint passes: `shellcheck hooks/scripts/context-monitor.sh || true` (may have warnings)

---

### Phase 2: Update State Schema

#### Overview
Modify the initial state schema to use `threshold_crossed_at` timestamp instead of `handoff_triggered` boolean.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Update the initial state in read_state function (lines 123-130)

Replace:
```bash
{
    "session_start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "estimated_tokens": 0,
    "tool_calls": 0,
    "handoff_triggered": false,
    "breakdown": {}
}
```

With:
```bash
{
    "session_start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "estimated_tokens": 0,
    "tool_calls": 0,
    "threshold_crossed_at": null,
    "handoff_complete": false,
    "breakdown": {}
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Script syntax is valid: `bash -n hooks/scripts/context-monitor.sh`

---

### Phase 3: Update State Reading Logic

#### Overview
Update the main function to read `threshold_crossed_at` instead of `handoff_triggered`.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Update line 160 to read new fields

Replace:
```bash
HANDOFF_TRIGGERED=$(echo "$STATE" | jq -r '.handoff_triggered // false')
```

With:
```bash
THRESHOLD_CROSSED_AT=$(echo "$STATE" | jq -r '.threshold_crossed_at // ""')
HANDOFF_COMPLETE=$(echo "$STATE" | jq -r '.handoff_complete // false')
```

#### Success Criteria

**Automated Verification**:
- [ ] Script syntax is valid: `bash -n hooks/scripts/context-monitor.sh`

---

### Phase 4: Implement Persistent Reminder Logic

#### Overview
Replace the one-time trigger logic with persistent reminders that detect handoff completion.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`
**Changes**: Replace lines 182-198 (threshold check block)

Replace entire block:
```bash
# Check if threshold reached and not already triggered
if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ] && [ "$HANDOFF_TRIGGERED" != "true" ]; then
    # Mark as triggered
    NEW_STATE=$(echo "$NEW_STATE" | jq '.handoff_triggered = true')
    write_state "$NEW_STATE"

    # Output handoff trigger message
    cat <<EOF
[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated) - threshold ${THRESHOLD}% reached

IMPORTANT: Context usage threshold reached. To preserve your work, please run:
  /ll:handoff

This will generate a continuation prompt for a fresh session.
EOF
    exit 0
fi
```

With:
```bash
# Check if threshold reached
if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ]; then
    # Record threshold crossing time if not already set
    if [ -z "$THRESHOLD_CROSSED_AT" ] || [ "$THRESHOLD_CROSSED_AT" = "null" ]; then
        THRESHOLD_CROSSED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$THRESHOLD_CROSSED_AT" '.threshold_crossed_at = $t')
    fi

    # Skip if handoff already complete
    if [ "$HANDOFF_COMPLETE" = "true" ]; then
        write_state "$NEW_STATE"
        exit 0
    fi

    # Check if handoff was completed (file exists and modified after threshold)
    HANDOFF_FILE=".claude/ll-continue-prompt.md"
    if [ -f "$HANDOFF_FILE" ]; then
        PROMPT_MTIME=$(get_mtime "$HANDOFF_FILE")
        THRESHOLD_EPOCH=$(parse_iso_date "$THRESHOLD_CROSSED_AT")

        if [ -n "$PROMPT_MTIME" ] && [ -n "$THRESHOLD_EPOCH" ] && \
           [ "$PROMPT_MTIME" -gt "$THRESHOLD_EPOCH" ] 2>/dev/null; then
            # Handoff complete - mark it and stop reminding
            NEW_STATE=$(echo "$NEW_STATE" | jq '.handoff_complete = true')
            write_state "$NEW_STATE"
            exit 0
        fi
    fi

    # Handoff not complete - output reminder
    write_state "$NEW_STATE"
    cat <<EOF
[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated)

Run /ll:handoff to preserve your work before context exhaustion.
EOF
    exit 0
fi
```

#### Success Criteria

**Automated Verification**:
- [ ] Script syntax is valid: `bash -n hooks/scripts/context-monitor.sh`
- [ ] Helper functions work on macOS: test with sample file

**Manual Verification**:
- [ ] Enable context_monitor in config and verify reminder appears after threshold
- [ ] Run multiple tool calls, verify reminder appears each time
- [ ] Run `/ll:handoff`, verify reminders stop

---

### Phase 5: Update Documentation

#### Overview
Update the context-monitor.md documentation to reflect new behavior.

#### Changes Required

**File**: `hooks/prompts/context-monitor.md`
**Changes**: Update state file format and behavior description

1. Update state file format section (around lines 51-58) to show new schema:
```json
{
  "session_start": "<ISO timestamp>",
  "estimated_tokens": 0,
  "tool_calls": 0,
  "threshold_crossed_at": null,
  "handoff_complete": false
}
```

2. Update "Important Notes" section (around line 105) - change:
   - "Handoff triggers **once** per session (won't spam)"

   To:
   - "Handoff reminder repeats on every tool call after threshold until `/ll:handoff` is run"

3. Update the state file example (around lines 86-98) to show new fields

#### Success Criteria

**Automated Verification**:
- [ ] Markdown is valid

---

## Testing Strategy

### Unit Tests
- Test `get_mtime` returns valid epoch on existing file
- Test `get_mtime` returns empty on non-existent file
- Test `parse_iso_date` parses valid ISO dates
- Test threshold logic triggers reminder when above threshold
- Test reminder stops when handoff file exists and is newer

### Integration Tests
1. Enable context_monitor in config
2. Simulate tool calls until threshold
3. Verify reminder appears on each subsequent call
4. Create `.claude/ll-continue-prompt.md` with current timestamp
5. Verify next tool call does NOT produce reminder

## References

- Original issue: `.issues/enhancements/P2-ENH-013-persistent-handoff-reminder.md`
- Current implementation: `hooks/scripts/context-monitor.sh:182-198`
- State file schema: `hooks/scripts/context-monitor.sh:123-130`
- Handoff command: `commands/handoff.md`
- Related feature: `.issues/completed/P2-FEAT-006-continuation-prompt-handoff-integration.md`
