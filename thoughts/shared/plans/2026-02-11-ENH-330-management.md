# ENH-330: Context Monitor Should Track Claude Output and User Message Tokens - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-330-context-monitor-track-claude-output-and-user-message-tokens.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The context monitor (`hooks/scripts/context-monitor.sh`) only estimates tokens from tool responses via the `estimate_tokens()` function (lines 43-105). Each PostToolUse hook invocation estimates tokens for the tool response only.

### Key Discoveries
- `context-monitor.sh:43-105` — `estimate_tokens()` handles tool responses only
- `context-monitor.sh:206-207` — Token accumulation: `NEW_TOKENS = CURRENT_TOKENS + TOKENS`
- State file tracks `estimated_tokens`, `tool_calls`, and per-tool `breakdown`
- PostToolUse hook data contains `tool_name`, `tool_input`, `tool_response` — no Claude output or user message data
- `config-schema.json` defines configurable weights under `context_monitor.estimate_weights`
- `context-monitor.sh:118-126` — State initialization sets `estimated_tokens: 0` with no baseline

### What's Missing
1. **Claude output tokens** — Each tool call is preceded by Claude reasoning/output (~500-2000 tokens per turn)
2. **User message tokens** — User prompts consume context (~100-500 tokens per message)
3. **System prompt baseline** — CLAUDE.md, skill definitions, system instructions (~5000-15000 tokens, loaded once)

## Desired End State

The token estimate includes per-turn overhead for Claude output and user messages, plus a one-time system prompt baseline, making the estimate closer to actual context usage.

### How to Verify
- State file shows non-zero `estimated_tokens` even for cheap tool calls (due to per-turn overhead)
- `breakdown` includes `"claude_overhead"` and `"system_prompt"` entries
- Config schema includes new weight parameters
- Existing tests still pass

## What We're NOT Doing

- Not implementing exact tokenization (heuristics are fine per issue scope)
- Not tracking individual message-level detail
- Not changing the handoff command itself
- Not adding new hooks (using existing PostToolUse hook)

## Solution Approach

1. **Per-turn overhead**: Add a configurable `per_turn_overhead` weight (default: 800 tokens) added on every tool call to account for Claude's response + user message that preceded it. This is a simple, low-risk heuristic.
2. **System prompt baseline**: On first tool call (when `tool_calls == 0`), add a configurable `system_prompt_baseline` (default: 10000 tokens) to account for system prompt, CLAUDE.md, and skill definitions.

Both are added to `estimated_tokens` and tracked in `breakdown` for transparency.

## Implementation Phases

### Phase 1: Add Configuration Parameters

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add two new weight parameters under `context_monitor.estimate_weights`:
- `per_turn_overhead` (integer, default: 800, min: 0, max: 5000) — tokens to add per tool call for Claude output + user message
- `system_prompt_baseline` (integer, default: 10000, min: 0, max: 50000) — one-time tokens for system prompt on first call

### Phase 2: Update Context Monitor Script

#### Changes Required

**File**: `hooks/scripts/context-monitor.sh`

1. **Load new config values** (after line 33):
```bash
PER_TURN_OVERHEAD=$(ll_config_value "context_monitor.estimate_weights.per_turn_overhead" "800")
SYSTEM_PROMPT_BASELINE=$(ll_config_value "context_monitor.estimate_weights.system_prompt_baseline" "10000")
```

2. **Add system prompt baseline on first call** (after line 207, when `CURRENT_CALLS == 0`):
```bash
# Add system prompt baseline on first tool call
if [ "$CURRENT_CALLS" -eq 0 ]; then
    NEW_TOKENS=$((NEW_TOKENS + SYSTEM_PROMPT_BASELINE))
fi
```

3. **Add per-turn overhead on every call** (after tool token addition):
```bash
# Add per-turn overhead for Claude output + user message
NEW_TOKENS=$((NEW_TOKENS + PER_TURN_OVERHEAD))
```

4. **Track in breakdown** — add `claude_overhead` key accumulating per-turn + baseline tokens.

### Phase 3: Update Tests

**File**: `scripts/tests/test_hooks_integration.py`
**Changes**: Update expected token counts in existing tests to account for the new overhead. Add a test verifying system prompt baseline is only added once.

#### Success Criteria

- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Config schema is valid JSON

## Testing Strategy

### Unit Tests
- Verify first tool call includes system prompt baseline
- Verify subsequent calls include per-turn overhead but NOT baseline again
- Verify `breakdown` tracks `claude_overhead`
- Verify compaction reset clears overhead tracking properly

## References

- Original issue: `.issues/enhancements/P3-ENH-330-context-monitor-track-claude-output-and-user-message-tokens.md`
- Context monitor: `hooks/scripts/context-monitor.sh`
- Config schema: `config-schema.json`
- Tests: `scripts/tests/test_hooks_integration.py`
