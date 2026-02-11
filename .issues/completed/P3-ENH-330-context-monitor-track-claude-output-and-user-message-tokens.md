---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-330: Context Monitor Should Track Claude Output and User Message Tokens

## Summary

The context monitor only estimates tokens from tool responses. It completely ignores Claude's own output tokens, user messages, and the system prompt — all of which consume significant context window space. This makes the estimate systematically undercount actual usage (counteracting the overcount from BUG-329).

## Current Behavior

Only tool call results contribute to `estimated_tokens`. A session with verbose Claude responses and lengthy user messages will have a lower estimate than actual usage. The system prompt (CLAUDE.md, skill definitions, etc.) is also unaccounted for.

## Expected Behavior

The token estimate should approximate total context window consumption, including Claude's output, user messages, and a baseline for the system prompt.

## Motivation

Accurate context tracking is essential for reliable handoff timing. Undercounting means sessions could hit real context limits before the monitor warns, while combined with the compaction bug (BUG-329), the estimate diverges from reality in both directions depending on session characteristics.

## Scope Boundaries

- Out of scope: exact tokenization (heuristics are fine)
- Out of scope: tracking individual message-level detail
- Out of scope: changes to the handoff command itself

## Proposed Solution

TBD - requires investigation. Possible approaches:
1. Estimate Claude output tokens from PostToolUse hook metadata if available
2. Add a fixed per-turn overhead to account for Claude response + user message
3. Add a one-time system prompt baseline at session start

## Impact

- **Priority**: P3 - Improves accuracy but current heuristic is functional
- **Effort**: Small - Adding per-turn overhead is straightforward
- **Risk**: Low - Additive improvement to existing heuristic
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook lifecycle documentation |

## Labels

`enhancement`, `context-monitor`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `hooks/scripts/context-monitor.sh`: Added per-turn overhead (800 tokens default) for Claude output + user messages, and system prompt baseline (10000 tokens default) on first tool call. Tracked in `breakdown["claude_overhead"]`.
- `config-schema.json`: Added `per_turn_overhead` and `system_prompt_baseline` weight parameters under `context_monitor.estimate_weights`.

### Verification Results
- Tests: PASS (2675 passed)
- Lint: PASS
- Types: N/A (bash script)
- Integration: PASS
