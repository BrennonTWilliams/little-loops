# BUG-329: Context Monitor Token Estimate Never Decreases After Compaction - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-329-context-monitor-token-estimate-never-decreases-after-compaction.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The context monitor (`hooks/scripts/context-monitor.sh`) accumulates `estimated_tokens` monotonically at line 163:
```bash
NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
```

The PreCompact hook (`hooks/scripts/precompact-state.sh`) already captures state to `.claude/ll-precompact-state.json` with a `compacted_at` timestamp before compaction, but nothing resets the context monitor's estimate afterward.

### Key Discoveries
- `precompact-state.sh` writes `.claude/ll-precompact-state.json` with `compacted_at` timestamp (line 36-46)
- `context-monitor.sh` never checks for compaction events (lines 137-231)
- `session-start.sh:13` deletes `ll-context-state.json` on new session (but not on compaction)
- The precompact state file already captures `context_state_at_compact` (lines 49-54)

## Desired End State

After compaction, the context monitor detects that `ll-precompact-state.json` exists with a `compacted_at` timestamp newer than the last check, resets `estimated_tokens` to a post-compaction baseline, and clears the threshold/handoff flags so the session can continue productively.

### How to Verify
- Token estimate decreases after compaction (not monotonically increasing)
- Handoff warnings don't trigger prematurely after compaction
- Existing concurrent access tests still pass

## What We're NOT Doing

- Not changing the token estimation algorithm itself (separate concern, see ENH-330)
- Not adding a new hook type — using existing PreCompact + PostToolUse coordination
- Not modifying precompact-state.sh — it already provides everything needed

## Problem Analysis

**Root cause**: `context-monitor.sh` has no awareness of compaction events. The `precompact-state.sh` hook writes a marker file, but `context-monitor.sh` never reads it.

**Solution**: In `context-monitor.sh`, after reading state but before accumulating tokens, check if `.claude/ll-precompact-state.json` exists and has a `compacted_at` time newer than the last compaction we handled. If so, reset `estimated_tokens` to a configurable post-compaction estimate (default: 30% of context limit as safety margin), reset `threshold_crossed_at` and `handoff_complete`, record the compaction timestamp in state, and delete the precompact state file to avoid re-processing.

## Code Reuse & Integration

- **Reuse**: `to_epoch()` from `lib/common.sh` for timestamp comparison
- **Reuse**: `atomic_write_json()` for state file writes
- **Pattern**: Same jq-based state mutation pattern already used throughout `context-monitor.sh`

## Implementation Phases

### Phase 1: Add Compaction Detection to context-monitor.sh

#### Overview
Add a function to detect and handle compaction events before token accumulation.

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`

1. Add a configurable post-compaction estimate (after line 33):
```bash
# Post-compaction reset: percentage of context limit to use as new baseline
POST_COMPACT_PERCENT=$(ll_config_value "context_monitor.post_compaction_percent" "30")
```

2. Add compaction detection function (after `write_state()`, before `main()`):
```bash
# Check if context compaction occurred and reset estimate
check_compaction() {
    local state="$1"
    local precompact_file=".claude/ll-precompact-state.json"

    # No precompact file = no compaction happened
    [ -f "$precompact_file" ] || return 1

    # Read compaction timestamp
    local compacted_at
    compacted_at=$(jq -r '.compacted_at // ""' "$precompact_file" 2>/dev/null || echo "")
    [ -n "$compacted_at" ] && [ "$compacted_at" != "null" ] || return 1

    # Check if we already handled this compaction
    local last_compaction
    last_compaction=$(echo "$state" | jq -r '.last_compaction // ""')
    if [ "$last_compaction" = "$compacted_at" ]; then
        return 1
    fi

    # Compaction detected - reset estimate
    local reset_tokens=$((CONTEXT_LIMIT * POST_COMPACT_PERCENT / 100))

    # Build reset state
    local reset_state
    reset_state=$(echo "$state" | jq \
        --argjson tokens "$reset_tokens" \
        --arg compaction "$compacted_at" \
        '.estimated_tokens = $tokens | .threshold_crossed_at = null | .handoff_complete = false | .last_compaction = $compaction | .breakdown = {}')

    echo "$reset_state"
    return 0
}
```

3. In `main()`, add compaction check after reading state (after line 154, before line 156):
```bash
    # Check for compaction event and reset if needed
    RESET_STATE=$(check_compaction "$STATE" || true)
    if [ -n "$RESET_STATE" ]; then
        STATE="$RESET_STATE"
        # Remove precompact file to prevent re-processing
        rm -f ".claude/ll-precompact-state.json" 2>/dev/null || true
    fi
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Script has no bash syntax errors: `bash -n hooks/scripts/context-monitor.sh`

**Manual Verification**:
- [ ] In a long session, after compaction the token estimate drops to ~30% of limit
- [ ] Handoff warnings don't re-trigger immediately after compaction reset

### Phase 2: Add config schema entry

#### Overview
Add `post_compaction_percent` to config schema for discoverability.

#### Changes Required

**File**: `config-schema.json`

Add to the `context_monitor.properties` object:
```json
"post_compaction_percent": {
    "type": "integer",
    "default": 30,
    "minimum": 10,
    "maximum": 60,
    "description": "After context compaction, reset token estimate to this percentage of context_limit_estimate as a safety margin"
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Schema is valid JSON: `python -c "import json; json.load(open('config-schema.json'))"`

## Testing Strategy

### Unit Tests
- Verify bash syntax: `bash -n hooks/scripts/context-monitor.sh`
- Existing concurrent access tests should still pass

### Integration Tests
- Existing `test_hooks_integration.py::TestContextMonitor` tests verify state file integrity

## References

- Original issue: `.issues/bugs/P2-BUG-329-context-monitor-token-estimate-never-decreases-after-compaction.md`
- Context monitor: `hooks/scripts/context-monitor.sh:137-231`
- PreCompact hook: `hooks/scripts/precompact-state.sh:36-54`
- Shared utilities: `hooks/scripts/lib/common.sh`
