---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-329: Context Monitor Token Estimate Never Decreases After Compaction

## Summary

The context monitor (`hooks/scripts/context-monitor.sh`) tracks estimated token usage with a monotonically increasing counter. When Claude Code compacts the conversation context, actual token usage drops significantly, but the estimate keeps growing. This causes premature handoff warnings well before the real context limit is reached.

## Current Behavior

`estimated_tokens` in `.claude/ll-context-state.json` only ever increases. Each tool call adds to the running total. After context compaction frees substantial space, the estimate remains inflated and eventually crosses the 80% threshold too early.

## Expected Behavior

The token estimate should account for context compaction events. After compaction, the estimate should be reduced (or reset with a safety margin) to reflect the actual reduced context usage, allowing sessions to continue productively.

## Steps to Reproduce

1. Start a long session with many tool calls
2. Let Claude Code compact the conversation (automatic at ~180K tokens)
3. Observe that `.claude/ll-context-state.json` `estimated_tokens` continues from pre-compaction value
4. Receive premature handoff warning despite significant context headroom

## Actual Behavior

Handoff warning triggers based on stale pre-compaction estimate, cutting sessions short unnecessarily.

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: Token accumulation logic (around line 163-177)
- **Cause**: The script only adds tokens, never subtracts. There is no mechanism to detect or respond to context compaction events.

## Proposed Solution

TBD - requires investigation. Possible approaches:
1. Detect compaction by monitoring conversation state changes and reset estimate with safety margin
2. Use a decay/sliding-window approach instead of pure accumulation
3. Hook into a compaction event if Claude Code exposes one

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` - main fix location

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` - hook registration (no changes needed)
- `commands/handoff.md` - consumes handoff warnings (no changes needed)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/` - may need new test for compaction-aware behavior

### Documentation
- N/A

### Configuration
- `.claude/ll-config.json` `context_monitor` section

## Implementation Steps

1. Research whether Claude Code provides any signal for context compaction
2. Implement compaction detection (e.g., check for state file age vs conversation freshness)
3. Add estimate reduction logic when compaction is detected
4. Test with long sessions that trigger compaction

## Impact

- **Priority**: P2 - Causes premature session termination in long sessions
- **Effort**: Medium - Requires research into compaction detection
- **Risk**: Medium - Wrong reset values could cause missed handoffs
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle documentation |

## Labels

`bug`, `context-monitor`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P2
